"""Verify inert workflow startup, matching live authority dependencies and model-free constructor/shutdown composition."""

from types import SimpleNamespace

import pytest
from test_check_jobs import job_store as job_store
from test_check_startup import (
    test_later_startup_failure_drains_checks_before_all_authority_dependencies as run_later_startup_failure,
)
from test_coding_workflow_service import workflow_service as workflow_service

from apps.api.storage import coding_workflows as module


@pytest.mark.asyncio
async def test_disabled_workflow_does_not_inspect_dependencies_or_construct_inference(
    monkeypatch,
):
    """Keep the new default-off initializer inert without credentials, source roots or model/service construction."""
    monkeypatch.delenv("ASSISTANT_CODING_WORKFLOW_ENABLED", raising=False)

    def forbidden(*arguments, **options):
        """Fail if disabled startup constructs any model-facing workflow service."""
        pytest.fail("disabled workflow initialized")

    monkeypatch.setattr(module, "CodingWorkflowService", forbidden)
    assert (
        await module.initialize_coding_workflow_service(None, None, None, None) is None
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("missing", range(4))
async def test_enabled_workflow_requires_each_actual_authority_dependency(
    workflow_service, monkeypatch, missing
):
    """Reject every missing workspace/approval/durable-patch/check dependency before constructing the new service."""
    service = workflow_service[0]
    monkeypatch.setenv("ASSISTANT_CODING_WORKFLOW_ENABLED", "1")
    values = [service.workspace, service.approvals, service.patches, service.checks]
    values[missing] = None
    with pytest.raises(RuntimeError, match="require live durable"):
        await module.initialize_coding_workflow_service(*values)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "fault",
    [
        "workspace_closing",
        "approval_closing",
        "patch_closing",
        "checks_closing",
        "wrong_patch_workspace",
        "wrong_checks_approvals",
    ],
)
async def test_draining_or_mismatched_workflow_composition_is_rejected(
    workflow_service, monkeypatch, fault
):
    """Refuse independent or draining scopes instead of linking approvals/checks belonging to different live compositions."""
    service = workflow_service[0]
    monkeypatch.setenv("ASSISTANT_CODING_WORKFLOW_ENABLED", "1")
    if fault.endswith("closing"):
        item = {
            "workspace_closing": service.workspace,
            "approval_closing": service.approvals,
            "patch_closing": service.patches,
            "checks_closing": service.checks,
        }[fault]
        monkeypatch.setattr(item, "closing", True)
    elif fault == "wrong_patch_workspace":
        monkeypatch.setattr(
            service.patches, "workspace", SimpleNamespace(closing=False)
        )
    else:
        monkeypatch.setattr(service.checks, "approvals", SimpleNamespace(closing=False))
    with pytest.raises(RuntimeError, match="matching live"):
        await module.initialize_coding_workflow_service(
            service.workspace, service.approvals, service.patches, service.checks
        )


@pytest.mark.asyncio
async def test_explicit_live_workflow_initialization_creates_no_approval_or_model_call(
    workflow_service, monkeypatch
):
    """Bind only matching accepted services and drain the new empty controller before keeping its dependencies alive."""
    original = workflow_service[0]
    monkeypatch.setenv("ASSISTANT_CODING_WORKFLOW_ENABLED", "1")
    service = await module.initialize_coding_workflow_service(
        original.workspace, original.approvals, original.patches, original.checks
    )
    assert service is not None and not service.records and not service.operations
    assert not original.approvals._records and not original.checks.records
    await service.shutdown()
    assert (
        not original.checks.closing
        and not original.patches.closing
        and not original.approvals.closing
    )


def test_later_lifespan_failure_drains_actual_controller_before_native_authorities(
    job_store, tmp_path, monkeypatch
):
    """Exercise actual startup then fail the later engine and verify workflow→checks→checkpoint→approval→workspace drain without database access."""
    from apps.api.main import app
    from apps.api.storage import lifecycle

    monkeypatch.setenv("ASSISTANT_CODING_WORKFLOW_ENABLED", "1")
    original = lifecycle.initialize_coding_workflow_service
    completed = []

    async def initialize(*arguments):
        """Wrap only actual controller shutdown observation while preserving its real initializer and dependencies."""
        service = await original(*arguments)
        shutdown = service.shutdown

        async def draining():
            """Complete owned workflow teardown while all native/approval/source dependencies still remain alive."""
            await shutdown()
            assert (
                not service.checks.closing
                and not service.patches.closing
                and not service.approvals.closing
                and not service.workspace.closing
            )
            completed.append("workflow")

        monkeypatch.setattr(service, "shutdown", draining)
        return service

    monkeypatch.setattr(lifecycle, "initialize_coding_workflow_service", initialize)
    run_later_startup_failure(job_store, tmp_path, monkeypatch)
    assert completed == ["workflow"] and app.state.coding_workflow_service is None
