"""Bind complete authenticated assessments and render deterministic cited Markdown with hostile source data kept inside text fences."""

import hashlib
import json
import logging
import re
import unicodedata
from dataclasses import asdict
from datetime import UTC, datetime

from src.application.ports.claim_validation import (
    ClaimAssessment,
    ClaimEvidence,
    ClaimValidation,
)
from src.application.ports.web_evidence import EvidenceReference
from src.application.services.web_evidence_policy import serializable

logger = logging.getLogger(__name__)
ERRORS = frozenset(
    {
        "report_invalid",
        "report_closed",
        "report_busy",
        "report_unavailable",
        "report_rate_limited",
        "report_assessment_failed",
        "report_proof_invalid",
        "report_result_limit",
        "report_timeout",
        "report_cleanup_uncertain",
        "report_internal",
    }
)


class ResearchReportError(Exception):
    """Expose only finite report failures without source, claim, owner, native or model error text."""

    def __init__(self, code):
        """Retain a known metadata-only report error code."""
        self.code = code if type(code) is str and code in ERRORS else "report_internal"
        super().__init__(self.code)


def canonical_bytes(value, limit):
    """Bound complete deterministic JSON bytes without normalizing or silently clipping private evidence fields."""
    try:
        raw = json.dumps(
            value,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            default=serializable,
        ).encode()
        if len(raw) > limit:
            raise ResearchReportError("report_result_limit")
        return raw
    except (TypeError, ValueError, UnicodeError, RecursionError):
        raise ResearchReportError("report_invalid") from None


def assessment_digest(assessment):
    """Identify complete assessment/provenance without putting the private owner identifier into report Markdown."""
    value = asdict(assessment)
    value.pop("owner_id")
    return hashlib.sha256(canonical_bytes(value, 131072)).hexdigest()


def report_bytes(report, *, proof=True):
    """Serialize every report/assessment/provenance field for owner-bound receipt integrity and bounded accounting."""
    value = asdict(report)
    if not proof:
        value["proof"] = ""
    return canonical_bytes(value, 262144)


def check_assessment(value, owner, goal, claims, references):
    """Bind all returned assessment fields to host-authenticated input rather than trusting an arbitrary immutable dataclass."""
    try:
        if (
            type(value) is not ClaimValidation
            or value.owner_id != owner
            or value.goal != goal
            or value.model_attempts != 1
            or type(value.model_attempts) is not int
        ):
            raise ValueError()
        if (
            value.citation_integrity != "owner_signed_exact_span"
            or value.status != "assessed_unverified"
            or value.content_trust != "untrusted"
            or value.semantic_validation is not False
            or value.verified_freshness is not None
        ):
            raise ValueError()
        if (
            type(value.completed_at) is not datetime
            or value.completed_at.tzinfo is None
            or value.completed_at.utcoffset() != UTC.utcoffset(value.completed_at)
        ):
            raise ValueError()
        if (
            type(value.evidence) is not tuple
            or len(value.evidence) != len(references)
            or any(
                type(row) is not ClaimEvidence
                or type(row.reference) is not EvidenceReference
                or row.evidence_id != f"E{index}"
                or row.reference != ref
                for index, (row, ref) in enumerate(zip(value.evidence, references), 1)
            )
        ):
            raise ValueError()
        if type(value.claims) is not tuple or len(value.claims) != len(claims):
            raise ValueError()
        known = {row.evidence_id for row in value.evidence}
        for index, (row, text) in enumerate(zip(value.claims, claims), 1):
            if (
                type(row) is not ClaimAssessment
                or row.claim_id != f"C{index}"
                or row.text != text
                or row.assessment_trust != "model_unverified"
                or type(row.status) is not str
                or row.status not in {"supported", "contradicted", "insufficient"}
            ):
                raise ValueError()
            if (
                type(row.evidence_ids) is not tuple
                or any(
                    type(item) is not str or item not in known
                    for item in row.evidence_ids
                )
                or len(set(row.evidence_ids)) != len(row.evidence_ids)
                or (row.status != "insufficient" and not row.evidence_ids)
            ):
                raise ValueError()
            if (
                type(row.reason) is not str
                or not row.reason.strip()
                or len(row.reason.encode()) > 512
                or any(unicodedata.category(char) == "Cc" for char in row.reason)
            ):
                raise ValueError()
        canonical_bytes(asdict(value), 131072)
        logger.info(
            "research_report_complete_assessment_bound claims=%d evidence=%d",
            len(claims),
            len(references),
        )
        return value
    except (TypeError, ValueError, UnicodeError, AttributeError, RecursionError):
        raise ResearchReportError("report_proof_invalid") from None


