"""Verify actual idle native patch retirement preserves source/checkpoints/approval history and never closes busy or foreign capabilities."""

import os
from uuid import UUID, uuid4

import pytest
from test_check_jobs import job_store as job_store
from test_check_service import approve
from test_coding_workflow_service import propose
from test_coding_workflow_service import workflow_service as workflow_service

from apps.api.services.workflow_cancellation import retire_pending_patch
from src.application.services.workspace_policy import WorkspaceAccessError


@pytest.mark.asyncio
@pytest.mark.parametrize("approved", [False, True])
async def test_real_pending_patch_retirement_keeps_checkpoint_ready_and_history_unchanged(
    workflow_service, approved
):
    """Close only the exact pending action while keeping original bytes, captured Git history and prior explicit approval events intact."""
    service, source, root, core = workflow_service
    value = await propose(workflow_service)
    request = UUID(value["patch"]["approval_id"])
    if approved:
        approve(service, source.owner, request)
    identifier = UUID(value["patch"]["proposal_id"])
    result, uncertain = await retire_pending_patch(
        service.patches, source.owner, source.workspace, identifier
    )
    assert (
        result["state"] == "failed"
        and result["error_code"] == "workflow_cancelled"
        and result["receipt"] is None
    )
    assert not uncertain and service.patches.records[identifier].closed
    assert service.approvals.review(source.owner, request)["state"] == (
        "approved" if approved else "pending"
    )
    assert (root / "sample.py").read_text() == core.case["target"]["source"]
    checkpoint = await service.patches.checkpoint(
        source.owner, source.workspace, UUID(result["checkpoint_id"])
    )
    assert (
        checkpoint["journal"]["state"] == "ready"
        and checkpoint["journal"]["receipt"] is None
    )
    with pytest.raises(WorkspaceAccessError):
        await service.patches.apply(source.owner, source.workspace, identifier, request)


@pytest.mark.asyncio
async def test_foreign_retirement_has_no_effect_on_a_pending_native_pin(
    workflow_service,
):
    """Authorize exact owner scope before mutating state or closing a pending root descriptor."""
    service, source, _, _ = workflow_service
    value = await propose(workflow_service)
    identifier = UUID(value["patch"]["proposal_id"])
    native = service.patches.records[identifier]
    with pytest.raises(WorkspaceAccessError) as caught:
        await retire_pending_patch(
            service.patches, uuid4(), source.workspace, identifier
        )
    assert (
        caught.value.status_code == 404
        and not native.closed
        and native.state == "proposed"
    )
    os.fstat(native.handle.fd)


@pytest.mark.asyncio
async def test_busy_patch_admission_prevents_premature_native_close(workflow_service):
    """Keep an admitted component action's pin alive rather than bypassing its serialized lifecycle during cancellation."""
    service, source, _, _ = workflow_service
    value = await propose(workflow_service)
    identifier = UUID(value["patch"]["proposal_id"])
    native = service.patches.records[identifier]
    async with service.patches.operation():
        with pytest.raises(WorkspaceAccessError) as caught:
            await retire_pending_patch(
                service.patches, source.owner, source.workspace, identifier
            )
        assert (
            caught.value.status_code == 429
            and not native.closed
            and native.state == "proposed"
        )
        os.fstat(native.handle.fd)


@pytest.mark.asyncio
async def test_closed_pin_acknowledgement_failure_keeps_retired_capability_and_uncertainty(
    workflow_service, monkeypatch
):
    """Close the actual owned pin then retain a controlled lost-close acknowledgement without restoring action authority or deleting its checkpoint."""
    service, source, root, core = workflow_service
    value = await propose(workflow_service)
    identifier = UUID(value["patch"]["proposal_id"])
    native = service.patches.records[identifier]
    close = native.close

    def uncertain_close():
        """Perform actual descriptor cleanup before injecting an acknowledgement error on the cancelled pending action."""
        close()
        raise OSError("CONTROLLED-PATCH-CANCEL-CLOSE")

    monkeypatch.setattr(native, "close", uncertain_close)
    try:
        result, uncertain = await retire_pending_patch(
            service.patches, source.owner, source.workspace, identifier
        )
        assert uncertain and result["state"] == "failed" and native.closed
        assert (root / "sample.py").read_text() == core.case["target"]["source"]
    finally:
        monkeypatch.setattr(native, "close", close)
