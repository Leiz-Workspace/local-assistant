"""Verify finite session orchestration, fresh-proof resume, archival classification and joined lifecycle with authored dependency fixtures."""

import asyncio
import json
import logging
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from test_claim_validation import Core as ClaimCore
from test_claim_validation_policy import CLAIMS
from test_report_export import AuthoredExporter
from test_research import configured as planner_fixture
from test_web_evidence import Source
from test_web_evidence import service as evidence_fixture

from src.application.ports.source_reconciliation import SourceSpan
from src.application.services import research_sessions as module
from src.application.services import web_fetch_tasks
from src.application.services.report_export import ReportExportService
from src.application.services.report_export_policy import ReportExportError
from src.application.services.research_report import ResearchReportService
from src.application.services.research_session_policy import ResearchSessionError
from src.application.services.research_sessions import ResearchSessionService
from src.infrastructure.readonly_workspace import WorkspaceCatalog
from src.infrastructure.research_sessions import PrivateResearchSessions

logger = logging.getLogger(__name__)


@pytest_asyncio.fixture
async def components(tmp_path):
    """Own explicit authored dependencies and a temporary real journal root, joining all resources after every control."""
    path = tmp_path / "sessions"
    path.mkdir(mode=0o700)
    store = PrivateResearchSessions(path, WorkspaceCatalog())
    evidence, source, clock = evidence_fixture(
        Source(text="Atlas restore generation is G-17. Atlas upload quota is 128 MiB.")
    )
    core, native = ClaimCore(), AuthoredExporter()
    reports = ResearchReportService(
        evidence=evidence, inference=core, expected_model="fixture-core"
    )
    exports = ReportExportService(reports=reports, exporter=native)
    planner, plan_core, provider = planner_fixture()
    service = ResearchSessionService(
        store=store, planner=planner, reports=reports, exports=exports
    )
    owner = uuid4()
    record = service.create(owner, "Compare sources", CLAIMS)
    run_id = UUID(record["run_id"])
    snapshot = (await evidence.read(owner, "https://example.org/source")).snapshot
    c = dict(
        service=service,
        store=store,
        path=path,
        owner=owner,
        run_id=run_id,
        evidence=evidence,
        source=source,
        clock=clock,
        core=core,
        native=native,
        reports=reports,
        exports=exports,
        planner=planner,
        plan_core=plan_core,
        provider=provider,
        selections=(SourceSpan(snapshot, 0, len(snapshot.text)),),
    )
    yield c
    await service.shutdown()
    await exports.shutdown()
    await reports.shutdown()
    await planner.shutdown()
    await evidence.shutdown()
    store.close()


async def first(c):
    """Run exactly the authored discover stage and assert an explicit durable pause before publication."""
    result = await c["service"].advance(c["owner"], c["run_id"])
    assert result["state"] == "paused" and result["attempts"] == ["discover"]
    return result


@pytest.mark.asyncio
async def test_two_explicit_stages_retain_all_bytes_without_loops_or_persisted_receipts(
    components, caplog
):
    """Run both stages once, preserving complete report/export identities and unknowns with no archive-to-proof conversion."""
    c = components
    caplog.set_level(logging.INFO)
    await first(c)
    assert not c["core"].calls and not c["native"].calls
    result = await c["service"].advance(c["owner"], c["run_id"], c["selections"])
    assert result["state"] == "complete" and result["attempts"] == [
        "discover",
        "publish",
    ]
    assert (
        len(c["plan_core"].calls) == len(c["core"].calls) == len(c["native"].calls) == 1
    )
    assert len(c["provider"].calls) == 2
    report = json.loads(c["service"].archive(c["owner"], c["run_id"], "report"))
    exported = json.loads(c["service"].archive(c["owner"], c["run_id"], "export"))
    assert (
        report["archived"]
        and report["semantic_validation"] is False
        and report["verified_freshness"] is None
    )
    assert (
        "proof" not in report["payload"]
        and "citation_deadline" not in report["payload"]
    )
    assert (
        report["payload"]["markdown_sha256"]
        == exported["payload"]["source_markdown_sha256"]
    )
    assert all(claim in report["payload"]["markdown"] for claim in CLAIMS)
    with pytest.raises(ResearchSessionError, match="session_state_invalid"):
        await c["service"].advance(c["owner"], c["run_id"])
    assert not c["service"].operations and not c["service"].admission.locked()
    assert str(c["owner"]) not in caplog.text and CLAIMS[0] not in caplog.text
    assert not any(
        getattr(c[name], "closing", False)
        for name in ("store", "planner", "reports", "exports", "evidence")
    )


