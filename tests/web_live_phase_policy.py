"""Project live discovery metadata and select only actually returned frozen primary-source URLs and exact bounded quote spans for D60 evaluation."""

import hashlib
import logging
from datetime import datetime, timedelta
from uuid import UUID

from src.application.ports.research import ResearchQuery, ResearchResult, ResearchSource
from src.application.ports.search import SearchBatch, SearchHit
from src.application.ports.source_reconciliation import SourceSpan
from src.application.services.research_policy import canonical_query, check_result
from src.application.services.search_pipeline import validate_batch
from src.application.services.web_fetch_policy import public_url

logger = logging.getLogger(__name__)
PRIMARY_FAMILIES = (
    ("searxng", ("docs.searxng.org",), ("/dev/search_api.html", "/dev/search_api")),
    (
        "rfc",
        ("rfc-editor.org", "www.rfc-editor.org"),
        ("/rfc/rfc9111.html", "/rfc/rfc9111.txt", "/rfc/rfc9111"),
    ),
)
QUOTE_MARKERS = {
    "searxng": ("Two endpoints,", "methods."),
    "rfc": ("The unqualified private response directive", "store the response"),
}
ERRORS = frozenset(
    {
        "live_input_invalid",
        "live_missing_primary_sources",
        "live_quote_unavailable",
        "live_quote_limit",
    }
)


class LivePhaseError(Exception):
    """Expose finite evaluation failures without original provider/page/query text or native diagnostics."""

    def __init__(self, code):
        """Retain one known evaluation-only failure identifier and metadata log."""
        self.code = (
            code if type(code) is str and code in ERRORS else "live_input_invalid"
        )
        super().__init__(self.code)
        logger.warning("web_live_phase_rejected code=%s", self.code)


def check_live_result(result, owner, goal):
    """Check the exact full typed run, original attempt/state prefixes, complete source IDs/hashes and UTC fields before minimizing it."""
    check_result(result)
    if (
        type(result) is not ResearchResult
        or type(owner) is not UUID
        or type(result.run_id) is not UUID
        or canonical_query(goal) != goal
        or result.owner_id != owner
        or result.goal != goal
        or type(result.queries) is not tuple
        or not 1 <= len(result.queries) <= 3
        or type(result.model_attempts) is not int
        or result.model_attempts != 1
        or type(result.provider_attempts) is not int
        or result.content_trust != "untrusted"
        or result.semantic_validation is not False
        or result.verified_freshness is not None
        or result.evidence_kind != "provider_snippet_not_fetched"
        or type(result.completed_at) is not datetime
        or result.completed_at.utcoffset() != timedelta(0)
    ):
        raise ValueError()
    seen_unattempted = False
    for index, query in enumerate(result.queries, 1):
        if (
            type(query) is not ResearchQuery
            or query.query_id != f"Q{index}"
            or canonical_query(query.query) != query.query
            or type(query.sources) is not tuple
            or len(query.sources) > 5
            or type(query.attempted) is not bool
        ):
            raise ValueError()
        if query.attempted and seen_unattempted:
            raise ValueError()
        seen_unattempted = seen_unattempted or not query.attempted
        if query.status in {"sources", "empty"}:
            if (
                not query.attempted
                or query.error_code is not None
                or type(query.received_at) is not datetime
                or query.received_at.utcoffset() != timedelta(0)
                or bool(query.sources) != (query.status == "sources")
            ):
                raise ValueError()
        elif query.status in {"error", "not_run_budget", "not_run_quota"}:
            if (
                query.attempted != (query.status == "error")
                or query.sources
                or query.received_at is not None
                or query.error_code
                not in {
                    "research_provider_failed",
                    "research_provider_timeout",
                    "research_timeout",
                    "research_rate_limited",
                }
            ):
                raise ValueError()
        else:
            raise ValueError()
        hits = []
        for rank, source in enumerate(query.sources, 1):
            if (
                type(source) is not ResearchSource
                or source.source_id != f"Q{index}:S{rank}"
                or type(source.snippet) is not str
                or hashlib.sha256(source.snippet.encode()).hexdigest()
                != source.snippet_sha256
            ):
                raise ValueError()
            hits.append(SearchHit(source.title, source.url, source.snippet))
        validate_batch(SearchBatch("metadata", tuple(hits)), "metadata")
    has_sources = any(query.sources for query in result.queries)
    incomplete = any(
        query.status in {"error", "not_run_budget", "not_run_quota"}
        for query in result.queries
    )
    expected = (
        "no_sources" if not has_sources else "partial" if incomplete else "complete"
    )
    if (
        result.status != expected
        or result.provider_attempts != sum(query.attempted for query in result.queries)
        or len({query.query for query in result.queries}) != len(result.queries)
    ):
        raise ValueError()


