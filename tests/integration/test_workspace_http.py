"""Verify actual authenticated workspace HTTP/TCP source provenance, scope denial and pre-header delivery fences."""

import hashlib
import json
import logging
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from test_reranker_tcp_trial import localhost_server

from apps.api.main import app

logger = logging.getLogger(__name__)


@pytest.fixture
def workspace_client(auth_settings, tmp_path, monkeypatch):
    """Enable only a temporary two-owner workspace catalog without database/model credentials or real project roots."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    roots = []
    specifications = []
    for index, owner in enumerate(auth_settings["principals"]):
        root = tmp_path / str(index)
        root.mkdir()
        text = (
            '"""Synthetic source."""\nclass Cedar:\n    def greet(self):\n        return "Xin chào 𝄞"\n'
            if index == 0
            else "FOREIGN-WORKSPACE-CANARY\n"
        )
        (root / "main.py").write_text(text)
        (root / ".env").write_text("HIDDEN-WORKSPACE-CANARY")
        roots.append(root)
        specifications.append(
            dict(
                owner_id=str(owner),
                workspace_id=str(uuid4()),
                root=str(root),
                name="demo",
            )
        )
    path = tmp_path / "workspaces.json"
    path.write_text(
        json.dumps(
            dict(description="Synthetic workspace config.", workspaces=specifications)
        )
    )
    path.chmod(0o600)
    monkeypatch.setenv("ASSISTANT_WORKSPACE_ENABLED", "1")
    monkeypatch.setenv("ASSISTANT_WORKSPACE_CONFIG_FILE", str(path))
    with TestClient(app, client=("127.0.0.1", 43000)) as client:
        yield client, auth_settings, specifications, roots
    assert app.state.workspace_service is None


def test_real_http_inventory_lines_literal_search_and_hints(workspace_client, caplog):
    """Verify exact file/line/hash/Unicode-column results through actual auth/startup/routes without a model."""
    client, auth, specs, roots = workspace_client
    caplog.set_level(logging.INFO)
    headers = auth["headers"][0]
    base = "/api/v1/workspaces/" + specs[0]["workspace_id"]
    assert client.get(base, headers=headers).json()["repository_kind"] == "directory"
    for operation, body, key in [
        ("inventory", {}, "files"),
        ("read", dict(path="main.py", start_line=2, end_line=4), "lines"),
        ("search", dict(query="chào 𝄞"), "matches"),
        ("symbols", {}, "hints"),
    ]:
        response = client.post(base + "/" + operation, headers=headers, json=body)
        assert response.status_code == 200, response.text
        assert (
            response.headers["cache-control"] == "private, no-store"
            and response.headers["x-content-type-options"] == "nosniff"
        )
        data = response.json()
        assert data[key] and data["content_trust"] == "untrusted"
        if operation != "inventory":
            for row in data[key]:
                assert (
                    row["source_sha256"]
                    == hashlib.sha256((roots[0] / row["path"]).read_bytes()).hexdigest()
                )
                assert (roots[0] / row["path"]).read_text().split("\n")[
                    row["line_number"] - 1
                ] == row["line_text"]
                if operation == "search":
                    assert (
                        row["line_text"][row["column_start"] : row["column_end"]]
                        == "chào 𝄞"
                    )
        assert (
            str(roots[0]) not in response.text
            and "FOREIGN-WORKSPACE-CANARY" not in response.text
            and "HIDDEN-WORKSPACE-CANARY" not in response.text
        )
    assert "Xin chào" not in caplog.text and str(roots[0]) not in caplog.text
    assert (
        not client.app.state.workspace_service.operations
        and not client.app.state.workspace_service.admission.locked()
    )


@pytest.mark.parametrize(
    "operation,body",
    [
        ("read", dict(path="main.py")),
        ("inventory", {}),
        ("search", dict(query="CANARY")),
        ("symbols", {}),
    ],
)
def test_foreign_unknown_and_unauthenticated_scopes(workspace_client, operation, body):
    """Reject foreign and unknown workspaces identically and authenticate before read-only root access."""
    client, auth, specs, _ = workspace_client
    route = "/api/v1/workspaces/" + specs[1]["workspace_id"] + "/" + operation
    assert client.post(route, json=body).status_code == 401
    foreign = client.post(route, headers=auth["headers"][0], json=body)
    unknown = client.post(
        "/api/v1/workspaces/" + str(uuid4()) + "/" + operation,
        headers=auth["headers"][0],
        json=body,
    )
    assert (
        foreign.status_code == unknown.status_code == 404
        and foreign.json() == unknown.json()
    )
    assert "CANARY" not in foreign.text


@pytest.mark.parametrize(
    "body",
    [
        dict(path="../outside"),
        dict(path=".env"),
        dict(path="/etc/passwd"),
        dict(path="main.py", start_line=True),
        dict(path="main.py", end_line=201),
        dict(path="main.py", owner_id=str(uuid4())),
        dict(path="main.py", root="/"),
    ],
)
def test_strict_input_and_hidden_path_denial(workspace_client, body):
    """Refuse ownership/root overrides and coercible limits as well as hidden/traversal targets."""
    client, auth, specs, _ = workspace_client
    response = client.post(
        "/api/v1/workspaces/" + specs[0]["workspace_id"] + "/read",
        headers=auth["headers"][0],
        json=body,
    )
    assert response.status_code == 422
    assert not client.app.state.workspace_service.operations


def test_actual_change_at_final_header_fence_returns_no_stale_source(
    workspace_client, monkeypatch
):
    """Mutate a real source after snapshot creation and require sanitized rejection before any old lines are sent."""
    client, auth, specs, roots = workspace_client
    service = client.app.state.workspace_service
    original = service.validate

    async def changed(snapshot):
        """Change actual source bytes immediately before the real pre-header inode/hash checks."""
        (roots[0] / "main.py").write_text("SOURCE-REPLACED-CANARY\n")
        await original(snapshot)

    monkeypatch.setattr(service, "validate", changed)
    response = client.post(
        "/api/v1/workspaces/" + specs[0]["workspace_id"] + "/read",
        headers=auth["headers"][0],
        json=dict(path="main.py"),
    )
    assert (
        response.status_code == 409
        and "Xin chào" not in response.text
        and "SOURCE-REPLACED-CANARY" not in response.text
    )
    assert response.headers["cache-control"] == "private, no-store"
    assert not service.operations and not service.admission.locked()


def test_serialization_limit_releases_owned_resources(workspace_client):
    """Reject repeated long exact matches that exceed serialized response bytes without leaking the payload."""
    client, auth, specs, roots = workspace_client
    (roots[0] / "long.txt").write_text("z" * 100 + "x" * 7900 + "\n")
    response = client.post(
        "/api/v1/workspaces/" + specs[0]["workspace_id"] + "/search",
        headers=auth["headers"][0],
        json=dict(query="z"),
    )
    assert (
        response.status_code == 413
        and response.json()["detail"]["code"] == "workspace_response_limit"
    )
    service = client.app.state.workspace_service
    assert not service.operations and not service.admission.locked()


def test_actual_local_tcp_source_provenance_and_joined_delivery(workspace_client):
    """Exercise a real temporary Uvicorn socket while keeping fixture auth/root resources and final fence active."""
    client, auth, specs, roots = workspace_client
    with (
        localhost_server(client) as url,
        httpx.Client(base_url=url, trust_env=False, timeout=10) as wire,
    ):
        response = wire.post(
            "/api/v1/workspaces/" + specs[0]["workspace_id"] + "/search",
            headers=auth["headers"][0],
            json=dict(query="chào 𝄞"),
        )
        assert response.status_code == 200, response.text
        row = response.json()["matches"][0]
        assert (
            row["source_sha256"]
            == hashlib.sha256((roots[0] / "main.py").read_bytes()).hexdigest()
            and row["line_number"] == 4
        )
    assert not client.app.state.workspace_service.operations
    logger.info("workspace_actual_tcp_provenance_verified")


def test_disabled_auth_origin_and_remote_contract(auth_settings, monkeypatch):
    """Retain actual loopback/bearer/Origin policy and inert workspace startup without affecting other features."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("ASSISTANT_WORKSPACE_ENABLED", raising=False)
    route = "/api/v1/workspaces/" + str(uuid4())
    with TestClient(app, client=("127.0.0.1", 43000)) as client:
        assert client.get(route).status_code == 401
        assert client.get(route, headers=auth_settings["headers"][0]).status_code == 503
        assert (
            client.get(
                route,
                headers={
                    **auth_settings["headers"][0],
                    "Origin": "http://example.invalid",
                },
            ).status_code
            == 403
        )
    with TestClient(app, client=("203.0.113.7", 43000)) as client:
        assert client.get(route, headers=auth_settings["headers"][0]).status_code == 403


