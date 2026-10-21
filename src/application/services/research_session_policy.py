"""Define finite durable research states and nonexecutable archive schemas without reviving evidence receipts."""

import base64
import hashlib
import json
import logging
import re
from dataclasses import asdict
from uuid import UUID

from src.application.ports.report_export import ExportArtifact, ReportExport
from src.application.services.claim_validation_policy import prepare_claims
from src.application.services.research_report_policy import canonical_bytes
from src.application.services.search_pipeline import unique_pairs

logger = logging.getLogger(__name__)
LIMITS = {"discover": 131072, "report": 262144, "export": 9 * 1024**2}
ERRORS = frozenset(
    {
        "session_invalid",
        "session_not_found",
        "session_busy",
        "session_closed",
        "session_state_invalid",
        "session_capacity",
        "session_fresh_sources_required",
        "session_cancelled",
        "session_timeout",
        "session_stage_failed",
        "session_dispatch_failed",
        "session_process_interrupted",
        "session_cleanup_uncertain",
        "session_store_invalid",
        "session_internal",
    }
)


class ResearchSessionError(Exception):
    """Expose only finite session failures without principal, goal, source, path or backend diagnostics."""

    def __init__(self, code):
        """Retain an allowed metadata-only error identifier."""
        self.code = code if type(code) is str and code in ERRORS else "session_internal"
        super().__init__(self.code)
        logger.warning("research_session_rejected code=%s", self.code)


def identifiers(owner, *run_ids):
    """Require actual authenticated UUID capabilities rather than caller strings or path-shaped identifiers."""
    if (
        type(owner) is not UUID
        or len(run_ids) > 1
        or any(type(item) is not UUID for item in run_ids)
    ):
        raise ResearchSessionError("session_invalid")


def encode(value, limit):
    """Bound complete canonical archive bytes without clipping or accepting nonfinite JSON values."""
    try:
        return canonical_bytes(value, limit)
    except Exception:
        raise ResearchSessionError("session_invalid") from None


def decode(raw, limit):
    """Reject oversized, duplicate-key, nonfinite or malformed stored JSON before interpreting metadata."""

    def reject(value):
        """Reject JSON constants without retaining their raw diagnostic text."""
        raise ValueError()

    try:
        if type(raw) is not bytes or not 0 < len(raw) <= limit:
            raise ValueError()
        value = json.loads(raw, object_pairs_hook=unique_pairs, parse_constant=reject)
        if type(value) is not dict:
            raise ValueError()
        return value
    except Exception:
        raise ResearchSessionError("session_store_invalid") from None


def check_journal(value):
    """Require one exact owner/input/state/attempt prefix and complete acknowledged blob manifest."""
    try:
        if set(value) != {
            "description",
            "schema_version",
            "run_id",
            "owner_id",
            "goal",
            "claims",
            "state",
            "attempts",
            "blobs",
            "error_code",
        }:
            raise ValueError()
        if (
            value["description"] != "Private bounded research session journal."
            or value["schema_version"] != "research-session-v1"
            or any(
                str(UUID(value[key])) != value[key] for key in ("run_id", "owner_id")
            )
            or type(value["claims"]) is not list
        ):
            raise ValueError()
        goal, claims = prepare_claims(value["goal"], tuple(value["claims"]))
        if goal != value["goal"] or list(claims) != value["claims"]:
            raise ValueError()
        state, attempts, blobs = value["state"], value["attempts"], value["blobs"]
        if type(attempts) is not list or attempts not in (
            [],
            ["discover"],
            ["discover", "publish"],
        ):
            raise ValueError()
        if type(blobs) is not dict or not set(blobs) <= set(LIMITS):
            raise ValueError()
        for kind, info in blobs.items():
            if (
                type(info) is not dict
                or set(info) != {"sha256", "bytes"}
                or type(info["sha256"]) is not str
                or re.fullmatch(r"[a-f0-9]{64}", info["sha256"]) is None
                or type(info["bytes"]) is not int
                or not 0 < info["bytes"] <= LIMITS[kind]
            ):
                raise ValueError()
        if ("report" in blobs and (len(attempts) != 2 or "discover" not in blobs)) or (
            "export" in blobs and "report" not in blobs
        ):
            raise ValueError()
        if state == "ready":
            valid = attempts == [] and blobs == {}
        elif state == "paused":
            valid = attempts == ["discover"] and set(blobs) == {"discover"}
        elif state == "complete":
            valid = len(attempts) == 2 and set(blobs) == set(LIMITS)
        elif state in {"running", "interrupted"}:
            valid = bool(attempts) and (
                len(attempts) == 2 or set(blobs) <= {"discover"}
            )
            valid = valid and (len(attempts) != 2 or "discover" in blobs)
        else:
            valid = False
        if not valid or (
            value["error_code"] not in ERRORS
            if state == "interrupted"
            else value["error_code"] is not None
        ):
            raise ValueError()
        encode(value, 32768)
        return value
    except Exception:
        raise ResearchSessionError("session_store_invalid") from None