@pytest.mark.asyncio
async def test_real_store_restart_boundary_requires_new_signed_sources_and_preserves_discovery(
    components,
):
    """Resume after exclusive storage reopen with new issuer proofs rather than deserializing old source/report capabilities."""
    c = components
    await first(c)
    raw = c["service"].archive(c["owner"], c["run_id"], "discover")
    await c["service"].shutdown()
    c["store"].close()
    second_store = PrivateResearchSessions(c["path"], WorkspaceCatalog())
    fresh_evidence, _, _ = evidence_fixture(Source(text=c["source"].text))
    fresh_reports = ResearchReportService(
        evidence=fresh_evidence, inference=c["core"], expected_model="fixture-core"
    )
    fresh_exports = ReportExportService(reports=fresh_reports, exporter=c["native"])
    resumed = ResearchSessionService(
        store=second_store,
        planner=c["planner"],
        reports=fresh_reports,
        exports=fresh_exports,
    )
    try:
        assert second_store.recover() == 0
        for selections in ((), c["selections"]):
            with pytest.raises(
                ResearchSessionError, match="session_fresh_sources_required"
            ):
                await resumed.advance(c["owner"], c["run_id"], selections)
        assert resumed.status(c["owner"], c["run_id"])["attempts"] == ["discover"]
        snapshot = (
            await fresh_evidence.read(c["owner"], "https://example.org/source")
        ).snapshot
        result = await resumed.advance(
            c["owner"], c["run_id"], (SourceSpan(snapshot, 0, len(snapshot.text)),)
        )
        assert (
            result["state"] == "complete"
            and resumed.archive(c["owner"], c["run_id"], "discover") == raw
        )
        assert (
            len(c["plan_core"].calls)
            == len(c["core"].calls)
            == len(c["native"].calls)
            == 1
        )
    finally:
        await resumed.shutdown()
        await fresh_exports.shutdown()
        await fresh_reports.shutdown()
        await fresh_evidence.shutdown()
        second_store.close()


@pytest.mark.parametrize(
    "fault",
    ["foreign", "string_owner", "string_run", "early_sources", "closed", "missing"],
)
@pytest.mark.asyncio
async def test_invalid_admission_does_not_reserve_attempts_or_call_tools(
    components, fault
):
    """Reject wrong identities, early source selection and missing/closed dependencies before reserving a stage."""
    c = components
    owner, run_id, spans = c["owner"], c["run_id"], ()
    if fault == "foreign":
        owner = uuid4()
    elif fault == "string_owner":
        owner = str(owner)
    elif fault == "string_run":
        run_id = str(run_id)
    elif fault == "early_sources":
        spans = c["selections"]
    elif fault == "closed":
        await c["service"].shutdown()
    else:
        c["service"].exports = None
    with pytest.raises(ResearchSessionError):
        await c["service"].advance(owner, run_id, spans)
    assert c["store"].load(c["owner"], c["run_id"])["attempts"] == []
    assert not c["plan_core"].calls and not c["core"].calls and not c["native"].calls


@pytest.mark.asyncio
async def test_dispatch_failure_is_charged_once_and_never_replayed(
    components, monkeypatch
):
    """Persist one attempt before a real owned-task dispatch fault and close the never-started coroutine."""
    c = components

    def rejected(coroutine):
        """Simulate event-loop dispatch rejection before the coroutine can execute any dependency."""
        raise RuntimeError("PRIVATE-DISPATCH")

    with monkeypatch.context() as patch:
        patch.setattr(web_fetch_tasks, "create_task", rejected)
        with pytest.raises(ResearchSessionError, match="session_dispatch_failed"):
            await c["service"].advance(c["owner"], c["run_id"])
    value = c["store"].load(c["owner"], c["run_id"])
    assert value["state"] == "interrupted" and value["attempts"] == ["discover"]
    assert value["error_code"] == "session_dispatch_failed" and not c["plan_core"].calls
    with pytest.raises(ResearchSessionError, match="session_state_invalid"):
        await c["service"].advance(c["owner"], c["run_id"])


