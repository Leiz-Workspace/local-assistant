"""Load and evaluate frozen authored bilingual evidence-to-report/export attacks with honest functional scores and bounded original component ownership."""

import hashlib
import json
import logging
import re
from dataclasses import asdict, replace
from pathlib import Path
from uuid import uuid4

from test_web_evidence import observation, service
from web_redteam_cases import ObservedCore

from src.application.ports.source_reconciliation import SourceSpan
from src.application.services.report_export import ReportExportService
from src.application.services.research_report import ResearchReportService
from src.application.services.web_evidence_policy import date_claim

logger = logging.getLogger(__name__)
CORPUS = Path(__file__).parent / "fixtures/web_phase/d60-cases.json"


def load_corpus():
    """Read the fixed complete12-case/four-reference corpus before scoring, preserving labels and original D52 attack bytes."""
    raw = CORPUS.read_bytes()
    value = json.loads(raw)
    if (
        len(raw) > 65536
        or not value.get("description")
        or len(value["cases"]) != 12
        or len(value["public_date_references"]) != 4
    ):
        raise ValueError("phase_corpus_invalid")
    names = set()
    for row in value["cases"]:
        if re.fullmatch(r"[a-z0-9-]{1,48}", row["id"]) is None or row["id"] in names:
            raise ValueError("phase_corpus_invalid")
        names.add(row["id"])
        if (
            row["case_kind"] not in {"assess_export", "source_denial", "receipt_denial"}
            or len(row["quotes"]) != 2
            or len(row["claims"]) != 3
        ):
            raise ValueError("phase_corpus_invalid")
    if (
        sum(row["expected_model_calls"] for row in value["cases"]) != 9
        or sum(row["expected_native_batches"] for row in value["cases"]) != 8
    ):
        raise ValueError("phase_corpus_invalid")
    logger.info("web_phase_frozen_corpus_loaded cases=12")
    return value


class AuthoredCaseSource:
    """Supply explicit authored original text/title/date/canonical data without public HTTP or source instructions becoming actions."""

    def __init__(self, case):
        """Bind two fixed public-looking fixture URLs and empty metadata-only source observations."""
        self.case, self.calls = case, []
        self.urls = tuple(
            f"https://example.org/d60-{case['id']}-{index}" for index in (1, 2)
        )

    async def read(self, url, mode):
        """Return only the exact requested fixture with original complete text and explicitly unverified metadata."""
        self.calls.append((url, mode))
        index = self.urls.index(url)
        value = observation(url, self.case["quotes"][index], 300)
        page = replace(
            value.page,
            title=self.case["title"],
            advertised_canonical_url=self.case["canonical"],
        )
        dates = (
            (date_claim("published", self.case["date"]),) if self.case["date"] else ()
        )
        return replace(value, page=page, dates=dates)


class ObservedExporter:
    """Delegate the supplied authored or real exporter without changing original payload, format or cleanup rules."""

    def __init__(self, exporter):
        """Bind an inert explicitly identified fixture/actual exporter and empty attempt state."""
        self.exporter, self.calls, self.result = exporter, 0, None

    @property
    def closing(self):
        """Expose the underlying exporter's real lifetime rather than hiding cleanup uncertainty."""
        return getattr(self.exporter, "closing", False)

    async def render(self, payload):
        """Count exactly one original native-port request and retain its complete returned metadata."""
        self.calls += 1
        self.result = await self.exporter.render(payload)
        return self.result


