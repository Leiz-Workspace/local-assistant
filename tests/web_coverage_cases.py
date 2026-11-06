"""Load fixed bilingual primary-URI/date labels and produce bounded metadata-only coverage measurements without semantic or freshness inflation."""

import hashlib
import json
import logging
import re
from dataclasses import asdict
from pathlib import Path
from urllib.parse import urlsplit

from src.application.services.search_pipeline import validate_batch, validate_query

logger = logging.getLogger(__name__)
CORPUS = Path(__file__).parent / "fixtures/web_coverage/d53-cases.json"


def load_corpus():
    """Load only the fixed bounded eight-query/four-reference corpus before provider/source scoring."""
    raw = CORPUS.read_bytes()
    if len(raw) > 65536:
        raise ValueError("coverage_corpus_limit")
    value = json.loads(raw)
    if (
        not value.get("description")
        or len(value["references"]) != 4
        or len(value["queries"]) != 8
    ):
        raise ValueError("coverage_corpus_invalid")
    ids = {row["id"] for row in value["references"]}
    if len(ids) != 4 or len({row["id"] for row in value["queries"]}) != 8:
        raise ValueError("coverage_corpus_duplicate")
    for row in value["references"]:
        re.compile(row["path_pattern"])
        if urlsplit(row["url"]).scheme != "https":
            raise ValueError("coverage_reference_invalid")
    for row in value["queries"]:
        validate_query(row["query"])
        if row["topic"] not in ids or row["language"] not in {"en", "vi"}:
            raise ValueError("coverage_query_invalid")
    logger.info("web_coverage_corpus_loaded")
    return value


def primary_match(url, reference):
    """Match only predeclared official host/path families without rewriting runtime URLs or asserting semantic relevance."""
    parsed = urlsplit(url)
    original = urlsplit(reference["url"])
    if (
        parsed.scheme != "https"
        or parsed.username is not None
        or parsed.password is not None
        or parsed.port not in {None, 443}
    ):
        return False
    host = (parsed.hostname or "").removeprefix("www.")
    if (
        host == (original.hostname or "").removeprefix("www.")
        and parsed.path == original.path
    ):
        return True
    return (
        host == reference["host"].removeprefix("www.")
        and re.fullmatch(reference["path_pattern"], parsed.path) is not None
    )


def search_observation(query, reference, batch, error, elapsed, when):
    """Record every search outcome and rank with metadata hashes only, counting failures in the fixed query denominator."""
    rows = []
    if batch is not None:
        hits = validate_batch(batch, "searxng")
        rows = [
            dict(
                rank=index,
                url=hit.url,
                title_sha256=hashlib.sha256(hit.title.encode()).hexdigest(),
                snippet_sha256=hashlib.sha256(hit.snippet.encode()).hexdigest(),
                expected_primary=primary_match(hit.url, reference),
            )
            for index, hit in enumerate(hits, 1)
        ]
    ranks = [row["rank"] for row in rows if row["expected_primary"]]
    rank = min(ranks) if ranks else None
    logger.info("web_coverage_search_observed success=%s", error is None)
    return dict(
        query_id=query["id"],
        topic=query["topic"],
        language=query["language"],
        queried_at=when.isoformat(),
        elapsed_seconds=elapsed,
        status="error" if error is not None else "results" if rows else "empty",
        error_type=type(error).__name__ if error is not None else None,
        error_code=getattr(error, "code", "source_failed")
        if error is not None
        else None,
        results=rows,
        expected_primary_rank=rank,
        expected_primary_present=bool(ranks),
        reciprocal_primary_rank=1 / rank if rank is not None else 0.0,
        semantic_relevance_evaluated=False,
    )


def reference_observation(reference, result, service, owner, error):
    """Bind original source/date declarations and a predeclared date marker to issued source provenance without claiming verified freshness."""
    row = dict(
        reference_id=reference["id"],
        requested_url=reference["url"],
        status="error" if error is not None else "observed",
        error_type=type(error).__name__ if error is not None else None,
        error_code=getattr(error, "code", "source_failed")
        if error is not None
        else None,
        verified_publication_date=None,
        verified_freshness=None,
        date_marker_required=reference["date_marker"] is not None,
        date_marker_grounded=False,
    )
    if result is not None:
        snapshot = result.snapshot
        row.update(
            final_url=snapshot.final_url,
            title=snapshot.title,
            fetched_at=snapshot.fetched_at.isoformat(),
            text_sha256=snapshot.text_sha256,
            text_bytes=len(snapshot.text.encode()),
            resources=[asdict(resource) for resource in snapshot.resources],
            page_date_claims=[asdict(claim) for claim in snapshot.date_claims],
            structured_publication_date="declared_unverified"
            if any(claim.kind == "published" for claim in snapshot.date_claims)
            else "unknown",
        )
        marker = reference["date_marker"]
        if marker is not None and marker in snapshot.text:
            start = snapshot.text.index(marker)
            citation = service.cite(owner, snapshot, start, start + len(marker))
            row.update(
                date_marker_grounded=citation.quote == marker,
                date_marker_quote_sha256=citation.quote_sha256,
                date_marker_start=start,
                date_marker_end=citation.end,
                date_marker_source_url=citation.final_url,
                date_marker_fetched_at=citation.fetched_at.isoformat(),
            )
    logger.info("web_coverage_reference_observed success=%s", error is None)
    return row


def summarize(searches, references):
    """Report fixed-denominator URI coverage and unknown freshness separately, never turning failed queries into good results."""
    if len(searches) != 8 or len(references) != 4:
        raise ValueError("coverage_measurement_incomplete")
    languages = {
        language: dict(
            queries=sum(row["language"] == language for row in searches),
            primary_present=sum(
                row["expected_primary_present"]
                for row in searches
                if row["language"] == language
            ),
        )
        for language in ["en", "vi"]
    }
    logger.info("web_coverage_measurement_summarized")
    return dict(
        queries=8,
        reference_attempts=4,
        provider_success=sum(row["status"] != "error" for row in searches),
        provider_failed=sum(row["status"] == "error" for row in searches),
        expected_primary_present=sum(
            row["expected_primary_present"] for row in searches
        ),
        expected_primary_presence_at5=sum(
            row["expected_primary_present"] for row in searches
        )
        / 8,
        mean_reciprocal_primary_rank=sum(
            row["reciprocal_primary_rank"] for row in searches
        )
        / 8,
        by_language=languages,
        references_observed=sum(row["status"] == "observed" for row in references),
        date_markers_required=sum(row["date_marker_required"] for row in references),
        date_markers_grounded=sum(row["date_marker_grounded"] for row in references),
        verified_freshness=None,
        semantic_relevance_evaluated=False,
        human_independent=False,
        provider_or_model_comparison=False,
    )
