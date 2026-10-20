"""Verify finite workflow composition with real checkpoints/approvals/native checks and explicitly controlled inference, without model-quality claims."""

import asyncio
import base64
import hashlib
import json
import threading
from pathlib import Path
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from test_check_jobs import job_store as job_store
from test_check_service import approve

from apps.api.services import coding_workflows as module
from apps.api.services.checkpoint_patches import CheckpointPatchService
from apps.api.services.checks import CheckService
from apps.api.services.coding_workflows import CodingWorkflowService
from apps.api.services.workspaces import WorkspaceService
from src.application.ports.inference import CompletionResult
from src.application.services.approvals import ApprovalStore
from src.application.services.workspace_policy import WorkspaceAccessError
from src.infrastructure import check_runner as runner_module
from src.infrastructure.checkpoints import CheckpointStore


def sample_case():
    """Load only the immutable pre-inference visible fixture without calling a model or treating it as measured evidence."""
    path = Path("docs/evidence/d43-visible-sample-case.pending.json")
    assert (
        hashlib.sha256(path.read_bytes()).hexdigest()
        == "2153fba8d61b1d5cc2cda3f980a388a567cdddbd3634500e45e72ae216607075"
    )
    return json.loads(path.read_text())


class ControlledCore:
    """Provide disclosed deterministic output or held generation for actual source/lifecycle tests without model inference."""

    def __init__(self):
        """Prepare one observable attempt using only the frozen controlled sample repair."""
        self.case = sample_case()
        self.raw = json.dumps(
            dict(
                plan=[
                    "Replace the subtraction operator with addition and retain the other statements."
                ],
                replacement=self.case["target"]["source"].replace(
                    "return left - right", "return left + right"
                ),
            )
        )
        self.finish = "stop"
        self.calls = []
        self.entered, self.release, self.exited = (
            asyncio.Event(),
            asyncio.Event(),
            asyncio.Event(),
        )
        self.block, self.after_complete = False, None

    async def complete(self, **options):
        """Record the actual fixed model-port request while allowing controlled source mutation or joined cancellation."""
        self.calls.append(options)
        self.entered.set()
        try:
            if self.block:
                await self.release.wait()
            if self.after_complete is not None:
                self.after_complete()
            return CompletionResult(self.raw, "controlled-core", "fast", self.finish)
        finally:
            self.exited.set()


@pytest_asyncio.fixture
async def workflow_service(job_store):
    """Bind only disposable real workspace/check/checkpoint roots and approvals with a disclosed controlled CORE port."""
    store, source, paths, _, _ = job_store
    case = sample_case()
    for row in [case["target"], *case["tests"]]:
        path = paths[0] / row["path"]
        path.write_bytes(row["source"].encode())
        path.chmod(0o644)
    workspace = WorkspaceService(store.catalog)
    approvals = ApprovalStore(store.catalog)
    patches = CheckpointPatchService(
        workspace, approvals, CheckpointStore(str(paths[2]), store.catalog)
    )
    checks = CheckService(workspace, approvals, store)
    core = ControlledCore()
    service = CodingWorkflowService(
        workspace, approvals, patches, checks, inference=core
    )
    try:
        yield service, source, paths[0], core
    finally:
        await service.shutdown()
        await checks.shutdown()
        await patches.shutdown()
        approvals.close()
        await workspace.shutdown()


async def propose(workflow_service):
    """Create a controlled source-selected pending workflow with no approval or automatic action."""
    service, source, _, core = workflow_service
    case = core.case
    return await service.propose(
        source.owner,
        source.workspace,
        case["issue"],
        dict(path=case["target"]["path"], expected_sha256=case["target"]["sha256"]),
        [
            dict(path=row["path"], expected_sha256=row["sha256"])
            for row in case["tests"]
        ],
        "python_unittest",
    )


