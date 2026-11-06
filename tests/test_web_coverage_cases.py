"""Verify fixed-denominator bilingual URI scoring, truthful source-date uncertainty and exact issued date spans without live search."""

import json
import logging
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from test_web_evidence import Source, service
from web_coverage_cases import (
    load_corpus,
    primary_match,
    reference_observation,
    search_observation,
    summarize,
)

from src.application.ports.search import SearchBatch, SearchHit
from src.infrastructure.searxng_search import SearxNGError

logger = logging.getLogger(__name__)
CORPUS = load_corpus()
REFS = {row["id"]: row for row in CORPUS["references"]}


@pytest.mark.parametrize(
    "topic,url,expected",
    [
        ("searxng", "https://docs.searxng.org/dev/search_api.html", True),
        (
            "searxng",
            "https://docs.searxng.org/dev/search_api.html?language=vi#json",
            True,
        ),
        ("searxng", "https://evil.example/dev/search_api.html", False),
        ("searxng", "https://docs.searxng.org.evil.example/dev/search_api.html", False),
        ("searxng", "http://docs.searxng.org/dev/search_api.html", False),
        (
            "searxng",
            "https://user:password@docs.searxng.org/dev/search_api.html",
            False,
        ),
        ("searxng", "https://docs.searxng.org:444/dev/search_api.html", False),
        ("searxng", "https://docs.searxng.org/dev/other.html", False),
        ("python", "https://docs.python.org/3/library/urllib.parse.html", True),
        (
            "python",
            "https://docs.python.org/3.15/library/urllib.parse.html#urljoin",
            True,
        ),
        ("python", "https://docs.python.org/3/library/urllib.request.html", False),
        ("rfc", "https://www.rfc-editor.org/rfc/rfc9111.html", True),
        ("rfc", "https://rfc-editor.org/rfc/rfc9111.txt", True),
        ("rfc", "https://rfc-editor.org/rfc/rfc91110.html", False),
        (
            "cdp",
            "https://chromedevtools.github.io/devtools-protocol/tot/Browser/#method-setDownloadBehavior",
            True,
        ),
        (
            "cdp",
            "https://chromedevtools.github.io/devtools-protocol/1-3/Browser/",
            True,
        ),
        (
            "cdp",
            "https://chromedevtools.github.io/devtools-protocol/tot/Network/",
            False,
        ),
        (
            "cdp",
            "https://raw.githubusercontent.com/ChromeDevTools/devtools-protocol/master/pdl/domains/Browser.pdl",
            True,
        ),
    ],
)
def test_only_frozen_official_uri_families_match_without_semantic_or_runtime_rewrite(
    topic, url, expected
):
    """Distinguish known primary identifiers from lookalike hosts/paths while ignoring only declared query/fragment metadata."""
    assert primary_match(url, REFS[topic]) is expected


def observed_rows(*, failed=False):
    """Create a complete eight-query authored cohort without any provider/network or model call."""
    rows = []
    for query in CORPUS["queries"]:
        reference = REFS[query["topic"]]
        batch = (
            None
            if failed
            else SearchBatch(
                "searxng",
                (
                    SearchHit(
                        "Authored title",
                        reference["url"],
                        "AUTHORED-SNIPPET-NOT-STORED",
                    ),
                ),
            )
        )
        error = SearxNGError("searxng_upstream_unavailable") if failed else None
        rows.append(
            search_observation(
                query, reference, batch, error, 0.01, datetime(2026, 10, 21, tzinfo=UTC)
            )
        )
    return rows


@pytest.mark.parametrize("failed", [False, True])
def test_provider_failures_keep_fixed_denominator_and_raw_snippets_out_of_report(
    failed,
):
    """Report failures as zero primary coverage without dropping queries or persisting actual title/snippet text."""
    rows = observed_rows(failed=failed)
    refs = [
        reference_observation(ref, None, None, None, RuntimeError("PRIVATE-ERROR"))
        for ref in CORPUS["references"]
    ]
    result = summarize(rows, refs)
    assert result["queries"] == 8 and result["expected_primary_present"] == (
        0 if failed else 8
    )
    assert result["expected_primary_presence_at5"] == (0 if failed else 1)
    assert result["provider_failed"] == (8 if failed else 0)
    assert (
        result["by_language"]["en"]["queries"]
        == result["by_language"]["vi"]["queries"]
        == 4
    )
    assert (
        result["verified_freshness"] is None
        and result["semantic_relevance_evaluated"] is False
    )
    raw = json.dumps(rows + refs)
    assert (
        "AUTHORED-SNIPPET-NOT-STORED" not in raw
        and "Authored title" not in raw
        and "PRIVATE-ERROR" not in raw
    )


def test_first_primary_rank_has_zero_contribution_for_missing_or_empty_results():
    """Measure reciprocal primary rank rather than labeling arbitrary high-ranked sources relevant."""
    query = CORPUS["queries"][0]
    ref = REFS[query["topic"]]
    batch = SearchBatch(
        "searxng",
        (
            SearchHit("Other", "https://example.org/", "Other source"),
            SearchHit("Official", ref["url"], "Declared source"),
        ),
    )
    row = search_observation(query, ref, batch, None, 0.01, datetime.now(UTC))
    assert row["expected_primary_rank"] == 2 and row["reciprocal_primary_rank"] == 0.5
    empty = search_observation(
        query, ref, SearchBatch("searxng", ()), None, 0.01, datetime.now(UTC)
    )
    assert empty["status"] == "empty" and empty["reciprocal_primary_rank"] == 0


@pytest.mark.asyncio
async def test_declared_date_marker_requires_exact_signed_source_span_and_remains_unverified():
    """Ground the curated month declaration in issued source evidence without turning fetch time or a quote into verified publication truth."""
    current, _, _ = service(Source(text="RFC9111 publication June 2022."))
    owner = uuid4()
    ref = REFS["rfc"]
    try:
        result = await current.read(owner, ref["url"])
        row = reference_observation(ref, result, current, owner, None)
        assert (
            row["date_marker_grounded"] and row["date_marker_source_url"] == ref["url"]
        )
        assert row["date_marker_fetched_at"] == result.snapshot.fetched_at.isoformat()
        assert (
            row["verified_freshness"] is None
            and row["verified_publication_date"] is None
        )
        assert row["structured_publication_date"] == "unknown"
        assert "RFC9111 publication June 2022." not in json.dumps(row)
        logger.info("web_coverage_date_declaration_provenance_verified")
    finally:
        await current.shutdown()


def test_partial_measurements_cannot_be_reported_as_complete():
    """Refuse a report that omits a failed query or reference attempt from its required measurement denominator."""
    with pytest.raises(ValueError, match="coverage_measurement_incomplete"):
        summarize(observed_rows()[:-1], [])
