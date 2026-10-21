"""Verify issuer-bound export admission, complete artifact fields and joined cancellation using explicit nonnative byte fixtures."""

import asyncio
import json
import logging
from dataclasses import replace
from uuid import uuid4

import pytest
from test_claim_validation_policy import CLAIMS
from test_report_export_policy import authored_native
from test_research_report import configured as report_fixture

from src.application.services import report_export as module
from src.application.services import web_fetch_tasks
from src.application.services.report_export import ReportExportService
from src.application.services.report_export_policy import (
    ReportExportError,
    parse_native,
)

logger = logging.getLogger(__name__)


class AuthoredExporter:
    """Return explicit transport-only byte fixtures without claiming real DOCX/PDF structure, Office conversion or namespace execution."""

    def __init__(self):
        """Initialize inert fixture calls and a controlled dependency-lifetime flag."""
        self.calls, self.closing = [], False

    async def render(self, payload):
        """Record the explicit fixture request and construct protocol-only placeholder artifact values."""
        self.calls.append(payload)
        return parse_native(json.dumps(authored_native(payload)).encode(), payload, b"")


async def configured():
    """Create an authentic receipt-bearing fixture report and inert export facade without actual model/source/native work."""
    reports, evidence, source, core, clock, owner, spans = await report_fixture()
    report = await reports.generate(owner, "Compare sources", CLAIMS, spans)
    native = AuthoredExporter()
    exports = ReportExportService(reports=reports, exporter=native)
    return exports, native, reports, evidence, core, clock, owner, report


@pytest.mark.asyncio
async def test_one_complete_both_format_attempt_preserves_owner_source_hash_and_shared_lifetime(
    caplog,
):
    """Return only fixed source-bound artifact fields without another model call or shutting down shared report/evidence services."""
    exports, native, reports, evidence, core, _, owner, report = await configured()
    caplog.set_level(logging.INFO)
    result = await exports.export(owner, report)
    assert (
        result.owner_id == owner
        and result.source_markdown_sha256 == report.markdown_sha256
    )
    assert [row.format for row in result.artifacts] == ["docx", "pdf"] and all(
        row.source_markdown_sha256 == report.markdown_sha256 for row in result.artifacts
    )
    assert result.semantic_validation is False and result.verified_freshness is None
    assert len(native.calls) == exports.quota.total == 1 and len(core.calls) == 1
    assert (
        str(owner) not in caplog.text
        and CLAIMS[0] not in caplog.text
        and report.proof not in caplog.text
    )
    assert not exports.operations and not exports.admission.locked()
    await exports.shutdown()
    assert (
        not reports.closing
        and reports.verify(owner, report) is report
        and not evidence.closing
    )
    await reports.shutdown()
    await evidence.shutdown()


@pytest.mark.parametrize(
    "mutation",
    ["foreign", "changed", "expired", "owner_type", "missing_issuer", "missing_native"],
)
@pytest.mark.asyncio
async def test_invalid_owner_receipt_or_dependency_is_inert_before_native_admission(
    mutation,
):
    """Reject whole unauthorized export input before counters, native calls or model work."""
    exports, native, reports, evidence, core, clock, owner, report = await configured()
    if mutation == "foreign":
        owner = uuid4()
    elif mutation == "changed":
        report = replace(report, markdown=report.markdown + "FORGED")
    elif mutation == "expired":
        clock.value += 300
    elif mutation == "owner_type":
        owner = str(owner)
    elif mutation == "missing_issuer":
        exports.reports = None
    else:
        exports.exporter = None
    with pytest.raises(ReportExportError):
        await exports.export(owner, report)
    assert not native.calls and exports.quota.total == 0 and len(core.calls) == 1
    assert not exports.operations and not exports.admission.locked()
    await reports.shutdown()
    await evidence.shutdown()


@pytest.mark.asyncio
async def test_receipt_expiry_during_native_work_refuses_completed_artifact_publication(
    monkeypatch,
):
    """Reverify the original issuer receipt after native cleanup instead of exporting stale evidence on valid preflight alone."""
    exports, native, reports, evidence, core, clock, owner, report = await configured()
    original = native.render

    async def expire(payload):
        """Return controlled complete byte fixtures after advancing only the authored source-proof clock."""
        result = await original(payload)
        clock.value += 300
        return result

    monkeypatch.setattr(native, "render", expire)
    with pytest.raises(ReportExportError, match="export_proof_invalid"):
        await exports.export(owner, report)
    assert len(native.calls) == exports.quota.total == 1 and not exports.operations
    await reports.shutdown()
    await evidence.shutdown()


@pytest.mark.asyncio
async def test_changed_native_tail_hash_cannot_publish_either_artifact(monkeypatch):
    """Refuse a complete result with one altered artifact even if the first format is otherwise valid."""
    exports, native, reports, evidence, core, _, owner, report = await configured()
    original = native.render

    async def alter(payload):
        """Mutate only the tail artifact's declared hash after controlled protocol decoding."""
        result = await original(payload)
        return replace(
            result,
            artifacts=(
                result.artifacts[0],
                replace(result.artifacts[1], sha256="0" * 64),
            ),
        )

    monkeypatch.setattr(native, "render", alter)
    with pytest.raises(ReportExportError, match="export_native_failed"):
        await exports.export(owner, report)
    assert len(native.calls) == exports.quota.total == 1 and not exports.operations
    await reports.shutdown()
    await evidence.shutdown()


