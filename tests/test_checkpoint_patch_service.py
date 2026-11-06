"""Verify real private checkpoint→approved edit→fresh approved byte restore and durable pre/post-commit failure boundaries."""

import asyncio
import hashlib
import os
import stat
import threading
from uuid import UUID

import pytest
import pytest_asyncio
from test_atomic_patch import patch_fixture as patch_fixture
from test_checkpoints import checkpoint_store as checkpoint_store
from test_patch_service import approve_existing, propose

from apps.api.services.checkpoint_patches import CheckpointPatchService
from apps.api.services.workspaces import WorkspaceService
from src.application.services.workspace_policy import WorkspaceAccessError
from src.infrastructure.atomic_patch import NativePatch
from src.infrastructure.checkpoints import CheckpointStore


@pytest_asyncio.fixture
async def durable_patch_service(checkpoint_store, patch_fixture):
    """Bind actual checkpoint/native/approval services on isolated temporary sources and drain every owned capability."""
    store, _ = checkpoint_store
    spec = patch_fixture[3]
    service = CheckpointPatchService(
        WorkspaceService(store.catalog), patch_fixture[4], store
    )
    yield service, spec
    await service.shutdown()


@pytest.mark.asyncio
async def test_actual_fresh_approval_restore_drill_preserves_original_exact_bytes(
    durable_patch_service, patch_fixture
):
    """Apply then independently approve byte rollback with actual Git checkpoints and deny old-grant reuse on the new proposal."""
    service, spec = durable_patch_service
    _, source, raw, _, _, _ = patch_fixture
    value = await propose(service, spec, raw)
    assert source.read_bytes() == raw
    checkpoint = UUID(value["checkpoint_id"])
    first = approve_existing(service, spec, value)
    applied = await service.apply(
        spec.owner_id, spec.workspace_id, UUID(value["proposal_id"]), first
    )
    assert applied["receipt"]["applied"] is True
    changed = source.read_bytes()
    rollback = await service.rollback(
        spec.owner_id,
        spec.workspace_id,
        checkpoint,
        hashlib.sha256(changed).hexdigest(),
    )
    assert (
        rollback["restores_checkpoint_id"] == str(checkpoint)
        and rollback["replacement"].encode() == raw
    )
    assert source.read_bytes() == changed
    with pytest.raises(WorkspaceAccessError):
        await service.apply(
            spec.owner_id, spec.workspace_id, UUID(rollback["proposal_id"]), first
        )
    second = approve_existing(service, spec, rollback)
    assert second != first
    result = await service.apply(
        spec.owner_id, spec.workspace_id, UUID(rollback["proposal_id"]), second
    )
    assert result["receipt"]["applied"] is True and source.read_bytes() == raw
    assert (await service.checkpoint(spec.owner_id, spec.workspace_id, checkpoint))[
        "journal"
    ]["state"] == "applied"
    assert len(await service.checkpoints(spec.owner_id, spec.workspace_id)) == 2


@pytest.mark.parametrize("stage", ["capture", "intent", "finish"])
@pytest.mark.asyncio
async def test_checkpoint_journal_faults_cannot_misreport_actual_commit(
    durable_patch_service, patch_fixture, monkeypatch, stage
):
    """Inject private persistence failures before/after actual native commit and preserve source/grant/receipt truth."""
    service, spec = durable_patch_service
    _, source, raw, _, approvals, _ = patch_fixture
    store = service.checkpoint_store
    if stage == "capture":

        def fail_capture(*arguments):
            """Fail private backup persistence before publishing pending review or writing any workspace bytes."""
            raise OSError("CONTROLLED-PRIVATE-CHECKPOINT")

        monkeypatch.setattr(store, "capture", fail_capture)
        with pytest.raises(OSError):
            await propose(service, spec, raw)
        assert (
            source.read_bytes() == raw
            and not approvals._records
            and not service.records
        )
        return
    value = await propose(service, spec, raw)
    approval = approve_existing(service, spec, value)
    original = store.transition

    def fail_transition(proposal, identifier, stop=None, *, finish=False):
        """Fail only the requested private journal boundary while retaining all actual Git/native edit behavior."""
        if finish == (stage == "finish"):
            raise OSError("CONTROLLED-PRIVATE-JOURNAL")
        return original(proposal, identifier, stop, finish=finish)

    monkeypatch.setattr(store, "transition", fail_transition)
    key = UUID(value["proposal_id"])
    if stage == "intent":
        with pytest.raises(OSError):
            await service.apply(spec.owner_id, spec.workspace_id, key, approval)
        assert (
            source.read_bytes() == raw
            and approvals.review(spec.owner_id, approval)["state"] == "approved"
        )
    else:
        result = await service.apply(spec.owner_id, spec.workspace_id, key, approval)
        assert (
            result["receipt"]["state"] == "applied_checkpoint_uncertain"
            and result["receipt"]["applied"] is True
        )
        assert (
            source.read_bytes() == b"approved replacement\n"
            and approvals.review(spec.owner_id, approval)["state"] == "consumed"
        )
    assert service.records[key].closed and not service.operations