@pytest.mark.parametrize("mode", ["caller", "owner", "shutdown"])
@pytest.mark.asyncio
async def test_repeated_cancellation_waits_for_actual_backend_join_before_interruption(
    components, monkeypatch, mode
):
    """Hold session ownership through repeated caller/owner/shutdown cancellation until the dependency's finally block really completes."""
    c = components
    entered, cleaning, release = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def blocked(owner, goal):
        """Hold an explicit authored operation and expose delayed joined cleanup without real network/model calls."""
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            cleaning.set()
            await release.wait()

    monkeypatch.setattr(c["planner"], "research", blocked)
    task = asyncio.create_task(c["service"].advance(c["owner"], c["run_id"]))
    await entered.wait()
    with pytest.raises(ResearchSessionError, match="session_not_found"):
        await c["service"].cancel(uuid4(), c["run_id"])
    if mode == "caller":
        task.cancel()
        control = None
    elif mode == "owner":
        control = asyncio.create_task(c["service"].cancel(c["owner"], c["run_id"]))
    else:
        control = asyncio.create_task(c["service"].shutdown())
    await cleaning.wait()
    task.cancel()
    await asyncio.sleep(0)
    assert not task.done() and c["service"].admission.locked()
    assert c["store"].load(c["owner"], c["run_id"])["state"] == "running"
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    if control is not None:
        await control
    value = c["store"].load(c["owner"], c["run_id"])
    assert (
        value["state"] == "interrupted" and value["error_code"] == "session_cancelled"
    )
    assert not c["service"].operations and not c["service"].admission.locked()
    assert (
        not c["planner"].closing
        and not c["reports"].closing
        and not c["exports"].closing
    )


@pytest.mark.parametrize(
    "fault", ["native_failure", "cleanup_uncertain", "expiry", "cancel_after_draft"]
)
@pytest.mark.asyncio
async def test_publish_interruption_retains_original_draft_without_replaying_report(
    components, monkeypatch, fault
):
    """Retain the acknowledged draft if native work fails/cancels or original proof expires; never reauthorize it from the archive."""
    c = components
    await first(c)
    entered = asyncio.Event()

    async def failed(owner, report):
        """Observe a durably acknowledged draft before exercising a finite native/expiry/cancel failure."""
        value = c["store"].load(owner, c["run_id"])
        assert "report" in value["blobs"] and "export" not in value["blobs"]
        entered.set()
        if fault == "expiry":
            c["clock"].value += 300
            c["reports"].verify(owner, report)
        if fault == "cancel_after_draft":
            await asyncio.Event().wait()
        raise ReportExportError(
            "export_cleanup_uncertain"
            if fault == "cleanup_uncertain"
            else "export_native_failed"
        )

    monkeypatch.setattr(c["exports"], "export", failed)
    task = asyncio.create_task(
        c["service"].advance(c["owner"], c["run_id"], c["selections"])
    )
    await entered.wait()
    if fault == "cancel_after_draft":
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    else:
        with pytest.raises(ResearchSessionError):
            await task
    value = c["store"].load(c["owner"], c["run_id"])
    assert value["state"] == "interrupted" and set(value["blobs"]) == {
        "discover",
        "report",
    }
    archived = c["service"].archive(c["owner"], c["run_id"], "report")
    assert all(claim in json.loads(archived)["payload"]["markdown"] for claim in CLAIMS)
    assert len(c["core"].calls) == 1 and not c["native"].calls
    if fault == "cleanup_uncertain":
        assert c["service"].closing
    with pytest.raises(ResearchSessionError):
        await c["service"].advance(c["owner"], c["run_id"], c["selections"])
    assert len(c["core"].calls) == 1


