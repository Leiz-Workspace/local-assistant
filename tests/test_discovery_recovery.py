"""Verify archived-query selection ownership, inert denial, budgets, joined cancellation and expired checkpoint refusal."""

import asyncio
import json
import logging
from dataclasses import replace
from datetime import timedelta
from uuid import uuid4

import pytest
from test_discovery_recovery_policy import GOAL, NOW, PINS, checkpoint, completion

import src.application.services.discovery_recovery as module
from src.application.services.discovery_recovery import DiscoveryRecoveryService
from src.application.services.discovery_recovery_policy import DiscoveryRecoveryError


class Core:
    """Observe controlled fixed-model calls without external inference or source/provider access."""

    def __init__(self):
        """Initialize one authored valid ID-only completion and an empty call ledger."""
        self.calls, self.result, self.closing = [], completion(), False

    async def complete(self, **options):
        """Return the unchanged authored result while recording the complete original host options."""
        self.calls.append(options)
        return self.result


def configured():
    """Compose one owner-bound real catalog and authored CORE with a deterministic current host clock."""
    catalog, core = checkpoint(), Core()
    return (
        DiscoveryRecoveryService(
            catalog,
            archive_sha256=PINS[0],
            corpus_sha256=PINS[1],
            inference=core,
            expected_model="fixture-core",
            utcnow=lambda: NOW,
        ),
        core,
        catalog.owner_id,
    )


@pytest.mark.asyncio
async def test_original_options_zero_provider_activity_and_metadata_only_logs(caplog):
    """Disclose historical provenance and issue only one bounded selection without leaking the goal or owner."""
    caplog.set_level(logging.INFO)
    service, core, owner = configured()
    result = await service.recover(owner, "Explicit PRIVATE-GOAL-CANARY")
    assert result.owner_id == owner and result.provider_requests == 0
    assert len(core.calls) == service.quota.total == 1
    assert {
        key: value for key, value in core.calls[0].items() if key != "messages"
    } == dict(profile="core", preset="fast", temperature=0, max_tokens=512)
    assert str(owner) not in json.dumps(core.calls) + caplog.text
    assert "PRIVATE-GOAL-CANARY" not in caplog.text + repr(result)
    assert not service.operations and not service.admission.locked()
    await service.shutdown()
    assert not core.closing


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kind",
    [
        "foreign",
        "invalid_owner",
        "bad_goal",
        "expired",
        "changed",
        "unavailable",
        "closed",
    ],
)
async def test_pre_admission_denials_have_no_model_or_quota_side_effects(kind):
    """Refuse bad ownership, state, clock and input before admitting or charging a backend call."""
    service, core, owner = configured()
    goal = GOAL
    if kind == "foreign":
        owner = uuid4()
    elif kind == "invalid_owner":
        owner = "forged"
    elif kind == "bad_goal":
        goal = "!brave override"
    elif kind == "expired":
        service.utcnow = lambda: NOW + timedelta(days=3)
    elif kind == "changed":
        service.checkpoint = replace(service.checkpoint, queries=())
    elif kind == "unavailable":
        service.inference = None
    elif kind == "closed":
        await service.shutdown()
    with pytest.raises(DiscoveryRecoveryError):
        await service.recover(owner, goal)
    assert not core.calls and service.quota.total == 0
    assert not service.operations and not service.admission.locked()


@pytest.mark.asyncio
async def test_failed_plan_charges_without_refund_and_owner_quota_denies_fifth_attempt():
    """Charge each actual selection once, preserve failed attempts and cap repeated owner work before dispatch."""
    service, core, owner = configured()
    core.result = completion("{}")
    for _ in range(4):
        with pytest.raises(DiscoveryRecoveryError, match="recovery_plan_invalid"):
            await service.recover(owner, GOAL)
    with pytest.raises(DiscoveryRecoveryError, match="recovery_rate_limited"):
        await service.recover(owner, GOAL)
    assert len(core.calls) == service.quota.total == 4
    assert not service.operations and not service.admission.locked()


