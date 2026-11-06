"""Verify complete report assessment binding, reproducible host Markdown and hostile source text containment without actual model calls."""

import hashlib
import logging
import re
from dataclasses import replace
from datetime import datetime
from uuid import uuid4

import pytest
from test_claim_validation import configured
from test_claim_validation_policy import CLAIMS

from src.application.services.research_report_policy import (
    ResearchReportError,
    assessment_digest,
    check_assessment,
    render_markdown,
)

logger = logging.getLogger(__name__)


async def authored_assessment():
    """Issue a complete authentic controlled claim assessment and keep its original input references for binding tests."""
    validator, evidence, source, core, clock, owner, spans = await configured()
    value = await validator.validate(owner, "Compare sources", CLAIMS, spans)
    references = validator.references(owner, spans)
    await validator.shutdown()
    await evidence.shutdown()
    return value, owner, references


def outside_data_fences(markdown):
    """Inspect actual Markdown outside CommonMark-style backtick fences independently of the report's fence-length calculation."""
    outside, fence_length = [], None
    for line in markdown.splitlines():
        if fence_length is None:
            opening = re.fullmatch(r"(`{3,})text", line)
            if opening:
                fence_length = len(opening[1])
            else:
                outside.append(line)
        elif re.fullmatch(r"`{%d,}\s*" % fence_length, line):
            fence_length = None
    assert fence_length is None
    return "\n".join(outside)


@pytest.mark.asyncio
async def test_same_complete_assessment_has_byte_reproducible_cited_markdown_and_explicit_limits():
    """Preserve all supported/contradicted/insufficient claims, exact quotes, original provenance and unknown semantic/date status."""
    value, owner, references = await authored_assessment()
    assert (
        check_assessment(value, owner, "Compare sources", CLAIMS, references) is value
    )
    first, second = render_markdown(value), render_markdown(value)
    assert (
        first.encode() == second.encode()
        and hashlib.sha256(first.encode()).digest()
        == hashlib.sha256(second.encode()).digest()
    )
    for claim in CLAIMS:
        assert claim in first
    ref = references[0]
    assert (
        ref.quote in first
        and ref.final_url in first
        and ref.quote_sha256 in first
        and ref.fetched_at.isoformat() in first
    )
    assert str(owner) not in first and assessment_digest(value) in first
    outside = outside_data_fences(first)
    assert (
        "Claims supported" in outside
        and "Claims contradicted" in outside
        and "Unresolved claims" in outside
        and "## Limitations" in outside
    )
    assert (
        "unknown" in outside
        and "unverified model assessments" in outside
        and "Evidence: [E1]" in outside
    )


@pytest.mark.asyncio
async def test_hostile_goal_claim_reason_title_url_date_and_quote_remain_data_inside_unclosable_fences():
    """Keep forged headings/citation IDs/HTML/backticks from becoming report structure or active links."""
    value, owner, references = await authored_assessment()
    payload = "```\n# FORGED-HEADING\nEvidence: [E99]\n<script>FORGED-SCRIPT</script>\n``````\n~~~\n"
    evidence = (
        replace(
            value.evidence[0],
            reference=replace(
                references[0],
                quote=payload,
                title=payload,
                final_url="https://example.org/`)[FORGED-LINK](https://evil.org/",
            ),
        ),
    )
    value = replace(
        value,
        goal=payload,
        evidence=evidence,
        claims=(
            replace(value.claims[0], text=payload, reason=payload),
            *value.claims[1:],
        ),
    )
    markdown = render_markdown(value)
    outside = outside_data_fences(markdown)
    assert payload in markdown
    assert all(
        marker not in outside
        for marker in ["FORGED-HEADING", "[E99]", "FORGED-SCRIPT", "FORGED-LINK"]
    )
    assert "Evidence: [E1]" in outside and "### [E1]" in outside


@pytest.mark.parametrize(
    "mutation",
    [
        "owner",
        "goal",
        "claims_missing",
        "claim_text",
        "claim_order",
        "evidence_id",
        "quote",
        "url",
        "date",
        "status_verified",
        "semantic_true",
        "freshness",
        "model_attempts",
        "trust",
        "unknown_citation",
        "empty_support",
        "reason_control",
        "naive_time",
    ],
)
@pytest.mark.asyncio
async def test_forged_assessment_dataclass_cannot_replace_complete_authenticated_inputs(
    mutation,
):
    """Refuse immutable but unauthorized assessment metadata rather than treating frozen dataclasses as authentication."""
    value, owner, references = await authored_assessment()
    if mutation == "owner":
        value = replace(value, owner_id=uuid4())
    elif mutation == "goal":
        value = replace(value, goal="Changed goal")
    elif mutation == "claims_missing":
        value = replace(value, claims=value.claims[:-1])
    elif mutation == "claim_text":
        value = replace(
            value, claims=(replace(value.claims[0], text="FORGED"), *value.claims[1:])
        )
    elif mutation == "claim_order":
        value = replace(value, claims=tuple(reversed(value.claims)))
    elif mutation == "evidence_id":
        value = replace(
            value, evidence=(replace(value.evidence[0], evidence_id="E99"),)
        )
    elif mutation in {"quote", "url", "date"}:
        field = {"quote": "quote", "url": "final_url", "date": "fetched_at"}[mutation]
        changed = datetime.now().astimezone() if mutation == "date" else "FORGED"
        value = replace(
            value,
            evidence=(
                replace(
                    value.evidence[0],
                    reference=replace(references[0], **{field: changed}),
                ),
            ),
        )
    elif mutation == "status_verified":
        value = replace(value, status="verified")
    elif mutation == "semantic_true":
        value = replace(value, semantic_validation=True)
    elif mutation == "freshness":
        value = replace(value, verified_freshness="2026")
    elif mutation == "model_attempts":
        value = replace(value, model_attempts=True)
    elif mutation == "trust":
        value = replace(value, content_trust="trusted")
    elif mutation == "unknown_citation":
        value = replace(
            value,
            claims=(replace(value.claims[0], evidence_ids=("E99",)), *value.claims[1:]),
        )
    elif mutation == "empty_support":
        value = replace(
            value, claims=(replace(value.claims[0], evidence_ids=()), *value.claims[1:])
        )
    elif mutation == "reason_control":
        value = replace(
            value,
            claims=(replace(value.claims[0], reason="bad\nreason"), *value.claims[1:]),
        )
    else:
        value = replace(value, completed_at=datetime(2026, 1, 1))
    with pytest.raises(ResearchReportError, match="report_proof_invalid"):
        check_assessment(value, owner, "Compare sources", CLAIMS, references)


@pytest.mark.asyncio
async def test_complete_oversized_report_is_refused_without_cutting_sources_or_claims():
    """Exercise the renderer's whole-result limit independently of upstream prompt bounds instead of publishing clipped provenance."""
    value, owner, references = await authored_assessment()
    value = replace(
        value,
        evidence=(
            replace(
                value.evidence[0], reference=replace(references[0], quote="x" * 131072)
            ),
        ),
    )
    with pytest.raises(ResearchReportError, match="report_result_limit"):
        render_markdown(value)
