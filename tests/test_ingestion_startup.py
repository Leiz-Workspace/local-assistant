"""Verify default-off ingestion and private approved configuration before any database/vector side effect."""

import json
from types import SimpleNamespace

import pytest

from apps.api.storage import ingestion


def private_config(tmp_path):
    """Write an owner-only dummy credential file for isolated configuration validation tests."""
    path = tmp_path / "ingestion.json"
    path.write_text(
        json.dumps(
            dict(owner_id="00000000-0000-0000-0000-000000000001", api_key="k" * 40)
        )
    )
    path.chmod(0o600)
    return path


def test_private_configuration_accepts_exact_approved_model(tmp_path):
    """Verify selection hash and opaque ownership without creating a model or client."""
    selection, owner, key = ingestion.read_configuration(private_config(tmp_path))
    assert selection["candidate"]["repository"] == "Qwen/Qwen3-Embedding-0.6B"
    assert str(owner) == "00000000-0000-0000-0000-000000000001" and key == "k" * 40


@pytest.mark.parametrize(
    "case", ["permissions", "symlink", "hardlink", "oversize", "key", "owner", "extra"]
)
def test_invalid_configuration_cannot_reach_vector_startup(tmp_path, case):
    """Reject shared/symlinked/malformed credential material without accepting unrelated secret fields."""
    path = private_config(tmp_path)
    if case == "permissions":
        path.chmod(0o644)
    elif case == "symlink":
        other = tmp_path / "link.json"
        other.symlink_to(path)
        path = other
    elif case == "hardlink":
        import os

        os.link(path, tmp_path / "hardlink.json")
    elif case == "oversize":
        path.write_text("x" * 16385)
    else:
        data = json.loads(path.read_text())
        if case == "key":
            data["api_key"] = "bad\nvalue"
        elif case == "owner":
            data["owner_id"] = "foreign-owner"
        else:
            data["root_token"] = "must-not-be-accepted"
        path.write_text(json.dumps(data))
    with pytest.raises((ValueError, OSError)):
        ingestion.read_configuration(path)


def test_changed_selected_model_requires_new_approval(tmp_path, monkeypatch):
    """Refuse a modified selection even when an operator supplies valid private credentials."""
    path = private_config(tmp_path)
    root = tmp_path / "project"
    (root / "configs").mkdir(parents=True)
    original = (ingestion.ROOT / "configs/embedding-selected.json").read_text()
    (root / "configs/embedding-selected.json").write_text(original + " ")
    selected = json.loads(original)
    record = root / selected["approval_record"]
    record.parent.mkdir(parents=True)
    record.write_text((ingestion.ROOT / selected["approval_record"]).read_text())
    monkeypatch.setattr(ingestion, "ROOT", root)
    with pytest.raises(ValueError, match="approval_invalid"):
        ingestion.read_configuration(path)


@pytest.mark.asyncio
async def test_default_off_ingestion_does_not_read_credentials(monkeypatch):
    """Keep existing API startup unchanged when the feature has not been explicitly enabled."""
    monkeypatch.delenv("ASSISTANT_INGESTION_ENABLED", raising=False)
    assert await ingestion.initialize_ingestion_service(None) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["files", "closing", "path"])
async def test_enabled_ingestion_requires_existing_source_resources_and_config(
    monkeypatch, case
):
    """Refuse partial startup before constructing a vector client or background task."""
    monkeypatch.setenv("ASSISTANT_INGESTION_ENABLED", "1")
    monkeypatch.delenv("ASSISTANT_INGESTION_CONFIG_FILE", raising=False)
    files = None if case == "files" else SimpleNamespace(closing=case == "closing")
    with pytest.raises(RuntimeError):
        await ingestion.initialize_ingestion_service(files)


def test_http_feature_off_and_auth_boundaries(auth_settings, monkeypatch):
    """Reject anonymous/proxied requests and keep authenticated ingestion unavailable by default."""
    from fastapi.testclient import TestClient

    from apps.api.main import app

    monkeypatch.setenv("ASSISTANT_INGESTION_ENABLED", "0")
    monkeypatch.setenv("ASSISTANT_FILES_ENABLED", "0")
    identifier = "00000000-0000-0000-0000-000000000001"
    headers = auth_settings["headers"][0]
    with TestClient(app, client=("127.0.0.1", 43000)) as client:
        assert (
            client.post(
                f"/api/v1/files/{identifier}/index", headers=headers
            ).status_code
            == 503
        )
        assert (
            client.get(f"/api/v1/ingestion/{identifier}", headers=headers).status_code
            == 503
        )
        assert client.get(f"/api/v1/ingestion/{identifier}").status_code == 401
        assert (
            client.post(
                f"/api/v1/files/{identifier}/index",
                headers={**headers, "Origin": "http://foreign.invalid"},
            ).status_code
            == 403
        )