def discovery_metadata(result, owner, goal):
    """Retain every bounded outcome/attempt/source ID/URL/hash while explicitly excluding raw actual provider titles/snippets and queries."""
    try:
        check_live_result(result, owner, goal)
        queries = []
        for row in result.queries:
            queries.append(
                dict(
                    query_id=row.query_id,
                    query_sha256=hashlib.sha256(row.query.encode()).hexdigest(),
                    status=row.status,
                    attempted=row.attempted,
                    error_code=row.error_code,
                    received_at=row.received_at,
                    sources=[
                        dict(
                            source_id=source.source_id,
                            url=source.url,
                            title_sha256=hashlib.sha256(
                                source.title.encode()
                            ).hexdigest(),
                            snippet_sha256=source.snippet_sha256,
                        )
                        for source in row.sources
                    ],
                )
            )
        value = dict(
            description="Complete live discovery outcome metadata; original provider/query text was not retained.",
            schema_version="live-discovery-metadata-v1",
            raw_provider_payload_retained=False,
            raw_query_text_retained=False,
            result_status=result.status,
            model_attempts=result.model_attempts,
            provider_attempts=result.provider_attempts,
            completed_at=result.completed_at,
            queries=queries,
            content_trust="untrusted",
            semantic_validation=False,
            verified_freshness=None,
        )
        logger.info("web_live_discovery_metadata_projected queries=%d", len(queries))
        return value
    except Exception:
        raise LivePhaseError("live_input_invalid") from None


def source_family(url):
    """Recognize only fixed primary host/path families after original strict public-URL admission, preserving the returned URL itself."""
    try:
        target = public_url(url)
        path = target.target.decode("ascii").split("?", 1)[0]
        for name, hosts, paths in PRIMARY_FAMILIES:
            if target.host in hosts and path in paths:
                return name
    except Exception:
        pass
    return None


def select_primary(metadata):
    """Choose the first actually returned result for each frozen primary family without synthesizing URLs, canonical aliases or fallback."""
    selected = {}
    try:
        if (
            metadata["schema_version"] != "live-discovery-metadata-v1"
            or metadata["raw_provider_payload_retained"] is not False
        ):
            raise ValueError()
        for query in metadata["queries"]:
            for rank, row in enumerate(query["sources"], 1):
                family = source_family(row["url"])
                if family is not None and family not in selected:
                    selected[family] = dict(
                        family=family,
                        url=row["url"],
                        source_id=row["source_id"],
                        query_id=query["query_id"],
                        rank=rank,
                    )
        if set(selected) != {"searxng", "rfc"}:
            raise LivePhaseError("live_missing_primary_sources")
        logger.info("web_live_actual_primary_results_selected count=2")
        return tuple(selected[name] for name in ("searxng", "rfc"))
    except LivePhaseError:
        raise
    except Exception:
        raise LivePhaseError("live_input_invalid") from None


def exact_quote(snapshot, family):
    """Select one unique predeclared literal start/end-marker range and refuse missing, ambiguous or oversized source excerpts."""
    try:
        if family not in QUOTE_MARKERS or source_family(snapshot.final_url) != family:
            raise ValueError()
        start_marker, end_marker = QUOTE_MARKERS[family]
        if snapshot.text.count(start_marker) != 1:
            raise ValueError()
        start = snapshot.text.index(start_marker)
        end = snapshot.text.index(end_marker, start) + len(end_marker)
        quote = snapshot.text[start:end]
        if len(quote.split()) > 25 or len(quote.encode()) > 512:
            raise LivePhaseError("live_quote_limit")
        logger.info(
            "web_live_exact_primary_quote_selected words=%d", len(quote.split())
        )
        return SourceSpan(snapshot, start, end)
    except LivePhaseError:
        raise
    except Exception:
        raise LivePhaseError("live_quote_unavailable") from None
