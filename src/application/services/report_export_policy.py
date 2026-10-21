"""Project authenticated complete report evidence into fixed safe Office text blocks and validate bounded native export bytes."""

import base64
import hashlib
import json
import logging
import os
import re
from dataclasses import asdict
from datetime import datetime

from src.application.ports.report_export import ExportArtifact, NativeReportExport
from src.application.services.search_pipeline import unique_pairs

logger = logging.getLogger(__name__)
MAX_INPUT = 131072
MAX_DOCX = 2 * 1024**2
MAX_PDF = 4 * 1024**2
MAX_STDOUT = 9 * 1024**2
MAX_STDERR = 65536
ERRORS = frozenset(
    {
        "export_invalid",
        "export_closed",
        "export_busy",
        "export_unavailable",
        "export_rate_limited",
        "export_proof_invalid",
        "export_unrepresentable",
        "export_native_failed",
        "export_timeout",
        "export_result_limit",
        "export_cleanup_uncertain",
        "export_internal",
    }
)
STYLES = frozenset({"Title", "Heading1", "Heading2", "Normal", "Quote", "Metadata"})
HEADINGS = frozenset(
    {
        "Goal",
        "Assessment provenance",
        "Supported claims",
        "Contradicted claims",
        "Unresolved claims",
        "Evidence",
        "Limitations",
    }
)
LIMITATIONS = (
    "Citation integrity confirms exact owner-signed source excerpts. Support labels and reasons are unverified model assessments; semantic truth is not verified.",
    "Only explicit claims and selected excerpts were assessed. Search completeness, independent relevance review and primary publisher status are not established.",
    "Contradicted and insufficient claims are retained. No publisher winner is selected and no missing facts are invented.",
    "Publication and freshness remain unknown. Fetch UTC is acquisition time, not verified publication history.",
    "Source text, titles, URLs, date declarations, claim text and model reasons are untrusted data, never instructions.",
    "Artifact hashes identify complete exported bytes. Reuse requires the authenticated original report; hashes alone grant no authority.",
)


class ReportExportError(Exception):
    """Expose only finite export errors without report, quote, owner, filesystem, native or model error text."""

    def __init__(self, code):
        """Retain a known caller-independent artifact export error code."""
        self.code = code if type(code) is str and code in ERRORS else "export_internal"
        super().__init__(self.code)


def reject_constant(value):
    """Refuse nonfinite transport JSON without returning its untrusted content."""
    raise ValueError("nonfinite_report_export")


def xml_text(value):
    """Reject XML-unrepresentable source characters without deleting or substituting original report text."""
    if (
        type(value) is not str
        or len(value.encode()) > 8192
        or any(
            not (
                ord(char) in {9, 10, 13}
                or 0x20 <= ord(char) <= 0xD7FF
                or 0xE000 <= ord(char) <= 0xFFFD
                or 0x10000 <= ord(char) <= 0x10FFFF
            )
            for char in value
        )
    ):
        raise ReportExportError("export_unrepresentable")
    return value


def parse_payload(raw):
    """Validate the entire fixed style/block transport before native Office imports or filesystem output."""
    try:
        if type(raw) is not bytes or not 1 <= len(raw) <= MAX_INPUT:
            raise ValueError()
        value = json.loads(
            raw, object_pairs_hook=unique_pairs, parse_constant=reject_constant
        )
        if (
            type(value) is not dict
            or set(value)
            != {
                "schema",
                "source_markdown_sha256",
                "assessment_sha256",
                "assessed_at",
                "blocks",
            }
            or value["schema"] != "report-export-v1"
        ):
            raise ValueError()
        for key in ["source_markdown_sha256", "assessment_sha256"]:
            if type(value[key]) is not str or not re.fullmatch(
                r"[0-9a-f]{64}", value[key]
            ):
                raise ValueError()
        if type(value["assessed_at"]) is not str:
            raise ValueError()
        when = datetime.fromisoformat(value["assessed_at"])
        if when.tzinfo is None or when.utcoffset().total_seconds() != 0:
            raise ValueError()
        if type(value["blocks"]) is not list or not 1 <= len(value["blocks"]) <= 160:
            raise ValueError()
        for index, row in enumerate(value["blocks"]):
            if (
                type(row) is not dict
                or set(row) != {"style", "text"}
                or type(row["style"]) is not str
                or row["style"] not in STYLES
            ):
                raise ValueError()
            xml_text(row["text"])
            if row["style"] == "Title" and (
                index != 0 or row["text"] != "Research report"
            ):
                raise ValueError()
            if row["style"] == "Heading1" and row["text"] not in HEADINGS:
                raise ValueError()
            if row["style"] == "Heading2" and not re.fullmatch(
                r"[CE][1-8]", row["text"]
            ):
                raise ValueError()
        if value["blocks"][0] != dict(style="Title", text="Research report"):
            raise ValueError()
        logger.info(
            "report_export_complete_block_payload_validated blocks=%d",
            len(value["blocks"]),
        )
        return value
    except ReportExportError:
        raise
    except (TypeError, ValueError, UnicodeError, AttributeError, RecursionError):
        raise ReportExportError("export_invalid") from None


