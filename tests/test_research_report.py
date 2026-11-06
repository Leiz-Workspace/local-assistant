"""Exercise report generation through accepted claim validation, owner-bound receipts and nested cancellation without actual model/source HTTP."""

import asyncio
import hashlib
import logging
from dataclasses import replace
from uuid import uuid4

import pytest
from test_claim_validation import Core
from test_claim_validation_policy import CLAIMS
from test_web_evidence import Source, service

from src.application.ports.source_reconciliation import SourceSpan
from src.application.services import research_report as module
from src.application.services import web_fetch_tasks
from src.application.services.research_report import ResearchReportService
from src.application.services.research_report_policy import (
    ResearchReportError,
    render_markdown,
)

logger = logging.getLogger(__name__)


async def configured():
    """Bind inert report dependencies and an authentic fixture span without production model or public network calls."""
    evidence, source, clock = service(
        Source(text="Atlas restore generation is G-17. Atlas upload quota is 128 MiB.")
    )
    core, owner = Core(), uuid4()
    reports = ResearchReportService(
        evidence=evidence, inference=core, expected_model="fixture-core"
    )
    snapshot = (await evidence.read(owner, "https://example.org/source")).snapshot
    return (
        reports,
        evidence,
        source,
        core,
        clock,
        owner,
        (SourceSpan(snapshot, 0, len(snapshot.text)),),
    )


@pytest.mark.asyncio
async def test_complete_report_uses_one_assessment_no_fetch_and_receipt_preserves_shared_lifetime(
    caplog,
):
    """Verify complete reproducible report bytes and owner receipt without introducing report-drafting inference or persistent source data."""
    reports, evidence, source, core, _, owner, spans = await configured()
    caplog.set_level(logging.INFO)
    report = await reports.generate(owner, "Compare sources", CLAIMS, spans)
    assert report.markdown == render_markdown(report.assessment)
    assert (
        report.markdown_sha256 == hashlib.sha256(report.markdown.encode()).hexdigest()
    )
    assert (
        reports.verify(owner, report) is report
        and report.citation_deadline == spans[0].snapshot.citation_deadline
    )
    assert (
        len(core.calls) == reports.validator.quota.total == 1 and len(source.calls) == 1
    )
    assert (
        not reports.operations
        and not reports.validator.operations
        and not reports.admission.locked()
    )
    assert report.semantic_validation is False and report.verified_freshness is None
    assert (
        str(owner) not in report.markdown
        and str(owner) not in caplog.text
        and CLAIMS[0] not in caplog.text
        and report.proof not in caplog.text
    )
    assert "G-17" not in repr(report)
    await reports.shutdown()
    assert (
        reports.proof_key == b"" and reports.validator.closing and not evidence.closing
    )
    with pytest.raises(ResearchReportError, match="report_closed"):
        reports.verify(owner, report)
    assert evidence.cite(owner, spans[0].snapshot, 0, 1).quote
    await evidence.shutdown()


@pytest.mark.parametrize(
    "mutation",
    [
        "foreign",
        "markdown",
        "markdown_hash",
        "assessment_text",
        "owner",
        "deadline",
        "proof",
        "schema",
        "semantic",
        "huge",
    ],
)
@pytest.mark.asyncio
async def test_changed_foreign_or_oversized_receipts_cannot_authorize_report_reuse(
    mutation,
):
    """Authenticate every complete report field and original owner rather than trusting a matching Markdown hash or dataclass type."""
    reports, evidence, source, core, clock, owner, spans = await configured()
    report = await reports.generate(owner, "Compare sources", CLAIMS, spans)
    if mutation == "foreign":
        owner = uuid4()
    elif mutation == "markdown":
        report = replace(report, markdown=report.markdown + "FORGED")
    elif mutation == "markdown_hash":
        report = replace(report, markdown_sha256="0" * 64)
    elif mutation == "assessment_text":
        report = replace(
            report,
            assessment=replace(
                report.assessment,
                claims=(
                    replace(report.assessment.claims[0], text="FORGED"),
                    *report.assessment.claims[1:],
                ),
            ),
        )
    elif mutation == "owner":
        report = replace(report, owner_id=uuid4())
    elif mutation == "deadline":
        report = replace(report, citation_deadline=report.citation_deadline + 1)
    elif mutation == "proof":
        report = replace(report, proof="0" * 64)
    elif mutation == "schema":
        report = replace(report, schema_version="FORGED")
    elif mutation == "semantic":
        report = replace(report, semantic_validation=True)
    else:
        report = replace(report, markdown="x" * 262145)
    with pytest.raises(ResearchReportError, match="report_proof_invalid"):
        reports.verify(owner, report)
    assert len(core.calls) == 1 and len(source.calls) == 1
    await reports.shutdown()
    await evidence.shutdown()


