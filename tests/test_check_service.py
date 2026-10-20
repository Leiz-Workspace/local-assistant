"""Verify actual async check approval/run/history/expiry/drain ownership without production roots or recovered grants."""

from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from test_check_jobs import job_store as job_store

from apps.api.services.checks import CheckService
from src.application.services.approvals import ApprovalStore
from src.application.services.workspace_policy import WorkspaceAccessError


@pytest_asyncio.fixture
async def check_service(job_store):
    """Bind only existing disposable native job-store fixtures and real process-local approvals to the async service."""
    store, sources, _, _, _ = job_store
    approvals = ApprovalStore(store.catalog)
    workspace = SimpleNamespace(catalog=store.catalog, closing=False)
    service = CheckService(workspace, approvals, store)
    try:
        yield service, sources
    finally:
        await service.shutdown()
        approvals.close()


async def proposal(check_service):
    """Propose only exact already described disposable sources without approving or executing a check."""
    service, sources = check_service
    values = [
        dict(path=item.path, expected_sha256=item.sha256) for item in sources.receipts
    ]
    return await service.propose(sources.owner, sources.workspace, "ruff_check", values)


def approve(service, owner, identifier):
    """Approve only the concrete synthetic fixture request using its actual owner scope and fresh nonce."""
    value = service.approvals.review(owner, identifier)
    service.approvals.decide(
        owner, identifier, "approve", value["scope_digest"], value["review_nonce"]
    )


@pytest.mark.asyncio
async def test_actual_service_requires_fresh_approval_then_returns_known_historical_observation(
    check_service,
):
    """Propose and run actual pinned Ruff only after explicit fixture approval, retaining non-quality history and denying replay."""
    service, sources = check_service
    value = await proposal(check_service)
    identifier, request = UUID(value["job_id"]), UUID(value["approval_id"])
    assert value["live_proposal"] and value["observation"] is None
    with pytest.raises(WorkspaceAccessError):
        await service.run(sources.owner, sources.workspace, identifier, request)
    approve(service, sources.owner, request)
    result = await service.run(sources.owner, sources.workspace, identifier, request)
    assert result["state"] == "observed" and result["observation"]["exit_code"] == 0
    assert (
        not result["observation"]["quality_evaluated"] and not result["live_proposal"]
    )
    with pytest.raises(WorkspaceAccessError):
        await service.run(sources.owner, sources.workspace, identifier, request)
    result["observation"]["policy"]["network"] = True
    assert not (await service.read(sources.owner, sources.workspace, identifier))[
        "observation"
    ]["policy"]["network"]
    await service.shutdown()


@pytest.mark.asyncio
async def test_foreign_status_and_cancel_cannot_expire_or_close_a_pending_source(
    check_service,
):
    """Authorize lookup before pending-state/clock cleanup so another principal cannot affect the owner's proposal."""
    service, sources = check_service
    value = await proposal(check_service)
    identifier = UUID(value["job_id"])
    live = service.records[identifier]
    for method in (service.read, service.cancel):
        with pytest.raises(WorkspaceAccessError) as caught:
            await method(uuid4(), sources.workspace, identifier)
        assert caught.value.status_code == 404
    assert live.state == "proposed" and live.sources is not None
    await service.shutdown()


@pytest.mark.asyncio
async def test_pending_expiry_and_cancel_release_pins_but_retain_durable_history(
    check_service,
):
    """Close expired/cancelled ephemeral source capabilities without deleting snapshots or consuming any pending grant."""
    service, sources = check_service
    first = await proposal(check_service)
    identifier = UUID(first["job_id"])
    service.records[identifier].expires = service.clock()
    expired = await service.read(sources.owner, sources.workspace, identifier)
    assert expired["state"] == "expired" and not expired["live_proposal"]
    second = await proposal(check_service)
    cancelled = await service.cancel(
        sources.owner, sources.workspace, UUID(second["job_id"])
    )
    assert cancelled["state"] == "cancelled" and cancelled["observation"] is None
    assert len(await service.list(sources.owner, sources.workspace)) == 2
    await service.shutdown()


@pytest.mark.asyncio
async def test_async_nonqueued_admission_rejects_overlapping_normal_work(check_service):
    """Retain one normal operation and reject concurrent request admission without queuing new private/native work."""
    service, sources = check_service
    async with service.operation():
        with pytest.raises(WorkspaceAccessError) as caught:
            await service.list(sources.owner, sources.workspace)
        assert caught.value.code == "checks_busy"
    await service.shutdown()