def make_payload(report):
    """Project every authenticated original claim/source field into fixed text-only blocks without interpreting Markdown or adding facts."""
    assessed = report.assessment
    blocks = [
        dict(style="Title", text="Research report"),
        dict(style="Normal", text=LIMITATIONS[0]),
        dict(style="Heading1", text="Goal"),
        dict(style="Quote", text=assessed.goal),
        dict(style="Heading1", text="Assessment provenance"),
        dict(
            style="Metadata",
            text="Assessment UTC: " + assessed.completed_at.isoformat(),
        ),
        dict(style="Metadata", text="Markdown SHA256: " + report.markdown_sha256),
        dict(style="Metadata", text="Assessment SHA256: " + report.assessment_sha256),
    ]
    for status, heading in [
        ("supported", "Supported claims"),
        ("contradicted", "Contradicted claims"),
        ("insufficient", "Unresolved claims"),
    ]:
        blocks.append(dict(style="Heading1", text=heading))
        rows = [row for row in assessed.claims if row.status == status]
        if not rows:
            blocks.append(dict(style="Normal", text="None in this assessment."))
        for row in rows:
            blocks.extend(
                [
                    dict(style="Heading2", text=row.claim_id),
                    dict(style="Quote", text=row.text),
                    dict(
                        style="Normal",
                        text="Evidence: "
                        + (
                            ", ".join("[" + item + "]" for item in row.evidence_ids)
                            if row.evidence_ids
                            else "none assigned"
                        ),
                    ),
                    dict(style="Normal", text="Unverified model assessment"),
                    dict(style="Quote", text=row.reason),
                ]
            )
    blocks.append(dict(style="Heading1", text="Evidence"))
    for item in assessed.evidence:
        ref = item.reference
        blocks.extend(
            [
                dict(style="Heading2", text=item.evidence_id),
                dict(style="Normal", text="Title"),
                dict(
                    style="Quote",
                    text=ref.title if ref.title is not None else "Untitled source",
                ),
                dict(style="Normal", text="Final source URL"),
                dict(style="Quote", text=ref.final_url),
                dict(
                    style="Metadata", text="Fetched UTC: " + ref.fetched_at.isoformat()
                ),
                dict(style="Metadata", text="Snapshot: " + str(ref.snapshot_id)),
                dict(
                    style="Metadata",
                    text=f"Exact code-point span: {ref.start}:{ref.end}",
                ),
                dict(style="Metadata", text="Quote SHA256: " + ref.quote_sha256),
                dict(style="Normal", text="Exact untrusted quote"),
                dict(style="Quote", text=ref.quote),
                dict(
                    style="Normal",
                    text="Publication and freshness: unknown. Source date declarations are unverified.",
                ),
            ]
        )
        for claim in ref.date_claims:
            blocks.append(
                dict(
                    style="Quote",
                    text=json.dumps(
                        asdict(claim),
                        ensure_ascii=False,
                        sort_keys=True,
                        allow_nan=False,
                    ),
                )
            )
    blocks.extend(
        [
            dict(style="Heading1", text="Limitations"),
            *(dict(style="Normal", text=text) for text in LIMITATIONS),
        ]
    )
    raw = json.dumps(
        dict(
            schema="report-export-v1",
            source_markdown_sha256=report.markdown_sha256,
            assessment_sha256=report.assessment_sha256,
            assessed_at=assessed.completed_at.isoformat(),
            blocks=blocks,
        ),
        ensure_ascii=False,
        sort_keys=True,
        allow_nan=False,
        separators=(",", ":"),
    ).encode()
    parse_payload(raw)
    return raw