@pytest.mark.parametrize("committed", [False, True])
@pytest.mark.asyncio
async def test_actual_cancel_and_shutdown_join_native_work_then_durable_terminal_record(
    durable_patch_service, patch_fixture, checkpoint_store, monkeypatch, committed
):
    """Cancel a paused actual native stage and reopen durable evidence only after shutdown joins worker, source pin and journal."""
    service, spec = durable_patch_service
    _, source, raw, _, _, _ = patch_fixture
    value = await propose(service, spec, raw)
    key = UUID(value["proposal_id"])
    approval = approve_existing(service, spec, value)
    entered, release, exited = threading.Event(), threading.Event(), threading.Event()
    original = NativePatch.apply

    def paused(self, store, identifier, stop):
        """Pause before or after a real native commit while retaining its owned source descriptor lifetime."""
        try:
            result = original(self, store, identifier, stop) if committed else None
            entered.set()
            assert release.wait(3)
            assert not self.closed
            return result if committed else original(self, store, identifier, stop)
        finally:
            exited.set()

    monkeypatch.setattr(NativePatch, "apply", paused)
    work = asyncio.create_task(
        service.apply(spec.owner_id, spec.workspace_id, key, approval)
    )
    assert await asyncio.to_thread(entered.wait, 3)
    work.cancel()
    shutdown = asyncio.create_task(service.shutdown())
    await asyncio.sleep(0)
    assert (
        not work.done()
        and not shutdown.done()
        and not service.checkpoint_store.storage.closing
    )
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await work
    await shutdown
    assert exited.is_set() and service.records[key].closed
    reopened = CheckpointStore(checkpoint_store[1], service.workspace.catalog)
    try:
        snapshot = reopened.read(
            spec.owner_id, spec.workspace_id, UUID(value["checkpoint_id"])
        )
        assert snapshot["journal"]["state"] == ("applied" if committed else "failed")
    finally:
        reopened.close()
    assert source.read_bytes() == (b"approved replacement\n" if committed else raw)


@pytest.mark.asyncio
async def test_capture_cancellation_joins_before_closing_source_pin(
    durable_patch_service, patch_fixture, monkeypatch
):
    """Retain a completed durable backup but never publish approval when cancellation interrupts native checkpoint-result transfer."""
    service, spec = durable_patch_service
    store = service.checkpoint_store
    entered, release = threading.Event(), threading.Event()
    original = store.capture
    proposals = []

    def paused(proposal, stop):
        """Finish a real durable source checkpoint then pause transfer while its native proposal root remains retained."""
        result = original(proposal, stop)
        proposals.append(proposal)
        entered.set()
        assert release.wait(3)
        assert not proposal.closed and not store.storage.closing
        return result

    monkeypatch.setattr(store, "capture", paused)
    work = asyncio.create_task(propose(service, spec, patch_fixture[2]))
    assert await asyncio.to_thread(entered.wait, 3)
    work.cancel()
    await asyncio.sleep(0)
    assert not work.done() and not proposals[0].closed
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await work
    assert (
        proposals[0].closed and not service.records and not service.approvals._records
    )
    assert len(store.list(spec.owner_id, spec.workspace_id)) == 1
    assert patch_fixture[1].read_bytes() == patch_fixture[2]


@pytest.mark.asyncio
async def test_native_pin_close_uncertainty_is_in_durable_journal(
    durable_patch_service, patch_fixture, monkeypatch
):
    """Close the native pin before terminal journal publication so its acknowledgement error survives process restart inspection."""
    service, spec = durable_patch_service
    value = await propose(service, spec, patch_fixture[2])
    key = UUID(value["proposal_id"])
    approval = approve_existing(service, spec, value)
    native = service.records[key]
    original = native.close

    def lost_ack():
        """Actually release the source root pin then inject only its cleanup acknowledgement failure."""
        original()
        raise OSError("CONTROLLED-PRIVATE-PIN-ACK")

    with monkeypatch.context() as scoped:
        scoped.setattr(native, "close", lost_ack)
        result = await service.apply(spec.owner_id, spec.workspace_id, key, approval)
    assert result["receipt"]["state"] == "applied_cleanup_uncertain"
    stored = await service.checkpoint(
        spec.owner_id, spec.workspace_id, UUID(value["checkpoint_id"])
    )
    assert stored["journal"]["receipt"] == result["receipt"]


