"""Join newly executed owner-bound research to fresh catalogue evidence while preserving direct, redirect and observed-publisher provenance."""

import asyncio
import hashlib
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit
from uuid import UUID

from apps.api.services.publisher_evidence import (
    PublisherEvidence,
    PublisherEvidenceResolver,
)
from src.application.ports.research import ResearchQuery, ResearchResult, ResearchSource
from src.application.ports.search import SearchBatch, SearchHit
from src.application.ports.web_evidence import EvidenceRead
from src.application.services.research import cancelled
from src.application.services.research_policy import canonical_query, check_result
from src.application.services.search_pipeline import validate_batch
from src.application.services.web_fetch_policy import public_url
from src.application.services.web_fetch_tasks import finish_owned, spawn_owned
from src.infrastructure.public_https import PublicHTTPSClient
from src.infrastructure.publisher_links import rfc_url

logger = logging.getLogger(__name__)
TOTAL_SECONDS = 75
SOURCE_SECONDS = 30
FAMILIES = ("searxng", "rfc")
ERRORS = frozenset(
    {
        "live_research_invalid",
        "live_research_busy",
        "live_research_closed",
        "live_research_timeout",
        "live_discovery_invalid",
        "live_discovery_stale",
        "live_discovery_incomplete",
        "live_discovery_failed",
        "live_sources_missing",
        "live_source_scope",
        "live_source_failed",
        "live_source_timeout",
    }
)


class LiveResearchError(Exception):
    """Expose finite composition failures without owner, goal, provider prose, URL or backend diagnostics."""

    def __init__(self, code):
        """Retain one known stable error code and an audit event without sensitive input values."""
        self.code = (
            code if type(code) is str and code in ERRORS else "live_research_invalid"
        )
        super().__init__(self.code)
        logger.warning("live_publisher_research_rejected code=%s", self.code)


@dataclass(frozen=True, slots=True, repr=False)
class DiscoveredEvidence:
    """Bind an actually returned locator to fresh evidence and explicitly distinguish publisher children from literal search hits."""

    family: str
    query_id: str
    source_id: str
    search_url: str
    route: str
    evidence: EvidenceRead
    publisher: PublisherEvidence | None
    evidence_is_direct_search_hit: bool


@dataclass(frozen=True, slots=True, repr=False)
class LiveResearchEvidence:
    """Retain one newly executed discovery and its two fresh source bindings in bounded process memory only."""

    discovery: ResearchResult
    sources: tuple[DiscoveredEvidence, ...]
    started_at: datetime
    acquired_at: datetime


def catalogue_route(url, number):
    """Recognize exact trusted source paths without granting authority to snippets, query parameters or guessed aliases."""
    try:
        target = public_url(url)
        parsed = urlsplit(target.url)
        if parsed.query or parsed.fragment:
            return None
        if target.host == "docs.searxng.org" and parsed.path in {
            "/dev/search_api.html",
            "/dev/search_api",
        }:
            return "searxng", "direct"
        if target.host in {"www.rfc-editor.org", "rfc-editor.org"}:
            if parsed.path in {f"/info/rfc{number}", f"/info/rfc{number}/"}:
                rfc_url(url, number, parent=True)
                return "rfc", "publisher_link"
            if parsed.path in {
                f"/rfc/rfc{number}.html",
                f"/rfc/rfc{number}.txt",
                f"/rfc/rfc{number}",
            }:
                return "rfc", "direct"
    except Exception:
        return None
    return None


def utc_time(value):
    """Recognize exact timezone-aware UTC timestamps without coercing strings or naive datetimes."""
    return type(value) is datetime and value.utcoffset() == timedelta(0)