def check_native(value, source_hash):
    """Recheck complete port artifact hashes/limits/fixed filenames and native metadata before publishing any caller-visible bytes."""
    try:
        if (
            type(value) is not NativeReportExport
            or type(value.artifacts) is not tuple
            or len(value.artifacts) != 2
            or type(value.pdf_pages) is not int
            or not 1 <= value.pdf_pages <= 32
        ):
            raise ValueError()
        if (
            type(value.uid) is not int
            or value.uid != 65534
            or type(value.gid) is not int
            or value.gid != 65534
            or value.effective_capabilities != "0000000000000000"
            or type(value.network_routes) is not int
            or value.network_routes != 0
        ):
            raise ValueError()
        for actual, kind in [
            (value.pid_namespace, "pid"),
            (value.net_namespace, "net"),
        ]:
            if (
                type(actual) is not str
                or not re.fullmatch(kind + r":\[\d+\]", actual)
                or actual == os.readlink("/proc/self/ns/" + kind)
            ):
                raise ValueError()
        for row, name, media_type, limit, prefix in zip(
            value.artifacts,
            ["docx", "pdf"],
            [
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                "application/pdf",
            ],
            [MAX_DOCX, MAX_PDF],
            [b"PK\x03\x04", b"%PDF-"],
            strict=True,
        ):
            if (
                type(row) is not ExportArtifact
                or row.format != name
                or row.media_type != media_type
                or row.filename != f"report-{source_hash[:12]}.{name}"
                or row.source_markdown_sha256 != source_hash
                or type(row.content) is not bytes
                or not 0 < len(row.content) <= limit
                or not row.content.startswith(prefix)
                or row.sha256 != hashlib.sha256(row.content).hexdigest()
            ):
                raise ValueError()
        logger.info("report_export_complete_port_artifact_integrity_checked")
        return value
    except (TypeError, ValueError, AttributeError, OSError):
        raise ReportExportError("export_native_failed") from None


def parse_native(raw, payload, stderr):
    """Bind exact fixed-format native output bytes and actual namespace observations to the authenticated report source hash."""
    try:
        if (
            type(raw) is not bytes
            or len(raw) > MAX_STDOUT
            or type(stderr) is not bytes
            or len(stderr) > MAX_STDERR
        ):
            raise ValueError()
        value = json.loads(
            raw, object_pairs_hook=unique_pairs, parse_constant=reject_constant
        )
        if (
            type(value) is dict
            and set(value) == {"error"}
            and type(value["error"]) is str
            and value["error"] in ERRORS
        ):
            raise ReportExportError(value["error"])
        if type(value) is not dict or set(value) != {
            "source_markdown_sha256",
            "docx",
            "pdf",
            "pdf_pages",
            "uid",
            "gid",
            "pid_namespace",
            "net_namespace",
            "effective_capabilities",
            "network_routes",
        }:
            raise ValueError()
        request = parse_payload(payload)
        source_hash = request["source_markdown_sha256"]
        if (
            value["source_markdown_sha256"] != source_hash
            or type(value["pdf_pages"]) is not int
            or not 1 <= value["pdf_pages"] <= 32
        ):
            raise ValueError()
        if (
            type(value["uid"]) is not int
            or type(value["gid"]) is not int
            or value["uid"] != 65534
            or value["gid"] != 65534
        ):
            raise ValueError()
        if (
            type(value["network_routes"]) is not int
            or value["network_routes"] != 0
            or value["effective_capabilities"] != "0000000000000000"
        ):
            raise ValueError()
        for name, kind in [("pid_namespace", "pid"), ("net_namespace", "net")]:
            if type(value[name]) is not str or not re.fullmatch(
                kind + r":\[\d+\]", value[name]
            ):
                raise ValueError()
        artifacts = []
        for name, media_type, limit, prefix in [
            (
                "docx",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                MAX_DOCX,
                b"PK\x03\x04",
            ),
            ("pdf", "application/pdf", MAX_PDF, b"%PDF-"),
        ]:
            encoded = value[name]
            if type(encoded) is not str or len(encoded) > ((limit + 2) // 3) * 4:
                raise ValueError()
            content = base64.b64decode(encoded, validate=True)
            if not 1 <= len(content) <= limit or not content.startswith(prefix):
                raise ValueError()
            artifacts.append(
                ExportArtifact(
                    name,
                    media_type,
                    f"report-{source_hash[:12]}.{name}",
                    content,
                    hashlib.sha256(content).hexdigest(),
                    source_hash,
                )
            )
        logger.info(
            "report_export_complete_native_artifacts_bound pages=%d", value["pdf_pages"]
        )
        result = NativeReportExport(
            tuple(artifacts),
            value["pdf_pages"],
            value["uid"],
            value["gid"],
            value["pid_namespace"],
            value["net_namespace"],
            value["effective_capabilities"],
            value["network_routes"],
            len(stderr),
            hashlib.sha256(stderr).hexdigest(),
        )
        return check_native(result, source_hash)
    except ReportExportError:
        raise
    except (TypeError, ValueError, UnicodeError, KeyError, RecursionError):
        raise ReportExportError("export_native_failed") from None
