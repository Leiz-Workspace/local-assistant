"""Score a preregistered bilingual official-source panel without fetching results or claiming semantic relevance or publication freshness."""

import hashlib
import json
import logging
from pathlib import Path
from urllib.parse import urlsplit

from src.application.services.search_pipeline import validate_batch, validate_query

logger = logging.getLogger(__name__)
CORPUS = (
    Path(__file__).resolve().parents[1] / "tests/fixtures/web_coverage/d60-fresh.json"
)
TOPICS = ("searxng", "rfc", "python", "cdp")


def load_corpus(path=CORPUS):
    """Validate eight uniquely identified bilingual questions and fixed official path labels before any provider request."""
    raw = Path(path).read_bytes()
    if len(raw) > 32768:
        raise ValueError("fresh_coverage_corpus_limit")
    value = json.loads(raw)
    if (
        type(value) is not dict
        or not value.get("description")
        or set(value.get("references", {})) != set(TOPICS)
        or len(value.get("queries", [])) != 8
    ):
        raise ValueError("fresh_coverage_corpus_invalid")
    seen = set()
    for row in value["queries"]:
        if (
            set(row) != {"id", "topic", "language", "query"}
            or row["topic"] not in TOPICS
            or row["language"] not in {"en", "vi"}
            or row["id"] != row["topic"] + "-" + row["language"]
            or row["id"] in seen
        ):
            raise ValueError("fresh_coverage_query_invalid")
        seen.add(row["id"])
        validate_query(row["query"])
    for ref in value["references"].values():
        if set(ref) != {"hosts", "direct_paths", "publisher_paths"}:
            raise ValueError("fresh_coverage_reference_invalid")
        if not ref["hosts"] or not ref["direct_paths"]:
            raise ValueError("fresh_coverage_reference_invalid")
        if any(type(h) is not str or "/" in h or ":" in h for h in ref["hosts"]):
            raise ValueError("fresh_coverage_reference_invalid")
        if any(
            type(p) is not str or not p.startswith("/") or "?" in p or "#" in p
            for p in ref["direct_paths"] + ref["publisher_paths"]
        ):
            raise ValueError("fresh_coverage_reference_invalid")
    logger.info("d60_fresh_coverage_corpus_validated queries=8")
    return value


def source_route(url, reference):
    """Classify exact returned official URLs, retaining publisher locators separately from literal direct source hits."""
    try:
        parsed = urlsplit(url)
        if (
            parsed.scheme != "https"
            or parsed.username is not None
            or parsed.password is not None
            or parsed.port not in {None, 443}
            or parsed.query
            or parsed.fragment
            or parsed.hostname not in reference["hosts"]
        ):
            return None
        if parsed.path in reference["direct_paths"]:
            return "direct"
        if parsed.path in reference["publisher_paths"]:
            return "publisher_link"
    except (TypeError, ValueError):
        return None
    return None


def observation(question, reference, batch, error_code, elapsed):
    """Retain complete ranked metadata and first outcomes without raw provider titles, snippets or error prose."""
    if error_code not in {None, "provider_failed", "not_run_after_error"}:
        raise ValueError("fresh_coverage_error_invalid")
    if (batch is None) != (error_code is not None):
        raise ValueError("fresh_coverage_outcome_invalid")
    rows = []
    if batch is not None:
        hits = validate_batch(batch, "searxng")
        if len(hits) > 5:
            raise ValueError("fresh_coverage_top5_limit")
        rows = [
            dict(
                rank=rank,
                url=hit.url,
                title_sha256=hashlib.sha256(hit.title.encode()).hexdigest(),
                snippet_sha256=hashlib.sha256(hit.snippet.encode()).hexdigest(),
                route=source_route(hit.url, reference),
            )
            for rank, hit in enumerate(hits, 1)
        ]
    logger.info("d60_fresh_coverage_outcome_recorded success=%s", error_code is None)
    return dict(
        query_id=question["id"],
        language=question["language"],
        topic=question["topic"],
        status=error_code or ("results" if rows else "empty"),
        elapsed_seconds=elapsed,
        results=rows,
        direct_rank=next((r["rank"] for r in rows if r["route"] == "direct"), None),
        primary_route_rank=next((r["rank"] for r in rows if r["route"]), None),
    )


def summarize(corpus, rows):
    """Apply frozen eight-question denominators and language/topic thresholds, preserving every error, empty result and miss."""
    questions = corpus["queries"]
    if len(rows) != 8 or [r["query_id"] for r in rows] != [q["id"] for q in questions]:
        raise ValueError("fresh_coverage_rows_incomplete")
    for q, r in zip(questions, rows, strict=True):
        if r["language"] != q["language"] or r["topic"] != q["topic"]:
            raise ValueError("fresh_coverage_labels_changed")
    valid = sum(r["status"] in {"results", "empty"} for r in rows)
    present = sum(r["primary_route_rank"] is not None for r in rows)
    languages = {
        lang: sum(
            r["primary_route_rank"] is not None for r in rows if r["language"] == lang
        )
        for lang in ("en", "vi")
    }
    topics = {
        topic: sum(
            r["primary_route_rank"] is not None for r in rows if r["topic"] == topic
        )
        for topic in TOPICS
    }
    accepted = (
        valid == 8
        and present >= 6
        and min(languages.values()) >= 2
        and min(topics.values()) >= 1
    )
    logger.info("d60_fresh_coverage_summarized accepted=%s", accepted)
    return dict(
        accepted=accepted,
        questions=8,
        valid_responses=valid,
        primary_route_present=present,
        literal_direct_present=sum(r["direct_rank"] is not None for r in rows),
        by_language=languages,
        by_topic=topics,
        semantic_relevance_evaluated=False,
        verified_freshness=None,
        original_direct_metric_rewritten=False,
    )