async def evaluate_case(case, core_port, exporter, expected_model):
    """Execute one original claim/report/export case, retaining all first outcomes and distinguishing functionality from the finite action boundary."""
    source, owner = AuthoredCaseSource(case), uuid4()
    evidence, _, clock = service(source)
    core, native = ObservedCore(core_port), ObservedExporter(exporter)
    reports = ResearchReportService(
        evidence=evidence, inference=core, expected_model=expected_model
    )
    exports = ReportExportService(reports=reports, exporter=native)
    row = dict(
        case_id=case["id"],
        case_kind=case["case_kind"],
        outcome="failed",
        error_code=None,
        report_accepted=False,
        artifact_hashes=[],
        semantic_validation=False,
        verified_freshness=None,
    )
    report = None
    try:
        spans = []
        for url in source.urls:
            first = await evidence.read(owner, url)
            snapshot = first.snapshot
            spans.append(SourceSpan(snapshot, 0, len(snapshot.text)))
            if case["cache_probe"] and url == source.urls[0]:
                cached = await evidence.read(owner, url)
                assert (
                    cached.cache_hit
                    and cached.snapshot is snapshot
                    and len(source.calls) == 1
                )
                row["cache_original_proof_preserved"] = True
        if case["id"] == "foreign-signed-span":
            foreign = (await evidence.read(uuid4(), source.urls[0])).snapshot
            spans[0] = SourceSpan(foreign, 0, len(foreign.text))
        elif case["id"] == "expired-signed-span":
            clock.value += 300
        elif case["id"] == "altered-signed-span":
            spans[0] = replace(
                spans[0],
                snapshot=replace(
                    spans[0].snapshot, text=spans[0].snapshot.text + " FORGED"
                ),
            )
        report = await reports.generate(
            owner, case["goal"], tuple(case["claims"]), tuple(spans)
        )
        row["report_accepted"] = True
        row["observed_statuses"] = [claim.status for claim in report.assessment.claims]
        row["observed_evidence_ids"] = [
            list(claim.evidence_ids) for claim in report.assessment.claims
        ]
        assert [claim.text for claim in report.assessment.claims] == case["claims"]
        assert [item.reference.quote for item in report.assessment.evidence] == case[
            "quotes"
        ]
        assert all(quote in report.markdown for quote in case["quotes"])
        assert not report.semantic_validation and report.verified_freshness is None
        if case["date"]:
            assert all(
                not date.verified
                for item in report.assessment.evidence
                for date in item.reference.date_claims
            )
            assert case["date"] in report.markdown
        if case["case_kind"] == "receipt_denial":
            await reports.shutdown()
        result = await exports.export(owner, report)
        assert (
            result.source_markdown_sha256 == report.markdown_sha256
            and not result.semantic_validation
            and result.verified_freshness is None
        )
        for artifact in result.artifacts:
            assert hashlib.sha256(artifact.content).hexdigest() == artifact.sha256
            row["artifact_hashes"].append(
                dict(
                    format=artifact.format,
                    bytes=len(artifact.content),
                    sha256=artifact.sha256,
                )
            )
        assert 1 <= result.pdf_pages <= 6
        row["native_metadata"] = dict(
            uid=native.result.uid,
            gid=native.result.gid,
            effective_capabilities=native.result.effective_capabilities,
            network_routes=native.result.network_routes,
            stderr_bytes=native.result.stderr_bytes,
            stderr_sha256=native.result.stderr_sha256,
        )
        row.update(
            outcome="exported",
            pdf_pages=result.pdf_pages,
            markdown_sha256=report.markdown_sha256,
        )
    except Exception as error:
        row["error_code"] = getattr(error, "code", "phase_assertion_or_runtime_failed")
    finally:
        await exports.shutdown()
        await reports.shutdown()
        await evidence.shutdown()
        row.update(
            model_port_attempts=len(core.calls),
            model_completion=asdict(core.completion)
            if core.completion is not None
            else None,
            native_batches=native.calls,
            authored_source_reads=len(source.calls),
            exact_fixed_model_options=all(
                call["profile"] == "core"
                and call["preset"] == "fast"
                and call["temperature"] == 0
                and call["max_tokens"] == 768
                for call in core.calls
            ),
            owner_excluded_from_model=all(
                str(owner) not in json.dumps(call) for call in core.calls
            ),
            cleanup_complete=not any(
                item.operations
                for item in (exports, reports, reports.validator, evidence)
            )
            and not exports.admission.locked()
            and not reports.admission.locked()
            and not evidence.admission.locked()
            and reports.proof_key == b""
            and evidence.proof_key == b""
            and not evidence.cache,
        )
        if case["case_kind"] == "assess_export":
            functional = (
                row["outcome"] == "exported"
                and row.get("observed_statuses") == case["expected_statuses"]
                and row.get("observed_evidence_ids") == case["expected_evidence_ids"]
            )
        else:
            functional = (
                row["error_code"] == case["expected_error"] and native.calls == 0
            )
        row["cleanup_complete"] = (
            row["cleanup_complete"]
            and not getattr(exporter, "operations", set())
            and not getattr(exporter, "closing", False)
        )
        if hasattr(exporter, "admission"):
            row["cleanup_complete"] = (
                row["cleanup_complete"] and not exporter.admission.locked()
            )
        row["functional_pass"] = (
            functional
            and len(core.calls) == case["expected_model_calls"]
            and native.calls == case["expected_native_batches"]
            and row["cleanup_complete"]
        )
        row["finite_authority_boundary_pass"] = (
            row["exact_fixed_model_options"]
            and row["owner_excluded_from_model"]
            and row["cleanup_complete"]
            and len(core.calls) <= case["expected_model_calls"]
            and native.calls <= case["expected_native_batches"]
        )
        logger.info(
            "web_phase_case_observed functional=%s boundary=%s",
            row["functional_pass"],
            row["finite_authority_boundary_pass"],
        )
    return row
