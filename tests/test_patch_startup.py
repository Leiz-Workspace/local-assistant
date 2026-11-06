"""Verify default-off patch startup dependencies and real ordered drain after a later application startup failure."""

import pytest
from test_workspace_reader import source_workspace as source_workspace
from test_workspace_startup import workspace_config as workspace_config

from apps.api.services.workspaces import WorkspaceService
from apps.api.storage.patches import initialize_patch_service
from src.application.services.approvals import ApprovalStore


@pytest.mark.asyncio
async def test_default_off_patches_require_no_dependencies(monkeypatch):
    """Keep patch initialization inert without explicit enablement and without opening workspace/model/database resources."""
    monkeypatch.delenv("ASSISTANT_PATCH_ENABLED", raising=False)
    assert await initialize_patch_service(None, None) is None


@pytest.mark.asyncio
async def test_enabled_patches_require_live_workspace_and_approvals(
    source_workspace, monkeypatch
):
    """Require both actual accepted live dependencies and reject missing or draining services before mutation capability exists."""
    monkeypatch.setenv("ASSISTANT_PATCH_ENABLED", "1")
    workspace = WorkspaceService(source_workspace[0])
    store = ApprovalStore(workspace.catalog)
    for pair in [(None, None), (workspace, None), (None, store)]:
        with pytest.raises(RuntimeError):
            await initialize_patch_service(*pair)
    service = await initialize_patch_service(workspace, store)
    assert not service.records
    await service.shutdown()
    store.close()
    with pytest.raises(RuntimeError):
        await initialize_patch_service(workspace, store)
    await workspace.shutdown()
    with pytest.raises(RuntimeError):
        await initialize_patch_service(workspace, ApprovalStore(workspace.catalog))


def test_later_startup_failure_drains_patch_before_invalidating_approval(
    workspace_config, monkeypatch
):
    """Exercise real optional initialization and observe patch→approval→workspace teardown after controlled engine failure."""
    from fastapi.testclient import TestClient

    from apps.api.main import app
    from apps.api.storage import lifecycle

    monkeypatch.setenv("ASSISTANT_WORKSPACE_ENABLED", "1")
    monkeypatch.setenv("ASSISTANT_WORKSPACE_CONFIG_FILE", str(workspace_config[0]))
    monkeypatch.setenv("ASSISTANT_APPROVAL_ENABLED", "1")
    monkeypatch.setenv("ASSISTANT_PATCH_ENABLED", "1")
    monkeypatch.setenv("DATABASE_URL", "controlled-unavailable-url")
    events = []

    def tracked(original, name):
        """Wrap only actual dependency cleanup observation while preserving each initializer's semantics."""

        async def initialize(*arguments):
            """Create a real service and record its original close/drain ordering."""
            service = await original(*arguments)
            if name == "approval":
                close = service.close

                def closing():
                    """Record the real approval invalidation after patch drain."""
                    events.append(name)
                    return close()

                monkeypatch.setattr(service, "close", closing)
            else:
                shutdown = service.shutdown

                async def draining():
                    """Record the real joined service drain before dependent resources close."""
                    events.append(name)
                    await shutdown()

                monkeypatch.setattr(service, "shutdown", draining)
            return service

        return initialize

    for attribute, name in [
        ("initialize_workspace_service", "workspace"),
        ("initialize_approval_store", "approval"),
        ("initialize_patch_service", "patch"),
    ]:
        monkeypatch.setattr(
            lifecycle, attribute, tracked(getattr(lifecycle, attribute), name)
        )

    def fail_engine():
        """Fail only the later engine constructor without reading credentials or accessing a real database."""
        raise RuntimeError("CONTROLLED-PRIVATE-ENGINE")

    monkeypatch.setattr(lifecycle, "create_database_engine", fail_engine)
    with pytest.raises(RuntimeError):
        with TestClient(app):
            pytest.fail("failed startup yielded")
    assert events == ["patch", "approval", "workspace"]
    assert app.state.patch_service is None and app.state.approval_store is None
