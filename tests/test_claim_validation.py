"""Verify complete signed-source claim admission, exact citation identity, finite ownership and truthful unverified model outcomes."""

import asyncio
import json
import logging
from dataclasses import replace
from uuid import uuid4

import pytest
from test_claim_validation_policy import CLAIMS, completion, reply
from test_web_evidence import Source, service

from src.application.ports.source_reconciliation import SourceSpan
from src.application.services import claim_validation as module
from src.application.services import web_fetch_tasks
from src.application.services.claim_validation import ClaimValidationService
from src.application.services.claim_validation_policy import ClaimValidationError

logger = logging.getLogger(__name__)


class Core:
    """Return one explicit authored assessment without pretending that fixture classification is actual CORE inference."""

    def __init__(self):
        """Bind the complete controlled response and an initially empty metadata-only call list."""
        self.calls, self.result = [], completion(reply())

    async def complete(self, **options):
        """Record exact caller options and return the immutable controlled completion."""
        self.calls.append(options)
        return self.result


async def configured():
    """Construct inert dependencies and one authentic owner-bound fixture quote for complete three-claim assertions."""
    evidence, source, clock = service(
        Source(text="Atlas restore generation is G-17. Atlas upload quota is 128 MiB.")
    )
    core, owner = Core(), uuid4()
    validator = ClaimValidationService(
        evidence=evidence, inference=core, expected_model="fixture-core"
    )
    snapshot = (await evidence.read(owner, "https://example.org/source")).snapshot
    selections = (SourceSpan(snapshot, 0, len(snapshot.text)),)
    return validator, evidence, source, core, clock, owner, selections


@pytest.mark.asyncio
async def test_complete_signed_claims_preserve_integrity_unverified_labels_and_shared_service_lifetime(
    caplog,
):
    """Bind original quote/text rather than model-provided citations and keep semantic/date uncertainty explicit."""
    validator, evidence, source, core, _, owner, spans = await configured()
    caplog.set_level(logging.INFO)
    result = await validator.validate(owner, "Compare sources", CLAIMS, spans)
    assert tuple(row.text for row in result.claims) == CLAIMS
    assert [row.status for row in result.claims] == [
        "supported",
        "contradicted",
        "insufficient",
    ]
    assert (
        result.evidence[0].reference.quote == spans[0].snapshot.text
        and result.evidence[0].evidence_id == "E1"
    )
    assert (
        result.citation_integrity == "owner_signed_exact_span"
        and result.status == "assessed_unverified"
    )
    assert result.semantic_validation is False and result.verified_freshness is None
    assert len(core.calls) == result.model_attempts == validator.quota.total == 1
    options = core.calls[0]
    assert (
        options["profile"],
        options["preset"],
        options["temperature"],
        options["max_tokens"],
    ) == ("core", "fast", 0, 768)
    assert str(owner) not in json.dumps(options) and len(source.calls) == 1
    assert (
        str(owner) not in caplog.text
        and CLAIMS[0] not in caplog.text
        and spans[0].snapshot.text not in caplog.text
    )
    assert (
        "G-17" not in repr(result)
        and not validator.operations
        and not validator.admission.locked()
    )
    await validator.shutdown()
    assert not evidence.closing and evidence.cite(owner, spans[0].snapshot, 0, 1).quote
    await evidence.shutdown()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mutation",
    [
        "foreign",
        "tamper",
        "expired",
        "duplicate",
        "bad_span",
        "empty",
        "bad_owner",
        "bad_claim_tail",
    ],
)
async def test_complete_input_and_signed_span_failures_are_inert_before_inference(
    mutation,
):
    """Refuse every invalid batch/proof before model charge, including valid prefix followed by a forged source."""
    validator, evidence, source, core, clock, owner, spans = await configured()
    claims = CLAIMS
    if mutation == "foreign":
        owner = uuid4()
    elif mutation == "tamper":
        spans = spans + (
            replace(spans[0], snapshot=replace(spans[0].snapshot, title="FORGED")),
        )
    elif mutation == "expired":
        clock.value += 300
    elif mutation == "duplicate":
        spans = spans + spans
    elif mutation == "bad_span":
        spans = (replace(spans[0], end=99999),)
    elif mutation == "empty":
        spans = ()
    elif mutation == "bad_owner":
        owner = str(owner)
    else:
        claims = CLAIMS + ("bad\nclaim",)
    with pytest.raises(ClaimValidationError):
        await validator.validate(owner, "Compare sources", claims, spans)
    assert (
        not core.calls
        and validator.quota.total == 0
        and not validator.operations
        and not validator.admission.locked()
    )
    await evidence.shutdown()


