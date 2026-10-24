"""Verify explicit two-proposal visible-feedback behavior with real native first failures and unchanged action/source/owner boundaries."""

import asyncio
import hashlib
import json
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from test_check_jobs import job_store as job_store
from test_check_service import approve
from test_coding_workflow_service import applied, propose
from test_coding_workflow_service import workflow_service as workflow_service

from apps.api.services.feedback_coding_workflows import FeedbackCodingWorkflowService
from src.application.services.workspace_policy import WorkspaceAccessError


@pytest_asyncio.fixture
async def feedback_workflow(workflow_service):
    """Bind the optional subclass only to owned fixture roots and the disclosed controlled inference port."""
    original, source, root, core = workflow_service
    service = FeedbackCodingWorkflowService(
        original.workspace,
        original.approvals,
        original.patches,
        original.checks,
        inference=core,
    )
    try:
        yield service, source, root, core
    finally:
        await service.shutdown()


async def failed_visible(scope):
    """Apply one known wrong complete source and separately approve actual visible checks to establish a trustworthy nonzero exit."""
    service, source, _, core = scope
    good = core.raw
    core.raw = json.dumps(
        dict(
            plan=["Retain the disclosed wrong fixture for native failure evidence."],
            replacement=core.case["target"]["source"] + "\n",
        )
    )
    value = await applied(scope)
    identifier = UUID(value["workflow_id"])
    value = await service.propose_checks(source.owner, source.workspace, identifier)
    request = UUID(value["check"]["approval_id"])
    approve(service, source.owner, request)
    value = await service.run_checks(
        source.owner, source.workspace, identifier, request
    )
    assert (
        value["state"] == "completed" and value["check"]["observation"]["exit_code"] > 0
    )
    core.raw = good
    return identifier, value