@pytest.mark.asyncio
async def test_global_quota_is_shared_without_importing_another_owners_private_history():
    """Bound a trusted explicitly public corpus across independent owner imports using one host-owned quota."""
    service, core, owner = configured()
    for _ in range(4):
        catalog = checkpoint()
        sibling = DiscoveryRecoveryService(
            catalog,
            archive_sha256=PINS[0],
            corpus_sha256=PINS[1],
            inference=core,
            expected_model="fixture-core",
            quota=service.quota,
            utcnow=lambda: NOW,
        )
        for _ in range(4):
            await sibling.recover(catalog.owner_id, GOAL)
        await sibling.shutdown()
    with pytest.raises(DiscoveryRecoveryError, match="recovery_rate_limited"):
        await service.recover(owner, GOAL)
    assert len(core.calls) == service.quota.total == 16
    assert len(service.quota.owners) == 4


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "stage,suppress",
    [
        ("MODEL_SECONDS", False),
        ("MODEL_SECONDS", True),
        ("TOTAL_SECONDS", False),
        ("TOTAL_SECONDS", True),
    ],
)
async def test_deadlines_join_backend_and_reject_suppressed_late_results(
    stage, suppress, monkeypatch
):
    """Reject valid late output even when a dependency consumes the deadline cancellation."""
    service, core, owner = configured()
    cleaned = asyncio.Event()

    async def held(**options):
        """Hold an authored model result until the host deadline and acknowledge cleanup before returning."""
        core.calls.append(options)
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            if suppress:
                return core.result
            raise
        finally:
            cleaned.set()

    monkeypatch.setattr(core, "complete", held)
    monkeypatch.setattr(module, stage, 0.01)
    with pytest.raises(
        DiscoveryRecoveryError,
        match="recovery_model_timeout"
        if stage == "MODEL_SECONDS"
        else "recovery_timeout",
    ):
        await service.recover(owner, GOAL)
    assert cleaned.is_set() and len(core.calls) == service.quota.total == 1
    assert not service.operations and not service.admission.locked()


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["expiry", "integrity", "backend_error", "closing"])
async def test_checkpoint_revalidation_and_backend_poisoning_after_inference(
    kind, monkeypatch
):
    """Recheck complete bytes and host time after model work while preserving finite private error redaction."""
    service, core, owner = configured()

    async def changed(**options):
        """Inject only controlled post-admission state changes instead of real network or private source access."""
        core.calls.append(options)
        if kind == "expiry":
            service.utcnow = lambda: NOW + timedelta(days=3)
        elif kind == "integrity":
            service.checkpoint = replace(service.checkpoint, queries=())
        elif kind == "backend_error":
            raise RuntimeError("PRIVATE-ERROR-CANARY")
        elif kind == "closing":
            core.closing = True
        return core.result

    monkeypatch.setattr(core, "complete", changed)
    if kind == "closing":
        await service.recover(owner, GOAL)
        assert service.closing
        with pytest.raises(DiscoveryRecoveryError, match="recovery_closed"):
            await service.recover(owner, GOAL)
    else:
        with pytest.raises(DiscoveryRecoveryError) as error:
            await service.recover(owner, GOAL)
        assert "PRIVATE-ERROR-CANARY" not in str(error.value)
    assert service.quota.total == 1 and not service.operations


@pytest.mark.asyncio
async def test_repeated_cancellation_keeps_nonqueued_admission_until_cleanup_acknowledgment(
    monkeypatch,
):
    """Prevent repeat cancellation from releasing ownership before the nested backend has fully retired."""
    service, core, owner = configured()
    entered, cleanup, release = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def held(**options):
        """Hold a controlled backend cleanup acknowledgment independently from repeated caller cancellation."""
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            cleanup.set()
            await release.wait()

    monkeypatch.setattr(core, "complete", held)
    task = asyncio.create_task(service.recover(owner, GOAL))
    await entered.wait()
    task.cancel()
    await cleanup.wait()
    task.cancel()
    with pytest.raises(DiscoveryRecoveryError, match="recovery_busy"):
        await service.recover(owner, GOAL)
    assert not task.done() and service.quota.total == 1
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert not service.operations and not service.admission.locked()


@pytest.mark.asyncio
async def test_shutdown_joins_owned_backend_and_preserves_unrelated_task(monkeypatch):
    """Close admission and await nested cleanup while leaving other services and the shared CORE untouched."""
    service, core, owner = configured()
    entered, cleanup, release = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def held(**options):
        """Acknowledge model cancellation only after an explicit controlled release."""
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            cleanup.set()
            await release.wait()

    monkeypatch.setattr(core, "complete", held)
    active = asyncio.create_task(service.recover(owner, GOAL))
    unrelated = asyncio.create_task(asyncio.Event().wait())
    await entered.wait()
    closing = asyncio.create_task(service.shutdown())
    await cleanup.wait()
    assert service.closing and not closing.done() and not unrelated.done()
    with pytest.raises(DiscoveryRecoveryError, match="recovery_closed"):
        await service.recover(owner, GOAL)
    release.set()
    await closing
    assert (
        active.cancelled() and not service.operations and not service.admission.locked()
    )
    assert not core.closing and not unrelated.done()
    unrelated.cancel()
    with pytest.raises(asyncio.CancelledError):
        await unrelated


@pytest.mark.asyncio
async def test_swallowed_caller_cancel_never_publishes_late_plan(monkeypatch):
    """Keep caller cancellation terminal even when inference returns a valid authored result after consuming it."""
    service, core, owner = configured()
    entered = asyncio.Event()

    async def suppress(**options):
        """Return controlled late output after explicitly swallowing the nested task cancellation."""
        entered.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            return core.result

    monkeypatch.setattr(core, "complete", suppress)
    active = asyncio.create_task(service.recover(owner, GOAL))
    await entered.wait()
    active.cancel()
    with pytest.raises(asyncio.CancelledError):
        await active
    assert not service.operations and not service.admission.locked()
    logging.getLogger(__name__).info("archived_discovery_lifecycle_controls_verified")