@pytest.mark.asyncio
async def test_whole_prompt_expansion_limit_refuses_authenticated_quotes_without_clipping():
    """Reject complete escaped-source overflow before inference while retaining the authenticated quote bytes intact."""
    validator, evidence, source, core, _, owner, _ = await configured()
    source.text = "<" * 4096
    snapshot = (
        await evidence.read(owner, "https://example.org/large", use_cache=False)
    ).snapshot
    with pytest.raises(ClaimValidationError, match="claim_result_limit"):
        await validator.validate(
            owner,
            "Compare sources",
            CLAIMS,
            (SourceSpan(snapshot, 0, len(snapshot.text)),),
        )
    assert (
        not core.calls and validator.quota.total == 0 and snapshot.text == source.text
    )
    await evidence.shutdown()


@pytest.mark.asyncio
async def test_changed_or_expired_proof_during_model_work_cannot_publish(monkeypatch):
    """Reauthenticate signed input after completion instead of trusting stale preflight admission."""
    validator, evidence, source, core, clock, owner, spans = await configured()

    async def expire(**options):
        """Advance only the authored proof clock after one controlled inference attempt."""
        core.calls.append(options)
        clock.value += 300
        return core.result

    monkeypatch.setattr(core, "complete", expire)
    with pytest.raises(ClaimValidationError, match="claim_proof_invalid"):
        await validator.validate(owner, "Compare sources", CLAIMS, spans)
    assert len(core.calls) == validator.quota.total == 1 and not validator.operations
    await evidence.shutdown()


@pytest.mark.asyncio
async def test_fabricated_final_claim_citation_rejects_entire_assessment_without_retry():
    """Refuse a complete otherwise valid model response with one invented source ID at the tail."""
    validator, evidence, source, core, _, owner, spans = await configured()
    value = reply()
    value["claims"][-1]["evidence_ids"] = ["E99"]
    core.result = completion(value)
    with pytest.raises(ClaimValidationError, match="claim_assessment_invalid"):
        await validator.validate(owner, "Compare sources", CLAIMS, spans)
    assert len(core.calls) == validator.quota.total == 1 and len(source.calls) == 1
    await evidence.shutdown()


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["model", "total"])
async def test_suppressed_cancelled_deadline_cannot_accept_late_assessment(
    stage, monkeypatch
):
    """Retain timeout truth when the model consumes cancellation and returns a structurally valid late reply."""
    validator, evidence, source, core, _, owner, spans = await configured()

    async def suppress(**options):
        """Return the controlled reply only after the owning stage has cancelled it."""
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            return core.result

    monkeypatch.setattr(core, "complete", suppress)
    monkeypatch.setattr(
        module, "MODEL_SECONDS" if stage == "model" else "TOTAL_SECONDS", 0.01
    )
    with pytest.raises(
        ClaimValidationError,
        match="claim_model_timeout" if stage == "model" else "claim_timeout",
    ):
        await validator.validate(owner, "Compare sources", CLAIMS, spans)
    assert (
        validator.quota.total == 1
        and not validator.operations
        and not validator.admission.locked()
    )
    await evidence.shutdown()


@pytest.mark.asyncio
@pytest.mark.parametrize("trigger", ["caller", "shutdown"])
async def test_repeated_cancellation_and_shutdown_hold_admission_until_owned_cleanup(
    trigger, monkeypatch
):
    """Join outstanding model cleanup while refusing concurrent work and retaining shared evidence lifetime."""
    validator, evidence, source, core, _, owner, spans = await configured()
    entered, cleanup, release = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def held(**options):
        """Keep controlled native-resource retirement pending until explicitly released."""
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            cleanup.set()
            await release.wait()

    monkeypatch.setattr(core, "complete", held)
    task = asyncio.create_task(
        validator.validate(owner, "Compare sources", CLAIMS, spans)
    )
    await entered.wait()
    shutdown = (
        asyncio.create_task(validator.shutdown()) if trigger == "shutdown" else None
    )
    if shutdown is None:
        task.cancel()
    await cleanup.wait()
    task.cancel()
    with pytest.raises(
        ClaimValidationError, match="claim_closed" if shutdown else "claim_busy"
    ):
        await validator.validate(owner, "Compare sources", CLAIMS, spans)
    assert not task.done() and validator.admission.locked()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    if shutdown is not None:
        await shutdown
    assert (
        not validator.operations
        and not validator.admission.locked()
        and not evidence.closing
    )
    assert evidence.cite(owner, spans[0].snapshot, 0, 1).quote
    await evidence.shutdown()


