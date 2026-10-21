"""Verify complete report projection, strict transport schemas and byte/hash limits without native Office or actual model calls."""

import base64
import hashlib
import json
import logging
import os
from dataclasses import replace

import pytest
from test_claim_validation_policy import CLAIMS
from test_research_report import configured

from src.application.services.report_export_policy import (
    ReportExportError,
    check_native,
    make_payload,
    parse_native,
    parse_payload,
)

logger = logging.getLogger(__name__)


async def authored_payload():
    """Build a receipt-authenticated fixture report and complete block payload without actual inference/source HTTP."""
    reports, evidence, source, core, clock, owner, spans = await configured()
    report = await reports.generate(owner, "Compare nguồn tiếng Việt", CLAIMS, spans)
    raw = make_payload(report)
    await reports.shutdown()
    await evidence.shutdown()
    return report, raw


def authored_native(payload):
    """Create explicit protocol-only placeholder bytes without pretending they are valid real Office/PDF artifacts."""
    source_hash = parse_payload(payload)["source_markdown_sha256"]
    value = dict(
        source_markdown_sha256=source_hash,
        docx=base64.b64encode(b"PK\x03\x04AUTHORED-ONLY").decode(),
        pdf=base64.b64encode(b"%PDF-AUTHORED-ONLY").decode(),
        pdf_pages=1,
        uid=65534,
        gid=65534,
        pid_namespace="pid:[111]",
        net_namespace="net:[222]",
        effective_capabilities="0000000000000000",
        network_routes=0,
    )
    return value


@pytest.mark.asyncio
async def test_complete_fixed_projection_preserves_original_claims_quotes_provenance_and_unknowns():
    """Retain all original source fields as text without interpreting hostile syntax or sending owner/report proof to the native worker."""
    report, raw = await authored_payload()
    value = parse_payload(raw)
    text = "\n".join(row["text"] for row in value["blocks"])
    assert all(claim in text for claim in CLAIMS)
    ref = report.assessment.evidence[0].reference
    assert all(
        piece in text
        for piece in [
            ref.quote,
            ref.final_url,
            ref.quote_sha256,
            ref.fetched_at.isoformat(),
            "Supported claims",
            "Contradicted claims",
            "Unresolved claims",
            "Limitations",
            "unknown",
            "unverified model assessments",
        ]
    )
    assert str(report.owner_id).encode() not in raw and report.proof.encode() not in raw
    assert raw == make_payload(report)


@pytest.mark.parametrize(
    "mutation",
    [
        "root_extra",
        "path",
        "schema",
        "bad_hash",
        "bad_time",
        "bad_style",
        "html_style",
        "forged_title",
        "forged_heading",
        "forged_subheading",
        "bad_text_type",
        "xml_control",
        "too_many_blocks",
        "large_block",
    ],
)
@pytest.mark.asyncio
async def test_entire_native_request_rejects_invalid_tail_and_arbitrary_authority(
    mutation,
):
    """Deny caller paths/options/templates/markup styles and invalid tail data before creating a native document."""
    _, raw = await authored_payload()
    value = json.loads(raw)
    if mutation == "root_extra":
        value["command"] = "PRIVATE-COMMAND"
    elif mutation == "path":
        value["output_path"] = "/PRIVATE-PATH"
    elif mutation == "schema":
        value["schema"] = "unknown"
    elif mutation == "bad_hash":
        value["source_markdown_sha256"] = "BAD"
    elif mutation == "bad_time":
        value["assessed_at"] = "2026-10-21"
    elif mutation == "bad_style":
        value["blocks"][-1]["style"] = "Execute"
    elif mutation == "html_style":
        value["blocks"][-1]["style"] = "HTML"
    elif mutation == "forged_title":
        value["blocks"][0]["text"] = "FORGED"
    elif mutation == "forged_heading":
        value["blocks"].append(dict(style="Heading1", text="FORGED"))
    elif mutation == "forged_subheading":
        value["blocks"].append(dict(style="Heading2", text="E99"))
    elif mutation == "bad_text_type":
        value["blocks"][-1]["text"] = None
    elif mutation == "xml_control":
        value["blocks"][-1]["text"] = "bad\x00text"
    elif mutation == "too_many_blocks":
        value["blocks"] += [dict(style="Normal", text="x")] * 161
    else:
        value["blocks"][-1]["text"] = "x" * 8193
    with pytest.raises(ReportExportError):
        parse_payload(json.dumps(value).encode())