@pytest.mark.asyncio
async def test_explicit_feedback_preserves_first_and_requires_fresh_child_reviews(
    feedback_workflow,
):
    """Create one second pending proposal on exact applied bytes without running actions or changing the first observation."""
    service, source, root, core = feedback_workflow
    identifier, first = await failed_visible(feedback_workflow)
    before = (root / "sample.py").read_bytes()
    frozen = json.dumps(first, sort_keys=True)
    (root / "private_oracle.py").write_text("HIDDEN_ORACLE_NEVER_SENT_TO_CORE")
    second = await service.propose_feedback(source.owner, source.workspace, identifier)
    child = UUID(second["workflow_id"])
    assert (
        second["state"] == "awaiting_patch_review"
        and child != identifier
        and len(core.calls) == 2
    )
    assert second["patch"]["approval_id"] != first["patch"]["approval_id"]
    assert (root / "sample.py").read_bytes() == before
    assert (
        json.dumps(
            await service.read(source.owner, source.workspace, identifier),
            sort_keys=True,
        )
        == frozen
    )
    assert (
        second["selected_files"][0]["expected_sha256"]
        == hashlib.sha256(before).hexdigest()
    )
    request = core.calls[-1]["messages"]
    assert request[0] == core.calls[0]["messages"][0]
    payload = json.loads(request[1]["content"])
    assert "Observed metadata" in payload["issue"]
    assert "HIDDEN_ORACLE_NEVER_SENT_TO_CORE" not in json.dumps(request)
    assert "Traceback" not in payload["issue"] and "stderr" not in payload["issue"]
    with pytest.raises(WorkspaceAccessError):
        await service.apply(
            source.owner, source.workspace, child, UUID(second["patch"]["approval_id"])
        )
    approve(service, source.owner, UUID(second["patch"]["approval_id"]))
    await service.apply(
        source.owner, source.workspace, child, UUID(second["patch"]["approval_id"])
    )
    checked = await service.propose_checks(source.owner, source.workspace, child)
    approval = UUID(checked["check"]["approval_id"])
    approve(service, source.owner, approval)
    final = await service.run_checks(source.owner, source.workspace, child, approval)
    assert final["check"]["observation"]["exit_code"] == 0
    for target in [identifier, child]:
        with pytest.raises(WorkspaceAccessError):
            await service.propose_feedback(source.owner, source.workspace, target)
        with pytest.raises(WorkspaceAccessError):
            await service.retry_proposal(source.owner, source.workspace, target)
    assert (
        len(core.calls) == 2
        and service.feedback_status(source.owner, source.workspace, identifier)[
            "action_grants_created_by_feedback"
        ]
        == 0
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "fault",
    [
        "passed",
        "signal",
        "bool_exit",
        "timeout",
        "cleanup",
        "stdout",
        "persistence",
        "recovery",
        "cancel",
        "hook",
        "profile",
        "source",
        "job",
        "untrusted",
    ],
)
async def test_unqualified_or_uncertain_native_evidence_has_no_feedback_effect(
    feedback_workflow, fault
):
    """Refuse altered success/signal/source/uncertainty evidence before reserving a slot, starting inference or publishing a component."""
    service, source, _, core = feedback_workflow
    identifier, _ = await failed_visible(feedback_workflow)
    record = service.records[identifier]
    check = record.value["check"]
    observation = check["observation"]
    if fault == "passed":
        observation["exit_code"] = 0
    elif fault == "signal":
        observation["exit_code"] = -9
    elif fault == "bool_exit":
        observation["exit_code"] = True
    elif fault == "timeout":
        observation["outcome"] = "wall_timeout"
    elif fault == "cleanup":
        observation["cleanup_uncertain"] = True
    elif fault == "stdout":
        observation["stdout_complete"] = False
    elif fault == "persistence":
        check["terminal_persistence_uncertain"] = True
    elif fault == "recovery":
        check["recovery_warnings"] = ["unavailable"]
    elif fault == "cancel":
        service.controls[identifier].cancel_requested = True
    elif fault == "hook":
        service.controls[identifier].hook_uncertain = True
    elif fault == "profile":
        check["profile"] = "ruff"
    elif fault == "source":
        check["selected_files"][0]["sha256"] = "f" * 64
    elif fault == "job":
        observation["job_id"] = str(uuid4())
    else:
        observation["output_is_untrusted"] = False
    with pytest.raises(WorkspaceAccessError):
        await service.propose_feedback(source.owner, source.workspace, identifier)
    assert (
        len(core.calls) == 1
        and not service.feedback_pairs
        and len(service.records) == 1
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("changed", ["sample.py", "test_sample.py"])
async def test_current_native_source_drift_consumes_slot_without_second_model(
    feedback_workflow, changed
):
    """Use the original exact capture guard and retain spent feedback admission when source changes before a second proposal."""
    service, source, root, core = feedback_workflow
    identifier, _ = await failed_visible(feedback_workflow)
    name = changed if changed == "sample.py" else core.case["tests"][0]["path"]
    path = root / name
    path.write_bytes(path.read_bytes() + b"\n")
    result = await service.propose_feedback(source.owner, source.workspace, identifier)
    assert result["state"] == "proposal_failed" and len(core.calls) == 1
    with pytest.raises(WorkspaceAccessError):
        await service.propose_feedback(source.owner, source.workspace, identifier)
    with pytest.raises(WorkspaceAccessError):
        await service.retry_proposal(
            source.owner, source.workspace, UUID(result["workflow_id"])
        )


@pytest.mark.asyncio
async def test_foreign_scope_cannot_inspect_or_spend_another_owners_feedback(
    feedback_workflow,
):
    """Mask foreign roots and metadata without allocating action/model/feedback state."""
    service, source, _, core = feedback_workflow
    identifier, _ = await failed_visible(feedback_workflow)
    for owner, workspace in [(uuid4(), source.workspace), (source.owner, uuid4())]:
        with pytest.raises(WorkspaceAccessError):
            await service.propose_feedback(owner, workspace, identifier)
        with pytest.raises(WorkspaceAccessError):
            service.feedback_status(owner, workspace, identifier)
    assert len(core.calls) == 1 and not service.feedback_pairs


@pytest.mark.asyncio
async def test_parent_cancel_during_generation_retires_only_child_proposal(
    feedback_workflow,
):
    """Fence parent evidence after actual model waiting and join child capability retirement while retaining the known first edit."""
    service, source, root, core = feedback_workflow
    identifier, _ = await failed_visible(feedback_workflow)
    before = (root / "sample.py").read_bytes()
    core.entered.clear()
    core.block = True
    task = asyncio.create_task(
        service.propose_feedback(source.owner, source.workspace, identifier)
    )
    await core.entered.wait()
    await service.cancel(source.owner, source.workspace, identifier)
    core.release.set()
    with pytest.raises(WorkspaceAccessError, match="workflow_feedback_parent_changed"):
        await task
    child = service.feedback_pairs[identifier]["child"]
    assert (root / "sample.py").read_bytes() == before and child is not None
    pending = service.records[child].value["patch"]
    if pending:
        with pytest.raises(WorkspaceAccessError):
            await service.apply(
                source.owner, source.workspace, child, UUID(pending["approval_id"])
            )
    assert not service.active_tasks and not service.operations


@pytest.mark.asyncio
async def test_cancelled_second_generation_is_joined_and_slot_not_refunded(
    feedback_workflow,
):
    """Retain interruption and one consumed child reservation after model cancellation without another attempt or automatic action."""
    service, source, root, core = feedback_workflow
    identifier, _ = await failed_visible(feedback_workflow)
    before = (root / "sample.py").read_bytes()
    core.entered.clear()
    core.block = True
    task = asyncio.create_task(
        service.propose_feedback(source.owner, source.workspace, identifier)
    )
    await core.entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert (
        core.exited.is_set()
        and len(core.calls) == 2
        and (root / "sample.py").read_bytes() == before
    )
    with pytest.raises(WorkspaceAccessError):
        await service.propose_feedback(source.owner, source.workspace, identifier)
    assert not service.operations and not service.active_tasks


@pytest.mark.asyncio
async def test_legacy_component_free_retry_still_uses_original_lineage_limits(
    feedback_workflow,
):
    """Keep pre-action explicit retry unchanged and reject its second member as a feedback origin."""
    service, source, _, core = feedback_workflow
    good = core.raw
    core.raw = "invalid first proposal"
    first = await propose(feedback_workflow)
    core.raw = good
    second = await service.retry_proposal(
        source.owner, source.workspace, UUID(first["workflow_id"])
    )
    assert second["controls"]["proposals_used"] == 2 and len(core.calls) == 2
    with pytest.raises(WorkspaceAccessError):
        await service.propose_feedback(
            source.owner, source.workspace, UUID(second["workflow_id"])
        )
    assert not service.feedback_pairs


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "fault",
    [
        "forged_exit",
        "missing_live",
        "receipt_hash",
        "receipt_uncertainty",
        "patch_path",
        "row_shape",
    ],
)
async def test_native_receipt_and_exact_patch_bindings_cannot_be_forged(
    feedback_workflow, fault
):
    """Require the live owned native observation and exact known commit binding rather than a superficially plausible copied report."""
    service, source, _, core = feedback_workflow
    identifier, _ = await failed_visible(feedback_workflow)
    value = service.records[identifier].value
    if fault == "forged_exit":
        value["check"]["observation"]["exit_code"] = 17
    elif fault == "missing_live":
        service.checks.records.pop(UUID(value["check"]["job_id"]))
    elif fault == "receipt_hash":
        value["patch"]["receipt"]["new_sha256"] = "1" * 64
    elif fault == "receipt_uncertainty":
        value["patch"]["receipt"]["uncertainties"] = ["unreconciled"]
    elif fault == "patch_path":
        value["patch"]["path"] = "foreign.py"
    else:
        value["check"]["selected_files"][0] = "invalid row"
    with pytest.raises(WorkspaceAccessError):
        await service.propose_feedback(source.owner, source.workspace, identifier)
    assert len(core.calls) == 1 and not service.feedback_pairs