async def applied(workflow_service):
    """Approve only the concrete synthetic patch and explicitly apply it without proposing or executing checks."""
    service, source, _, _ = workflow_service
    result = await propose(workflow_service)
    approval = UUID(result["patch"]["approval_id"])
    approve(service, source.owner, approval)
    result = await service.apply(
        source.owner, source.workspace, UUID(result["workflow_id"]), approval
    )
    assert result["summary"]["edit_applied"] is True
    return result


@pytest.mark.asyncio
async def test_actual_components_require_two_distinct_approvals_and_preserve_exact_snapshot_summary(
    workflow_service,
):
    """Perform the full controlled-port/native workflow and retain original trusted tests, exact patch/check linkage and non-quality observations."""
    service, source, root, core = workflow_service
    value = await propose(workflow_service)
    identifier, patch_approval = (
        UUID(value["workflow_id"]),
        UUID(value["patch"]["approval_id"]),
    )
    assert value["state"] == "awaiting_patch_review" and value["check"] is None
    assert (root / "sample.py").read_text() == core.case["target"]["source"]
    assert not service.checks.records and not value["summary"]["edit_applied"]
    with pytest.raises(WorkspaceAccessError):
        await service.apply(source.owner, source.workspace, identifier, patch_approval)
    assert not service.records[identifier].value["apply_attempted"]
    approve(service, source.owner, patch_approval)
    value = await service.apply(
        source.owner, source.workspace, identifier, patch_approval
    )
    assert value["state"] == "applied" and value["check"] is None
    value = await service.propose_checks(source.owner, source.workspace, identifier)
    check_approval = UUID(value["check"]["approval_id"])
    assert check_approval != patch_approval and value["check"]["observation"] is None
    for wrong in [patch_approval, check_approval]:
        with pytest.raises(WorkspaceAccessError):
            await service.run_checks(source.owner, source.workspace, identifier, wrong)
        assert not service.records[identifier].value["check_attempted"]
    approve(service, source.owner, check_approval)
    value = await service.run_checks(
        source.owner, source.workspace, identifier, check_approval
    )
    assert value["state"] == "completed"
    assert (
        value["summary"]["native_started"] and value["summary"]["native_exit_code"] == 0
    )
    assert value["summary"]["edit_applied"] and value["summary"]["checkpoint_id"]
    assert (
        not value["summary"]["current_source_observed"]
        and not value["summary"]["quality_evaluated"]
    )
    assert value["summary"]["tested_source_version"] == value["check"]["source_version"]
    assert (
        hashlib.sha256((root / "sample.py").read_bytes()).hexdigest()
        == core.case["expected_fixed_source_sha256"]
    )
    assert (root / "test_sample.py").read_text() == core.case["tests"][0]["source"]
    assert (
        len(core.calls) == 1
        and core.calls[0]["profile"] == "core"
        and core.calls[0]["preset"] == "fast"
    )
    assert core.calls[0]["max_tokens"] == 2048 and core.calls[0]["temperature"] == 0
    assert service.approvals.review(source.owner, patch_approval)["state"] == "consumed"
    assert service.approvals.review(source.owner, check_approval)["state"] == "consumed"
    value["check"]["observation"]["policy"]["network"] = True
    assert not (await service.read(source.owner, source.workspace, identifier))[
        "check"
    ]["observation"]["policy"]["network"]
    with pytest.raises(WorkspaceAccessError):
        await service.run_checks(
            source.owner, source.workspace, identifier, check_approval
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["extra_command", "fenced", "truncated"])
async def test_failed_first_completion_is_retained_without_repair_retry_or_action(
    workflow_service, kind
):
    """Record the first invalid/incomplete model response without creating approvals, changing source or silently repairing output."""
    service, _, root, core = workflow_service
    if kind == "extra_command":
        core.raw = json.dumps(json.loads(core.raw) | dict(command="true"))
    elif kind == "fenced":
        core.raw = "```json\n" + core.raw + "\n```"
    else:
        core.finish = "length"
    result = await propose(workflow_service)
    assert result["state"] == "proposal_failed" and result["patch"] is None
    assert (
        result["model_observation"]["raw_sha256"]
        == hashlib.sha256(core.raw.encode()).hexdigest()
    )
    assert (
        len(core.calls) == 1
        and not service.patches.records
        and not service.approvals._records
    )
    assert (root / "sample.py").read_text() == core.case["target"]["source"]