def pack_archive(kind, owner, run_id, payload):
    """Frame private retained output as untrusted archive data with no proof, executable policy or current-freshness authority."""
    identifiers(owner, run_id)
    if type(kind) is not str or kind not in LIMITS or type(payload) is not dict:
        raise ResearchSessionError("session_invalid")
    raw = encode(
        dict(
            description="Untrusted archived research output; not a live receipt.",
            schema_version="research-archive-v1",
            kind=kind,
            owner_id=str(owner),
            run_id=str(run_id),
            archived=True,
            content_trust="untrusted",
            semantic_validation=False,
            verified_freshness=None,
            payload=payload,
        ),
        LIMITS[kind],
    )
    logger.info("research_session_archive_encoded kind=%s bytes=%d", kind, len(raw))
    return raw


def check_archive(raw, kind, owner, run_id):
    """Authenticate an archive's owner/run through trusted private journal context without turning stored data into live evidence."""
    value = decode(raw, LIMITS[kind])
    if (
        set(value)
        != {
            "description",
            "schema_version",
            "kind",
            "owner_id",
            "run_id",
            "archived",
            "content_trust",
            "semantic_validation",
            "verified_freshness",
            "payload",
        }
        or value["description"]
        != "Untrusted archived research output; not a live receipt."
        or value["schema_version"] != "research-archive-v1"
        or value["kind"] != kind
        or value["owner_id"] != str(owner)
        or value["run_id"] != str(run_id)
        or value["archived"] is not True
        or value["content_trust"] != "untrusted"
        or value["semantic_validation"] is not False
        or value["verified_freshness"] is not None
        or type(value["payload"]) is not dict
    ):
        raise ResearchSessionError("session_store_invalid")
    return value


def report_payload(report):
    """Retain the complete assessment/Markdown provenance while deliberately excluding the live receipt and monotonic deadline."""
    return dict(
        markdown=report.markdown,
        markdown_sha256=report.markdown_sha256,
        assessment_sha256=report.assessment_sha256,
        assessment=asdict(report.assessment),
    )


def export_payload(exported, owner, report):
    """Verify fixed complete both-format bytes before archiving them as data bound to the original report identity."""
    try:
        if (
            type(exported) is not ReportExport
            or exported.owner_id != owner
            or exported.source_markdown_sha256 != report.markdown_sha256
            or type(exported.pdf_pages) is not int
            or not 1 <= exported.pdf_pages <= 32
            or type(exported.artifacts) is not tuple
            or len(exported.artifacts) != 2
            or exported.semantic_validation is not False
            or exported.verified_freshness is not None
        ):
            raise ValueError()
        artifacts = []
        for item, kind, media, limit in zip(
            exported.artifacts,
            ("docx", "pdf"),
            (
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                "application/pdf",
            ),
            (2 * 1024**2, 4 * 1024**2),
            strict=True,
        ):
            if (
                type(item) is not ExportArtifact
                or item.format != kind
                or item.media_type != media
                or item.filename != f"report-{report.markdown_sha256[:12]}.{kind}"
                or item.source_markdown_sha256 != report.markdown_sha256
                or type(item.content) is not bytes
                or not 0 < len(item.content) <= limit
                or hashlib.sha256(item.content).hexdigest() != item.sha256
            ):
                raise ValueError()
            artifacts.append(
                dict(
                    format=kind,
                    media_type=media,
                    filename=item.filename,
                    sha256=item.sha256,
                    bytes=len(item.content),
                    content_base64=base64.b64encode(item.content).decode(),
                )
            )
        return dict(
            source_markdown_sha256=report.markdown_sha256,
            completed_at=exported.completed_at,
            pdf_pages=exported.pdf_pages,
            artifacts=artifacts,
        )
    except Exception:
        raise ResearchSessionError("session_stage_failed") from None
