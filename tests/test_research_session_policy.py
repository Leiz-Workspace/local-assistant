"""Reject forged archive schemas, oversized data, malformed selectors and incomplete native artifacts without granting live receipt authority."""

import json
from dataclasses import replace
from uuid import uuid4

import pytest
from test_report_export import configured

from src.application.services.research_session_policy import (
    LIMITS,
    ResearchSessionError,
    check_archive,
    export_payload,
    identifiers,
    pack_archive,
)


@pytest.mark.parametrize(
    "mutation",
    [
        "owner",
        "run",
        "kind",
        "live",
        "semantic",
        "freshness",
        "extra",
        "payload",
        "schema",
    ],
)
def test_archive_classification_and_exact_owner_binding_cannot_be_overridden(mutation):
    """Keep private archived bytes distinct from live evidence/current truth even if stored-looking JSON is supplied."""
    owner, run_id = uuid4(), uuid4()
    raw = pack_archive("report", owner, run_id, dict(markdown="Authored content"))
    value = json.loads(raw)
    if mutation == "owner":
        value["owner_id"] = str(uuid4())
    elif mutation == "run":
        value["run_id"] = str(uuid4())
    elif mutation == "kind":
        value["kind"] = "discover"
    elif mutation == "live":
        value["archived"] = False
    elif mutation == "semantic":
        value["semantic_validation"] = True
    elif mutation == "freshness":
        value["verified_freshness"] = "today"
    elif mutation == "extra":
        value["proof"] = "caller supplied"
    elif mutation == "payload":
        value["payload"] = []
    else:
        value["schema_version"] = "future"
    with pytest.raises(ResearchSessionError, match="session_store_invalid"):
        check_archive(json.dumps(value).encode(), "report", owner, run_id)


@pytest.mark.parametrize("kind", ["discover", "report", "export"])
def test_complete_archive_byte_budget_is_enforced_before_any_file_creation(kind):
    """Refuse a whole oversized archive instead of clipping original source/report/artifact data."""
    with pytest.raises(ResearchSessionError, match="session_invalid"):
        pack_archive(kind, uuid4(), uuid4(), dict(text="x" * LIMITS[kind]))


@pytest.mark.parametrize("value", [None, False, "../../path", [], {}, 1])
def test_exact_uuid_capabilities_are_required(value):
    """Reject missing/string/container/scalar run identifiers rather than interpreting them as a filesystem target."""
    with pytest.raises(ResearchSessionError, match="session_invalid"):
        identifiers(uuid4(), value)


@pytest.mark.parametrize(
    "mutation",
    [
        "owner",
        "source",
        "count",
        "order",
        "bytes",
        "hash",
        "name",
        "media",
        "format",
        "semantic",
        "pages",
    ],
)
@pytest.mark.asyncio
async def test_incomplete_or_changed_export_cannot_be_archived_as_complete(mutation):
    """Validate complete native-port artifact identity after the accepted export facade before declaring durable completion."""
    exports, native, reports, evidence, core, clock, owner, report = await configured()
    try:
        value = await exports.export(owner, report)
        if mutation == "owner":
            value = replace(value, owner_id=uuid4())
        elif mutation == "source":
            value = replace(value, source_markdown_sha256="0" * 64)
        elif mutation == "count":
            value = replace(value, artifacts=value.artifacts[:1])
        elif mutation == "order":
            value = replace(value, artifacts=tuple(reversed(value.artifacts)))
        elif mutation == "semantic":
            value = replace(value, semantic_validation=True)
        elif mutation == "pages":
            value = replace(value, pdf_pages=33)
        else:
            field, changed = {
                "bytes": ("content", b"FORGED"),
                "hash": ("sha256", "0" * 64),
                "name": ("filename", "../../target"),
                "media": ("media_type", "text/html"),
                "format": ("format", "html"),
            }[mutation]
            value = replace(
                value,
                artifacts=(
                    replace(value.artifacts[0], **{field: changed}),
                    *value.artifacts[1:],
                ),
            )
        with pytest.raises(ResearchSessionError, match="session_stage_failed"):
            export_payload(value, owner, report)
    finally:
        await exports.shutdown()
        await reports.shutdown()
        await evidence.shutdown()
