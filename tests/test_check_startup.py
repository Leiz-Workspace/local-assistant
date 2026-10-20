"""Verify disabled inert startup, explicit trust configuration, durable dependencies and actual private check-store lifecycle wiring."""

import asyncio
import json
import threading
from types import SimpleNamespace

import pytest
from test_check_jobs import job_store as job_store

from apps.api.services.checkpoint_patches import CheckpointPatchService
from apps.api.services.workspaces import WorkspaceService
from apps.api.storage import checks as module
from src.application.services.approvals import ApprovalStore
from src.application.services.workspace_policy import WorkspaceAccessError
from src.infrastructure.check_jobs import CheckJobStore
from src.infrastructure.checkpoints import CheckpointStore


@pytest.mark.asyncio
async def test_disabled_checks_are_inert_without_credentials_roots_or_dependencies(
    monkeypatch,
):
    """Do not open storage, inspect tools or require any new configuration when the separate feature flag is off."""
    monkeypatch.delenv("ASSISTANT_CHECKS_ENABLED", raising=False)

    def forbidden(*arguments, **options):
        """Fail if disabled initialization creates native storage or a runtime capability."""
        pytest.fail("disabled checks opened storage")

    monkeypatch.setattr(module, "CheckJobStore", forbidden)
    assert await module.initialize_check_service(None, None, None) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("missing", ["workspace", "approvals", "durable_patches"])
async def test_enabled_checks_require_live_durable_approval_composition(
    monkeypatch, missing
):
    """Refuse isolated execution enablement when scope, approval or checkpoint safety dependencies are absent."""
    monkeypatch.setenv("ASSISTANT_CHECKS_ENABLED", "1")
    workspace = None if missing == "workspace" else SimpleNamespace(closing=False)
    approvals = None if missing == "approvals" else SimpleNamespace(closing=False)
    with pytest.raises(RuntimeError, match="live workspace"):
        await module.initialize_check_service(workspace, approvals, None)


@pytest.mark.asyncio
async def test_actual_explicit_runtime_initialization_drains_before_dependencies(
    job_store, monkeypatch
):
    """Open only the existing disposable native roots and pinned installed runtime, then close checks before checkpoint/approval/workspace."""
    bootstrap, _, paths, spec, _ = job_store
    bootstrap.close()
    workspace = WorkspaceService(bootstrap.catalog)
    approvals = ApprovalStore(bootstrap.catalog)
    checkpoint_store = CheckpointStore(str(paths[2]), bootstrap.catalog)
    patches = CheckpointPatchService(workspace, approvals, checkpoint_store)
    monkeypatch.setenv("ASSISTANT_CHECKS_ENABLED", "1")
    values = [
        str(paths[1]),
        spec.python,
        spec.python_sha256,
        spec.stdlib,
        spec.ruff,
        spec.ruff_sha256,
    ]
    for name, value in zip(module.RUNTIME_SETTINGS, values):
        monkeypatch.setenv(name, value)
    service = await module.initialize_check_service(workspace, approvals, patches)
    try:
        assert service.workspace is workspace and service.approvals is approvals
        assert service.store.runtime.spec == spec
        assert not workspace.closing and not approvals.closing and not patches.closing
    finally:
        await service.shutdown()
        await patches.shutdown()
        approvals.close()
        await workspace.shutdown()


@pytest.mark.asyncio
@pytest.mark.parametrize("missing", module.RUNTIME_SETTINGS)
async def test_missing_explicit_runtime_setting_does_not_open_storage(
    job_store, monkeypatch, missing
):
    """Reject each absent operator setting before acquiring another private root or trusting implicit tool locations."""
    store, _, paths, spec, _ = job_store
    workspace = WorkspaceService(store.catalog)
    approvals = ApprovalStore(store.catalog)
    patches = CheckpointPatchService(
        workspace, approvals, CheckpointStore(str(paths[2]), store.catalog)
    )
    monkeypatch.setenv("ASSISTANT_CHECKS_ENABLED", "1")
    for name, value in zip(
        module.RUNTIME_SETTINGS,
        [
            str(paths[1]),
            spec.python,
            spec.python_sha256,
            spec.stdlib,
            spec.ruff,
            spec.ruff_sha256,
        ],
    ):
        monkeypatch.setenv(name, value)
    monkeypatch.delenv(missing)
    try:
        with pytest.raises(RuntimeError, match="explicit existing private root"):
            await module.initialize_check_service(workspace, approvals, patches)
        assert store.runtime.fd is not None and not workspace.closing
    finally:
        await patches.shutdown()
        approvals.close()
        await workspace.shutdown()


@pytest.mark.parametrize("location", ["workspace", "checkpoint_child"])
def test_native_private_check_root_overlap_is_rejected_before_runtime_capture(
    job_store, location
):
    """Keep runtime/snapshot storage outside both admitted source roots and private checkpoint ancestry."""
    store, _, paths, spec, checkpoint = job_store
    root = paths[0] if location == "workspace" else paths[2] / "nested-checks"
    if location != "workspace":
        root.mkdir(mode=0o700)
    with pytest.raises(WorkspaceAccessError):
        CheckJobStore(str(root), store.catalog, spec, checkpoint)
    assert not (root / "runtime").exists()