@pytest.mark.asyncio
async def test_cross_instance_expired_and_shared_source_closed_receipts_are_refused():
    """Keep process/key/source lifetime boundaries even when the same owner and valid original report bytes are supplied."""
    reports, evidence, source, core, clock, owner, spans = await configured()
    report = await reports.generate(owner, "Compare sources", CLAIMS, spans)
    other = ResearchReportService(
        evidence=evidence, inference=core, expected_model="fixture-core"
    )
    with pytest.raises(ResearchReportError, match="report_proof_invalid"):
        other.verify(owner, report)
    await other.shutdown()
    clock.value += 300
    with pytest.raises(ResearchReportError, match="report_proof_invalid"):
        reports.verify(owner, report)
    assert not reports.closing
    await evidence.shutdown()
    with pytest.raises(ResearchReportError, match="report_closed"):
        reports.verify(owner, report)
    await reports.shutdown()


@pytest.mark.asyncio
async def test_reassessment_cannot_extend_the_original_source_proof_deadline():
    """Retain the minimum source deadline instead of minting another300 seconds on old excerpts."""
    reports, evidence, source, core, clock, owner, spans = await configured()
    first = await reports.generate(owner, "Compare sources", CLAIMS, spans)
    clock.value += 200
    second = await reports.generate(owner, "Compare sources", CLAIMS, spans)
    assert first.citation_deadline == second.citation_deadline == 400
    assert len(core.calls) == 2 and len(source.calls) == 1
    await reports.shutdown()
    await evidence.shutdown()


@pytest.mark.parametrize("clock_value", [99, float("nan")])
@pytest.mark.asyncio
async def test_invalid_shared_monotonic_clock_poison_cannot_extend_report_receipt(
    clock_value,
):
    """Refuse backwards/nonfinite source clocks and close future report admission rather than making stale receipts reusable."""
    reports, evidence, source, core, clock, owner, spans = await configured()
    report = await reports.generate(owner, "Compare sources", CLAIMS, spans)
    clock.value = clock_value
    with pytest.raises(ResearchReportError, match="report_proof_invalid"):
        reports.verify(owner, report)
    assert reports.closing and evidence.closing
    await reports.shutdown()
    await evidence.shutdown()


@pytest.mark.asyncio
async def test_forged_returned_assessment_cannot_bind_changed_claim_or_source_to_original_input(
    monkeypatch,
):
    """Validate an internal boundary result before issuing a report receipt even when a frozen returned dataclass has been altered."""
    reports, evidence, source, core, _, owner, spans = await configured()
    original = reports.validator.validate

    async def forge(*args):
        """Return a controlled altered assessment after the genuine fixture model boundary completes."""
        value = await original(*args)
        return replace(
            value, claims=(replace(value.claims[0], text="FORGED"), *value.claims[1:])
        )

    monkeypatch.setattr(reports.validator, "validate", forge)
    with pytest.raises(ResearchReportError, match="report_proof_invalid"):
        await reports.generate(owner, "Compare sources", CLAIMS, spans)
    assert len(core.calls) == 1 and not reports.operations
    await reports.shutdown()
    await evidence.shutdown()


