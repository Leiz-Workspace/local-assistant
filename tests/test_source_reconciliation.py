"""Exercise owner-signed primary lookup and comparison budgets, partial states, proof integrity and cancellation without live sources/models."""

import asyncio
import json
import logging
from dataclasses import replace
from uuid import uuid4

import pytest
from test_web_evidence import Source, observation, service

from src.application.ports.inference import CompletionResult
from src.application.ports.source_reconciliation import SourceSpan
from src.application.services import source_reconciliation as module
from src.application.services.source_reconciliation import SourceReconciliationService
from src.application.services.source_reconciliation_policy import SourceComparisonError

logger = logging.getLogger(__name__)


class Core:
    """Supply an explicitly authored comparison schema with exact observable options, no real model or network."""

    def __init__(self):
        """Bind empty calls and a controlled two-source contradiction without reading source content."""
        self.calls = []
        self.result = CompletionResult(
            json.dumps(
                dict(
                    agreements=[],
                    conflicts=[
                        dict(topic="Restore generation", evidence_ids=["E1", "E2"])
                    ],
                    unresolved=[],
                )
            ),
            "fixture-core",
            "fast",
            "stop",
        )

    async def complete(self, **options):
        """Return the original controlled completion without changing its caller-selected fixed configuration."""
        self.calls.append(options)
        return self.result


def configured():
    """Create inert owner-evidence/model fixtures and independent source/model quotas for policy-only execution tests."""
    evidence, source, clock = service(Source(text="Atlas2.4 requires G-17."))
    core = Core()
    facade = SourceReconciliationService(
        evidence=evidence, inference=core, expected_model="fixture-core"
    )
    return facade, evidence, source, core, clock


async def selections(evidence, source, owner):
    """Issue two distinct signed snapshots and complete caller-selected spans with conflicting authored facts."""
    first = (await evidence.read(owner, "https://example.org/a")).snapshot
    source.text = "Atlas2.4 requires G-18."
    second = (await evidence.read(owner, "https://example.org/b")).snapshot
    return (
        SourceSpan(first, 0, len(first.text)),
        SourceSpan(second, 0, len(second.text)),
    )


@pytest.mark.asyncio
async def test_fragment_duplicate_host_exclusion_and_complete_signed_source_identity():
    """Fetch a declared page once, preserve both original anchored URIs and exclude unrelated hosts without assigning trusted publisher status."""
    facade, evidence, source, core, _ = configured()
    owner = uuid4()
    urls = (
        "https://example.org/a#first",
        "https://example.org/a#second",
        "https://sub.example.org/a",
        "https://other.example/a",
    )
    result = await facade.lookup(owner, urls, ("example.org",))
    assert (
        result.status == "complete"
        and result.attempts == 1
        and len(result.snapshots) == 1
    )
    assert [row.status for row in result.candidates] == [
        "observed",
        "duplicate",
        "excluded_primary_policy",
        "excluded_primary_policy",
    ]
    assert [row.original_url for row in result.candidates] == list(urls)
    assert (
        result.candidates[0].fragment_removed
        and result.candidates[0].navigation_url == "https://example.org/a"
    )
    assert (
        result.candidates[0].snapshot_id
        == result.candidates[1].snapshot_id
        == result.snapshots[0].identifier
    )
    assert source.calls == [("https://example.org/a", "static")] and not core.calls
    assert (
        result.primary_designation == "caller_designated_unverified"
        and result.content_trust == "untrusted"
        and result.verified_freshness is None
    )
    assert facade.source_quota.total == 1 and facade.model_quota.total == 0
    await facade.shutdown()
    assert evidence.cite(owner, result.snapshots[0], 0, 5).quote == "Atlas"
    await evidence.shutdown()


