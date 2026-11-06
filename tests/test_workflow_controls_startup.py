"""Verify separately default-off controller selection and actual matching-dependency/lifecycle behavior without loading models or changing runtime configuration."""

import pytest
from test_check_jobs import job_store as job_store
from test_coding_workflow_service import workflow_service as workflow_service
from test_coding_workflow_startup import (
    test_later_lifespan_failure_drains_actual_controller_before_native_authorities as run_later_failure,
)

from apps.api.services.coding_workflows import CodingWorkflowService
from apps.api.services.controlled_coding_workflows import (
    ControlledCodingWorkflowService,
)
from apps.api.storage import coding_workflows as module


@pytest.mark.asyncio
@pytest.mark.parametrize("controls", [None, "0", "true", "1"])
async def test_controls_require_exact_explicit_flag_with_existing_live_workflow(
    workflow_service, monkeypatch, controls
):
    """Select the subclass only for exact explicit enablement and preserve the accepted base service for every other flag value."""
    original = workflow_service[0]
    monkeypatch.setenv("ASSISTANT_CODING_WORKFLOW_ENABLED", "1")
    if controls is None:
        monkeypatch.delenv("ASSISTANT_CODING_WORKFLOW_CONTROLS_ENABLED", raising=False)
    else:
        monkeypatch.setenv("ASSISTANT_CODING_WORKFLOW_CONTROLS_ENABLED", controls)
    service = await module.initialize_coding_workflow_service(
        original.workspace, original.approvals, original.patches, original.checks
    )
    assert type(service) is (
        ControlledCodingWorkflowService if controls == "1" else CodingWorkflowService
    )
    assert not service.records and not original.approvals._records
    await service.shutdown()
    assert not original.workspace.closing and not original.checks.closing


@pytest.mark.asyncio
async def test_control_flag_alone_does_not_inspect_or_construct_authorities(
    monkeypatch,
):
    """Keep the controller flag inert when its parent workflow feature is not enabled."""
    monkeypatch.setenv("ASSISTANT_CODING_WORKFLOW_CONTROLS_ENABLED", "1")
    monkeypatch.delenv("ASSISTANT_CODING_WORKFLOW_ENABLED", raising=False)

    def forbidden(*arguments, **options):
        """Reject unexpected construction without the required parent opt-in."""
        pytest.fail("controller constructed without workflow enablement")

    monkeypatch.setattr(module, "ControlledCodingWorkflowService", forbidden)
    assert (
        await module.initialize_coding_workflow_service(None, None, None, None) is None
    )


@pytest.mark.asyncio
async def test_enabled_controller_cannot_accept_draining_dependencies(
    workflow_service, monkeypatch
):
    """Retain the existing live-composition fence before selecting or constructing any controller."""
    service = workflow_service[0]
    monkeypatch.setenv("ASSISTANT_CODING_WORKFLOW_ENABLED", "1")
    monkeypatch.setenv("ASSISTANT_CODING_WORKFLOW_CONTROLS_ENABLED", "1")
    monkeypatch.setattr(service.checks, "closing", True)
    with pytest.raises(RuntimeError, match="matching live"):
        await module.initialize_coding_workflow_service(
            service.workspace, service.approvals, service.patches, service.checks
        )


def test_actual_later_startup_failure_drains_controlled_service_before_native_dependencies(
    job_store, tmp_path, monkeypatch
):
    """Exercise actual application startup with the selected subclass and preserve workflow-first teardown when a later initializer fails."""
    monkeypatch.setenv("ASSISTANT_CODING_WORKFLOW_CONTROLS_ENABLED", "1")
    run_later_failure(job_store, tmp_path, monkeypatch)
