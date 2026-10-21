"""Own bounded private source provenance, exact-content reuse and signed quote references without models or persistent state."""

import asyncio
import hashlib
import hmac
import logging
import math
import re
import secrets
import time
from collections import OrderedDict
from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID, uuid4

from src.application.ports.browser import BrowserPage, BrowserResource
from src.application.ports.web_evidence import (
    EvidenceRead,
    EvidenceReference,
    EvidenceResource,
    EvidenceSnapshot,
    ObservedSource,
    SourceDateClaim,
)
from src.application.ports.web_fetch import FetchedPage
from src.application.services.web_evidence_policy import (
    WebEvidenceError,
    snapshot_bytes,
)
from src.application.services.web_fetch_policy import public_url
from src.application.services.web_fetch_tasks import finish_owned, spawn_owned

logger = logging.getLogger(__name__)
SHA256 = re.compile(r"[0-9a-f]{64}")


class WebEvidenceService:
    """Retain only bounded owner-scoped cache entries and join explicit source acquisitions before admitting another caller."""

    def __init__(self, source, *, monotonic=None, utcnow=None):
        """Bind an inert trusted source/clock seam and ephemeral proof key without network, filesystem or model activity."""
        self.source = source
        self.monotonic = monotonic if monotonic is not None else time.monotonic
        self.utcnow = utcnow if utcnow is not None else self.system_utc
        self.proof_key = secrets.token_bytes(32)
        self.cache = OrderedDict()
        self.last_tick = None
        self.admission = asyncio.Lock()
        self.operations = set()
        self.closing = False
        logger.info("web_evidence_service_initialized")

    @staticmethod
    def system_utc():
        """Read aware host UTC separately from untrusted page date declarations."""
        return datetime.now(UTC)

    def tick(self):
        """Reject invalid/backward monotonic time instead of extending cached source lifetime."""
        value = self.monotonic()
        if (
            type(value) not in {int, float}
            or not math.isfinite(value)
            or value < 0
            or (self.last_tick is not None and value < self.last_tick)
        ):
            self.closing = True
            raise WebEvidenceError("evidence_clock_invalid")
        self.last_tick = float(value)
        return self.last_tick

    def utc(self):
        """Require an aware trusted host timestamp and serialize source acquisition times in UTC."""
        value = self.utcnow()
        if (
            type(value) is not datetime
            or value.tzinfo is None
            or value.utcoffset() is None
        ):
            raise WebEvidenceError("evidence_clock_invalid")
        return value.astimezone(UTC)

    def expire(self, tick):
        """Evict every expired source entry without changing any original acquisition record."""
        for key, (_, deadline, _) in list(self.cache.items()):
            if tick >= deadline:
                del self.cache[key]
        logger.info("web_evidence_expiration_checked")

    def cache_bytes(self):
        """Account exact private text once per owner/content and serialized metadata per retained source record."""
        blobs, total = set(), 0
        for snapshot, _, _ in self.cache.values():
            key = (snapshot.owner_id, snapshot.text_sha256)
            if key not in blobs:
                total += len(snapshot.text.encode())
                blobs.add(key)
            total += len(snapshot_bytes(snapshot, text=False))
        return total

    def sign(self, snapshot):
        """Authenticate every immutable source/content/time/owner field with this service's ephemeral integrity key."""
        return hmac.digest(
            self.proof_key, snapshot_bytes(snapshot, proof=False), "sha256"
        ).hex()

    def validate_source(self, observation, url, mode):
        """Reject malformed or drifted trusted-port evidence before issuing a source snapshot or making it reusable."""
        if type(observation) is not ObservedSource:
            raise WebEvidenceError("evidence_integrity")
        page = observation.page
        expected = FetchedPage if mode == "static" else BrowserPage
        if (
            type(page) is not expected
            or page.requested_url != url
            or public_url(page.final_url).url != page.final_url
        ):
            raise WebEvidenceError("evidence_integrity")
        if (
            type(page.text) is not str
            or not 1 <= len(page.text.encode()) <= 131072
            or (
                page.title is not None
                and (type(page.title) is not str or len(page.title.encode()) > 1024)
            )
        ):
            raise WebEvidenceError("evidence_limit")
        if (
            page.text_sha256 != hashlib.sha256(page.text.encode()).hexdigest()
            or page.content_trust != "untrusted"
        ):
            raise WebEvidenceError("evidence_integrity")
        if (
            type(observation.cache_seconds) is not int
            or not 0 <= observation.cache_seconds <= 300
        ):
            raise WebEvidenceError("evidence_integrity")
        if type(observation.dates) is not tuple or len(observation.dates) > 4:
            raise WebEvidenceError("evidence_limit")
        for claim in observation.dates:
            if (
                type(claim) is not SourceDateClaim
                or claim.kind not in {"published", "modified", "unspecified"}
                or type(claim.raw_value) is not str
                or not 1 <= len(claim.raw_value.encode()) <= 128
                or (
                    claim.parsed_iso is not None
                    and (
                        type(claim.parsed_iso) is not str or len(claim.parsed_iso) > 128
                    )
                )
                or type(claim.timezone_present) is not bool
                or claim.verified is not False
            ):
                raise WebEvidenceError("evidence_integrity")
        if (
            type(observation.resources) is not tuple
            or not 1 <= len(observation.resources) <= 32
        ):
            raise WebEvidenceError("evidence_limit")
        total, documents = 0, []
        for resource in observation.resources:
            if (
                type(resource) is not EvidenceResource
                or public_url(resource.url).url != resource.url
                or resource.kind
                not in {"Document", "Script", "Stylesheet", "XHR", "Fetch"}
                or type(resource.status) is not int
                or resource.status not in {200, 301, 302, 303, 307, 308}
                or type(resource.body_bytes) is not int
                or not 0 <= resource.body_bytes <= 1048576
                or type(resource.body_sha256) is not str
                or not SHA256.fullmatch(resource.body_sha256)
            ):
                raise WebEvidenceError("evidence_integrity")
            total += resource.body_bytes
            if resource.kind == "Document" and resource.status == 200:
                documents.append(resource)
        if total > 8388608 or len(documents) != 1 or documents[0].url != page.final_url:
            raise WebEvidenceError("evidence_integrity")
        if mode == "static":
            if (
                page.canonical_verified is not False
                or page.body_sha256 != documents[0].body_sha256
                or page.extractor_version != "static-html-utf8-v1"
            ):
                raise WebEvidenceError("evidence_integrity")
            if (
                type(page.redirects) is not tuple
                or len(page.redirects) > 3
                or len(observation.resources) != len(page.redirects) + 1
            ):
                raise WebEvidenceError("evidence_integrity")
            current_url = url
            for pair, resource in zip(page.redirects, observation.resources):
                if (
                    type(pair) is not tuple
                    or len(pair) != 2
                    or pair[0] != current_url
                    or resource.url != current_url
                    or resource.kind != "Document"
                    or resource.status not in {301, 302, 303, 307, 308}
                ):
                    raise WebEvidenceError("evidence_integrity")
                current_url = public_url(pair[1]).url
            if (
                current_url != page.final_url
                or observation.resources[-1] != documents[0]
                or page.media_type not in {"text/html", "text/plain"}
            ):
                raise WebEvidenceError("evidence_integrity")
            if (
                page.advertised_canonical_url is not None
                and public_url(page.advertised_canonical_url).url
                != page.advertised_canonical_url
            ):
                raise WebEvidenceError("evidence_integrity")
        elif (
            page.browser_direct_network is not False
            or page.semantic_validation is not False
        ):
            raise WebEvidenceError("evidence_integrity")
        elif (
            type(page.resources) is not tuple
            or any(type(resource) is not BrowserResource for resource in page.resources)
            or tuple(
                EvidenceResource(
                    resource.url,
                    resource.kind,
                    resource.status,
                    resource.body_bytes,
                    resource.body_sha256,
                )
                for resource in page.resources
            )
            != observation.resources
            or page.evidence_kind != "isolated_browser_layout_text"
        ):
            raise WebEvidenceError("evidence_integrity")
        logger.info("web_evidence_original_source_validated")

    def snapshot(self, owner, url, mode, observation, started_at, fetched_at, tick):
        """Issue distinct acquisition provenance while sharing only exact matching text already retained for this owner."""
        self.validate_source(observation, url, mode)
        page, text = observation.page, observation.page.text
        for previous, _, _ in self.cache.values():
            if previous.owner_id == owner and previous.text_sha256 == page.text_sha256:
                if previous.text != text:
                    raise WebEvidenceError("evidence_integrity")
                text = previous.text
                break
        content_id = hmac.digest(
            self.proof_key, owner.bytes + bytes.fromhex(page.text_sha256), "sha256"
        ).hex()
        result = EvidenceSnapshot(
            uuid4(),
            owner,
            url,
            page.final_url,
            page.title,
            mode,
            page.extractor_version
            if mode == "static"
            else "isolated-browser-layout-v1",
            started_at,
            fetched_at,
            observation.dates,
            text,
            page.text_sha256,
            content_id,
            observation.resources,
            page.advertised_canonical_url if mode == "static" else None,
            tick + 300.0,
            "",
        )
        result = replace(result, proof=self.sign(result))
        snapshot_bytes(result)
        logger.info("web_evidence_snapshot_issued")
        return result

    def retain(self, key, snapshot, deadline, acquired):
        """Apply owner/global LRU and accounted-byte bounds without erasing separate URL acquisition provenance."""
        self.cache.pop(key, None)
        owned = [
            existing for existing in self.cache if existing[0] == snapshot.owner_id
        ]
        while len(owned) >= 4:
            del self.cache[owned.pop(0)]
        self.cache[key] = (snapshot, deadline, acquired)
        while len(self.cache) > 16 or self.cache_bytes() > 4194304:
            self.cache.popitem(last=False)
        logger.info("web_evidence_private_cache_retained entries=%d", len(self.cache))

    async def acquire(self, owner, url, mode, start_tick, started_at):
        """Acquire exactly one explicit source and publish cache state only after source cleanup and validated provenance."""
        observation = await self.source.read(url, mode)
        if asyncio.current_task().cancelling():
            raise asyncio.CancelledError()
        tick, fetched_at = self.tick(), self.utc()
        if fetched_at < started_at:
            raise WebEvidenceError("evidence_clock_invalid")
        result = self.snapshot(
            owner, url, mode, observation, started_at, fetched_at, tick
        )
        deadline = start_tick + observation.cache_seconds
        if tick < deadline:
            self.retain((owner, mode, url), result, deadline, tick)
        else:
            self.cache.pop((owner, mode, url), None)
            logger.info("web_evidence_noncacheable_snapshot_not_retained")
        return EvidenceRead(result, False, fetched_at, 0.0)

    async def read(self, owner, url, mode="static", *, use_cache=True):
        """Return a visible original-time hit or join one fresh explicit source acquisition without cache fallback on failure."""
        if (
            type(owner) is not UUID
            or type(mode) is not str
            or mode not in {"static", "dynamic"}
            or type(use_cache) is not bool
        ):
            raise WebEvidenceError("evidence_invalid")
        try:
            url = public_url(url).url
        except Exception:
            raise WebEvidenceError("evidence_invalid") from None
        if self.closing:
            raise WebEvidenceError("evidence_closed")
        if self.admission.locked():
            raise WebEvidenceError("evidence_busy")
        await self.admission.acquire()
        caller = asyncio.current_task()
        try:
            self.operations.add(caller)
            tick, served_at = self.tick(), self.utc()
            self.expire(tick)
            key = (owner, mode, url)
            if use_cache and key in self.cache:
                snapshot, _, acquired = self.cache[key]
                self.cache.move_to_end(key)
                logger.info("web_evidence_private_cache_hit")
                return EvidenceRead(snapshot, True, served_at, tick - acquired)
            task = spawn_owned(self.acquire(owner, url, mode, tick, served_at))
            try:
                return await asyncio.shield(task)
            except asyncio.CancelledError:
                task.cancel()
                try:
                    await finish_owned(task)
                except BaseException as error:
                    if getattr(error, "code", None) == "browser_cleanup_uncertain":
                        self.closing = True
                    logger.info("web_evidence_cancelled_source_joined")
                raise
        except asyncio.CancelledError:
            raise
        except WebEvidenceError:
            raise
        except Exception as error:
            if getattr(error, "code", None) == "browser_cleanup_uncertain":
                self.closing = True
            logger.info("web_evidence_source_rejected")
            raise WebEvidenceError("evidence_source_failed") from None
        finally:
            self.operations.discard(caller)
            self.admission.release()
            logger.info("web_evidence_operation_closed")

    def cite(self, owner, snapshot, start, end):
        """Authenticate an issued snapshot and copy only a bounded exact code-point quote, with original source/fetch metadata."""
        if self.closing:
            raise WebEvidenceError("evidence_closed")
        if (
            type(owner) is not UUID
            or type(snapshot) is not EvidenceSnapshot
            or snapshot.owner_id != owner
            or type(snapshot.proof) is not str
            or not SHA256.fullmatch(snapshot.proof)
        ):
            raise WebEvidenceError("evidence_integrity")
        try:
            valid = hmac.compare_digest(self.sign(snapshot), snapshot.proof)
        except Exception:
            raise WebEvidenceError("evidence_integrity") from None
        if not valid:
            raise WebEvidenceError("evidence_integrity")
        if self.tick() >= snapshot.citation_deadline:
            raise WebEvidenceError("evidence_expired")
        if (
            type(start) is not int
            or type(end) is not int
            or not 0 <= start < end <= len(snapshot.text)
        ):
            raise WebEvidenceError("evidence_invalid")
        quote = snapshot.text[start:end]
        if len(quote.encode()) > 4096:
            raise WebEvidenceError("evidence_limit")
        logger.info("web_evidence_exact_span_bound")
        return EvidenceReference(
            snapshot.identifier,
            snapshot.content_id,
            start,
            end,
            quote,
            hashlib.sha256(quote.encode()).hexdigest(),
            snapshot.final_url,
            snapshot.title,
            snapshot.fetched_at,
            snapshot.date_claims,
        )

    async def shutdown(self):
        """Close admission, join only owned operations, revoke ephemeral proof use and clear only this service's memory."""
        self.closing = True
        for task in list(self.operations):
            if task is not asyncio.current_task():
                task.cancel()
        for task in list(self.operations):
            if task is not asyncio.current_task():
                try:
                    await finish_owned(task)
                except BaseException:
                    logger.info("web_evidence_shutdown_operation_joined")
        self.cache.clear()
        self.proof_key = b""
        logger.info("web_evidence_shutdown_complete")