@pytest.mark.asyncio
async def test_suppressed_timeout_cannot_publish_or_reserve_another_attempt(
    components, monkeypatch
):
    """Reject a dependency's otherwise valid late result after it swallowed the owning stage's deadline cancellation."""
    c = components
    result = await c["planner"].research(c["owner"], "Compare sources")

    async def late(owner, goal):
        """Return an authored late result only after swallowing a real asyncio deadline cancellation."""
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            return result

    monkeypatch.setattr(module, "STAGE_SECONDS", 0.01)
    monkeypatch.setattr(c["planner"], "research", late)
    with pytest.raises(ResearchSessionError, match="session_timeout"):
        await c["service"].advance(c["owner"], c["run_id"])
    value = c["store"].load(c["owner"], c["run_id"])
    assert value["state"] == "interrupted" and not value["blobs"]


@pytest.mark.asyncio
async def test_acknowledgement_uncertainty_closes_admission_before_any_dispatch(
    components, monkeypatch
):
    """Retain an actually published reservation after lost acknowledgement without invoking a dependency or resetting the attempt."""
    c = components
    original = c["store"].root.replace_journal

    def uncertain(directory, value):
        """Publish/fsync the real journal and then inject a lost acknowledgement at the native return boundary."""
        original(directory, value)
        raise OSError("PRIVATE-FSYNC-ACK")

    with monkeypatch.context() as patch:
        patch.setattr(c["store"].root, "replace_journal", uncertain)
        with pytest.raises(ResearchSessionError, match="session_store_invalid"):
            await c["service"].advance(c["owner"], c["run_id"])
    assert c["store"].closing and c["service"].closing
    assert not c["plan_core"].calls and not c["core"].calls and not c["native"].calls
    c["store"].close()
    reopened = PrivateResearchSessions(c["path"], WorkspaceCatalog())
    try:
        assert reopened.recover() == 1
        value = reopened.load(c["owner"], c["run_id"])
        assert value["attempts"] == ["discover"] and value["state"] == "interrupted"
    finally:
        reopened.close()


@pytest.mark.asyncio
async def test_nonqueued_other_run_and_final_shutdown_preserve_shared_lifetimes(
    components, monkeypatch
):
    """Refuse another session while one explicit stage owns admission and retain all shared component lifetimes after shutdown."""
    c = components
    entered = asyncio.Event()

    async def blocked(owner, goal):
        """Hold a cancellable authored dependency until the session owner requests joined shutdown."""
        entered.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(c["planner"], "research", blocked)
    task = asyncio.create_task(c["service"].advance(c["owner"], c["run_id"]))
    await entered.wait()
    second = UUID(
        c["service"].create(c["owner"], "Second explicit goal", CLAIMS)["run_id"]
    )
    with pytest.raises(ResearchSessionError, match="session_busy"):
        await c["service"].advance(c["owner"], second)
    assert c["store"].load(c["owner"], second)["attempts"] == []
    await c["service"].shutdown()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert (
        not c["store"].closing
        and not c["planner"].closing
        and not c["evidence"].closing
    )
    assert c["service"].status(c["owner"], c["run_id"])["state"] == "interrupted"


@pytest.mark.asyncio
async def test_wrong_owner_or_late_proof_in_report_cannot_authorize_native_stage(
    components, monkeypatch
):
    """Reject forged report output before durable draft/native publication while retaining the original finite publish reservation."""
    c = components
    await first(c)

    async def forged(owner, goal, claims, selections):
        """Return a caller-shaped object explicitly lacking the issuing service's complete authenticated receipt."""
        return {"owner_id": str(owner), "markdown": "FORGED"}

    monkeypatch.setattr(c["reports"], "generate", forged)
    with pytest.raises(ResearchSessionError, match="session_stage_failed"):
        await c["service"].advance(c["owner"], c["run_id"], c["selections"])
    value = c["store"].load(c["owner"], c["run_id"])
    assert value["state"] == "interrupted" and set(value["blobs"]) == {"discover"}
    assert not c["native"].calls and not c["core"].calls
