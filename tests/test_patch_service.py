"""Exercise bounded owner-only patch ownership, exact expiry, native cancellation/commit ordering and joined shutdown."""

import asyncio
import hashlib
import threading
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from test_atomic_patch import patch_fixture as patch_fixture

from apps.api.services.patches import PatchService
from apps.api.services.workspaces import WorkspaceService
from src.application.services.workspace_policy import WorkspaceAccessError
from src.infrastructure.atomic_patch import NativePatch


@pytest_asyncio.fixture
async def patch_service(patch_fixture):
    """Bind a real temporary native catalog and close every service-owned retained root pin after each test."""
    _, _, _, spec, store, _ = patch_fixture
    service = PatchService(WorkspaceService(store.catalog), store)
    yield service, spec
    await service.shutdown()


async def propose(service, spec, raw, replacement="approved replacement\n"):
    """Create a complete real proposal using the explicitly known temporary source digest."""
    return await service.propose(
        spec.owner_id,
        spec.workspace_id,
        "src/main.py",
        hashlib.sha256(raw).hexdigest(),
        replacement,
    )


def approve_existing(service, spec, proposal):
    """Explicitly approve the exact already-linked synthetic review without creating another proposal or grant."""
    identifier = UUID(proposal["approval_id"])
    review = service.approvals.review(spec.owner_id, identifier)
    service.approvals.decide(
        spec.owner_id,
        identifier,
        "approve",
        review["scope_digest"],
        review["review_nonce"],
    )
    return identifier


@pytest.mark.asyncio
async def test_service_pending_then_actual_apply_and_historical_receipt(
    patch_service, patch_fixture
):
    """Leave pending source intact, apply exact approved bytes once and retain a queryable receipt after closing the native pin."""
    service, spec = patch_service
    root, source, raw, _, _, _ = patch_fixture
    value = await propose(service, spec, raw)
    key, approval = UUID(value["proposal_id"]), UUID(value["approval_id"])
    with pytest.raises(WorkspaceAccessError, match="patch_approval_required"):
        await service.apply(spec.owner_id, spec.workspace_id, key, approval)
    assert source.read_bytes() == raw and not list(root.rglob(".assistant-patch-*"))
    approve_existing(service, spec, value)
    result = await service.apply(spec.owner_id, spec.workspace_id, key, approval)
    assert (
        result["receipt"]["applied"] is True
        and source.read_text() == "approved replacement\n"
    )
    assert service.records[key].closed
    source.write_text("later independent edit")
    assert (await service.review(spec.owner_id, spec.workspace_id, key))[
        "receipt"
    ] == result["receipt"]
    with pytest.raises(WorkspaceAccessError):
        await service.apply(spec.owner_id, spec.workspace_id, key, approval)


@pytest.mark.parametrize("fault", ["owner", "workspace", "unknown", "typed_owner"])
@pytest.mark.asyncio
async def test_foreign_lookup_cannot_expire_or_close_pin(
    patch_service, patch_fixture, fault
):
    """Match unknown denial without performing expiry or descriptor cleanup on another owner's live proposal."""
    service, spec = patch_service
    value = await propose(service, spec, patch_fixture[2])
    key = UUID(value["proposal_id"])
    record = service.records[key]
    record.clock = lambda: record.expires
    owner = (
        uuid4()
        if fault == "owner"
        else str(spec.owner_id)
        if fault == "typed_owner"
        else spec.owner_id
    )
    workspace = uuid4() if fault == "workspace" else spec.workspace_id
    with pytest.raises(WorkspaceAccessError, match="patch_not_found"):
        await service.review(owner, workspace, uuid4() if fault == "unknown" else key)
    assert record.state == "proposed" and not record.closed
    assert (await service.review(spec.owner_id, spec.workspace_id, key))[
        "state"
    ] == "expired"
    assert record.closed


@pytest.mark.asyncio
async def test_bounded_capacity_and_expired_pin_retirement(
    patch_service, patch_fixture
):
    """Reject the seventeenth active pin, retire only closed records and keep all workspace bytes unchanged."""
    service, spec = patch_service
    for _ in range(16):
        await propose(service, spec, patch_fixture[2])
    with pytest.raises(WorkspaceAccessError, match="patch_capacity"):
        await propose(service, spec, patch_fixture[2])
    first = next(iter(service.records.values()))
    first.clock = lambda: first.expires
    await propose(service, spec, patch_fixture[2])
    assert (
        len(service.records) == 16
        and first.closed
        and first.identifier not in service.records
    )
    assert patch_fixture[1].read_bytes() == patch_fixture[2]