@pytest.mark.asyncio
async def test_oversized_multibyte_completion_retains_exact_bounded_prefix_without_lossy_decode(
    workflow_service,
):
    """Preserve exact bytes even when the bounded model prefix ends inside a Unicode character and refuse the oversized proposal."""
    _, _, _, core = workflow_service
    core.raw = "界" * 6000
    value = await propose(workflow_service)
    observation = value["model_observation"]
    prefix = base64.b64decode(observation["raw_prefix_base64"], validate=True)
    assert (
        prefix == core.raw.encode()[:16384]
        and len(prefix) == observation["prefix_bytes"] == 16384
    )
    assert observation["prefix_sha256"] == hashlib.sha256(prefix).hexdigest()
    assert observation["prefix_truncated"] and observation["valid_unicode"]
    assert value["state"] == "proposal_failed" and value["patch"] is None


@pytest.mark.asyncio
async def test_changed_selected_test_during_generation_prevents_patch_publication(
    workflow_service,
):
    """Fence the complete model source context instead of checking only the intended edit target after inference."""
    service, _, root, core = workflow_service

    def mutate_test():
        """Make an actual controlled independent test edit after the model-port call and before final context validation."""
        (root / "test_sample.py").write_text('"""Independent test context change."""\n')

    core.after_complete = mutate_test
    value = await propose(workflow_service)
    assert value["state"] == "proposal_failed" and value["patch"] is None
    assert not service.patches.records and not service.approvals._records
    assert (root / "sample.py").read_text() == core.case["target"]["source"]


@pytest.mark.asyncio
async def test_foreign_and_unknown_workflows_have_no_component_side_effect(
    workflow_service,
):
    """Deny foreign identity before observing retained issue/model/source contents or changing pending approvals."""
    service, source, _, _ = workflow_service
    value = await propose(workflow_service)
    identifier = UUID(value["workflow_id"])
    for owner, key in [(uuid4(), identifier), (source.owner, uuid4())]:
        with pytest.raises(WorkspaceAccessError) as caught:
            await service.read(owner, source.workspace, key)
        assert (
            caught.value.code == "workflow_not_found"
            and caught.value.status_code == 404
        )
    with pytest.raises(WorkspaceAccessError):
        await service.apply(
            uuid4(), source.workspace, identifier, UUID(value["patch"]["approval_id"])
        )
    assert service.records[identifier].value["state"] == "awaiting_patch_review"
    assert len(await service.list(source.owner, source.workspace)) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["request", "shutdown", "timeout"])
async def test_generation_cancellation_and_timeout_join_before_source_dependency_release(
    workflow_service, monkeypatch, mode
):
    """Stop an actually held model coroutine and preserve its failed/cancelled attempt while leaving source and approvals untouched."""
    service, _, root, core = workflow_service
    core.block = True
    if mode == "timeout":
        monkeypatch.setattr(module, "MODEL_SECONDS", 0.01)
    task = asyncio.create_task(propose(workflow_service))
    await asyncio.wait_for(core.entered.wait(), 5)
    if mode == "shutdown":
        await service.shutdown()
    elif mode == "request":
        task.cancel()
    if mode != "timeout":
        with pytest.raises(asyncio.CancelledError):
            await task
    else:
        result = await task
        assert result["error_code"] == "workflow_model_timeout"
    assert (
        core.exited.is_set()
        and not service.operations
        and not service.admission.locked()
    )
    assert (
        len(core.calls) == 1
        and not service.patches.records
        and not service.approvals._records
    )
    assert (root / "sample.py").read_text() == core.case["target"]["source"]