@pytest.mark.asyncio
async def test_failed_task_dispatch_releases_admission_and_closes_pending_coroutine(
    monkeypatch,
):
    """Retain model charge without coroutine leaks when dispatch fails before dependency execution."""
    facade, evidence, source, core, _ = configured()
    owner = uuid4()
    spans = await selections(evidence, source, owner)
    pending = []

    def fail_dispatch(coroutine):
        """Raise a controlled scheduler failure while retaining the unstarted coroutine for lifecycle inspection."""
        pending.append(coroutine)
        raise RuntimeError("PRIVATE-SCHEDULER-DETAIL")

    monkeypatch.setattr(module, "spawn_owned", fail_dispatch)
    with pytest.raises(SourceComparisonError, match="source_internal"):
        await facade.reconcile(owner, "Compare sources", spans)
    assert pending[0].cr_frame is None
    assert facade.model_quota.total == 1 and not core.calls
    assert not facade.operations and not facade.admission.locked()
    await evidence.shutdown()


@pytest.mark.asyncio
async def test_active_shutdown_joins_facade_work_and_leaves_shared_evidence_usable(
    monkeypatch,
):
    """Drain owned work before shutdown returns while retaining shared source proofs for other callers."""
    facade, evidence, source, core, _ = configured()
    owner = uuid4()
    spans = await selections(evidence, source, owner)
    entered, cleanup, release = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def hold(**options):
        """Keep model cleanup pending until the test explicitly acknowledges resource retirement."""
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            cleanup.set()
            await release.wait()

    monkeypatch.setattr(core, "complete", hold)
    caller = asyncio.create_task(facade.reconcile(owner, "Compare sources", spans))
    await entered.wait()
    closing = asyncio.create_task(facade.shutdown())
    await cleanup.wait()
    assert not closing.done() and facade.admission.locked()
    release.set()
    await closing
    with pytest.raises(asyncio.CancelledError):
        await caller
    assert facade.closing and not evidence.closing and not facade.operations
    assert evidence.cite(owner, spans[0].snapshot, 0, 1).quote
    await evidence.shutdown()


@pytest.mark.asyncio
async def test_model_quota_cannot_be_reset_by_source_lookup_or_failed_inference(
    monkeypatch,
):
    """Charge unsuccessful model attempts and reject the fifth without opening the original inference port again."""
    facade, evidence, source, core, _ = configured()
    owner = uuid4()
    spans = await selections(evidence, source, owner)

    async def fail(**options):
        """Record one authored model failure without including dependency details in the public error."""
        core.calls.append(options)
        raise RuntimeError("PRIVATE-MODEL-DETAIL")

    monkeypatch.setattr(core, "complete", fail)
    for _ in range(4):
        with pytest.raises(SourceComparisonError, match="source_model_failed"):
            await facade.reconcile(owner, "Compare sources", spans)
    await facade.lookup(owner, ("https://example.org/c",), ("example.org",))
    with pytest.raises(SourceComparisonError, match="source_rate_limited"):
        await facade.reconcile(owner, "Compare sources", spans)
    assert len(core.calls) == facade.model_quota.total == 4
    assert facade.source_quota.total == 1 and not facade.operations
    await evidence.shutdown()


@pytest.mark.asyncio
async def test_invalid_complete_uri_tail_blocks_all_source_and_model_dispatch():
    """Reject the full list before a good prefix causes I/O, charging or creation of a source snapshot."""
    facade, evidence, source, core, _ = configured()
    with pytest.raises(SourceComparisonError, match="source_invalid"):
        await facade.lookup(
            uuid4(), ("https://example.org/a", "https://127.0.0.1/"), ("example.org",)
        )
    assert (
        not source.calls
        and not core.calls
        and facade.source_quota.total == 0
        and not facade.operations
    )
    await evidence.shutdown()