@pytest.mark.parametrize("chunked", [False, True])
def test_request_bytes_are_bounded_before_json_or_root_access(
    workspace_client, monkeypatch, chunked
):
    """Reject actual oversized fixed/chunked request streams before parsing their body or reading a configured root."""
    from src.infrastructure import readonly_workspace

    client, auth, specs, _ = workspace_client

    def forbidden_root(*arguments):
        """Prove oversized input never reaches a workspace filesystem capability."""
        pytest.fail("oversized request reached root access")

    monkeypatch.setattr(readonly_workspace, "open_root", forbidden_root)
    data = b'{"query":"' + b"x" * 17000 + b'"}'
    content = iter([data[:8192], data[8192:]]) if chunked else data
    response = client.post(
        "/api/v1/workspaces/" + specs[0]["workspace_id"] + "/search",
        headers={**auth["headers"][0], "Content-Type": "application/json"},
        content=content,
    )
    assert response.status_code == 413
    assert response.json()["detail"]["code"] == "workspace_request_limit"
    assert not client.app.state.workspace_service.operations


@pytest.mark.parametrize("failure", ["cancel", "send_error"])
def test_actual_snapshot_joins_after_response_transport_failure(
    workspace_client, failure
):
    """Close a real source/root snapshot if ASGI delivery is cancelled or its transport raises an error."""
    import asyncio

    from apps.api.routes.workspaces import WorkspaceResponse

    client, auth, specs, _ = workspace_client
    service = client.app.state.workspace_service

    async def drive():
        """Run actual source construction/final validation and inject only the final ASGI send failure."""
        from uuid import UUID

        context = service.operation(
            auth["principals"][0],
            UUID(specs[0]["workspace_id"]),
            "read",
            dict(path="main.py"),
        )
        snapshot = await context.__aenter__()
        response = WorkspaceResponse(context, service, snapshot)

        async def receive():
            """Provide an inert complete request without substituting source or authorization behavior."""
            return dict(type="http.request", body=b"", more_body=False)

        async def send(message):
            """Interrupt response delivery at its first transport event."""
            if failure == "cancel":
                raise asyncio.CancelledError()
            raise OSError("controlled transport failure")

        with pytest.raises(asyncio.CancelledError if failure == "cancel" else OSError):
            await response(dict(type="http"), receive, send)
        assert (
            snapshot.closed
            and not service.operations
            and not service.admission.locked()
        )

    client.portal.call(drive)