@pytest.mark.asyncio
async def test_scheduler_failure_closes_unstarted_coroutine_and_retains_charge(
    monkeypatch,
):
    """Exercise the accepted spawn helper's actual task-creation fault instead of leaking or retrying an unstarted inference coroutine."""
    validator, evidence, source, core, _, owner, spans = await configured()
    pending = []

    def fail(coroutine):
        """Retain the unstarted coroutine only for post-failure closure inspection."""
        pending.append(coroutine)
        raise RuntimeError("PRIVATE-SCHEDULER-DETAIL")

    with monkeypatch.context() as patch:
        patch.setattr(web_fetch_tasks, "create_task", fail)
        with pytest.raises(ClaimValidationError, match="claim_internal"):
            await validator.validate(owner, "Compare sources", CLAIMS, spans)
    assert pending[0].cr_frame is None and validator.quota.total == 1 and not core.calls
    assert not validator.operations and not validator.admission.locked()
    await evidence.shutdown()


@pytest.mark.asyncio
async def test_failed_inference_quota_is_not_refunded_or_bypassed_by_fresh_signed_quotes(
    monkeypatch,
):
    """Refuse the fifth owner attempt after four failures without retrying or resetting counters through source acquisition."""
    validator, evidence, source, core, _, owner, spans = await configured()

    async def fail(**options):
        """Record a controlled failure while ensuring its private message is not a public error."""
        core.calls.append(options)
        raise RuntimeError("PRIVATE-MODEL-DETAIL")

    monkeypatch.setattr(core, "complete", fail)
    for _ in range(4):
        with pytest.raises(ClaimValidationError, match="claim_model_failed"):
            await validator.validate(owner, "Compare sources", CLAIMS, spans)
    with pytest.raises(ClaimValidationError, match="claim_rate_limited"):
        await validator.validate(owner, "Compare sources", CLAIMS, spans)
    assert (
        len(core.calls) == validator.quota.total == 4
        and not validator.operations
        and not validator.admission.locked()
    )
    await evidence.shutdown()


@pytest.mark.asyncio
async def test_shared_source_closure_during_model_work_prevents_publication_and_further_admission(
    monkeypatch,
):
    """Poison admission when signed source service lifetime becomes uncertain before model publication."""
    validator, evidence, source, core, _, owner, spans = await configured()

    async def close_source(**options):
        """Return a valid authored completion after closing its shared proof authority."""
        await evidence.shutdown()
        return core.result

    monkeypatch.setattr(core, "complete", close_source)
    with pytest.raises(ClaimValidationError, match="claim_cleanup_uncertain"):
        await validator.validate(owner, "Compare sources", CLAIMS, spans)
    assert (
        validator.closing
        and not validator.operations
        and not validator.admission.locked()
    )
    with pytest.raises(ClaimValidationError, match="claim_closed"):
        await validator.validate(owner, "Compare sources", CLAIMS, spans)


@pytest.mark.asyncio
async def test_cancelled_shared_source_uncertainty_poison_is_retained_after_join(
    monkeypatch,
):
    """Preserve closed-source admission when a cancelled model call reports shared evidence lifetime uncertainty."""
    validator, evidence, source, core, _, owner, spans = await configured()
    entered = asyncio.Event()

    async def close_on_cancel(**options):
        """Close the shared proof authority only after caller cancellation reaches the controlled model port."""
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            await evidence.shutdown()

    monkeypatch.setattr(core, "complete", close_on_cancel)
    task = asyncio.create_task(
        validator.validate(owner, "Compare sources", CLAIMS, spans)
    )
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert (
        validator.closing
        and not validator.operations
        and not validator.admission.locked()
    )
    with pytest.raises(ClaimValidationError, match="claim_closed"):
        await validator.validate(owner, "Compare sources", CLAIMS, spans)


@pytest.mark.asyncio
@pytest.mark.parametrize("dependency", ["evidence", "inference", "closed"])
async def test_missing_or_closed_dependencies_do_not_charge_or_acquire_resources(
    dependency,
):
    """Refuse unavailable shared boundaries before model requests, counters or new source work."""
    validator, evidence, source, core, _, owner, spans = await configured()
    if dependency == "closed":
        await evidence.shutdown()
    else:
        setattr(validator, dependency, None)
    with pytest.raises(
        ClaimValidationError,
        match="claim_closed" if dependency == "closed" else "claim_unavailable",
    ):
        await validator.validate(owner, "Compare sources", CLAIMS, spans)
    assert not core.calls and validator.quota.total == 0 and not validator.operations
    await evidence.shutdown()