def validate_fresh_discovery(result, owner, goal, started, received):
    """Validate the entire typed discovery and invocation interval before selecting any source or issuing source I/O."""
    try:
        if (
            type(result) is not ResearchResult
            or type(result.run_id) is not UUID
            or result.owner_id != owner
            or type(result.owner_id) is not UUID
            or result.goal != goal
            or result.content_trust != "untrusted"
            or result.evidence_kind != "provider_snippet_not_fetched"
            or result.semantic_validation is not False
            or result.verified_freshness is not None
            or type(result.model_attempts) is not int
            or result.model_attempts != 1
            or type(result.provider_attempts) is not int
            or type(result.queries) is not tuple
            or not 1 <= len(result.queries) <= 3
            or not utc_time(result.completed_at)
        ):
            raise ValueError()
        check_result(result)
        if not started <= result.completed_at <= received:
            raise LiveResearchError("live_discovery_stale")
        queries, sources_present, incomplete, attempts = set(), False, False, 0
        previous_time, unattempted = started, False
        for index, query in enumerate(result.queries, 1):
            if (
                type(query) is not ResearchQuery
                or query.query_id != f"Q{index}"
                or canonical_query(query.query) != query.query
                or query.query in queries
                or type(query.attempted) is not bool
                or type(query.sources) is not tuple
                or len(query.sources) > 5
                or (unattempted and query.attempted)
            ):
                raise ValueError()
            queries.add(query.query)
            attempts += query.attempted
            unattempted = unattempted or not query.attempted
            if query.status in {"sources", "empty"}:
                if (
                    query.attempted is not True
                    or query.error_code is not None
                    or not utc_time(query.received_at)
                    or not previous_time <= query.received_at <= result.completed_at
                    or bool(query.sources) != (query.status == "sources")
                ):
                    raise ValueError()
                previous_time = query.received_at
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
                incomplete = True
            else:
                raise ValueError()
            hits = []
            for rank, source in enumerate(query.sources, 1):
                if (
                    type(source) is not ResearchSource
                    or source.source_id != f"Q{index}:S{rank}"
                    or type(source.snippet) is not str
                    or source.snippet_sha256
                    != hashlib.sha256(source.snippet.encode()).hexdigest()
                ):
                    raise ValueError()
                hits.append(SearchHit(source.title, source.url, source.snippet))
            validate_batch(SearchBatch("live_catalogue", tuple(hits)), "live_catalogue")
            sources_present = sources_present or bool(hits)
        expected = (
            "no_sources"
            if not sources_present
            else "partial"
            if incomplete
            else "complete"
        )
        if result.status != expected or result.provider_attempts != attempts:
            raise ValueError()
        if result.status != "complete":
            raise LiveResearchError("live_discovery_incomplete")
    except LiveResearchError:
        raise
    except Exception:
        raise LiveResearchError("live_discovery_invalid") from None
    logger.info("live_research_fresh_discovery_verified queries=%d", len(queries))


class CatalogueHTTPClient:
    """Restrict every source transport hop to the host-configured catalogue before unchanged public HTTPS validation."""

    def __init__(self, number, client):
        """Bind inert trusted dependencies without DNS, HTTP, source cache or provider access."""
        self.number, self.client = number, client

    async def get(self, url):
        """Reject unknown or parameter-bearing source hops before delegating one accepted public request."""
        if catalogue_route(url, self.number) is None:
            raise LiveResearchError("live_source_scope")
        logger.info("live_catalogue_source_hop_admitted")
        return await self.client.get(url)