@pytest.mark.asyncio
async def test_limit_duplicate_failure_and_quota_states_are_all_retained_without_retry(
    monkeypatch,
):
    """Respect four distinct source attempts and never retry a failed duplicate URI while recording every candidate state."""
    facade, evidence, source, _, _ = configured()
    owner = uuid4()

    async def respond(url, mode):
        """Fail one authored source URI and return complete signed fixture data for all other declared pages."""
        source.calls.append((url, mode))
        if url.endswith("/b"):
            raise RuntimeError("PRIVATE-SOURCE-ERROR")
        return observation(url)

    monkeypatch.setattr(source, "read", respond)
    urls = tuple(
        "https://example.org/" + path for path in ["a", "b", "b#again", "c", "d", "e"]
    )
    result = await facade.lookup(owner, urls, ("example.org",))
    assert (
        result.status == "partial"
        and result.attempts == 4
        and len(result.snapshots) == 3
    )
    assert [row.status for row in result.candidates] == [
        "observed",
        "error",
        "duplicate_unavailable",
        "observed",
        "observed",
        "not_run_limit",
    ]
    assert len(source.calls) == 4 and facade.source_quota.total == 4
    later = await facade.lookup(
        owner, ("https://example.org/z", "https://example.org/y"), ("example.org",)
    )
    assert later.attempts == 0 and all(
        row.status == "not_run_quota" and not row.attempted for row in later.candidates
    )
    assert len(source.calls) == 4
    await evidence.shutdown()


@pytest.mark.asyncio
async def test_redirected_public_host_is_explicitly_unconfirmed_not_a_primary_alias(
    monkeypatch,
):
    """Retain actual final source provenance after a valid redirect without silently extending caller primary-host authority."""
    facade, evidence, source, _, _ = configured()
    owner = uuid4()

    async def redirected(url, mode):
        """Return a complete authored redirected source chain using no real network or public-peer claim."""
        from src.application.ports.web_evidence import EvidenceResource

        result = observation("https://other.example/final")
        page = replace(
            result.page, requested_url=url, redirects=((url, result.page.final_url),)
        )
        resources = (
            EvidenceResource(
                url,
                "Document",
                302,
                0,
                "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            ),
        ) + result.resources
        return replace(result, page=page, resources=resources)

    monkeypatch.setattr(source, "read", redirected)
    result = await facade.lookup(
        owner, ("https://example.org/a", "https://example.org/a#two"), ("example.org",)
    )
    assert (
        result.status == "partial"
        and result.attempts == 1
        and len(result.snapshots) == 1
    )
    assert [row.status for row in result.candidates] == [
        "unconfirmed_redirect_host",
        "duplicate_unconfirmed",
    ]
    assert result.snapshots[0].final_url == "https://other.example/final"
    await evidence.shutdown()


@pytest.mark.asyncio
async def test_actual_signed_excerpt_composition_preserves_conflict_and_shared_evidence_lifetime(
    caplog,
):
    """Publish source-group assessments with original exact quote/hash/time metadata, keeping owner data out of model/logs and truth flags false."""
    caplog.set_level(logging.INFO)
    facade, evidence, source, core, _ = configured()
    owner = uuid4()
    spans = await selections(evidence, source, owner)
    result = await facade.reconcile(owner, "PRIVATE-GOAL-CANARY <compare>", spans)
    assert (
        result.conflicts[0].evidence_ids == ("E1", "E2")
        and not result.agreements
        and not result.unresolved
    )
    assert (
        result.evidence[0].quote == spans[0].snapshot.text
        and result.evidence[1].quote == spans[1].snapshot.text
    )
    assert (
        result.content_trust == "untrusted"
        and result.semantic_validation is False
        and result.verified_freshness is None
    )
    assert (
        result.model_attempts == facade.model_quota.total == 1
        and facade.source_quota.total == 0
    )
    assert {
        key: value for key, value in core.calls[0].items() if key != "messages"
    } == dict(profile="core", preset="fast", temperature=0, max_tokens=768)
    assert (
        str(owner) not in json.dumps(core.calls)
        and "PRIVATE-GOAL-CANARY" not in caplog.text
        and spans[0].snapshot.text not in caplog.text
    )
    assert "PRIVATE-GOAL-CANARY" not in repr(result)
    await facade.shutdown()
    assert (
        not evidence.closing
        and evidence.cite(owner, spans[0].snapshot, 0, 5).quote == "Atlas"
    )
    await evidence.shutdown()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mutation",
    ["foreign", "changed", "expired", "duplicate", "one_snapshot", "invalid_index"],
)
async def test_all_proofs_validate_before_model_and_model_cannot_receive_forged_source(
    mutation,
):
    """Deny owner/proof/expiry/source-identity/span violations with zero inference/quota instead of dropping a bad excerpt tail."""
    facade, evidence, source, core, clock = configured()
    owner = uuid4()
    spans = await selections(evidence, source, owner)
    if mutation == "foreign":
        owner = uuid4()
    elif mutation == "changed":
        spans = (
            spans[0],
            replace(spans[1], snapshot=replace(spans[1].snapshot, title="Forged")),
        )
    elif mutation == "expired":
        clock.value += 300
    elif mutation == "duplicate":
        spans = (spans[0], spans[0])
    elif mutation == "one_snapshot":
        spans = (spans[0], SourceSpan(spans[0].snapshot, 1, 5))
    elif mutation == "invalid_index":
        spans = (spans[0], replace(spans[1], start=-1))
    with pytest.raises(SourceComparisonError, match="source_proof_invalid"):
        await facade.reconcile(owner, "Compare sources", spans)
    assert not core.calls and facade.model_quota.total == 0 and not facade.operations
    await evidence.shutdown()