@pytest.mark.asyncio
async def test_proof_expiry_during_rendering_refuses_publication_after_valid_model_work(
    monkeypatch,
):
    """Recheck original quotes after rendering rather than issuing a receipt from an expired preflight."""
    reports, evidence, source, core, clock, owner, spans = await configured()
    original = module.render_markdown

    def expire(value):
        """Advance only the authored source clock after deterministic report rendering."""
        result = original(value)
        clock.value += 300
        return result

    monkeypatch.setattr(module, "render_markdown", expire)
    with pytest.raises(ResearchReportError, match="report_proof_invalid"):
        await reports.generate(owner, "Compare sources", CLAIMS, spans)
    assert len(core.calls) == 1 and not reports.operations
    await reports.shutdown()
    await evidence.shutdown()


@pytest.mark.parametrize("fail_on", [1, 2])
@pytest.mark.asyncio
async def test_outer_and_inner_task_dispatch_failures_close_coroutines_with_accurate_charges(
    fail_on, monkeypatch
):
    """Close unstarted outer/assessment work while charging only an actually admitted assessment attempt."""
    reports, evidence, source, core, _, owner, spans = await configured()
    actual, pending = web_fetch_tasks.create_task, []

    def dispatch(coroutine):
        """Inject one controlled scheduling failure at a specific ownership transfer."""
        pending.append(coroutine)
        if len(pending) == fail_on:
            raise RuntimeError("PRIVATE-SCHEDULER")
        return actual(coroutine)

    monkeypatch.setattr(web_fetch_tasks, "create_task", dispatch)
    with pytest.raises(
        ResearchReportError,
        match="report_internal" if fail_on == 1 else "report_assessment_failed",
    ):
        await reports.generate(owner, "Compare sources", CLAIMS, spans)
    assert (
        pending[-1].cr_frame is None
        and reports.validator.quota.total == fail_on - 1
        and not core.calls
    )
    assert (
        not reports.operations
        and not reports.validator.operations
        and not reports.admission.locked()
    )
    await reports.shutdown()
    await evidence.shutdown()


@pytest.mark.parametrize("trigger", ["caller", "shutdown"])
@pytest.mark.asyncio
async def test_nested_cancel_and_shutdown_join_model_retirement_before_report_admission_releases(
    trigger, monkeypatch
):
    """Retain both ownership layers through repeated cancellation without revoking shared evidence or releasing busy admission early."""
    reports, evidence, source, core, _, owner, spans = await configured()
    entered, cleanup, release = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def held(**options):
        """Hold the controlled model resource until cancellation cleanup is explicitly acknowledged."""
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            cleanup.set()
            await release.wait()

    monkeypatch.setattr(core, "complete", held)
    task = asyncio.create_task(
        reports.generate(owner, "Compare sources", CLAIMS, spans)
    )
    await entered.wait()
    closing = asyncio.create_task(reports.shutdown()) if trigger == "shutdown" else None
    if closing is None:
        task.cancel()
    await cleanup.wait()
    task.cancel()
    with pytest.raises(
        ResearchReportError, match="report_closed" if closing else "report_busy"
    ):
        await reports.generate(owner, "Compare sources", CLAIMS, spans)
    assert (
        not task.done()
        and reports.admission.locked()
        and reports.validator.admission.locked()
    )
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    if closing is not None:
        await closing
    assert (
        not reports.operations
        and not reports.validator.operations
        and not evidence.closing
    )
    await reports.shutdown()
    await evidence.shutdown()


@pytest.mark.asyncio
async def test_report_total_deadline_refuses_cancel_suppressing_nested_model_reply(
    monkeypatch,
):
    """Propagate nested cleanup to the outer report deadline without publishing a late otherwise valid assessment."""
    reports, evidence, source, core, _, owner, spans = await configured()

    async def suppress(**options):
        """Return a controlled reply only after outer cancellation reaches the model resource."""
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            return core.result

    monkeypatch.setattr(core, "complete", suppress)
    monkeypatch.setattr(module, "TOTAL_SECONDS", 0.01)
    with pytest.raises(ResearchReportError, match="report_timeout"):
        await reports.generate(owner, "Compare sources", CLAIMS, spans)
    assert (
        reports.validator.quota.total == 1
        and not reports.operations
        and not reports.validator.operations
    )
    await reports.shutdown()
    await evidence.shutdown()