@pytest.mark.parametrize(
    "raw",
    [
        b"{}",
        b'{"schema":NaN}',
        b'{"schema":"a","schema":"b"}',
        b"[1]",
        b"\xff",
        b"x" * 131073,
    ],
)
def test_duplicate_nonfinite_malformed_or_oversized_transport_is_rejected(raw):
    """Refuse ambiguous or oversized transport rather than salvaging an otherwise valid prefix."""
    with pytest.raises(ReportExportError, match="export_invalid"):
        parse_payload(raw)


@pytest.mark.parametrize(
    "mutation",
    [
        "wrong_source",
        "uid",
        "gid",
        "network",
        "capabilities",
        "namespace",
        "pages",
        "boolean_pages",
        "bad_base64",
        "bad_prefix",
        "extra",
        "stderr_limit",
        "stdout_limit",
    ],
)
@pytest.mark.asyncio
async def test_native_output_requires_source_fixed_namespace_and_complete_bounded_bytes(
    mutation,
):
    """Reject forged native metadata or incomplete formats even when a valid artifact prefix is present."""
    _, payload = await authored_payload()
    value = authored_native(payload)
    stderr = b""
    if mutation == "wrong_source":
        value["source_markdown_sha256"] = "0" * 64
    elif mutation == "uid":
        value["uid"] = 0
    elif mutation == "gid":
        value["gid"] = 0
    elif mutation == "network":
        value["network_routes"] = 1
    elif mutation == "capabilities":
        value["effective_capabilities"] = "0000000000000001"
    elif mutation == "namespace":
        value["net_namespace"] = "host"
    elif mutation == "pages":
        value["pdf_pages"] = 33
    elif mutation == "boolean_pages":
        value["pdf_pages"] = True
    elif mutation == "bad_base64":
        value["pdf"] = "!!"
    elif mutation == "bad_prefix":
        value["pdf"] = base64.b64encode(b"WRONG").decode()
    elif mutation == "extra":
        value["filename"] = "/PRIVATE"
    elif mutation == "stderr_limit":
        stderr = b"x" * 65537
    raw = (
        json.dumps(value).encode()
        if mutation != "stdout_limit"
        else b"x" * (9 * 1024**2 + 1)
    )
    with pytest.raises(ReportExportError, match="export_native_failed"):
        parse_native(raw, payload, stderr)


@pytest.mark.asyncio
async def test_port_byte_hash_filename_and_format_binding_cannot_be_changed_after_native_decode():
    """Authenticate all complete port artifact fields before returning application bytes, independently of native parser correctness."""
    _, payload = await authored_payload()
    native = parse_native(
        json.dumps(authored_native(payload)).encode(), payload, b"metadata-only"
    )
    source_hash = parse_payload(payload)["source_markdown_sha256"]
    assert check_native(native, source_hash) is native
    assert all(
        row.sha256 == hashlib.sha256(row.content).hexdigest()
        for row in native.artifacts
    )
    for change in [
        dict(filename="../../PRIVATE"),
        dict(sha256="0" * 64),
        dict(content=b"WRONG"),
        dict(media_type="text/html"),
        dict(source_markdown_sha256="0" * 64),
    ]:
        altered = replace(
            native,
            artifacts=(replace(native.artifacts[0], **change), native.artifacts[1]),
        )
        with pytest.raises(ReportExportError, match="export_native_failed"):
            check_native(altered, source_hash)


@pytest.mark.parametrize("kind", ["pid", "net"])
@pytest.mark.asyncio
async def test_host_namespace_identity_cannot_be_reported_as_isolated_native_output(
    kind,
):
    """Reject plausible namespace strings that actually identify the application host namespace."""
    _, payload = await authored_payload()
    value = authored_native(payload)
    value[kind + "_namespace"] = os.readlink("/proc/self/ns/" + kind)
    with pytest.raises(ReportExportError, match="export_native_failed"):
        parse_native(json.dumps(value).encode(), payload, b"")