@pytest.mark.parametrize(
    "raw",
    [
        b'{"query":NaN}',
        b'{"query":Infinity}',
        b'{"query":1e9999}',
        b'{"query":"one","query":"two"}',
        b"[]",
        b"null",
        b"not-json",
        b'{"query":"\\ud800"}',
        json.dumps(dict(query="\ud800" * 257)).encode(),
        b'{"extra":' + b"[" * 20 + b"0" + b"]" * 20 + b"}",
        b'{"query":"\xff"}',
    ],
)
def test_malformed_json_is_safely_rejected_before_root_access(
    workspace_client, monkeypatch, raw
):
    """Reject actual nonfinite/duplicate/deep/invalid-Unicode HTTP bodies without framework serialization crashes."""
    from src.infrastructure import readonly_workspace

    client, auth, specs, _ = workspace_client

    def forbidden_root(*arguments):
        """Fail if malformed body parsing attempts any configured workspace filesystem read."""
        pytest.fail("malformed JSON reached root access")

    monkeypatch.setattr(readonly_workspace, "open_root", forbidden_root)
    response = client.post(
        "/api/v1/workspaces/" + specs[0]["workspace_id"] + "/search",
        headers={**auth["headers"][0], "Content-Type": "application/json"},
        content=raw,
    )
    assert response.status_code == 422
    assert response.json() == dict(detail=dict(code="workspace_json_invalid"))
    assert not client.app.state.workspace_service.operations
