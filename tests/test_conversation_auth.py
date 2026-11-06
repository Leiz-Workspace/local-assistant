"""Exercise fail-closed bearer authentication and safe operational error reporting."""

import json
import logging
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import TimeoutError as PoolTimeout

from apps.api.main import app

logger = logging.getLogger(__name__)


def client_for_auth(auth_settings, monkeypatch):
    """Build a loopback HTTP client while disabling real storage for authentication tests."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    return TestClient(app, client=("127.0.0.1", 42000))


@pytest.mark.parametrize(
    "authorization",
    [
        None,
        "Basic invalid",
        "Bearer short",
        "Bearer " + "x" * 48,
        "Bearer " + "x" * 513,
    ],
)
def test_invalid_authentication(auth_settings, monkeypatch, authorization, caplog):
    """Reject missing or invalid credentials before touching conversation storage."""
    with client_for_auth(auth_settings, monkeypatch) as client:
        response = client.get(
            "/api/v1/conversations",
            headers={} if authorization is None else {"Authorization": authorization},
        )
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert "x" * 48 not in caplog.text


@pytest.mark.parametrize(
    "kind", ["missing", "permissions", "symlink", "malformed", "duplicate", "identity"]
)
def test_bad_auth_file_is_unavailable(
    auth_settings, monkeypatch, kind, tmp_path, caplog
):
    """Fail closed on unreadable, unsafe or malformed principal configuration."""
    path = auth_settings["path"]
    if kind == "missing":
        monkeypatch.delenv("ASSISTANT_AUTH_FILE")
    elif kind == "permissions":
        path.chmod(0o644)
    elif kind == "symlink":
        link = tmp_path / "linked.json"
        link.symlink_to(path)
        monkeypatch.setenv("ASSISTANT_AUTH_FILE", str(link))
    elif kind == "malformed":
        path.write_text("{private invalid json")
    else:
        payload = json.loads(path.read_text())
        if kind == "duplicate":
            payload["principals"].append(payload["principals"][0])
        else:
            payload["principals"][0]["id"] = {"invalid": "identity"}
        path.write_text(json.dumps(payload))
    with client_for_auth(auth_settings, monkeypatch) as client:
        response = client.get(
            "/api/v1/conversations", headers=auth_settings["headers"][0]
        )
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "auth_unavailable"
    assert auth_settings["tokens"][0] not in response.text + caplog.text


def test_tokens_are_reloaded_and_owner_is_bound(auth_settings, monkeypatch, caplog):
    """Bind only the authenticated identity and honor revocation without process restart."""
    service = Mock()
    service.list = AsyncMock(return_value=[])
    service.for_owner.return_value = service
    with client_for_auth(auth_settings, monkeypatch) as client:
        app.state.conversation_service = service
        with caplog.at_level(logging.INFO):
            assert (
                client.get(
                    "/api/v1/conversations", headers=auth_settings["headers"][0]
                ).status_code
                == 200
            )
        service.for_owner.assert_called_once_with(auth_settings["principals"][0])
        payload = json.loads(auth_settings["path"].read_text())
        payload["principals"] = payload["principals"][1:]
        auth_settings["path"].write_text(json.dumps(payload))
        assert (
            client.get(
                "/api/v1/conversations", headers=auth_settings["headers"][0]
            ).status_code
            == 401
        )
        assert (
            client.get(
                "/api/v1/conversations", headers=auth_settings["headers"][1]
            ).status_code
            == 200
        )
    assert all(token not in caplog.text for token in auth_settings["tokens"])


def test_pool_timeout_maps_to_safe_503(auth_settings, monkeypatch, caplog):
    """Export a pool timeout counter while withholding driver and credential details."""
    service = Mock()
    service.for_owner.return_value = service
    service.list = AsyncMock(side_effect=PoolTimeout("private SQL details"))
    observer = Mock()
    with client_for_auth(auth_settings, monkeypatch) as client:
        app.state.conversation_service = service
        app.state.pool_telemetry = observer
        response = client.get(
            "/api/v1/conversations", headers=auth_settings["headers"][0]
        )
        observer.note_timeout.assert_called_once()
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "pool_timeout"
    assert "private SQL" not in response.text + caplog.text


def test_duplicate_authorization_is_rejected(auth_settings, monkeypatch):
    """Reject ambiguous multiple bearer headers instead of picking a credential implicitly."""
    with client_for_auth(auth_settings, monkeypatch) as client:
        response = client.get(
            "/api/v1/conversations",
            headers=[
                ("Authorization", "Bearer " + token)
                for token in auth_settings["tokens"]
            ],
        )
    assert response.status_code == 401