def test_later_startup_failure_drains_checks_before_all_authority_dependencies(
    job_store, tmp_path, monkeypatch
):
    """Exercise actual lifespan initialization and check→checkpoint→approval→workspace teardown after a later database constructor failure."""
    from fastapi.testclient import TestClient

    from apps.api.main import app
    from apps.api.storage import lifecycle

    store, sources, paths, spec, checkpoint = job_store
    store.close()
    config = tmp_path / "workspaces.json"
    config.write_text(
        json.dumps(
            dict(
                description="Controlled lifecycle roots.",
                workspaces=[
                    dict(
                        owner_id=str(sources.owner),
                        workspace_id=str(sources.workspace),
                        root=str(paths[0]),
                        name="fixture",
                    )
                ],
            )
        )
    )
    config.chmod(0o600)
    for name in (
        "ASSISTANT_WORKSPACE_ENABLED",
        "ASSISTANT_APPROVAL_ENABLED",
        "ASSISTANT_PATCH_ENABLED",
        "ASSISTANT_CHECKPOINT_ENABLED",
        "ASSISTANT_CHECKS_ENABLED",
    ):
        monkeypatch.setenv(name, "1")
    monkeypatch.setenv("ASSISTANT_WORKSPACE_CONFIG_FILE", str(config))
    monkeypatch.setenv("ASSISTANT_CHECKPOINT_ROOT", str(paths[2]))
    monkeypatch.setenv("DATABASE_URL", "controlled-unused-url")
    for name, value in zip(
        module.RUNTIME_SETTINGS,
        [
            str(paths[1]),
            spec.python,
            spec.python_sha256,
            spec.stdlib,
            spec.ruff,
            spec.ruff_sha256,
        ],
    ):
        monkeypatch.setenv(name, value)
    events = []

    def tracked(original, name):
        """Wrap only cleanup observation while retaining real initializers and native stores."""

        async def initialize(*arguments):
            """Return the actual dependency with a cleanup wrapper that records completion order."""
            value = await original(*arguments)
            if name == "approval":
                close = value.close

                def closing():
                    """Record actual grant invalidation after all admitted check work has joined."""
                    close()
                    events.append(name)

                monkeypatch.setattr(value, "close", closing)
            else:
                shutdown = value.shutdown

                async def draining():
                    """Record completed shutdown before dependencies lose their private capabilities."""
                    await shutdown()
                    events.append(name)

                monkeypatch.setattr(value, "shutdown", draining)
            return value

        return initialize

    for attribute, name in [
        ("initialize_check_service", "checks"),
        ("initialize_patch_service", "checkpoint"),
        ("initialize_approval_store", "approval"),
        ("initialize_workspace_service", "workspace"),
    ]:
        monkeypatch.setattr(
            lifecycle, attribute, tracked(getattr(lifecycle, attribute), name)
        )

    def failed_engine():
        """Fail only after verifying that real checks acquired the exclusive private runtime root."""
        assert app.state.check_service is not None
        with pytest.raises(WorkspaceAccessError):
            CheckJobStore(str(paths[1]), store.catalog, spec, checkpoint)
        raise RuntimeError("CONTROLLED-LATE-ENGINE")

    monkeypatch.setattr(lifecycle, "create_database_engine", failed_engine)
    with pytest.raises(
        RuntimeError, match="Conversation storage initialization failed"
    ):
        with TestClient(app):
            pytest.fail("failed startup yielded")
    assert events == ["checks", "checkpoint", "approval", "workspace"]
    assert app.state.check_service is None and app.state.workspace_service is None
    reopened = CheckJobStore(str(paths[1]), store.catalog, spec, checkpoint)
    reopened.close()


@pytest.mark.asyncio
async def test_cancelled_initializer_joins_and_closes_late_native_result(
    job_store, monkeypatch
):
    """Cancel real initialization after native acquisition and verify the returned store is closed before cancellation propagates."""
    store, _, paths, spec, checkpoint = job_store
    store.close()
    workspace = WorkspaceService(store.catalog)
    approvals = ApprovalStore(store.catalog)
    patches = CheckpointPatchService(
        workspace, approvals, CheckpointStore(str(paths[2]), store.catalog)
    )
    monkeypatch.setenv("ASSISTANT_CHECKS_ENABLED", "1")
    for name, value in zip(
        module.RUNTIME_SETTINGS,
        [
            str(paths[1]),
            spec.python,
            spec.python_sha256,
            spec.stdlib,
            spec.ruff,
            spec.ruff_sha256,
        ],
    ):
        monkeypatch.setenv(name, value)
    started, observed = threading.Event(), []

    def delayed(*arguments):
        """Return the actual acquired store only after cancellation signals the shared stop event."""
        value = CheckJobStore(*arguments)
        observed.append(value)
        started.set()
        assert arguments[-1].wait(5), "initializer did not signal cancellation"
        return value

    monkeypatch.setattr(module, "CheckJobStore", delayed)
    task = asyncio.create_task(
        module.initialize_check_service(workspace, approvals, patches)
    )
    try:
        assert await asyncio.to_thread(started.wait, 5)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert observed[0].runtime.fd is None and observed[0].storage.fd is None
        reopened = CheckJobStore(str(paths[1]), store.catalog, spec, checkpoint)
        reopened.close()
    finally:
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        await patches.shutdown()
        approvals.close()
        await workspace.shutdown()