@pytest.mark.asyncio
async def test_check_capture_failure_keeps_actual_applied_receipt_without_implicit_rollback(
    workflow_service, monkeypatch
):
    """Keep known committed bytes/checkpoint when later check proposal construction fails, and reject an automatic second attempt."""
    service, source, root, core = workflow_service
    result = await applied(workflow_service)
    identifier = UUID(result["workflow_id"])

    async def fail_capture(*arguments, **options):
        """Fail only the subsequent check proposal without executing or modifying any source."""
        raise OSError("CONTROLLED-CHECK-CAPTURE")

    monkeypatch.setattr(service.checks, "propose", fail_capture)
    value = await service.propose_checks(source.owner, source.workspace, identifier)
    assert (
        value["state"] == "check_proposal_failed"
        and value["summary"]["edit_applied"] is True
    )
    assert value["summary"]["checkpoint_id"] and value["check"] is None
    assert (
        hashlib.sha256((root / "sample.py").read_bytes()).hexdigest()
        == core.case["expected_fixed_source_sha256"]
    )
    with pytest.raises(WorkspaceAccessError):
        await service.propose_checks(source.owner, source.workspace, identifier)


@pytest.mark.asyncio
async def test_context_changed_during_checkpoint_preparation_keeps_pending_patch_unapplied(
    workflow_service, monkeypatch
):
    """Fence selected tests again after joined checkpoint preparation and retain the known pending component without applying stale model context."""
    service, source, root, core = workflow_service
    original = service.patches.propose

    async def change_after_checkpoint(*arguments, **options):
        """Create the actual pending checkpoint first, then independently change a selected test before workflow publication."""
        value = await original(*arguments, **options)
        (root / "test_sample.py").write_text(
            '"""Changed selected test during checkpoint preparation."""\n'
        )
        return value

    monkeypatch.setattr(service.patches, "propose", change_after_checkpoint)
    value = await propose(workflow_service)
    assert value["state"] == "proposal_failed" and value["patch"] is not None
    assert value["patch"]["receipt"] is None and not value["apply_attempted"]
    assert (root / "sample.py").read_text() == core.case["target"]["source"]
    assert (
        service.approvals.review(source.owner, UUID(value["patch"]["approval_id"]))[
            "state"
        ]
        == "pending"
    )


@pytest.mark.asyncio
async def test_failed_model_attempts_remain_charged_without_retry_or_history_eviction(
    workflow_service,
):
    """Retain all four actual owner attempts and deny another before inference rather than freeing failed history silently."""
    service, _, _, core = workflow_service
    core.raw = "invalid completion"
    for _ in range(4):
        assert (await propose(workflow_service))["state"] == "proposal_failed"
    with pytest.raises(WorkspaceAccessError) as caught:
        await propose(workflow_service)
    assert caught.value.code == "workflow_capacity"
    assert len(core.calls) == len(service.records) == 4


