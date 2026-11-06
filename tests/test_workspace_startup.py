"""Verify private explicit workspace configuration, inert defaults and fail-closed startup without model or database dependencies."""

import json
import os
from uuid import uuid4

import pytest

from apps.api.storage.workspaces import (
    initialize_workspace_service,
    load_workspace_catalog,
)


@pytest.fixture
def workspace_config(tmp_path):
    """Create one operator-only config and explicitly scoped disposable repository root."""
    root = tmp_path / "repo"
    root.mkdir()
    payload = dict(
        description="Synthetic workspace config.",
        workspaces=[
            dict(
                owner_id=str(uuid4()),
                workspace_id=str(uuid4()),
                root=str(root),
                name="demo",
            )
        ],
    )
    path = tmp_path / "workspaces.json"
    path.write_text(json.dumps(payload))
    path.chmod(0o600)
    return path, payload, root


@pytest.mark.asyncio
async def test_disabled_startup_never_loads_catalog(monkeypatch):
    """Keep default startup free of workspace registration, roots, model calls and credential lookup."""
    monkeypatch.delenv("ASSISTANT_WORKSPACE_ENABLED", raising=False)
    monkeypatch.setenv("ASSISTANT_WORKSPACE_CONFIG_FILE", "/does/not/exist")
    assert await initialize_workspace_service() is None


@pytest.mark.asyncio
async def test_enabled_explicit_catalog_initializes_and_drains(
    workspace_config, monkeypatch
):
    """Initialize only the configured roots independently of database/model availability and drain cleanly."""
    path, payload, _ = workspace_config
    monkeypatch.setenv("ASSISTANT_WORKSPACE_ENABLED", "1")
    monkeypatch.setenv("ASSISTANT_WORKSPACE_CONFIG_FILE", str(path))
    service = await initialize_workspace_service()
    assert len(service.catalog.specifications) == 1
    assert (
        str(service.catalog.specifications[0].workspace_id)
        == payload["workspaces"][0]["workspace_id"]
    )
    await service.shutdown()
    assert service.closing and not service.operations


@pytest.mark.parametrize(
    "fault",
    [
        "mode",
        "directory",
        "symlink",
        "ancestor_link",
        "hardlink",
        "large",
        "malformed",
        "duplicate",
        "extra",
        "owner_type",
        "workspace_id",
        "root",
        "description",
        "count",
        "missing_root",
    ],
)
def test_unsafe_or_ambiguous_operator_config_rejected(
    workspace_config, tmp_path, fault
):
    """Refuse malformed/private-control-plane violations without accepting implicit roots or duplicate identities."""
    path, payload, root = workspace_config
    if fault == "mode":
        path.chmod(0o644)
    elif fault == "directory":
        path.unlink()
        path.mkdir()
    elif fault == "symlink":
        alias = tmp_path / "alias.json"
        alias.symlink_to(path)
        path = alias
    elif fault == "ancestor_link":
        alias = tmp_path / "alias"
        alias.symlink_to(tmp_path, target_is_directory=True)
        path = alias / path.name
    elif fault == "hardlink":
        os.link(path, tmp_path / "second.json")
    elif fault == "large":
        path.write_text("x" * 32769)
    elif fault == "malformed":
        path.write_text("not json")
    elif fault == "duplicate":
        path.write_text('{"description":"a","description":"b","workspaces":[]}')
    else:
        if fault == "extra":
            payload["allow_all"] = True
        elif fault == "owner_type":
            payload["workspaces"][0]["owner_id"] = 1
        elif fault == "workspace_id":
            payload["workspaces"][0]["workspace_id"] = "bad"
        elif fault == "root":
            payload["workspaces"][0]["root"] = "~/repo"
        elif fault == "description":
            payload["description"] = ""
        elif fault == "count":
            payload["workspaces"] *= 9
        elif fault == "missing_root":
            root.rmdir()
        path.write_text(json.dumps(payload))
    with pytest.raises(Exception):
        load_workspace_catalog(str(path))


@pytest.mark.asyncio
async def test_failed_startup_error_and_logs_hide_private_values(monkeypatch, caplog):
    """Sanitize native control-plane errors rather than logging configuration paths or raw source diagnostics."""
    monkeypatch.setenv("ASSISTANT_WORKSPACE_ENABLED", "1")
    monkeypatch.setenv(
        "ASSISTANT_WORKSPACE_CONFIG_FILE", "/PRIVATE-CONFIG-CANARY/missing"
    )
    with pytest.raises(RuntimeError) as caught:
        await initialize_workspace_service()
    assert "PRIVATE-CONFIG-CANARY" not in str(caught.value) + caplog.text


def test_later_database_startup_failure_drains_workspace(workspace_config, monkeypatch):
    """Rollback the independent workspace service if an existing later app resource cannot initialize."""
    from fastapi.testclient import TestClient

    from apps.api.main import app
    from apps.api.storage import lifecycle

    path, _, _ = workspace_config
    monkeypatch.setenv("ASSISTANT_WORKSPACE_ENABLED", "1")
    monkeypatch.setenv("ASSISTANT_WORKSPACE_CONFIG_FILE", str(path))
    monkeypatch.setenv("DATABASE_URL", "controlled-unavailable-url")

    def failed_engine():
        """Inject a later resource initialization error without attempting a database or credential operation."""
        raise RuntimeError("CONTROLLED-PRIVATE-DATABASE-ERROR")

    monkeypatch.setattr(lifecycle, "create_database_engine", failed_engine)
    with pytest.raises(RuntimeError) as caught:
        with TestClient(app):
            pytest.fail("failed startup yielded an application")
    assert "CONTROLLED-PRIVATE" not in str(caught.value)
    assert app.state.workspace_service is None
