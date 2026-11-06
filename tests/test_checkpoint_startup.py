"""Verify explicit durable-checkpoint startup dependencies, private root rejection and joined cleanup after later startup failures."""

import pytest
from test_workspace_reader import source_workspace as source_workspace
from test_workspace_startup import workspace_config as workspace_config

from apps.api.services.checkpoint_patches import CheckpointPatchService
from apps.api.services.workspaces import WorkspaceService
from apps.api.storage.patches import initialize_patch_service
from src.application.services.approvals import ApprovalStore
from src.application.services.workspace_policy import WorkspaceAccessError
from src.infrastructure.checkpoints import CheckpointStore


@pytest.mark.asyncio
async def test_checkpoint_enablement_requires_patch_and_explicit_root(
    monkeypatch, source_workspace, tmp_path
):
    """Reject independent enablement/missing root and initialize only an explicit existing owned private directory."""
    monkeypatch.setenv("ASSISTANT_CHECKPOINT_ENABLED", "1")
    monkeypatch.delenv("ASSISTANT_PATCH_ENABLED", raising=False)
    with pytest.raises(RuntimeError):
        await initialize_patch_service(None, None)
    monkeypatch.setenv("ASSISTANT_PATCH_ENABLED", "1")
    monkeypatch.delenv("ASSISTANT_CHECKPOINT_ROOT", raising=False)
    workspace = WorkspaceService(source_workspace[0])
    approvals = ApprovalStore(workspace.catalog)
    with pytest.raises(RuntimeError):
        await initialize_patch_service(workspace, approvals)
    path = tmp_path / "private-checkpoints"
    path.mkdir(mode=0o700)
    monkeypatch.setenv("ASSISTANT_CHECKPOINT_ROOT", str(path))
    service = await initialize_patch_service(workspace, approvals)
    assert isinstance(service, CheckpointPatchService)
    await service.shutdown()
    assert service.checkpoint_store.storage.closing
    approvals.close()
    await workspace.shutdown()


@pytest.mark.asyncio
async def test_root_inside_workspace_is_rejected_without_backup_creation(
    monkeypatch, source_workspace
):
    """Fail enabled checkpoint startup before creating any storage lock inside the configured source root."""
    workspace = WorkspaceService(source_workspace[0])
    approvals = ApprovalStore(workspace.catalog)
    monkeypatch.setenv("ASSISTANT_PATCH_ENABLED", "1")
    monkeypatch.setenv("ASSISTANT_CHECKPOINT_ENABLED", "1")
    monkeypatch.setenv(
        "ASSISTANT_CHECKPOINT_ROOT", workspace.catalog.specifications[0].root
    )
    with pytest.raises(WorkspaceAccessError):
        await initialize_patch_service(workspace, approvals)
    approvals.close()
    await workspace.shutdown()


def test_later_engine_startup_failure_releases_private_root_lock(
    workspace_config, tmp_path, monkeypatch
):
    """Exercise real enabled startup then fail the later engine and reopen storage to prove ordered checkpoint lock cleanup."""
    from fastapi.testclient import TestClient

    from apps.api.main import app
    from apps.api.storage import lifecycle

    path = tmp_path / "private-checkpoints"
    path.mkdir(mode=0o700)
    for name in (
        "ASSISTANT_WORKSPACE_ENABLED",
        "ASSISTANT_PATCH_ENABLED",
        "ASSISTANT_APPROVAL_ENABLED",
        "ASSISTANT_CHECKPOINT_ENABLED",
    ):
        monkeypatch.setenv(name, "1")
    monkeypatch.setenv("ASSISTANT_WORKSPACE_CONFIG_FILE", str(workspace_config[0]))
    monkeypatch.setenv("ASSISTANT_CHECKPOINT_ROOT", str(path))
    monkeypatch.setenv("DATABASE_URL", "controlled-unavailable-url")
    catalogs = []

    def fail_engine():
        """Observe actual locked checkpoint initialization before a controlled later failure without credentials/database access."""
        store = app.state.patch_service.checkpoint_store
        catalogs.append(store.catalog)
        with pytest.raises(WorkspaceAccessError, match="checkpoint_store_busy"):
            CheckpointStore(path, store.catalog)
        raise RuntimeError("CONTROLLED-PRIVATE-ENGINE")

    monkeypatch.setattr(lifecycle, "create_database_engine", fail_engine)
    with pytest.raises(RuntimeError):
        with TestClient(app):
            pytest.fail("failed startup yielded")
    assert (
        app.state.patch_service is None
        and app.state.approval_store is None
        and app.state.workspace_service is None
    )
    reopened = CheckpointStore(path, catalogs[0])
    reopened.close()
