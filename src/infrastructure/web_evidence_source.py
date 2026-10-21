"""Observe original-response metadata while delegating accepted static fetch and isolated browser ownership unchanged."""

import hashlib
import logging

from src.application.ports.web_evidence import EvidenceResource, ObservedSource
from src.application.services.browser_policy import resource_representation
from src.application.services.web_evidence_policy import (
    WebEvidenceError,
    cache_lifetime,
)
from src.application.services.web_fetch_policy import public_url, representation
from src.infrastructure.browser_resources import BrowserResourceClient
from src.infrastructure.evidence_metadata import source_dates
from src.infrastructure.public_https import PublicHTTPSClient
from src.infrastructure.readonly_browser import ReadOnlyBrowser
from src.infrastructure.web_fetch import BoundedWebFetcher

logger = logging.getLogger(__name__)


class ResponseObservation:
    """Retain bounded source/date/cache metadata only, never raw response bytes after delegated extraction finishes."""

    def __init__(self, client, *, dynamic=False, utcnow=None):
        """Bind one trusted original-response client and empty per-acquisition metadata without I/O."""
        self.client, self.dynamic = client, dynamic
        self.utcnow = utcnow
        self.records, self.dates, self.cache_seconds = [], (), 300
        self.document_url = None
        logger.info("web_evidence_response_observer_initialized")

    async def get(self, url, kind="Document"):
        """Delegate one actual response and preserve its bounded metadata without changing TLS, bytes, status or headers."""
        response = (
            await self.client.get(url, kind)
            if self.dynamic
            else await self.client.get(url)
        )
        if len(self.records) >= 32:
            raise WebEvidenceError("evidence_limit")
        self.cache_seconds = min(
            self.cache_seconds,
            cache_lifetime(
                response.headers, now=self.utcnow() if self.utcnow is not None else None
            ),
        )
        self.records.append(
            EvidenceResource(
                url,
                kind,
                response.status,
                len(response.body),
                hashlib.sha256(response.body).hexdigest(),
            )
        )
        if kind == "Document" and response.status == 200:
            media, encoding = (
                resource_representation(response.headers, kind)
                if self.dynamic
                else representation(response.headers)
            )
            self.document_url = url
            self.dates = source_dates(response.body, media, encoding)
        logger.info("web_evidence_response_metadata_observed")
        return response


class ObservedWebSource:
    """Return explicit-mode source evidence only after accepted per-operation static/browser cleanup is joined."""

    def __init__(
        self,
        *,
        static_client=None,
        browser_resources=None,
        worker_factory=None,
        utcnow=None,
    ):
        """Bind inert original clients and an optional trusted native test seam without network, model or filesystem activity."""
        self.static_client = (
            static_client if static_client is not None else PublicHTTPSClient()
        )
        self.browser_resources = (
            browser_resources
            if browser_resources is not None
            else BrowserResourceClient()
        )
        self.worker_factory = worker_factory
        self.utcnow = utcnow
        logger.info("web_evidence_source_initialized")

    async def read(self, url, mode):
        """Acquire exactly the requested static/dynamic source, never fallback, retry or reuse a profile on unsupported pages."""
        public_url(url)
        if mode not in {"static", "dynamic"}:
            raise WebEvidenceError("evidence_invalid")
        observer = ResponseObservation(
            self.browser_resources if mode == "dynamic" else self.static_client,
            dynamic=mode == "dynamic",
            utcnow=self.utcnow,
        )
        reader = (
            ReadOnlyBrowser(resources=observer, worker_factory=self.worker_factory)
            if mode == "dynamic"
            else BoundedWebFetcher(client=observer)
        )
        try:
            page = (
                await reader.navigate(url)
                if mode == "dynamic"
                else await reader.fetch(url)
            )
        finally:
            await reader.shutdown()
        if observer.document_url != page.final_url:
            raise WebEvidenceError("evidence_integrity")
        logger.info("web_evidence_source_acquisition_retired")
        return ObservedSource(
            page, observer.dates, tuple(observer.records), observer.cache_seconds
        )
