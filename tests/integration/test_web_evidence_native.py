"""Compose real network-none native browser execution with source metadata, owner-bound cache and signed exact-span evidence."""

import logging
from uuid import uuid4

import pytest

from src.application.ports.browser import BrowserHTTPResponse
from src.application.services.web_evidence import WebEvidenceService
from src.infrastructure.browser_runtime import NativeBrowserWorker
from src.infrastructure.web_evidence_source import ObservedWebSource

logger = logging.getLogger(__name__)


class NativeAuthoredResources:
    """Supply clearly authored source bytes to a real native browser without claiming actual public DNS/TLS."""

    def __init__(self, *, no_store=False):
        """Bind complete authored dynamic HTML and an explicit source cache policy."""
        self.calls, self.no_store = [], no_store

    async def get(self, url, kind):
        """Return complete fixture bytes while recording only the source-call boundary for test assertions."""
        self.calls.append((url, kind))
        headers = (
            ("content-type", "text/html"),
            ("cache-control", "no-store" if self.no_store else "max-age=120"),
        )
        body = b"""<html><head><title>Native provenance</title><meta property="article:published_time" content="2026-10-20T10:00:00Z"></head><body><p id="message">Loading</p><script>document.getElementById("message").textContent="Native evidence G-17.";document.querySelector("meta").setAttribute("content","2099-01-01");</script></body></html>"""
        return BrowserHTTPResponse(url, 200, headers, body, "8.8.8.8")


@pytest.mark.asyncio
@pytest.mark.parametrize("no_store", [False, True])
async def test_native_original_date_rendered_text_signed_reference_and_cache_require_confirmed_cleanup(
    tmp_path, no_store
):
    """Verify real JS/native layout, original-source dates, no-store behavior and exact container retirement before cache/ref issuance."""
    resources, workers = NativeAuthoredResources(no_store=no_store), []

    def factory():
        """Create only known ephemeral native workers under the private isolated test root."""
        worker = NativeBrowserWorker(root=tmp_path / "jobs")
        workers.append(worker)
        return worker

    source = ObservedWebSource(browser_resources=resources, worker_factory=factory)
    current, owner = WebEvidenceService(source), uuid4()
    url = "https://example.org/provenance"
    try:
        first = await current.read(owner, url, "dynamic")
        second = await current.read(owner, url, "dynamic")
        assert second.cache_hit is (not no_store)
        assert len(workers) == len(resources.calls) == (2 if no_store else 1)
        snapshot = first.snapshot
        assert (
            "Native evidence G-17." in snapshot.text and "Loading" not in snapshot.text
        )
        assert (
            snapshot.title == "Native provenance" and snapshot.source_mode == "dynamic"
        )
        assert (
            snapshot.date_claims[0].raw_value == "2026-10-20T10:00:00Z"
            and not snapshot.date_claims[0].verified
        )
        assert snapshot.resources[0].url == snapshot.final_url == url
        ref = current.cite(owner, snapshot, 0, len(snapshot.text))
        assert ref.quote == snapshot.text and ref.fetched_at == snapshot.fetched_at
        assert all(
            worker.retired and worker.closed and not worker.directory.exists()
            for worker in workers
        )
        assert not list((tmp_path / "jobs").iterdir()) and not current.operations
        logger.info("web_evidence_native_provenance_cache_span_and_retirement_verified")
    finally:
        await current.shutdown()