@pytest.mark.asyncio
async def test_report_quota_reuses_no_refund_model_counter_without_additional_drafting_call():
    """Refuse owner attempt five without resetting quota or adding another model/HTTP call for report prose."""
    reports, evidence, source, core, _, owner, spans = await configured()
    for _ in range(4):
        await reports.generate(owner, "Compare sources", CLAIMS, spans)
    with pytest.raises(ResearchReportError, match="report_rate_limited"):
        await reports.generate(owner, "Compare sources", CLAIMS, spans)
    assert (
        len(core.calls) == reports.validator.quota.total == 4 and len(source.calls) == 1
    )
    assert not reports.operations and not reports.admission.locked()
    await reports.shutdown()
    await evidence.shutdown()


@pytest.mark.parametrize(
    "mutation",
    ["owner", "claim_tail", "foreign_span", "expired", "missing_inference", "closed"],
)
@pytest.mark.asyncio
async def test_invalid_complete_report_input_remains_inert_before_any_assessment_attempt(
    mutation,
):
    """Refuse bad input/dependency state without model charge, extra source acquisition or issued report receipts."""
    reports, evidence, source, core, clock, owner, spans = await configured()
    claims = CLAIMS
    if mutation == "owner":
        owner = str(owner)
    elif mutation == "claim_tail":
        claims = CLAIMS + ("bad\nclaim",)
    elif mutation == "foreign_span":
        owner = uuid4()
    elif mutation == "expired":
        clock.value += 300
    elif mutation == "missing_inference":
        reports.validator.inference = None
    else:
        await evidence.shutdown()
    with pytest.raises(ResearchReportError):
        await reports.generate(owner, "Compare sources", claims, spans)
    assert (
        not core.calls and reports.validator.quota.total == 0 and len(source.calls) == 1
    )
    assert not reports.operations and not reports.admission.locked()
    await reports.shutdown()
    await evidence.shutdown()


@pytest.mark.parametrize("trigger", ["completion", "cancellation"])
@pytest.mark.asyncio
async def test_shared_source_closure_poison_survives_nested_model_cleanup(
    trigger, monkeypatch
):
    """Close report admission when shared source uncertainty appears during normal or cancelled nested assessment work."""
    reports, evidence, source, core, _, owner, spans = await configured()
    entered = asyncio.Event()

    async def close_source(**options):
        """Close the shared proof authority from a controlled model dependency before returning or acknowledging cancellation."""
        entered.set()
        if trigger == "completion":
            await evidence.shutdown()
            return core.result
        try:
            await asyncio.Event().wait()
        finally:
            await evidence.shutdown()

    monkeypatch.setattr(core, "complete", close_source)
    task = asyncio.create_task(
        reports.generate(owner, "Compare sources", CLAIMS, spans)
    )
    await entered.wait()
    if trigger == "cancellation":
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    else:
        with pytest.raises(ResearchReportError, match="report_cleanup_uncertain"):
            await task
    assert (
        reports.closing and not reports.operations and not reports.validator.operations
    )
    with pytest.raises(ResearchReportError, match="report_closed"):
        await reports.generate(owner, "Compare sources", CLAIMS, spans)
    await reports.shutdown()


@pytest.mark.asyncio
async def test_all_insufficient_claims_remain_visible_without_invented_supported_findings():
    """Generate an honest report when every explicit claim lacks support while preserving all original unknowns and sources."""
    import json

    from test_claim_validation_policy import completion, reply

    reports, evidence, source, core, _, owner, spans = await configured()
    value = reply()
    for row in value["claims"]:
        row.update(
            status="insufficient",
            evidence_ids=[],
            reason="Required information is not provided.",
        )
    core.result = completion(json.dumps(value))
    report = await reports.generate(owner, "Compare sources", CLAIMS, spans)
    assert all(
        row.status == "insufficient" and not row.evidence_ids
        for row in report.assessment.claims
    )
    assert report.markdown.count("None in this assessment.") == 2
    assert report.markdown.count("Evidence: none assigned") == 3
    assert all(text in report.markdown for text in CLAIMS)
    assert reports.verify(owner, report) is report and len(core.calls) == 1
    await reports.shutdown()
    await evidence.shutdown()