@pytest.mark.asyncio
async def test_failed_second_reply_keeps_first_score_and_cannot_use_old_retry(
    feedback_workflow,
):
    """Charge an invalid second completion without converting it to a patch or permitting a third model call."""
    service, source, _, core = feedback_workflow
    identifier, first = await failed_visible(feedback_workflow)
    frozen = json.dumps(first, sort_keys=True)
    core.raw = "invalid second completion"
    second = await service.propose_feedback(source.owner, source.workspace, identifier)
    child = UUID(second["workflow_id"])
    assert second["state"] == "proposal_failed" and second["patch"] is None
    assert (
        service.feedback_status(source.owner, source.workspace, identifier)["state"]
        == "proposal_failed"
    )
    assert (
        json.dumps(
            await service.read(source.owner, source.workspace, identifier),
            sort_keys=True,
        )
        == frozen
    )
    with pytest.raises(WorkspaceAccessError):
        await service.retry_proposal(source.owner, source.workspace, child)
    assert len(core.calls) == 2


@pytest.mark.asyncio
async def test_feedback_request_is_nonqueued_under_real_generation(feedback_workflow):
    """Reject a concurrent feedback request immediately without another child/model reservation."""
    service, source, _, core = feedback_workflow
    identifier, _ = await failed_visible(feedback_workflow)
    core.entered.clear()
    core.block = True
    task = asyncio.create_task(
        service.propose_feedback(source.owner, source.workspace, identifier)
    )
    await core.entered.wait()
    with pytest.raises(WorkspaceAccessError) as error:
        await service.propose_feedback(source.owner, source.workspace, identifier)
    assert error.value.status_code == 429 and len(service.feedback_pairs) == 1
    core.release.set()
    await task
    assert len(core.calls) == 2


