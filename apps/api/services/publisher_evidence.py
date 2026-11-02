"""Compose explicit owner-bound discovery locators, fresh publisher anchors and signed full-text evidence without search-hit relabeling or implicit crawling."""

import asyncio
import logging
from dataclasses import dataclass
from urllib.parse import urljoin
from uuid import UUID

from src.application.ports.research import ResearchResult
from src.application.ports.web_evidence import EvidenceRead
from src.application.services.web_evidence import WebEvidenceService
from src.application.services.web_evidence_policy import WebEvidenceError
from src.application.services.web_fetch_tasks import finish_owned, spawn_owned
from src.infrastructure.public_https import PublicHTTPSClient
from src.infrastructure.publisher_links import PublisherSource, rfc_url

logger = logging.getLogger(__name__)


class PublisherEvidenceIssuer(WebEvidenceService):
    """Admit explicit anchor-only RFC parents after common source guards without broadening the default evidence issuer."""

    _static_extractors = frozenset({"static-html-utf8-v1", "publisher-anchors-utf8-v1"})

    def validate_source(self, observation, url, mode):
        """Require truthful parent-only metadata and exact trusted raw-anchor binding before signing a new extractor kind."""
        super().validate_source(observation, url, mode)
        page = observation.page
        if mode != "static" or page.extractor_version != "publisher-anchors-utf8-v1":
            return
        try:
            rfc_url(url, self.source.number, parent=True)
            final, child, sha, anchors = self.source.parent_binding
            rfc_url(final, self.source.number, parent=True)
            rfc_url(child, self.source.number, parent=False)
            for row in anchors:
                if (
                    type(row) is not tuple
                    or len(row) != 4
                    or type(row[0]) is not str
                    or not 0 < len(row[0]) <= 2048
                    or row[0] != row[0].strip()
                    or type(row[2]) is not int
                    or row[2] < 1
                    or type(row[3]) is not int
                    or row[3] < 0
                    or rfc_url(urljoin(final, row[0]), self.source.number, parent=False)
                    != child
                ):
                    raise ValueError("publisher_anchor_metadata")
            if (
                final != page.final_url
                or sha != page.body_sha256
                or page.text != "\n".join(row[0] for row in anchors)
                or page.title is not None
                or observation.dates != ()
                or observation.cache_seconds != 0
                or page.advertised_canonical_url is not None
                or not anchors
                or any(row[1] != child for row in anchors)
            ):
                raise ValueError("publisher_parent_metadata")
        except Exception:
            raise WebEvidenceError("evidence_integrity") from None
        logger.info("publisher_anchor_only_source_verified")


@dataclass(frozen=True, slots=True, repr=False)
class PublisherEvidence:
    """Retain distinct discovery identity, original landing/anchor binding and newly signed child without a freshness or semantic claim."""

    owner_id: UUID
    discovery_run_id: UUID
    source_id: str
    parent: EvidenceRead
    child: EvidenceRead
    parent_body_sha256: str
    observed_anchors: tuple
    child_is_search_hit: bool = False
    discovery_is_source_proof: bool = False


class PublisherEvidenceResolver:
    """Own one nonqueued explicit RFC resolution while retaining signed evidence until shutdown and joining cancellation before release."""

    def __init__(self, number, *, client=None):
        """Bind an opt-in exact publisher policy and existing transport without changing shared services or issuing requests."""
        self.number = number
        self.source = PublisherSource(
            number, client if client is not None else PublicHTTPSClient()
        )
        self.evidence = PublisherEvidenceIssuer(self.source)
        self.admission, self.operations, self.closing = asyncio.Lock(), set(), False
        logger.info("publisher_evidence_resolver_initialized")

    async def resolve(self, owner, discovery, source_id):
        """Use a trusted composition's exact owner/query locator, fetch the present anchor and issue fresh parent/child source proofs."""
        if self.closing or self.admission.locked():
            raise ValueError("publisher_closed_or_busy")
        if (
            type(owner) is not UUID
            or type(discovery) is not ResearchResult
            or discovery.owner_id != owner
            or type(discovery.run_id) is not UUID
            or type(source_id) is not str
        ):
            raise ValueError("publisher_owner_or_discovery_invalid")
        hits = [
            source
            for query in discovery.queries
            if query.attempted is True and query.status == "sources"
            for source in query.sources
            if source.source_id == source_id
        ]
        if len(hits) != 1:
            raise ValueError("publisher_discovery_source_missing_or_ambiguous")
        url = rfc_url(hits[0].url, self.number, parent=True)
        task = asyncio.current_task()
        async with self.admission:
            self.operations.add(task)
            child = None
            try:
                child = spawn_owned(
                    self._resolve(owner, discovery.run_id, source_id, url)
                )
                return await asyncio.shield(child)
            except asyncio.CancelledError:
                if child is not None and not child.done():
                    child.cancel()
                if child is not None:
                    try:
                        await finish_owned(child)
                    except BaseException:
                        logger.info("publisher_resolution_cancel_joined")
                raise
            finally:
                self.operations.discard(task)

    async def _resolve(self, owner, run_id, source_id, url):
        """Reacquire both pages with no cache fallback, revalidate the parent after child I/O and keep all provenance separate."""
        async with asyncio.timeout(30):
            parent = await self.evidence.read(owner, url, use_cache=False)
            final, target, sha, anchors = self.source.parent_binding
            if (
                final != parent.snapshot.final_url
                or sha != parent.snapshot.resources[-1].body_sha256
            ):
                raise ValueError("publisher_parent_proof_mismatch")
            child = await self.evidence.read(owner, target, use_cache=False)
            for value in (parent, child):
                self.evidence.cite(owner, value.snapshot, 0, 1)
            logger.info("publisher_source_chain_completed child_is_search_hit=False")
            return PublisherEvidence(
                owner, run_id, source_id, parent, child, sha, anchors
            )

    async def shutdown(self):
        """Close admission, join only owned operations and revoke this resolver's source proof key without stopping shared services."""
        self.closing = True
        tasks = tuple(
            task for task in self.operations if task is not asyncio.current_task()
        )
        for task in tasks:
            task.cancel()
        for task in tasks:
            try:
                await finish_owned(task)
            except BaseException:
                logger.info("publisher_shutdown_operation_joined")
        await self.evidence.shutdown()
        logger.info("publisher_evidence_resolver_closed")