@pytest.mark.asyncio
async def test_excerpt_expansion_limit_rejects_complete_input_without_clipping_before_model():
    """Refuse an overescaped exact excerpt pair even though each individual4096-byte quote is otherwise valid."""
    facade, evidence, source, core, _ = configured()
    owner = uuid4()
    source.text = "<" * 4096
    first = (
        await evidence.read(owner, "https://example.org/e", use_cache=False)
    ).snapshot
    second = (
        await evidence.read(owner, "https://example.org/f", use_cache=False)
    ).snapshot
    spans = (
        SourceSpan(first, 0, len(first.text)),
        SourceSpan(second, 0, len(second.text)),
    )
    with pytest.raises(SourceComparisonError, match="source_result_limit"):
        await facade.reconcile(owner, "Compare complete sources", spans)
    assert not core.calls and facade.model_quota.total == 0
    await evidence.shutdown()


@pytest.mark.asyncio
@pytest.mark.parametrize("trigger", ["deadline", "caller"])
async def test_cancelled_uncertain_source_poisons_future_facade_admission(
    trigger, monkeypatch
):
    """Keep unknown source cleanup fatal even when it is reported during timeout or caller cancellation."""
    facade, evidence, source, core, _ = configured()
    entered = asyncio.Event()

    async def uncertain(*args, **options):
        """Report dependency cleanup uncertainty from a cancelled source operation."""
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            evidence.closing = True

    monkeypatch.setattr(evidence, "read", uncertain)
    if trigger == "deadline":
        monkeypatch.setattr(module, "LOOKUP_SECONDS", 0.01)
    task = asyncio.create_task(
        facade.lookup(uuid4(), ("https://example.org/a",), ("example.org",))
    )
    await entered.wait()
    if trigger == "caller":
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    else:
        with pytest.raises(SourceComparisonError, match="source_cleanup_uncertain"):
            await task
    assert facade.closing and not facade.operations and not facade.admission.locked()
    with pytest.raises(SourceComparisonError, match="source_closed"):
        await facade.lookup(uuid4(), ("https://example.org/b",), ("example.org",))
    await evidence.shutdown()


