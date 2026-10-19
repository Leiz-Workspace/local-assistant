"""Verify inert default startup, strict grounded input and authenticated local error contracts."""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from test_grounded_answer import hits as hits
from test_grounded_service import Port, Retrieval

from apps.api.main import app
from apps.api.routes.grounded import GroundedInput
from apps.api.services.grounded import GroundedService
from apps.api.storage.grounded import initialize_grounded_service
from src.application.ports.inference import InferenceFailure


@pytest.mark.asyncio
async def test_default_off_and_enabled_dependency(monkeypatch, hits):
    """Require explicit enablement/live retrieval and leave disabled startup free of model/collection work."""
    monkeypatch.delenv("ASSISTANT_GROUNDED_ENABLED", raising=False)
    assert await initialize_grounded_service(None) is None
    monkeypatch.setenv("ASSISTANT_GROUNDED_ENABLED", "1")
    with pytest.raises(RuntimeError):
        await initialize_grounded_service(None)
    dense = Retrieval(hits)
    service = await initialize_grounded_service(dense)
    assert service.retrieval is dense
    dense.closing = True
    with pytest.raises(RuntimeError):
        await initialize_grounded_service(dense)


@pytest.mark.parametrize(
    "extra",
    [
        dict(top_k=4),
        dict(top_k=True),
        dict(top_k="2"),
        dict(model="replacement"),
        dict(owner_id=str(uuid4())),
        dict(citations=[]),
        dict(file_ids=[]),
        dict(file_ids=["not-a-uuid"]),
    ],
)
def test_grounded_strict_input(extra):
    """Reject caller model/ownership/citation injection, coercible limits and invalid narrowing."""
    with pytest.raises(ValueError):
        GroundedInput.model_validate(dict(query="query", **extra))


def test_uuid_json_shape():
    """Preserve authenticated UUID-only scope narrowing without treating source IDs as capabilities."""
    identifier = uuid4()
    body = GroundedInput.model_validate_json(
        '{"query":"q","file_ids":["' + str(identifier) + '"]}'
    )
    assert body.file_ids == [identifier] and body.top_k == 3


def test_disabled_and_local_auth_contract(auth_settings, monkeypatch):
    """Keep disabled generation unavailable and enforce real loopback/bearer/Origin guards first."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with TestClient(app, client=("127.0.0.1", 43000)) as client:
        assert (
            client.post("/api/v1/grounded/answer", json=dict(query="q")).status_code
            == 401
        )
        assert (
            client.post(
                "/api/v1/grounded/answer",
                headers=auth_settings["headers"][0],
                json=dict(query="q"),
            ).status_code
            == 503
        )
        assert (
            client.post(
                "/api/v1/grounded/answer",
                headers={
                    **auth_settings["headers"][0],
                    "Origin": "http://example.invalid",
                },
                json=dict(query="q"),
            ).status_code
            == 403
        )


@pytest.mark.parametrize(
    "error",
    [
        InferenceFailure("PRIVATE-ERROR", code="context_overflow", status_code=422),
        InferenceFailure("PRIVATE-ERROR", code="PRIVATE-CODE", status_code=502),
    ],
)
def test_model_failures_sanitized(auth_settings, monkeypatch, hits, error):
    """Return safe context/model codes without echoing untrusted upstream messages or diagnostic values."""

    class Failed:
        """Inject a bounded inference failure for the actual authenticated route contract."""

        async def complete(self, **kwargs):
            """Raise only the controlled upstream failure while leaving source tracking real to this test."""
            raise error

    monkeypatch.delenv("DATABASE_URL", raising=False)
    with TestClient(app, client=("127.0.0.1", 43000)) as client:
        dense = Retrieval(hits)
        app.state.grounded_service = GroundedService(dense, inference=Failed())
        response = client.post(
            "/api/v1/grounded/answer",
            headers=auth_settings["headers"][0],
            json=dict(query="q"),
        )
        assert response.status_code == (
            422 if error.code == "context_overflow" else 503
        )
        assert "PRIVATE" not in response.text and not dense.held
