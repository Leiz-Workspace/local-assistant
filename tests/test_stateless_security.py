"""Verify authenticated bounded stateless inference rejects unauthorized browser/proxy access before parsing or calling the model."""

from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from apps.api.main import app
from apps.api.routes import chat
from apps.api.services.llama_gateway import GatewayError

PAYLOAD = dict(messages=[dict(role="user", content="neutral fixture")], preset="fast")


@pytest.fixture
def secured_chat(auth_settings, monkeypatch):
    """Run actual application routing with private fixture principals and a deterministic model gateway only."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    gateway = AsyncMock()
    gateway.complete.return_value = dict(
        choices=[dict(message=dict(content="fixture"))]
    )
    monkeypatch.setattr(chat, "LlamaGateway", lambda **values: gateway)
    with TestClient(app, client=("127.0.0.1", 42000)) as client:
        yield client, gateway, auth_settings


@pytest.mark.parametrize("credential", [None, "Bearer short", "Bearer " + "x" * 48])
def test_unauthenticated_stateless_call_never_reaches_gateway(secured_chat, credential):
    """Require the existing owner credential before model work or response data becomes accessible."""
    client, gateway, _ = secured_chat
    result = client.post(
        "/api/v1/chat/completions",
        json=PAYLOAD,
        headers={} if credential is None else {"Authorization": credential},
    )
    assert result.status_code == 401
    gateway.complete.assert_not_awaited()


@pytest.mark.parametrize(
    "headers",
    [
        {"Origin": "https://attacker.example"},
        {"Origin": "null"},
        {"Forwarded": "for=127.0.0.1"},
        {"X-Forwarded-For": "127.0.0.1"},
        {"X-Forwarded-Host": "localhost"},
        {"X-Real-IP": "127.0.0.1"},
    ],
)
def test_browser_or_proxy_call_denied_even_with_bearer(secured_chat, headers):
    """Reuse direct-local policy and never interpret a bearer token as permission to relax the browser-origin boundary."""
    client, gateway, auth = secured_chat
    result = client.post(
        "/api/v1/chat/completions",
        json=PAYLOAD,
        headers={**auth["headers"][0], **headers},
    )
    assert (
        result.status_code == 403
        and "access-control-allow-origin" not in result.headers
    )
    gateway.complete.assert_not_awaited()


def test_authenticated_stateless_response_contract_and_private_headers(secured_chat):
    """Preserve exact original gateway request/response with no conversation storage while preventing response caching."""
    client, gateway, auth = secured_chat
    result = client.post(
        "/api/v1/chat/completions", json=PAYLOAD, headers=auth["headers"][0]
    )
    assert result.status_code == 200 and result.json() == gateway.complete.return_value
    assert (
        result.headers["cache-control"] == "private, no-store"
        and result.headers["x-content-type-options"] == "nosniff"
    )
    gateway.complete.assert_awaited_once_with(
        messages=PAYLOAD["messages"], temperature=0.7, max_tokens=None, preset="fast"
    )


@pytest.mark.parametrize("kind", ["config", "gateway"])
def test_private_backend_error_never_enters_response_or_logs(
    secured_chat, monkeypatch, caplog, kind
):
    """Expose finite error codes while withholding raw credentials/query/backend diagnostics."""
    client, gateway, auth = secured_chat
    canary = "PRIVATE-BACKEND-CREDENTIAL-CANARY"
    if kind == "config":

        def broken(profile):
            """Raise a private diagnostic solely to verify the public route boundary."""
            raise chat.ModelConfigError(canary)

        monkeypatch.setattr(chat, "get_model_profile", broken)
    else:
        gateway.complete.side_effect = GatewayError(canary, status_code=502)
    result = client.post(
        "/api/v1/chat/completions", json=PAYLOAD, headers=auth["headers"][0]
    )
    assert result.status_code in {502, 503} and canary not in result.text + caplog.text
    assert result.json()["detail"]["code"] in {
        "model_configuration_error",
        "inference_unavailable",
    }


@pytest.mark.parametrize("kind", ["oversized", "media", "duplicate", "missing_config"])
def test_body_and_credential_ambiguity_fail_before_model(
    secured_chat, monkeypatch, kind
):
    """Bound stream bytes independently of Content-Length and reject ambiguous credentials or missing identity configuration."""
    client, gateway, auth = secured_chat
    headers = auth["headers"][0]
    if kind == "oversized":
        response = client.post(
            "/api/v1/chat/completions",
            headers={
                **headers,
                "content-type": "application/json",
                "content-length": "1",
            },
            content=b" " * 262145,
        )
        expected = 413
    elif kind == "media":
        response = client.post(
            "/api/v1/chat/completions", headers=headers, content="text"
        )
        expected = 415
    elif kind == "duplicate":
        response = client.post(
            "/api/v1/chat/completions",
            json=PAYLOAD,
            headers=[("Authorization", "Bearer " + t) for t in auth["tokens"]],
        )
        expected = 401
    else:
        monkeypatch.delenv("ASSISTANT_AUTH_FILE")
        response = client.post(
            "/api/v1/chat/completions", json=PAYLOAD, headers=headers
        )
        expected = 503
    assert response.status_code == expected
    gateway.complete.assert_not_awaited()


def test_unauthenticated_malformed_body_is_rejected_before_json_parsing(secured_chat):
    """Authenticate first so a malformed oversized request is not used as a body parser oracle."""
    client, gateway, _ = secured_chat
    result = client.post(
        "/api/v1/chat/completions",
        content=b"{",
        headers={"content-type": "application/json"},
    )
    assert result.status_code == 401
    gateway.complete.assert_not_awaited()


def test_remote_peer_cannot_use_a_valid_bearer(auth_settings, monkeypatch):
    """Deny non-loopback ASGI peers even when they hold an otherwise valid owner credential."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    gateway = AsyncMock()
    monkeypatch.setattr(chat, "LlamaGateway", lambda **values: gateway)
    with TestClient(app, client=("192.0.2.7", 42000)) as client:
        result = client.post(
            "/api/v1/chat/completions",
            json=PAYLOAD,
            headers=auth_settings["headers"][0],
        )
    assert result.status_code == 403
    gateway.complete.assert_not_awaited()
