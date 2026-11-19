"""Verify default-off ingestion and private approved configuration before any database/vector side effect."""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID

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


def startup_probe(monkeypatch, tmp_path, selection):
    """Enable ingestion with a private config and record which startup resources get constructed."""
    monkeypatch.setenv("ASSISTANT_INGESTION_ENABLED", "1")
    monkeypatch.setenv("ASSISTANT_INGESTION_CONFIG_FILE", str(private_config(tmp_path)))
    owner = UUID("00000000-0000-0000-0000-000000000001")
    monkeypatch.setattr(
        ingestion, "read_configuration", lambda path: (selection, owner, "k" * 40)
    )
    built = []

    class Vectors:
        """Record vector client construction without opening a client."""

        def __init__(self, *arguments):
            """Record that startup reached the vector boundary."""
            built.append("vectors")

    class Service:
        """Record service construction and start without a database or worker."""

        def __init__(self, files, selected, vectors):
            """Record that startup reached the service boundary."""
            built.append("service")
            self.start = AsyncMock()
            self.shutdown = AsyncMock()

    monkeypatch.setattr(ingestion, "QdrantIngestion", Vectors)
    monkeypatch.setattr(ingestion, "IngestionService", Service)
    return built


def approved_selection():
    """Load the shipped owner-approved embedding selection."""
    return json.loads((ingestion.ROOT / "configs/embedding-selected.json").read_text())


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["intra_op_threads", "batch_size", "missing"])
async def test_drifted_selection_fails_startup_closed_before_any_resource(
    monkeypatch, tmp_path, caplog, field
):
    """Refuse startup with the coded contract mismatch instead of failing every later request as 422."""
    selection = approved_selection()
    if field == "missing":
        del selection["runtime"]
    else:
        selection["runtime"][field] *= 2
    built = startup_probe(monkeypatch, tmp_path, selection)
    files = SimpleNamespace(closing=False)
    with caplog.at_level("INFO"), pytest.raises(RuntimeError):
        await ingestion.initialize_ingestion_service(files)
    assert built == []
    assert "code=ingestion_model_contract_mismatch status=503" in caplog.text
    assert "ingestion_startup_failed_safely" in caplog.text


@pytest.mark.asyncio
async def test_approved_selection_is_validated_once_before_resources(
    monkeypatch, tmp_path, caplog
):
    """Validate the shipped selection at startup, then construct vectors and the service."""
    built = startup_probe(monkeypatch, tmp_path, approved_selection())
    with caplog.at_level("INFO"):
        service = await ingestion.initialize_ingestion_service(
            SimpleNamespace(closing=False)
        )
    assert built == ["vectors", "service"]
    service.start.assert_awaited_once()
    assert caplog.text.count("ingestion_model_contract_validated") == 1


@pytest.mark.asyncio
async def test_cancelled_startup_still_propagates_cancellation(monkeypatch, tmp_path):
    """Keep cancellation during configuration reading as cancellation, not a startup failure."""
    built = startup_probe(monkeypatch, tmp_path, approved_selection())

    def cancelled(path):
        """Simulate cancellation while the configuration is being read."""
        raise asyncio.CancelledError()

    monkeypatch.setattr(ingestion, "read_configuration", cancelled)
    with pytest.raises(asyncio.CancelledError):
        await ingestion.initialize_ingestion_service(SimpleNamespace(closing=False))
    assert built == []


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
