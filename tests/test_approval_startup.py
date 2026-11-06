"""Verify approval state defaults off, needs existing scope and invalidates before workspace dependency teardown."""

import pytest
from test_workspace_reader import source_workspace as source_workspace
from test_workspace_startup import workspace_config as workspace_config

from apps.api.services.workspaces import WorkspaceService
from apps.api.storage.approvals import initialize_approval_store


@pytest.mark.asyncio
async def test_disabled_approvals_need_no_workspace(monkeypatch):
    """Keep startup inert without explicit approval enablement or credentials/database/model operations."""
    monkeypatch.delenv("ASSISTANT_APPROVAL_ENABLED", raising=False)
    assert await initialize_approval_store(None) is None


@pytest.mark.asyncio
async def test_enabled_approvals_need_live_catalog(source_workspace, monkeypatch):
    """Bind only an existing configured catalog and reject missing/draining workspace services."""
    monkeypatch.setenv("ASSISTANT_APPROVAL_ENABLED", "1")
    with pytest.raises(RuntimeError):
        await initialize_approval_store(None)
    workspace = WorkspaceService(source_workspace[0])
    store = await initialize_approval_store(workspace)
    assert store.catalog is workspace.catalog and not store._records
    store.close()
    await workspace.shutdown()
    with pytest.raises(RuntimeError):
        await initialize_approval_store(workspace)


def test_later_startup_failure_invalidates_approvals_before_dependents(
    workspace_config, monkeypatch
):
    """Exercise actual optional service startup and dependency-ordered cleanup after an existing later engine fails."""
    from fastapi.testclient import TestClient

    from apps.api.main import app
    from apps.api.storage import lifecycle

    monkeypatch.setenv("ASSISTANT_WORKSPACE_ENABLED", "1")
    monkeypatch.setenv("ASSISTANT_WORKSPACE_CONFIG_FILE", str(workspace_config[0]))
    monkeypatch.setenv("ASSISTANT_WORKSPACE_EXPLAIN_ENABLED", "1")
    monkeypatch.setenv("ASSISTANT_WORKSPACE_DIAGNOSE_ENABLED", "1")
    monkeypatch.setenv("ASSISTANT_APPROVAL_ENABLED", "1")
    monkeypatch.setenv("DATABASE_URL", "controlled-unavailable-url")
    events = []

    def tracked_initializer(original, name, synchronous):
        """Observe actual service teardown while retaining its original cleanup semantics."""

        async def initialize(*arguments):
            """Create the real service and wrap only its shutdown/close event ordering."""
            service = await original(*arguments)
            original_close = service.close if synchronous else service.shutdown
            if synchronous:

                def close():
                    """Record actual approval invalidation before dependent source teardown."""
                    events.append(name)
                    return original_close()

                monkeypatch.setattr(service, "close", close)
            else:

                async def shutdown():
                    """Record actual joined dependent service shutdown."""
                    events.append(name)
                    await original_close()

                monkeypatch.setattr(service, "shutdown", shutdown)
            return service

        return initialize

    for attribute, name in [
        ("initialize_workspace_service", "workspace"),
        ("initialize_workspace_explanations", "explanation"),
        ("initialize_workspace_diagnoses", "diagnosis"),
        ("initialize_approval_store", "approval"),
    ]:
        monkeypatch.setattr(
            lifecycle,
            attribute,
            tracked_initializer(
                getattr(lifecycle, attribute), name, name == "approval"
            ),
        )

    def fail_engine():
        """Fail only the later constructor without credential lookup or database access."""
        raise RuntimeError("CONTROLLED-PRIVATE-ENGINE-ERROR")

    monkeypatch.setattr(lifecycle, "create_database_engine", fail_engine)
    with pytest.raises(RuntimeError):
        with TestClient(app):
            pytest.fail("failed startup yielded")
    assert events == ["approval", "diagnosis", "explanation", "workspace"]
    assert app.state.approval_store is None and app.state.workspace_service is None
