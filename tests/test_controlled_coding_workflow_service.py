"""Verify finite workflow hooks, exact task cancellation, immutable explicit retry lineages and actual native component receipts using disclosed controlled inference."""

import asyncio
import hashlib
import threading
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from test_check_jobs import job_store as job_store
from test_check_service import approve
from test_coding_workflow_service import applied, propose
from test_coding_workflow_service import workflow_service as workflow_service

from apps.api.services import coding_workflows as base_module
from apps.api.services import controlled_coding_workflows as controller_module
from apps.api.services.controlled_coding_workflows import (
    ControlledCodingWorkflowService,
)
from src.application.services.workspace_policy import WorkspaceAccessError
from src.infrastructure import check_runner as runner_module


@pytest_asyncio.fixture
async def controlled_workflow(workflow_service):
    """Bind the new controller only to existing disposable native scopes/approvals and the explicitly controlled CORE port."""
    original, source, root, core = workflow_service
    service = ControlledCodingWorkflowService(
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


@pytest.mark.asyncio
async def test_real_four_stage_workflow_keeps_exact_separate_approvals_and_reserved_hooks(
    controlled_workflow,
):
    """Run actual checkpoint/edit/native checks and expose completed hook pairs without changing the accepted source/command/quality contract."""
    service, source, root, core = controlled_workflow
    value = await propose(controlled_workflow)
    identifier = UUID(value["workflow_id"])
    assert len(value["controls"]["events"]) == 2
    request = UUID(value["patch"]["approval_id"])
    with pytest.raises(WorkspaceAccessError):
        await service.apply(source.owner, source.workspace, identifier, request)
    assert (
        len(
            (await service.read(source.owner, source.workspace, identifier))[
                "controls"
            ]["events"]
        )
        == 2
    )
    approve(service, source.owner, request)
    await service.apply(source.owner, source.workspace, identifier, request)
    value = await service.propose_checks(source.owner, source.workspace, identifier)
    second = UUID(value["check"]["approval_id"])
    assert second != request
    approve(service, source.owner, second)
    result = await service.run_checks(
        source.owner, source.workspace, identifier, second
    )
    assert (
        result["summary"]["native_exit_code"] == 0
        and result["summary"]["edit_applied"] is True
    )
    assert (
        not result["summary"]["quality_evaluated"]
        and not result["summary"]["current_source_observed"]
    )
    assert (
        len(result["controls"]["events"]) == 8
        and result["controls"]["lineage_steps_used"] == 4
    )
    assert result["controls"]["proposals_used"] == 1 and not service.active_tasks
    assert (
        hashlib.sha256((root / "sample.py").read_bytes()).hexdigest()
        == core.case["expected_fixed_source_sha256"]
    )


@pytest.mark.asyncio
async def test_explicit_second_proposal_retains_first_failure_and_denies_third_or_after_action_retry(
    controlled_workflow,
):
    """Retry only a component-free failed proposal once with unchanged options and a distinct new concrete review, never replacing the original model output."""
    service, source, _, core = controlled_workflow
    successful = core.raw
    core.raw = "invalid first completion"
    first = await propose(controlled_workflow)
    root = UUID(first["workflow_id"])
    assert first["state"] == "proposal_failed" and len(core.calls) == 1
    original_sha = first["model_observation"]["raw_sha256"]
    core.raw = successful
    second = await service.retry_proposal(source.owner, source.workspace, root)
    assert (
        second["workflow_id"] != str(root)
        and second["state"] == "awaiting_patch_review"
    )
    assert (
        second["controls"]["lineage_id"] == str(root)
        and second["controls"]["proposal_ordinal"] == 2
    )
    assert second["selected_files"] == first["selected_files"] and len(core.calls) == 2
    retained = await service.read(source.owner, source.workspace, root)
    assert (
        retained["model_observation"]["raw_sha256"] == original_sha
        and retained["state"] == "proposal_failed"
    )
    for target in [root, UUID(second["workflow_id"])]:
        with pytest.raises(WorkspaceAccessError):
            await service.retry_proposal(source.owner, source.workspace, target)
    assert len(core.calls) == len(service.records) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("approved", [False, True])
async def test_owner_cancel_retires_pending_component_without_rewriting_approval_or_checkpoint(
    controlled_workflow, approved
):
    """Close only the pending native capability and preserve source/history while making repeated successful cancellation idempotent."""
    service, source, root, core = controlled_workflow
    value = await propose(controlled_workflow)
    identifier = UUID(value["workflow_id"])
    request = UUID(value["patch"]["approval_id"])
    if approved:
        approve(service, source.owner, request)
    result = await service.cancel(source.owner, source.workspace, identifier)
    assert result["state"] == "cancelled" and result["cancel_status"] == "completed"
    assert (
        result["controls"]["cancel_finished"] and len(result["controls"]["events"]) == 4
    )
    assert (
        result["patch"]["state"] == "failed"
        and result["patch"]["error_code"] == "workflow_cancelled"
    )
    assert service.approvals.review(source.owner, request)["state"] == (
        "approved" if approved else "pending"
    )
    assert (root / "sample.py").read_text() == core.case["target"]["source"]
    assert (await service.cancel(source.owner, source.workspace, identifier))[
        "controls"
    ]["events"] == result["controls"]["events"]
    with pytest.raises(WorkspaceAccessError):
        await service.apply(source.owner, source.workspace, identifier, request)


@pytest.mark.asyncio
async def test_progress_lookup_and_foreign_cancel_during_generation_do_not_affect_owned_task(
    controlled_workflow,
):
    """Discover an active exact workflow through bounded metadata and reject foreign cancellation before signalling any task."""
    service, source, root, core = controlled_workflow
    core.block = True
    task = asyncio.create_task(propose(controlled_workflow))
    await asyncio.wait_for(core.entered.wait(), 5)
    values = await service.list(source.owner, source.workspace)
    identifier = UUID(values[0]["workflow_id"])
    assert (await service.read(source.owner, source.workspace, identifier))[
        "state"
    ] == "generating"
    with pytest.raises(WorkspaceAccessError) as caught:
        await service.cancel(uuid4(), source.workspace, identifier)
    assert (
        caught.value.status_code == 404
        and not task.done()
        and not service.controls[identifier].cancel_requested
    )
    result = await service.cancel(source.owner, source.workspace, identifier)
    with pytest.raises(asyncio.CancelledError):
        await task
    assert result["state"] == "cancelled" and result["controls"]["cancel_finished"]
    assert (
        core.exited.is_set()
        and not service.operations
        and not service.active_tasks
        and not service.cancel_workers
    )
    assert not service.cancel_requests and not service.cancel_admission.locked()
    assert (
        not service.approvals._records
        and (root / "sample.py").read_text() == core.case["target"]["source"]
    )
    with pytest.raises(WorkspaceAccessError):
        await service.retry_proposal(source.owner, source.workspace, identifier)


@pytest.mark.asyncio
async def test_cancel_after_known_apply_preserves_committed_bytes_and_blocks_future_workflow_stages(
    controlled_workflow,
):
    """Retain a known consumed/applied checkpoint receipt without implicit rollback or a new check approval after cancellation."""
    service, source, root, core = controlled_workflow
    value = await applied(controlled_workflow)
    identifier = UUID(value["workflow_id"])
    result = await service.cancel(source.owner, source.workspace, identifier)
    assert result["summary"]["edit_applied"] is True and result["check"] is None
    assert result["state"] == "cancelled" and result["summary"]["checkpoint_id"]
    assert (
        hashlib.sha256((root / "sample.py").read_bytes()).hexdigest()
        == core.case["expected_fixed_source_sha256"]
    )
    with pytest.raises(WorkspaceAccessError):
        await service.propose_checks(source.owner, source.workspace, identifier)
    assert not service.checks.records


@pytest.mark.asyncio
async def test_cancel_during_actual_source_capture_joins_late_result_before_releasing_pin(
    controlled_workflow, monkeypatch
):
    """Hold a real captured capability until cancellation signals its worker and prove the late result closes before cancellation returns."""
    service, source, _, core = controlled_workflow
    captured, entered = [], asyncio.Event()
    loop, original = asyncio.get_running_loop(), base_module.NativeCheckSources

    def held_capture(*arguments):
        """Capture the actual selected files and return only after the owned worker receives its stop signal."""
        native = original(*arguments)
        captured.append(native)
        loop.call_soon_threadsafe(entered.set)
        assert arguments[-1].wait(5)
        return native

    monkeypatch.setattr(base_module, "NativeCheckSources", held_capture)
    task = asyncio.create_task(propose(controlled_workflow))
    await asyncio.wait_for(entered.wait(), 5)
    identifier = UUID(
        (await service.list(source.owner, source.workspace))[0]["workflow_id"]
    )
    result = await service.cancel(source.owner, source.workspace, identifier)
    with pytest.raises(asyncio.CancelledError):
        await task
    assert result["state"] == "cancelled" and captured[0].closed
    assert not core.calls and not service.active_tasks and not service.operations


@pytest.mark.asyncio
@pytest.mark.parametrize("boundary", ["before_commit", "after_commit"])
async def test_owner_cancel_joins_actual_native_write_and_preserves_its_commit_boundary(
    controlled_workflow, monkeypatch, boundary
):
    """Cancel a real native edit before its worker or after its committed rename and retain the actual approval/source outcome."""
    service, source, root, core = controlled_workflow
    value = await propose(controlled_workflow)
    identifier, request = (
        UUID(value["workflow_id"]),
        UUID(value["patch"]["approval_id"]),
    )
    native = service.patches.records[UUID(value["patch"]["proposal_id"])]
    approve(service, source.owner, request)
    entered, loop = asyncio.Event(), asyncio.get_running_loop()
    original = native.apply

    def held_apply(*arguments, **options):
        """Expose a deterministic real stop boundary without replacing the native commit or its one-shot approval semantics."""
        if boundary == "after_commit":
            original(*arguments, **options)
        loop.call_soon_threadsafe(entered.set)
        assert arguments[-1].wait(5)
        if boundary == "before_commit":
            return original(*arguments, **options)

    monkeypatch.setattr(native, "apply", held_apply)
    task = asyncio.create_task(
        service.apply(source.owner, source.workspace, identifier, request)
    )
    await asyncio.wait_for(entered.wait(), 5)
    assert not native.closed
    result = await service.cancel(source.owner, source.workspace, identifier)
    with pytest.raises(asyncio.CancelledError):
        await task
    committed = boundary == "after_commit"
    assert result["summary"]["edit_applied"] is committed
    assert service.approvals.review(source.owner, request)["state"] == (
        "consumed" if committed else "approved"
    )
    expected = (
        core.case["expected_fixed_source_sha256"]
        if committed
        else core.case["target"]["sha256"]
    )
    assert hashlib.sha256((root / "sample.py").read_bytes()).hexdigest() == expected
    assert native.closed and not service.patches.operations and not service.active_tasks


@pytest.mark.asyncio
async def test_owner_cancel_running_native_check_keeps_consumed_exit_and_applied_source(
    controlled_workflow, monkeypatch
):
    """Signal and join an actual sandbox process through owner cancellation while preserving consumed approval and native exit evidence."""
    service, source, root, core = controlled_workflow
    row = core.case["tests"][0]
    row["source"] += "\nimport time\ntime.sleep(10)\n"
    row["sha256"] = hashlib.sha256(row["source"].encode()).hexdigest()
    (root / row["path"]).write_text(row["source"])
    value = await applied(controlled_workflow)
    identifier = UUID(value["workflow_id"])
    value = await service.propose_checks(source.owner, source.workspace, identifier)
    request = UUID(value["check"]["approval_id"])
    approve(service, source.owner, request)
    started, loop, processes = asyncio.Event(), asyncio.get_running_loop(), []
    original = runner_module.subprocess.Popen

    def acknowledged(*arguments, **options):
        """Notify only after the real sandbox process handle has been returned to the owned launcher."""
        process = original(*arguments, **options)
        processes.append(process)
        loop.call_soon_threadsafe(started.set)
        return process

    monkeypatch.setattr(runner_module.subprocess, "Popen", acknowledged)
    task = asyncio.create_task(
        service.run_checks(source.owner, source.workspace, identifier, request)
    )
    await asyncio.wait_for(started.wait(), 5)
    result = await service.cancel(source.owner, source.workspace, identifier)
    with pytest.raises(asyncio.CancelledError):
        await task
    assert result["summary"]["edit_applied"] and result["summary"]["native_started"]
    assert result["summary"]["native_exit_code"] is not None
    assert service.approvals.review(source.owner, request)["state"] == "consumed"
    assert all(process.poll() is not None for process in processes)
    assert not any(
        thread.name.startswith("checks-native-") for thread in threading.enumerate()
    )


@pytest.mark.asyncio
async def test_cancelled_cancel_request_joins_owned_cleanup_before_propagating(
    controlled_workflow, monkeypatch
):
    """Lose a cancellation request acknowledgement while retaining ownership of its cleanup child until the pending patch is retired."""
    service, source, _, _ = controlled_workflow
    value = await propose(controlled_workflow)
    identifier = UUID(value["workflow_id"])
    entered, release = asyncio.Event(), asyncio.Event()
    original = service.cancel_owned

    async def held_cleanup(record):
        """Hold the actual owned cleanup before allowing its real native retirement to finish."""
        entered.set()
        await release.wait()
        return await original(record)

    monkeypatch.setattr(service, "cancel_owned", held_cleanup)
    request = asyncio.create_task(
        service.cancel(source.owner, source.workspace, identifier)
    )
    await asyncio.wait_for(entered.wait(), 5)
    request.cancel()
    await asyncio.sleep(0)
    assert not request.done() and service.cancel_workers
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await request
    result = await service.read(source.owner, source.workspace, identifier)
    assert (
        result["controls"]["cancel_finished"] and result["patch"]["state"] == "failed"
    )
    assert (
        not service.cancel_workers
        and not service.cancel_requests
        and not service.cancel_admission.locked()
    )


@pytest.mark.asyncio
async def test_shutdown_joins_held_model_before_component_dependencies_close(
    controlled_workflow,
):
    """Drain the actual held model operation without closing shared checks, patch, approval or workspace authorities first."""
    service, _, _, core = controlled_workflow
    core.block = True
    task = asyncio.create_task(propose(controlled_workflow))
    await asyncio.wait_for(core.entered.wait(), 5)
    await service.shutdown()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert core.exited.is_set() and not service.operations and not service.active_tasks
    assert not any(
        component.closing
        for component in (
            service.checks,
            service.patches,
            service.approvals,
            service.workspace,
        )
    )


@pytest.mark.asyncio
async def test_cancel_task_creation_failure_releases_admission_without_side_effect(
    controlled_workflow, monkeypatch
):
    """Fail before scheduling cleanup and retain the pending capability while releasing request/admission ownership for a later explicit cancellation."""
    service, source, _, _ = controlled_workflow
    value = await propose(controlled_workflow)
    identifier = UUID(value["workflow_id"])

    def failed_creation(coroutine):
        """Inject a synchronous scheduler failure without scheduling or adopting the supplied coroutine."""
        raise RuntimeError("CONTROLLED-TASK-CREATION")

    with monkeypatch.context() as scope:
        scope.setattr(controller_module.asyncio, "create_task", failed_creation)
        with pytest.raises(RuntimeError, match="CONTROLLED-TASK-CREATION"):
            await service.cancel(source.owner, source.workspace, identifier)
    assert (
        not service.cancel_admission.locked()
        and not service.cancel_requests
        and not service.cancel_workers
    )
    assert not service.controls[identifier].cancel_requested
    assert (await service.cancel(source.owner, source.workspace, identifier))[
        "controls"
    ]["cancel_finished"]


@pytest.mark.asyncio
async def test_busy_component_cancel_retains_intent_without_duplicate_events_or_premature_close(
    controlled_workflow,
):
    """Keep cancellation pending while independent component admission is busy and allow explicit later cleanup without another hook pair."""
    service, source, _, _ = controlled_workflow
    value = await propose(controlled_workflow)
    identifier = UUID(value["workflow_id"])
    native = service.patches.records[UUID(value["patch"]["proposal_id"])]
    async with service.patches.operation():
        with pytest.raises(WorkspaceAccessError):
            await service.cancel(source.owner, source.workspace, identifier)
        assert not native.closed and native.state == "proposed"
        pending = await service.read(source.owner, source.workspace, identifier)
        assert (
            pending["cancel_status"] == "waiting_for_component"
            and not pending["controls"]["cancel_finished"]
        )
    result = await service.cancel(source.owner, source.workspace, identifier)
    assert (
        result["controls"]["cancel_finished"]
        and len(result["controls"]["events"]) == 4
        and native.closed
    )


@pytest.mark.asyncio
async def test_terminal_hook_fault_preserves_actual_edit_and_cannot_silently_retry_hooks_or_actions(
    controlled_workflow, monkeypatch
):
    """Fail post-action metadata only after native commit and preserve its receipt with explicit hook uncertainty instead of another action attempt."""
    service, source, root, core = controlled_workflow
    value = await propose(controlled_workflow)
    identifier = UUID(value["workflow_id"])
    request = UUID(value["patch"]["approval_id"])
    approve(service, source.owner, request)
    control = service.controls[identifier]
    original = control.after

    def failing_after(stage, outcome):
        """Inject only the terminal apply hook fault without bypassing the completed native action."""
        if stage == "apply":
            raise OSError("CONTROLLED-TERMINAL-HOOK")
        return original(stage, outcome)

    monkeypatch.setattr(control, "after", failing_after)
    result = await service.apply(source.owner, source.workspace, identifier, request)
    assert (
        result["summary"]["edit_applied"] is True
        and result["controls"]["hook_uncertain"]
    )
    assert control.actions["apply"] == "finished"
    assert (
        hashlib.sha256((root / "sample.py").read_bytes()).hexdigest()
        == core.case["expected_fixed_source_sha256"]
    )
    with pytest.raises(WorkspaceAccessError):
        await service.propose_checks(source.owner, source.workspace, identifier)


@pytest.mark.asyncio
async def test_retry_source_drift_keeps_original_hash_and_charges_failed_second_record(
    controlled_workflow,
):
    """Revalidate unchanged selected hashes on explicit retry and retain its failed second record without reading changed bytes into another model call."""
    service, source, root, core = controlled_workflow
    core.raw = "invalid"
    first = await propose(controlled_workflow)
    (root / "sample.py").write_text("changed unreviewed source\n")
    result = await service.retry_proposal(
        source.owner, source.workspace, UUID(first["workflow_id"])
    )
    assert result["state"] == "proposal_failed" and not result["model_attempted"]
    assert (
        result["selected_files"] == first["selected_files"]
        and result["controls"]["proposals_used"] == 2
    )
    assert len(core.calls) == 1 and len(service.records) == 2


@pytest.mark.asyncio
async def test_busy_or_capacity_retry_before_registration_does_not_charge_lineage(
    controlled_workflow,
):
    """Keep the sole explicit retry slot available when admission or owner record capacity rejects before any new registration."""
    service, source, _, core = controlled_workflow
    core.raw = "invalid"
    first = await propose(controlled_workflow)
    identifier = UUID(first["workflow_id"])
    async with service.operation(source.owner, source.workspace):
        with pytest.raises(WorkspaceAccessError) as caught:
            await service.retry_proposal(source.owner, source.workspace, identifier)
        assert caught.value.code == "workflow_busy"
    for _ in range(3):
        await propose(controlled_workflow)
    with pytest.raises(WorkspaceAccessError) as caught:
        await service.retry_proposal(source.owner, source.workspace, identifier)
    assert caught.value.code == "workflow_capacity"
    assert (
        len(service.controls[identifier].lineage.members) == 1 and len(core.calls) == 4
    )


@pytest.mark.asyncio
async def test_pending_check_cancel_closes_snapshot_without_consuming_its_approval(
    controlled_workflow,
):
    """Retire only the pending check snapshot and preserve the already applied edit and unconsumed second approval."""
    service, source, root, core = controlled_workflow
    value = await applied(controlled_workflow)
    identifier = UUID(value["workflow_id"])
    value = await service.propose_checks(source.owner, source.workspace, identifier)
    request = UUID(value["check"]["approval_id"])
    result = await service.cancel(source.owner, source.workspace, identifier)
    assert (
        result["check"]["state"] == "cancelled"
        and not result["summary"]["native_started"]
    )
    assert (
        result["summary"]["edit_applied"]
        and service.approvals.review(source.owner, request)["state"] == "pending"
    )
    assert (
        hashlib.sha256((root / "sample.py").read_bytes()).hexdigest()
        == core.case["expected_fixed_source_sha256"]
    )
    with pytest.raises(WorkspaceAccessError):
        await service.retry_proposal(source.owner, source.workspace, identifier)


@pytest.mark.asyncio
async def test_close_fault_keeps_uncertain_cancellation_without_replaying_retirement(
    controlled_workflow, monkeypatch
):
    """Keep a real closed patch plus cleanup uncertainty after a lost close acknowledgement and never reclassify it as clean on repeated cancellation."""
    service, source, _, _ = controlled_workflow
    value = await propose(controlled_workflow)
    identifier = UUID(value["workflow_id"])
    native = service.patches.records[UUID(value["patch"]["proposal_id"])]
    original, calls = native.close, []

    def lost_acknowledgement():
        """Complete the actual capability close before raising its controlled acknowledgement failure."""
        original()
        calls.append(True)
        raise OSError("CONTROLLED-CLOSE-ACK")

    with monkeypatch.context() as scope:
        scope.setattr(native, "close", lost_acknowledgement)
        result = await service.cancel(source.owner, source.workspace, identifier)
        repeated = await service.cancel(source.owner, source.workspace, identifier)
    assert result == repeated and result["cancel_status"] == "cleanup_uncertain"
    assert native.closed and len(calls) == 1


@pytest.mark.asyncio
async def test_before_hook_denial_never_consumes_or_applies_approved_patch(
    controlled_workflow, monkeypatch
):
    """Fail a trusted pre-action hook after domain preconditions but before consuming the actual one-shot approval."""
    service, source, root, core = controlled_workflow
    value = await propose(controlled_workflow)
    identifier, request = (
        UUID(value["workflow_id"]),
        UUID(value["patch"]["approval_id"]),
    )
    approve(service, source.owner, request)
    control = service.controls[identifier]

    def denied(stage):
        """Reject before action reservation or native actuation without changing any approval state."""
        raise WorkspaceAccessError("workflow_hook_uncertain", 503)

    monkeypatch.setattr(control, "before", denied)
    with pytest.raises(WorkspaceAccessError):
        await service.apply(source.owner, source.workspace, identifier, request)
    assert service.approvals.review(source.owner, request)["state"] == "approved"
    assert (root / "sample.py").read_text() == core.case["target"]["source"]
    assert len(control.events) == 2 and not service.active_tasks


@pytest.mark.asyncio
async def test_independently_applying_patch_cannot_have_pin_closed_by_workflow_cancel(
    controlled_workflow, monkeypatch
):
    """Hold an actual separately invoked committed edit and report busy cancellation until its owned writer joins, then preserve the real commit."""
    service, source, root, core = controlled_workflow
    value = await propose(controlled_workflow)
    identifier, request, patch_id = (
        UUID(value["workflow_id"]),
        UUID(value["patch"]["approval_id"]),
        UUID(value["patch"]["proposal_id"]),
    )
    approve(service, source.owner, request)
    native = service.patches.records[patch_id]
    original, entered, release = native.apply, asyncio.Event(), threading.Event()
    loop = asyncio.get_running_loop()

    def held_actual_commit(*arguments, **options):
        """Complete the real atomic write and delay its independently owned acknowledgement without holding a fake capability."""
        original(*arguments, **options)
        loop.call_soon_threadsafe(entered.set)
        assert release.wait(5)

    monkeypatch.setattr(native, "apply", held_actual_commit)
    writer = asyncio.create_task(
        service.patches.apply(source.owner, source.workspace, patch_id, request)
    )
    try:
        await asyncio.wait_for(entered.wait(), 5)
        with pytest.raises(WorkspaceAccessError):
            await service.cancel(source.owner, source.workspace, identifier)
        assert not native.closed and not writer.done()
        assert service.controls[identifier].cancel_requested
    finally:
        release.set()
        await writer
    result = await service.cancel(source.owner, source.workspace, identifier)
    assert result["summary"]["edit_applied"] and native.closed
    assert (
        hashlib.sha256((root / "sample.py").read_bytes()).hexdigest()
        == core.case["expected_fixed_source_sha256"]
    )


@pytest.mark.asyncio
async def test_cancellation_terminal_hook_fault_keeps_retirement_and_no_hook_replay(
    controlled_workflow, monkeypatch
):
    """Retain completed native retirement with explicit hook uncertainty instead of silently reattempting a terminal cancellation hook."""
    service, source, _, _ = controlled_workflow
    value = await propose(controlled_workflow)
    identifier, calls = UUID(value["workflow_id"]), []

    def failed_terminal(outcome):
        """Fail only after actual cancellation cleanup has joined and preserve an observable single terminal-hook attempt."""
        calls.append(outcome)
        raise OSError("CONTROLLED-CANCEL-HOOK")

    monkeypatch.setattr(service.controls[identifier], "finish_cancel", failed_terminal)
    result = await service.cancel(source.owner, source.workspace, identifier)
    assert (
        result["controls"]["cancel_finished"] and result["controls"]["hook_uncertain"]
    )
    assert (
        result["cancel_status"] == "cleanup_uncertain"
        and result["patch"]["state"] == "failed"
    )
    assert await service.cancel(source.owner, source.workspace, identifier) == result
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_shutdown_joins_owned_cancellation_cleanup_without_cancelling_its_worker(
    controlled_workflow, monkeypatch
):
    """Shutdown cancels a held request but joins its cleanup child without a cancellation cycle or early dependency release."""
    service, source, _, _ = controlled_workflow
    value = await propose(controlled_workflow)
    identifier = UUID(value["workflow_id"])
    entered, release, original = asyncio.Event(), asyncio.Event(), service.cancel_owned

    async def held_cleanup(record):
        """Delay the real owned cleanup while retaining dependency ownership for shutdown."""
        entered.set()
        await release.wait()
        return await original(record)

    monkeypatch.setattr(service, "cancel_owned", held_cleanup)
    request = asyncio.create_task(
        service.cancel(source.owner, source.workspace, identifier)
    )
    await asyncio.wait_for(entered.wait(), 5)
    shutdown = asyncio.create_task(service.shutdown())
    await asyncio.sleep(0)
    assert not shutdown.done() and not service.patches.closing
    release.set()
    await asyncio.wait_for(shutdown, 5)
    with pytest.raises(asyncio.CancelledError):
        await request
    assert (
        not service.cancel_workers
        and not service.cancel_requests
        and not service.cancel_admission.locked()
    )
    assert service.controls[identifier].cancel_finished


@pytest.mark.asyncio
@pytest.mark.parametrize("fault", ["prior_close_ack", "unknown_commit_ack"])
async def test_cancellation_retains_prior_actual_patch_uncertainty(
    controlled_workflow, monkeypatch, fault
):
    """Preserve an earlier real commit with uncertain close or commit acknowledgement in both stage hooks and subsequent cancellation status."""
    service, source, root, core = controlled_workflow
    value = await propose(controlled_workflow)
    identifier, request = (
        UUID(value["workflow_id"]),
        UUID(value["patch"]["approval_id"]),
    )
    native = service.patches.records[UUID(value["patch"]["proposal_id"])]
    approve(service, source.owner, request)
    if fault == "prior_close_ack":
        original = native.close

        def lost_close():
            """Release the real native capability before losing only its cleanup acknowledgement."""
            original()
            raise OSError("CONTROLLED-PRIOR-CLOSE")

        method, replacement = "close", lost_close
    else:
        original = native.rename_prepared

        def unknown_commit(*arguments, **options):
            """Perform the actual reviewed rename but retain an explicitly unknown commit observation at the controlled acknowledgement boundary."""
            original(*arguments, **options)
            return native.record_commit("outcome_unknown", applied=None)

        method, replacement = "rename_prepared", unknown_commit
    with monkeypatch.context() as scope:
        scope.setattr(native, method, replacement)
        actual = await service.apply(
            source.owner, source.workspace, identifier, request
        )
    result = await service.cancel(source.owner, source.workspace, identifier)
    assert result["cancel_status"] == "cleanup_uncertain"
    assert result["patch"]["receipt"] == actual["patch"]["receipt"]
    assert (
        next(
            event
            for event in result["controls"]["events"]
            if event["stage"] == "apply" and event["phase"] == "after"
        )["outcome"]
        == "uncertain"
    )
    assert result["summary"]["edit_applied"] is (
        True if fault == "prior_close_ack" else None
    )
    assert (
        hashlib.sha256((root / "sample.py").read_bytes()).hexdigest()
        == core.case["expected_fixed_source_sha256"]
    )
    assert service.approvals.review(source.owner, request)["state"] == "consumed"


@pytest.mark.asyncio
@pytest.mark.parametrize("fault", ["check_close_ack", "check_retirement_ack"])
async def test_pending_check_cancellation_retains_actual_cleanup_and_journal_uncertainty(
    controlled_workflow, monkeypatch, fault
):
    """Retain actual pending-check source-close or journal acknowledgement uncertainty without consuming its approval or reporting clean cancellation."""
    service, source, _, _ = controlled_workflow
    value = await applied(controlled_workflow)
    identifier = UUID(value["workflow_id"])
    value = await service.propose_checks(source.owner, source.workspace, identifier)
    request = UUID(value["check"]["approval_id"])
    record = service.checks.records[UUID(value["check"]["job_id"])]
    if fault == "check_close_ack":
        target, method = record.sources, "close"
        original = target.close

        def lost_close():
            """Close the actual pending snapshot before losing its cleanup acknowledgement."""
            original()
            raise OSError("CONTROLLED-CHECK-CLOSE")

        replacement = lost_close
    else:
        target, method = service.checks.store, "retire_live"
        original = target.retire_live

        def lost_retirement(*arguments, **options):
            """Persist the actual pending job retirement before losing its journal acknowledgement."""
            original(*arguments, **options)
            raise OSError("CONTROLLED-CHECK-RETIREMENT")

        replacement = lost_retirement
    with monkeypatch.context() as scope:
        scope.setattr(target, method, replacement)
        result = await service.cancel(source.owner, source.workspace, identifier)
    assert result["cancel_status"] == "cleanup_uncertain"
    assert result["summary"]["edit_applied"] and not result["summary"]["native_started"]
    assert service.approvals.review(source.owner, request)["state"] == "pending"
    assert record.sources is None and record.finished.is_set()