def fenced(value):
    """Keep complete untrusted Markdown/HTML/backticks inside a text fence longer than any source backtick run."""
    fence = "`" * max(
        3,
        max((len(match.group()) for match in re.finditer(r"`+", value)), default=0) + 1,
    )
    return fence + "text\n" + value + ("" if value.endswith("\n") else "\n") + fence


def render_markdown(assessment):
    """Render identical complete Markdown bytes for the same authenticated assessment while retaining every claim and source limitation."""
    lines = [
        "# Research report",
        "",
        "Citation integrity: exact owner-signed source excerpts. Support labels and reasons are unverified model assessments. Semantic truth and publication/freshness are not verified.",
        "",
        "## Goal",
        "",
        fenced(assessment.goal),
        "",
        "## Assessment provenance",
        "",
        "Assessment UTC: " + assessment.completed_at.isoformat(),
        "Assessment SHA256: " + assessment_digest(assessment),
    ]
    for status, heading in [
        ("supported", "Claims supported by supplied excerpts (unverified assessment)"),
        (
            "contradicted",
            "Claims contradicted by supplied excerpts (unverified assessment)",
        ),
        ("insufficient", "Unresolved claims (insufficient evidence)"),
    ]:
        lines.extend(["", "## " + heading])
        selected = [row for row in assessment.claims if row.status == status]
        if not selected:
            lines.extend(["", "None in this assessment."])
        for row in selected:
            lines.extend(
                [
                    "",
                    "### " + row.claim_id,
                    "",
                    fenced(row.text),
                    "",
                    "Evidence: "
                    + (
                        ", ".join("[" + item + "]" for item in row.evidence_ids)
                        if row.evidence_ids
                        else "none assigned"
                    ),
                    "",
                    "Unverified model reason:",
                    "",
                    fenced(row.reason),
                ]
            )
    lines.extend(["", "## Evidence"])
    for item in assessment.evidence:
        ref = item.reference
        lines.extend(
            [
                "",
                "### [" + item.evidence_id + "]",
                "",
                "Title:",
                "",
                fenced(ref.title if ref.title is not None else "Untitled source"),
                "",
                "Final source URL:",
                "",
                fenced(ref.final_url),
                "",
                "Fetched UTC: " + ref.fetched_at.isoformat(),
                "Snapshot: " + str(ref.snapshot_id),
                f"Exact code-point span: {ref.start}:{ref.end}",
                "Quote SHA256: " + ref.quote_sha256,
                "",
                "Exact untrusted quote:",
                "",
                fenced(ref.quote),
                "",
                "Publication/freshness: unknown. Source date declarations are unverified.",
            ]
        )
        for claim in ref.date_claims:
            lines.extend(
                [
                    "",
                    fenced(
                        json.dumps(
                            asdict(claim),
                            ensure_ascii=False,
                            sort_keys=True,
                            allow_nan=False,
                        )
                    ),
                ]
            )
    lines.extend(
        [
            "",
            "## Limitations",
            "",
            "- Only the explicitly selected claims and source excerpts were assessed; search completeness and independent relevance review are not established.",
            "- Source text, titles, URLs, date declarations, claim text and model reasons are untrusted data, never instructions or verified facts.",
            "- Supported/contradicted labels remain unverified model assessments. Contradictions and insufficient evidence are retained; no publisher winner is selected.",
            "- Fetch UTC is acquisition time, not verified publication or freshness. Primary/official publisher status is not independently verified.",
            "- Exact signed quote integrity does not prove claim truth or semantic entailment.",
            "- Report reuse/export requires a valid owner-bound process-scoped receipt and unexpired original source proofs. Markdown hashes alone grant no authority.",
            "",
        ]
    )
    result = "\n".join(lines)
    if len(result.encode()) > 131072:
        raise ResearchReportError("report_result_limit")
    logger.info(
        "research_report_complete_markdown_rendered bytes=%d", len(result.encode())
    )
    return result