@pytest.mark.parametrize("trigger", ["caller", "shutdown"])
@pytest.mark.asyncio
async def test_repeated_cancel_and_shutdown_join_export_cleanup_before_releasing_admission(
    trigger, monkeypatch
):
    """Hold the export facade through native resource retirement without closing the shared report/evidence issuer."""
    exports, native, reports, evidence, core, _, owner, report = await configured()
    entered, cleanup, release = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def held(payload):
        """Retain a controlled resource until cancellation cleanup is explicitly acknowledged."""
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            cleanup.set()
            await release.wait()

    monkeypatch.setattr(native, "render", held)
    task = asyncio.create_task(exports.export(owner, report))
    await entered.wait()
    closing = asyncio.create_task(exports.shutdown()) if trigger == "shutdown" else None
    if closing is None:
        task.cancel()
    await cleanup.wait()
    task.cancel()
    with pytest.raises(
        ReportExportError, match="export_closed" if closing else "export_busy"
    ):
        await exports.export(owner, report)
    assert not task.done() and exports.admission.locked()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    if closing is not None:
        await closing
    assert (
        not exports.operations
        and not exports.admission.locked()
        and not reports.closing
        and reports.verify(owner, report)
    )
    await reports.shutdown()
    await evidence.shutdown()


@pytest.mark.asyncio
async def test_cancel_suppressing_export_dependency_cannot_publish_after_total_deadline(
    monkeypatch,
):
    """Retain deadline truth when the controlled native port returns a late structurally valid result."""
    exports, native, reports, evidence, core, _, owner, report = await configured()
    original = native.render

    async def suppress(payload):
        """Return the controlled byte fixtures only after the outer timer cancels native work."""
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            return await original(payload)

    monkeypatch.setattr(native, "render", suppress)
    monkeypatch.setattr(module, "TOTAL_SECONDS", 0.01)
    with pytest.raises(ReportExportError, match="export_timeout"):
        await exports.export(owner, report)
    assert exports.quota.total == 1 and not exports.operations
    await reports.shutdown()
    await evidence.shutdown()


@pytest.mark.asyncio
async def test_export_task_dispatch_failure_closes_coroutine_without_refunding_admitted_attempt(
    monkeypatch,
):
    """Exercise accepted task ownership transfer failure after charging but before any native process call."""
    exports, native, reports, evidence, core, _, owner, report = await configured()
    pending = []

    def fail(coroutine):
        """Retain one unstarted coroutine for closure inspection without executing its body."""
        pending.append(coroutine)
        raise RuntimeError("PRIVATE-SCHEDULER")

    with monkeypatch.context() as patch:
        patch.setattr(web_fetch_tasks, "create_task", fail)
        with pytest.raises(ReportExportError, match="export_internal"):
            await exports.export(owner, report)
    assert pending[0].cr_frame is None and exports.quota.total == 1 and not native.calls
    assert not exports.operations and not exports.admission.locked()
    await reports.shutdown()
    await evidence.shutdown()


@pytest.mark.asyncio
async def test_failed_export_attempts_are_not_refunded_and_fifth_owner_attempt_is_inert(
    monkeypatch,
):
    """Bound native retry pressure independently of the original one-call report assessment quota."""
    exports, native, reports, evidence, core, _, owner, report = await configured()

    async def fail(payload):
        """Record a controlled native failure without returning private dependency details."""
        native.calls.append(payload)
        raise ReportExportError("export_native_failed")

    monkeypatch.setattr(native, "render", fail)
    for _ in range(4):
        with pytest.raises(ReportExportError, match="export_native_failed"):
            await exports.export(owner, report)
    with pytest.raises(ReportExportError, match="export_rate_limited"):
        await exports.export(owner, report)
    assert len(native.calls) == exports.quota.total == 4 and len(core.calls) == 1
    assert not exports.operations and not exports.admission.locked()
    await reports.shutdown()
    await evidence.shutdown()


@pytest.mark.parametrize("trigger", ["completion", "cancellation"])
@pytest.mark.asyncio
async def test_explicit_native_cleanup_uncertainty_poisons_facade_even_without_dependency_flag(
    trigger, monkeypatch
):
    """Treat explicit unknown cleanup as fatal admission state independently of a port implementation's mutable closing flag."""
    exports, native, reports, evidence, core, _, owner, report = await configured()
    entered = asyncio.Event()

    async def uncertain(payload):
        """Report a controlled cleanup uncertainty on normal failure or cancellation acknowledgement."""
        entered.set()
        if trigger == "completion":
            raise ReportExportError("export_cleanup_uncertain")
        try:
            await asyncio.Event().wait()
        finally:
            raise ReportExportError("export_cleanup_uncertain")

    monkeypatch.setattr(native, "render", uncertain)
    task = asyncio.create_task(exports.export(owner, report))
    await entered.wait()
    if trigger == "cancellation":
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    else:
        with pytest.raises(ReportExportError, match="export_cleanup_uncertain"):
            await task
    assert exports.closing and not exports.operations and not exports.admission.locked()
    with pytest.raises(ReportExportError, match="export_closed"):
        await exports.export(owner, report)
    await reports.shutdown()
    await evidence.shutdown()
