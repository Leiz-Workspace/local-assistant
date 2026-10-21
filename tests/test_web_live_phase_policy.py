"""Verify live-provider minimization, actual-result-only primary selection and exact bounded source spans without network/model/native calls."""

import hashlib
import json
from dataclasses import replace
from uuid import uuid4

import pytest
from test_research import configured
from test_web_evidence import Source, service
from web_live_phase_policy import (
    LivePhaseError,
    discovery_metadata,
    exact_quote,
    select_primary,
    source_family,
)


async def live_fixture():
    """Produce an accepted authored research result with two primary-family URLs and explicit private-text canaries."""
    planner, core, provider = configured()
    owner = uuid4()
    try:
        result = await planner.research(owner, "Compare official APIs")
        queries = []
        for query, url in zip(
            result.queries,
            (
                "https://docs.searxng.org/dev/search_api.html?format=json",
                "https://www.rfc-editor.org/rfc/rfc9111.html",
            ),
            strict=True,
        ):
            source = replace(
                query.sources[0],
                url=url,
                title="PRIVATE-TITLE-CANARY",
                snippet="PRIVATE-SNIPPET-CANARY",
                snippet_sha256=hashlib.sha256(b"PRIVATE-SNIPPET-CANARY").hexdigest(),
            )
            queries.append(replace(query, sources=(source,)))
        return replace(result, queries=tuple(queries)), owner
    finally:
        await planner.shutdown()


@pytest.mark.asyncio
async def test_complete_outcome_metadata_excludes_provider_query_title_snippet_fields_and_owner(
    caplog,
):
    """Preserve exact URLs/hashes/attempts/statuses while explicitly classifying raw actual provider text as never admitted to storage."""
    result, owner = await live_fixture()
    value = discovery_metadata(result, owner, result.goal)
    raw = json.dumps(value, default=str)
    assert "PRIVATE-" not in raw and str(owner) not in raw
    assert all(query.query not in raw for query in result.queries)
    assert value["provider_attempts"] == 2 and value["model_attempts"] == 1
    assert (
        value["raw_provider_payload_retained"] is False
        and value["verified_freshness"] is None
    )
    assert value["queries"][0]["sources"][0]["url"] == result.queries[0].sources[0].url
    selected = select_primary(value)
    assert [row["family"] for row in selected] == ["searxng", "rfc"]
    assert (
        selected[0]["url"].endswith("?format=json")
        and selected[0]["source_id"] == "Q1:S1"
    )


@pytest.mark.parametrize("fault", ["foreign", "goal", "hash"])
@pytest.mark.asyncio
async def test_changed_or_foreign_live_result_is_refused_before_projection(fault):
    """Require exact accepted result/owner/goal/snippet identity rather than projecting caller-forged data as live discovery."""
    result, owner = await live_fixture()
    goal = result.goal
    if fault == "foreign":
        owner = uuid4()
    elif fault == "goal":
        goal = "FORGED"
    else:
        query = result.queries[0]
        result = replace(
            result,
            queries=(
                replace(
                    query, sources=(replace(query.sources[0], snippet_sha256="0" * 64),)
                ),
                *result.queries[1:],
            ),
        )
    with pytest.raises(LivePhaseError, match="live_input_invalid"):
        discovery_metadata(result, owner, goal)


@pytest.mark.parametrize(
    "url",
    [
        "http://docs.searxng.org/dev/search_api.html",
        "https://127.0.0.1/private",
        "https://docs.searxng.org.attacker.example/dev/search_api.html",
        "https://docs.searxng.org/dev/other.html",
        "https://docs.searxng.org@127.0.0.1/dev/search_api.html",
        "https://www.rfc-editor.org/rfc/rfc9110.html",
        "https://docs.searxng.org/dev/search_api.html#claim",
        "https://docs.searxng.org:444/dev/search_api.html",
    ],
)
def test_no_unapproved_scheme_host_path_port_or_fragment_becomes_a_selected_source(url):
    """Keep host-owned fixed families separate from arbitrary returned URLs without resolving or fetching any target."""
    assert source_family(url) is None


@pytest.mark.asyncio
async def test_missing_required_primary_has_no_synthetic_fallback():
    """Refuse a missing search-discovered primary instead of inventing a hit for an independently chosen reference URL."""
    result, owner = await live_fixture()
    value = discovery_metadata(result, owner, result.goal)
    value["queries"][1]["sources"] = []
    with pytest.raises(LivePhaseError, match="live_missing_primary_sources"):
        select_primary(value)


@pytest.mark.parametrize(
    "fault",
    [
        "count",
        "boolean_count",
        "status",
        "query_id",
        "source_id",
        "query_replay",
        "unknown_error",
        "naive_UTC",
    ],
)
@pytest.mark.asyncio
async def test_forged_attempt_state_ids_and_UTC_are_refused_before_metadata_storage(
    fault,
):
    """Bind metadata to complete original ordered attempts and source identities rather than trusting arbitrary stored-looking dataclasses."""
    result, owner = await live_fixture()
    query = result.queries[0]
    if fault == "count":
        result = replace(result, provider_attempts=0)
    elif fault == "boolean_count":
        result = replace(result, model_attempts=True)
    elif fault == "status":
        result = replace(result, status="no_sources")
    elif fault == "query_id":
        result = replace(
            result, queries=(replace(query, query_id="Q99"), result.queries[1])
        )
    elif fault == "source_id":
        result = replace(
            result,
            queries=(
                replace(
                    query, sources=(replace(query.sources[0], source_id="Q99:S1"),)
                ),
                result.queries[1],
            ),
        )
    elif fault == "query_replay":
        result = replace(
            result, queries=(query, replace(result.queries[1], query=query.query))
        )
    elif fault == "unknown_error":
        result = replace(
            result,
            queries=(replace(query, error_code="PRIVATE-RAW-ERROR"), result.queries[1]),
        )
    else:
        result = replace(result, completed_at=result.completed_at.replace(tzinfo=None))
    with pytest.raises(LivePhaseError, match="live_input_invalid"):
        discovery_metadata(result, owner, result.goal)


@pytest.mark.parametrize(
    "mutation", ["valid", "missing", "ambiguous", "oversized", "wrong_family"]
)
@pytest.mark.asyncio
async def test_exact_quote_is_a_complete_declared_span_and_never_silent_clipping(
    mutation,
):
    """Use fresh owned source proofs and fixed marker boundaries while refusing ambiguous or oversized excerpts before report work."""
    text = "Two endpoints, / and /search, are supported for both GET and POST methods. Outside source text."
    if mutation == "missing":
        text = "No expected marker."
    elif mutation == "ambiguous":
        text = text + " " + text
    elif mutation == "oversized":
        text = "Two endpoints, " + "word " * 30 + "methods."
    evidence, source, clock = service(Source(text=text))
    owner = uuid4()
    try:
        url = (
            "https://example.org/source"
            if mutation == "wrong_family"
            else "https://docs.searxng.org/dev/search_api.html"
        )
        snapshot = (await evidence.read(owner, url)).snapshot
        if mutation == "valid":
            span = exact_quote(snapshot, "searxng")
            quote = evidence.cite(owner, span.snapshot, span.start, span.end).quote
            assert (
                quote.endswith("methods.")
                and "Outside" not in quote
                and len(quote.split()) <= 25
            )
        else:
            with pytest.raises(LivePhaseError):
                exact_quote(snapshot, "searxng")
    finally:
        await evidence.shutdown()