class LivePublisherResearchService:
    """Own one new research-to-source operation without accepting archives, source overrides, automatic retries or production registration."""

    def __init__(self, research, *, number, client=None):
        """Borrow the trusted research port and own only this composition's resolver, admission and proof lifetime."""
        transport = CatalogueHTTPClient(
            number, client if client is not None else PublicHTTPSClient()
        )
        self.resolver = PublisherEvidenceResolver(number, client=transport)
        self.research, self.number = research, number
        self.admission, self.operations = asyncio.Lock(), set()
        self.closing, self.last_discovery = False, None
        logger.info("live_publisher_research_initialized")

    @property
    def evidence(self):
        """Expose the owned issuer to existing report composition without changing proof or permission rules."""
        return self.resolver.evidence

    async def _run(self, owner, goal):
        """Execute new discovery and acquire only its selected direct or observed-publisher evidence within unchanged nested budgets."""
        started = datetime.now(UTC)
        try:
            discovery = await self.research.research(owner, goal)
            cancelled()
        except asyncio.CancelledError:
            raise
        except Exception:
            raise LiveResearchError("live_discovery_failed") from None
        self.last_discovery = discovery
        validate_fresh_discovery(discovery, owner, goal, started, datetime.now(UTC))
        selected = {}
        for query in discovery.queries:
            for source in query.sources:
                route = catalogue_route(source.url, self.number)
                if route is not None and route[0] not in selected:
                    selected[route[0]] = query.query_id, source, route[1]
        if set(selected) != set(FAMILIES):
            raise LiveResearchError("live_sources_missing")
        bindings = []
        try:
            async with asyncio.timeout(SOURCE_SECONDS) as source_deadline:
                for family in FAMILIES:
                    query_id, source, route = selected[family]
                    publisher = None
                    if route == "publisher_link":
                        publisher = await self.resolver.resolve(
                            owner, discovery, source.source_id
                        )
                        read = publisher.child
                    else:
                        read = await self.evidence.read(
                            owner, source.url, "static", use_cache=False
                        )
                    cancelled()
                    if (
                        type(read) is not EvidenceRead
                        or read.cache_hit is not False
                        or catalogue_route(read.snapshot.final_url, self.number)
                        != (family, "direct")
                        or read.snapshot.fetch_started_at < discovery.completed_at
                    ):
                        raise LiveResearchError("live_source_scope")
                    self.evidence.cite(owner, read.snapshot, 0, 1)
                    bindings.append(
                        DiscoveredEvidence(
                            family,
                            query_id,
                            source.source_id,
                            source.url,
                            route,
                            read,
                            publisher,
                            route == "direct" and source.url == read.snapshot.final_url,
                        )
                    )
                if source_deadline.expired():
                    raise TimeoutError()
        except asyncio.CancelledError:
            raise
        except TimeoutError:
            raise LiveResearchError("live_source_timeout") from None
        except LiveResearchError:
            raise
        except Exception:
            raise LiveResearchError("live_source_failed") from None
        cancelled()
        logger.info("live_publisher_research_sources_acquired sources=2")
        return LiveResearchEvidence(
            discovery, tuple(bindings), started, datetime.now(UTC)
        )

    async def acquire(self, owner, goal):
        """Start a fresh owner/goal invocation and retain nonqueued admission until all dependency cancellation cleanup has joined."""
        if type(owner) is not UUID:
            raise LiveResearchError("live_research_invalid")
        try:
            goal = canonical_query(goal)
        except Exception:
            raise LiveResearchError("live_research_invalid") from None
        if self.closing:
            raise LiveResearchError("live_research_closed")
        if self.admission.locked():
            raise LiveResearchError("live_research_busy")
        await self.admission.acquire()
        caller, child = asyncio.current_task(), None
        self.operations.add(caller)
        self.last_discovery = None
        try:
            async with asyncio.timeout(TOTAL_SECONDS) as deadline:
                child = spawn_owned(self._run(owner, goal))
                try:
                    value = await asyncio.shield(child)
                except asyncio.CancelledError:
                    child.cancel()
                    try:
                        await finish_owned(child)
                    except BaseException:
                        logger.info("live_research_cancel_cleanup_joined")
                    raise
                if deadline.expired():
                    raise TimeoutError()
                cancelled()
                return value
        except TimeoutError:
            raise LiveResearchError("live_research_timeout") from None
        finally:
            self.operations.discard(caller)
            self.admission.release()
            logger.info("live_publisher_research_operation_closed")

    async def shutdown(self):
        """Join owned invocations and revoke owned source proofs without stopping borrowed research, models or shared services."""
        self.closing = True
        tasks = tuple(t for t in self.operations if t is not asyncio.current_task())
        for task in tasks:
            task.cancel()
        for task in tasks:
            try:
                await finish_owned(task)
            except BaseException:
                logger.info("live_research_shutdown_operation_joined")
        await self.resolver.shutdown()
        self.last_discovery = None
        logger.info("live_publisher_research_shutdown_complete")
