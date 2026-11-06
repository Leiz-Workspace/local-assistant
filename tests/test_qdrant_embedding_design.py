"""Verify Qdrant probe ownership, schema checks, scoped cleanup and shared inventory protection."""

import copy
from types import SimpleNamespace

import httpx
import pytest

from scripts import qdrant_embedding_design as module
from scripts.embedding_runtime import profiles


def client_for(mode="success"):
    """Emulate a shared collection plus a uniquely owned empty design probe."""
    state = dict(
        existing=dict(
            config=dict(params=dict(vectors=dict(size=12, distance="Cosine"))),
            points_count=7,
        )
    )
    calls = []

    def handle(request):
        """Accept only expected owned paths and never allow shared collection mutations."""
        import json

        calls.append((request.method, request.url.path))
        path = request.url.path
        if path == "/":
            return httpx.Response(200, json=dict(version="1.18.2"))
        if path == "/collections":
            return httpx.Response(
                200,
                json=dict(result=dict(collections=[dict(name=name) for name in state])),
            )
        name = path.split("/")[2]
        assert request.method == "GET" or name.startswith("la_d24_probe_")
        if request.method == "DELETE":
            state.pop(name)
            if mode == "changed_shared":
                state["existing"]["points_count"] = 8
            return httpx.Response(200, json=dict(result=True))
        if request.method == "PUT" and path.endswith("/index"):
            if mode == "index_failure":
                return httpx.Response(500, json=dict(error="private server detail"))
            data = json.loads(request.content)
            schema = data["field_schema"]
            state[name]["payload_schema"][data["field_name"]] = (
                dict(data_type=schema["type"], params=schema)
                if isinstance(schema, dict)
                else dict(data_type=schema)
            )
            return httpx.Response(200, json=dict(result=True))
        if request.method == "PUT":
            if mode == "create_failure":
                return httpx.Response(409, json=dict(error="private server detail"))
            data = json.loads(request.content)
            state[name] = dict(
                config=dict(params=data), points_count=0, payload_schema={}
            )
            return httpx.Response(200, json=dict(result=True))
        result = copy.deepcopy(state[name])
        if mode == "wrong_schema" and name != "existing":
            result["config"]["params"]["vectors"]["dense"]["size"] = 1
        return httpx.Response(200, json=dict(result=result))

    return (
        httpx.Client(
            base_url="http://127.0.0.1:6333", transport=httpx.MockTransport(handle)
        ),
        state,
        calls,
    )


def test_owned_probe_preserves_shared_data_and_validates_all_indexes():
    """Create/drop only the owned probe and retain an exact shared collection fingerprint."""
    client, state, calls = client_for()
    with client:
        result = module.probe_design("synthetic", profiles()[1], client=client)
    assert (
        result["passed"]
        and result["indexes_verified"] == 10
        and result["probe_removed"]
    )
    assert result["before_sha256"] == result["after_sha256"]
    assert list(state) == ["existing"] and state["existing"]["points_count"] == 7
    assert all(
        path != "/collections/existing" for method, path in calls if method != "GET"
    )


@pytest.mark.parametrize(
    "mode", ["index_failure", "wrong_schema", "changed_shared", "create_failure"]
)
def test_failed_probe_is_not_accepted_and_cleans_only_acknowledged_create(mode):
    """Refuse schema/server/inventory failures without exposing server bodies or deleting shared state."""
    client, state, calls = client_for(mode)
    with client, pytest.raises(ValueError) as failure:
        module.probe_design("synthetic", profiles()[1], client=client)
    assert "private server detail" not in str(failure.value)
    assert not any(name.startswith("la_d24_probe_") for name in state)
    deletes = [path for method, path in calls if method == "DELETE"]
    assert len(deletes) == (0 if mode == "create_failure" else 1)


def test_probe_collision_never_creates_or_deletes_existing_name(monkeypatch):
    """Refuse an existing target identity before any mutating request."""
    client, state, calls = client_for()
    name = "la_d24_probe_collision"
    state[name] = state.pop("existing")
    monkeypatch.setattr(module, "uuid4", lambda: SimpleNamespace(hex="collision"))
    with client, pytest.raises(ValueError, match="qdrant_probe_collision"):
        module.probe_design("synthetic", profiles()[1], client=client)
    assert all(method == "GET" for method, _ in calls)
    assert name in state