@pytest.mark.parametrize("stage", ["intent", "finish"])
@pytest.mark.parametrize("boundary", ["file_fsync", "directory_fsync"])
@pytest.mark.asyncio
async def test_actual_journal_fsync_faults_preserve_source_and_acknowledgement_truth(
    durable_patch_service, patch_fixture, monkeypatch, stage, boundary
):
    """Fail actual private journal file or post-rename directory fsync and distinguish no-source-write from committed-source uncertainty."""
    from src.infrastructure import checkpoint_storage as module

    service, spec = durable_patch_service
    _, source, raw, _, approvals, _ = patch_fixture
    value = await propose(service, spec, raw)
    key = UUID(value["proposal_id"])
    approval = approve_existing(service, spec, value)
    original_transition = service.checkpoint_store.transition
    original_fsync, original_replace = module.os.fsync, module.os.replace
    active, renamed, injected = [False], [False], [False]

    def transition(proposal, identifier, stop=None, *, finish=False):
        """Select only the actual intent or terminal private persistence stage while retaining all native operations."""
        active[0] = finish == (stage == "finish")
        try:
            return original_transition(proposal, identifier, stop, finish=finish)
        finally:
            active[0] = False

    def replace(source_name, target_name, **options):
        """Perform the real rename and identify only private journal publication before its directory fsync."""
        result = original_replace(source_name, target_name, **options)
        if active[0] and target_name == "journal.json":
            renamed[0] = True
        return result

    def fsync(descriptor):
        """Inject one private journal fsync error while preserving all real source/Git/unrelated sync operations."""
        info = os.fstat(descriptor)
        match = (
            stat.S_ISREG(info.st_mode)
            and os.readlink(f"/proc/self/fd/{descriptor}")
            .rsplit("/", 1)[-1]
            .startswith(".journal-")
            if boundary == "file_fsync"
            else stat.S_ISDIR(info.st_mode) and renamed[0]
        )
        if active[0] and not injected[0] and match:
            injected[0] = True
            raise OSError("CONTROLLED-PRIVATE-JOURNAL-FSYNC")
        return original_fsync(descriptor)

    monkeypatch.setattr(service.checkpoint_store, "transition", transition)
    monkeypatch.setattr(module.os, "replace", replace)
    monkeypatch.setattr(module.os, "fsync", fsync)
    if stage == "intent":
        with pytest.raises(OSError):
            await service.apply(spec.owner_id, spec.workspace_id, key, approval)
        assert (
            source.read_bytes() == raw
            and approvals.review(spec.owner_id, approval)["state"] == "approved"
        )
    else:
        result = await service.apply(spec.owner_id, spec.workspace_id, key, approval)
        assert (
            result["receipt"]["state"] == "applied_checkpoint_uncertain"
            and result["receipt"]["applied"] is True
        )
        assert (
            source.read_bytes() == b"approved replacement\n"
            and approvals.review(spec.owner_id, approval)["state"] == "consumed"
        )
    assert injected[0] and service.records[key].closed
    snapshot = await service.checkpoint(
        spec.owner_id, spec.workspace_id, UUID(value["checkpoint_id"])
    )
    expected = (
        ("ready" if stage == "intent" else "applying")
        if boundary == "file_fsync"
        else ("applying" if stage == "intent" else "applied")
    )
    assert snapshot["journal"]["state"] == expected
    if boundary == "file_fsync":
        assert snapshot["recovery_warnings"] == ["unacknowledged_private_entry"]


@pytest.mark.asyncio
async def test_terminal_journal_cancellation_joins_before_private_store_shutdown(
    durable_patch_service, patch_fixture, monkeypatch
):
    """Lose terminal persistence acknowledgement after actual source commit and keep storage alive until its owned worker joins."""
    service, spec = durable_patch_service
    value = await propose(service, spec, patch_fixture[2])
    key = UUID(value["proposal_id"])
    approval = approve_existing(service, spec, value)
    entered, release = threading.Event(), threading.Event()
    original = service.checkpoint_store.transition

    def paused(proposal, identifier, stop=None, *, finish=False):
        """Persist actual terminal evidence then pause its acknowledgement while retaining the private-store lifetime."""
        result = original(proposal, identifier, stop, finish=finish)
        if finish:
            entered.set()
            assert release.wait(3)
            assert not service.checkpoint_store.storage.closing and proposal.closed
        return result

    monkeypatch.setattr(service.checkpoint_store, "transition", paused)
    work = asyncio.create_task(
        service.apply(spec.owner_id, spec.workspace_id, key, approval)
    )
    assert await asyncio.to_thread(entered.wait, 3)
    work.cancel()
    shutdown = asyncio.create_task(service.shutdown())
    await asyncio.sleep(0)
    assert (
        not work.done()
        and not shutdown.done()
        and not service.checkpoint_store.storage.closing
    )
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await work
    await shutdown
    assert patch_fixture[1].read_bytes() == b"approved replacement\n"
    assert service.records[key].receipt["applied"] is True