@pytest.mark.asyncio
async def test_full_issue_budget_is_rejected_without_truncation_or_slot_charge(
    feedback_workflow,
):
    """Preserve the original bounded issue contract instead of silently removing requirements to fit feedback."""
    service, source, _, core = feedback_workflow
    core.case["issue"] = "x" * 1800
    identifier, _ = await failed_visible(feedback_workflow)
    with pytest.raises(WorkspaceAccessError):
        await service.propose_feedback(source.owner, source.workspace, identifier)
    assert len(core.calls) == 1 and not service.feedback_pairs


@pytest.mark.asyncio
async def test_unverifiable_parent_and_failed_retirement_keep_child_actions_closed(
    feedback_workflow, monkeypatch
):
    """Retain cleanup uncertainty and block child workflow actions if parent corruption and cancellation failure coincide."""
    service, source, root, core = feedback_workflow
    identifier, _ = await failed_visible(feedback_workflow)
    before = (root / "sample.py").read_bytes()
    core.entered.clear()
    core.block = True
    task = asyncio.create_task(
        service.propose_feedback(source.owner, source.workspace, identifier)
    )
    await core.entered.wait()
    service.records[identifier].value["invalid_nonfinite_metadata"] = float("nan")

    async def failed_cancel(*args):
        """Simulate unavailable retirement without touching source or generating another proposal."""
        raise RuntimeError("disclosed retirement fault")

    monkeypatch.setattr(service, "cancel", failed_cancel)
    core.release.set()
    with pytest.raises(WorkspaceAccessError):
        await task
    child = service.feedback_pairs[identifier]["child"]
    assert service.feedback_pairs[identifier]["state"] == "retirement_uncertain"
    for operation in [
        lambda: service.apply(source.owner, source.workspace, child, uuid4()),
        lambda: service.propose_checks(source.owner, source.workspace, child),
        lambda: service.run_checks(source.owner, source.workspace, child, uuid4()),
    ]:
        with pytest.raises(WorkspaceAccessError):
            await operation()
    assert (root / "sample.py").read_bytes() == before and len(core.calls) == 2
    service.records[identifier].value.pop("invalid_nonfinite_metadata")