@pytest.mark.parametrize("committed", [False, True])
@pytest.mark.asyncio
async def test_native_cancellation_and_shutdown_join_before_pin_release(
    patch_service, patch_fixture, monkeypatch, committed
):
    """Control only a native stage boundary and prove cancelled/shutdown callers wait for real worker completion around commit."""
    service, spec = patch_service
    value = await propose(service, spec, patch_fixture[2])
    key = UUID(value["proposal_id"])
    approval = approve_existing(service, spec, value)
    record = service.records[key]
    entered, release, exited = threading.Event(), threading.Event(), threading.Event()
    original = NativePatch.apply

    def delayed(self, store, identifier, stop):
        """Pause a real owned worker immediately before or after actual commit without releasing its source pin."""
        try:
            result = original(self, store, identifier, stop) if committed else None
            entered.set()
            assert release.wait(3)
            assert not self.closed
            return result if committed else original(self, store, identifier, stop)
        finally:
            exited.set()

    monkeypatch.setattr(NativePatch, "apply", delayed)
    work = asyncio.create_task(
        service.apply(spec.owner_id, spec.workspace_id, key, approval)
    )
    assert await asyncio.to_thread(entered.wait, 3)
    work.cancel()
    drain = asyncio.create_task(service.shutdown())
    await asyncio.sleep(0)
    assert not work.done() and not drain.done() and not record.closed
    with pytest.raises(WorkspaceAccessError, match="patch_unavailable"):
        await service.review(spec.owner_id, spec.workspace_id, key)
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await work
    await drain
    assert (
        exited.is_set()
        and record.closed
        and not service.operations
        and not service.admission.locked()
    )
    assert patch_fixture[1].read_bytes() == (
        b"approved replacement\n" if committed else patch_fixture[2]
    )
    assert (record.receipt is not None) == committed
    if committed:
        assert record.receipt["applied"] is True


@pytest.mark.asyncio
async def test_cancelled_constructor_transfer_closes_result(
    patch_service, patch_fixture, monkeypatch
):
    """Join a delayed native constructor and close its result when cancellation prevents ownership transfer to the service."""
    from apps.api.services import patches as module

    service, spec = patch_service
    entered, release = threading.Event(), threading.Event()
    created = []

    def delayed(*arguments):
        """Capture a real source pin then delay its transfer until the cancellation boundary is under observation."""
        result = NativePatch(*arguments)
        created.append(result)
        entered.set()
        assert release.wait(3)
        return result

    monkeypatch.setattr(module, "NativePatch", delayed)
    work = asyncio.create_task(propose(service, spec, patch_fixture[2]))
    assert await asyncio.to_thread(entered.wait, 3)
    work.cancel()
    await asyncio.sleep(0)
    assert not created[0].closed and not work.done()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await work
    assert created[0].closed and not service.records and not service.approvals._records


@pytest.mark.asyncio
async def test_postcommit_pin_cleanup_fault_is_in_returned_receipt(
    patch_service, patch_fixture, monkeypatch
):
    """Return the updated authoritative uncertainty state when pin cleanup fails after a successful actual rename."""
    service, spec = patch_service
    value = await propose(service, spec, patch_fixture[2])
    key = UUID(value["proposal_id"])
    approval = approve_existing(service, spec, value)
    record = service.records[key]
    original = record.close

    def failed_ack():
        """Actually close the root pin then simulate lost cleanup acknowledgement."""
        original()
        raise OSError("CONTROLLED-PRIVATE-CLOSE")

    with monkeypatch.context() as scoped:
        scoped.setattr(record, "close", failed_ack)
        result = await service.apply(spec.owner_id, spec.workspace_id, key, approval)
    assert result["receipt"]["state"] == "applied_cleanup_uncertain"
    assert result["receipt"]["applied"] is True and record.closed


@pytest.mark.asyncio
async def test_nonqueued_admission_rejects_without_waiting_or_opening_pin(
    patch_service, patch_fixture
):
    """Deny overlapping operations immediately and leave native proposal/approval inventories untouched."""
    service, spec = patch_service
    async with service.operation():
        with pytest.raises(WorkspaceAccessError, match="patch_busy"):
            await propose(service, spec, patch_fixture[2])
    assert not service.records and not service.approvals._records


@pytest.mark.asyncio
async def test_apply_at_exact_proposal_expiry_never_writes(
    patch_service, patch_fixture
):
    """Close an owner-authorized idle proposal exactly at its monotonic deadline before applying its valid reviewed grant."""
    service, spec = patch_service
    value = await propose(service, spec, patch_fixture[2])
    key = UUID(value["proposal_id"])
    approval = approve_existing(service, spec, value)
    record = service.records[key]
    record.clock = lambda: record.expires
    with pytest.raises(WorkspaceAccessError):
        await service.apply(spec.owner_id, spec.workspace_id, key, approval)
    assert (
        record.closed
        and record.state == "expired"
        and patch_fixture[1].read_bytes() == patch_fixture[2]
    )


@pytest.mark.asyncio
async def test_shutdown_closes_remaining_pins_after_one_close_ack_error(
    patch_service, patch_fixture, monkeypatch
):
    """Continue actual pin cleanup after a single acknowledged-close error without leaving dependent records open."""
    service, spec = patch_service
    for _ in range(2):
        await propose(service, spec, patch_fixture[2])
    first, second = service.records.values()
    original = first.close

    def fail_ack():
        """Close one actual native root pin then inject its cleanup acknowledgement failure."""
        original()
        raise OSError("CONTROLLED-PRIVATE-SHUTDOWN-CLOSE")

    with monkeypatch.context() as scoped:
        scoped.setattr(first, "close", fail_ack)
        await service.shutdown()
    assert first.closed and second.closed and not service.operations