@pytest.mark.asyncio
async def test_cancelled_real_native_check_retains_known_snapshot_exit_and_applied_receipt(
    workflow_service, monkeypatch
):
    """Cancel after a real native child acknowledgement and keep actual consumed-check/patch receipts instead of losing or retrying the result."""
    service, source, root, core = workflow_service
    row = core.case["tests"][0]
    row["source"] += "\nimport time\ntime.sleep(10)\n"
    row["sha256"] = hashlib.sha256(row["source"].encode()).hexdigest()
    (root / row["path"]).write_text(row["source"])
    value = await applied(workflow_service)
    identifier = UUID(value["workflow_id"])
    value = await service.propose_checks(source.owner, source.workspace, identifier)
    request = UUID(value["check"]["approval_id"])
    approve(service, source.owner, request)
    started, loop, processes = asyncio.Event(), asyncio.get_running_loop(), []
    original = runner_module.subprocess.Popen

    def acknowledged(*arguments, **options):
        """Notify the controlling event loop only after a real owned native handle has been returned."""
        process = original(*arguments, **options)
        processes.append(process)
        loop.call_soon_threadsafe(started.set)
        return process

    monkeypatch.setattr(runner_module.subprocess, "Popen", acknowledged)
    task = asyncio.create_task(
        service.run_checks(source.owner, source.workspace, identifier, request)
    )
    await asyncio.wait_for(started.wait(), 5)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    result = await service.read(source.owner, source.workspace, identifier)
    assert result["state"] == "completed" and result["summary"]["edit_applied"] is True
    assert (
        result["summary"]["native_started"]
        and result["summary"]["native_exit_code"] is not None
    )
    assert not result["summary"]["quality_evaluated"]
    assert service.approvals.review(source.owner, request)["state"] == "consumed"
    assert all(process.poll() is not None for process in processes)
    assert not any(
        thread.name.startswith("checks-native-") for thread in threading.enumerate()
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["patch", "check"])
async def test_component_expiry_cannot_be_extended_by_workflow_state(
    workflow_service, monkeypatch, stage
):
    """Expire the actual native proposal at its exact boundary and prevent writes/launch or approval consumption from stale workflow state."""
    service, source, root, core = workflow_service
    if stage == "patch":
        value = await propose(workflow_service)
        request = UUID(value["patch"]["approval_id"])
        native = service.patches.records[UUID(value["patch"]["proposal_id"])]
        monkeypatch.setattr(native, "clock", lambda: native.expires)
        action = service.apply
    else:
        value = await applied(workflow_service)
        value = await service.propose_checks(
            source.owner, source.workspace, UUID(value["workflow_id"])
        )
        request = UUID(value["check"]["approval_id"])
        live = service.checks.records[UUID(value["check"]["job_id"])]
        monkeypatch.setattr(service.checks, "clock", lambda: live.expires)
        action = service.run_checks
    approve(service, source.owner, request)
    result = await action(
        source.owner, source.workspace, UUID(value["workflow_id"]), request
    )
    assert not result["summary"]["native_started"]
    assert service.approvals.review(source.owner, request)["state"] == "approved"
    assert result["state"] == ("edit_failed" if stage == "patch" else "check_failed")
    if stage == "patch":
        assert (root / "sample.py").read_text() == core.case["target"]["source"]
    else:
        assert result["summary"]["edit_applied"] is True


@pytest.mark.asyncio
async def test_nonqueued_workflow_admission_does_not_start_another_model_or_component(
    workflow_service,
):
    """Reject overlapping normal work immediately while retaining the active operation and its source ownership."""
    service, source, _, core = workflow_service
    async with service.operation(source.owner, source.workspace):
        with pytest.raises(WorkspaceAccessError) as caught:
            await service.list(source.owner, source.workspace)
        assert caught.value.code == "workflow_busy"
        assert service.operations and service.admission.locked()
    assert not core.calls and not service.operations


@pytest.mark.asyncio
async def test_post_commit_cancellation_keeps_workflow_and_checkpoint_applied_receipts(
    workflow_service, monkeypatch
):
    """Inject cancellation after an actual native rename and retain consumed approval/committed bytes without implicit retry or rollback."""
    service, source, root, core = workflow_service
    value = await propose(workflow_service)
    identifier = UUID(value["workflow_id"])
    native = service.patches.records[UUID(value["patch"]["proposal_id"])]
    request = UUID(value["patch"]["approval_id"])
    approve(service, source.owner, request)
    original = native.apply

    def cancelled_after_commit(*arguments, **options):
        """Perform the actual reviewed edit before raising a controlled cancellation acknowledgement fault."""
        original(*arguments, **options)
        raise asyncio.CancelledError()

    monkeypatch.setattr(native, "apply", cancelled_after_commit)
    with pytest.raises(asyncio.CancelledError):
        await service.apply(source.owner, source.workspace, identifier, request)
    result = await service.read(source.owner, source.workspace, identifier)
    assert result["state"] == "applied" and result["summary"]["edit_applied"] is True
    assert service.approvals.review(source.owner, request)["state"] == "consumed"
    assert (
        hashlib.sha256((root / "sample.py").read_bytes()).hexdigest()
        == core.case["expected_fixed_source_sha256"]
    )
    assert native.closed and not service.operations and not service.patches.operations