@pytest.mark.asyncio
async def test_proof_expiring_during_actual_model_boundary_cannot_publish_assessment(
    monkeypatch,
):
    """Revalidate source proof after model completion so a valid preflight cannot authorize an expired published quote."""
    facade, evidence, source, core, clock = configured()
    owner = uuid4()
    spans = await selections(evidence, source, owner)

    async def expire(**options):
        """Return a controlled valid model group after advancing only the authored proof clock beyond its deadline."""
        core.calls.append(options)
        clock.value += 300
        return core.result

    monkeypatch.setattr(core, "complete", expire)
    with pytest.raises(SourceComparisonError, match="source_proof_invalid"):
        await facade.reconcile(owner, "Compare sources", spans)
    assert (
        len(core.calls) == 1 and facade.model_quota.total == 1 and not facade.operations
    )
    await evidence.shutdown()


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["lookup", "model"])
async def test_owned_stage_deadline_rejects_suppressed_cancelled_late_data(
    stage, monkeypatch
):
    """Keep timeout truth after dependencies swallow their cancellation instead of treating late source/model data as within budget."""
    facade, evidence, source, core, _ = configured()
    owner = uuid4()
    spans = await selections(evidence, source, owner)

    async def suppress(*args, **options):
        """Return late valid controlled source/model data only after the owning deadline has cancelled the call."""
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            if stage == "model":
                return core.result
            return type("AuthoredRead", (), dict(snapshot=spans[0].snapshot))()

    if stage == "model":
        monkeypatch.setattr(core, "complete", suppress)
        monkeypatch.setattr(module, "MODEL_SECONDS", 0.01)
        with pytest.raises(SourceComparisonError, match="source_model_timeout"):
            await facade.reconcile(owner, "Compare sources", spans)
    else:
        monkeypatch.setattr(evidence, "read", suppress)
        monkeypatch.setattr(module, "LOOKUP_SECONDS", 0.01)
        result = await facade.lookup(
            owner, ("https://example.org/a", "https://example.org/b"), ("example.org",)
        )
        assert (
            result.status == "no_primary_sources"
            and result.attempts == 1
            and [row.status for row in result.candidates]
            == ["error", "not_run_deadline"]
        )
    assert not facade.operations and not facade.admission.locked()
    await evidence.shutdown()


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["lookup", "model"])
async def test_repeated_cancellation_waits_for_owned_cleanup_before_releasing_admission(
    stage, monkeypatch
):
    """Retain a live owned cancellation boundary while refusing concurrent facade work and leaving shared resources alone."""
    facade, evidence, source, core, _ = configured()
    owner = uuid4()
    spans = await selections(evidence, source, owner)
    entered, cleanup, release = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def held(*args, **options):
        """Hold one controlled resource until cancellation cleanup is explicitly acknowledged."""
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            cleanup.set()
            await release.wait()

    monkeypatch.setattr(
        core if stage == "model" else evidence,
        "complete" if stage == "model" else "read",
        held,
    )
    pending = (
        facade.reconcile(owner, "Compare sources", spans)
        if stage == "model"
        else facade.lookup(owner, ("https://example.org/c",), ("example.org",))
    )
    task = asyncio.create_task(pending)
    await entered.wait()
    task.cancel()
    await cleanup.wait()
    task.cancel()
    with pytest.raises(SourceComparisonError, match="source_busy"):
        await facade.lookup(owner, ("https://example.org/z",), ("example.org",))
    assert not task.done()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert not facade.operations and not facade.admission.locked()
    await facade.shutdown()
    assert not evidence.closing
    await evidence.shutdown()


@pytest.mark.asyncio
async def test_source_cleanup_uncertainty_closes_facade_without_false_result(
    monkeypatch,
):
    """Stop further source/model admission when the shared source dependency reports that cleanup/state can no longer be trusted."""
    facade, evidence, source, core, _ = configured()

    async def uncertain(*args, **options):
        """Model a source dependency that marks itself closed before reporting uncertain cleanup."""
        evidence.closing = True
        raise RuntimeError("PRIVATE-CLEANUP-DETAIL")

    monkeypatch.setattr(evidence, "read", uncertain)
    with pytest.raises(SourceComparisonError, match="source_cleanup_uncertain"):
        await facade.lookup(uuid4(), ("https://example.org/a",), ("example.org",))
    assert (
        facade.closing
        and not core.calls
        and not facade.operations
        and not facade.admission.locked()
    )
    await evidence.shutdown()
