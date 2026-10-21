"""Verify original-response metadata observation through accepted fetch ownership without authored-peer claims of public TLS."""

import asyncio
import hashlib
import logging
from datetime import UTC, datetime

import pytest

from src.application.ports.web_fetch import PublicResponse
from src.application.services.web_evidence_policy import WebEvidenceError
from src.infrastructure.web_evidence_source import (
    ObservedWebSource,
    ResponseObservation,
)

logger = logging.getLogger(__name__)
URL = "https://example.org/source"
BODY = b'<html><head><title>Atlas release</title><meta property="article:published_time" content="2026-10-20T10:00:00Z"></head><body>Generation G-17.</body></html>'


class AuthoredStaticClient:
    """Supply complete explicit source responses without DNS, sockets or an actual TLS claim."""

    def __init__(self, responses):
        """Bind a finite response map and an empty original-client call trace."""
        self.responses, self.calls = responses, []

    async def get(self, url):
        """Return only the explicitly supplied response for an admitted source URL."""
        self.calls.append(url)
        return self.responses[url]


@pytest.mark.asyncio
async def test_original_static_response_metadata_is_observed_without_rewriting_source():
    """Retain explicit title/date/body hashes from actual authored response bytes, keeping HTTP Date separate from publication claims."""
    response = PublicResponse(
        200,
        (
            ("content-type", "text/html"),
            ("cache-control", "max-age=120"),
            ("age", "20"),
            ("date", "Wed, 21 Oct 2026 00:00:00 GMT"),
        ),
        BODY,
        "8.8.8.8",
    )
    client = AuthoredStaticClient({URL: response})
    observed = ResponseObservation(
        client, utcnow=lambda: datetime(2026, 10, 21, tzinfo=UTC)
    )
    assert await observed.get(URL) is response
    assert client.calls == [URL] and observed.cache_seconds == 100
    assert (
        observed.dates[0].raw_value == "2026-10-20T10:00:00Z"
        and observed.dates[0].verified is False
    )
    assert observed.records[0].body_sha256 == hashlib.sha256(BODY).hexdigest()
    source = ObservedWebSource(
        static_client=client, utcnow=lambda: datetime(2026, 10, 21, tzinfo=UTC)
    )
    result = await source.read(URL, "static")
    assert (
        result.page.text == "Generation G-17." and result.page.title == "Atlas release"
    )
    assert result.page.body_sha256 == result.resources[0].body_sha256
    assert result.cache_seconds == 100 and result.dates == observed.dates
    logger.info("web_evidence_authored_original_static_metadata_verified")


@pytest.mark.asyncio
async def test_protocol_redirect_dates_belong_to_actual_final_document_and_policy_is_conservative():
    """Keep requested/final lineage distinct and apply the shortest observed redirect/document policy without canonical aliasing."""
    final = URL + "/final"
    client = AuthoredStaticClient(
        {
            URL: PublicResponse(
                302,
                (("location", final), ("cache-control", "no-store")),
                b"",
                "8.8.8.8",
            ),
            final: PublicResponse(
                200, (("content-type", "text/html"),), BODY, "8.8.8.8"
            ),
        }
    )
    source = ObservedWebSource(static_client=client)
    result = await source.read(URL, "static")
    assert client.calls == [URL, final] and result.cache_seconds == 0
    assert result.page.requested_url == URL and result.page.final_url == final
    assert result.dates[0].kind == "published" and result.resources[-1].url == final
    assert result.page.redirects == ((URL, final),) and len(result.resources) == 2


@pytest.mark.asyncio
async def test_missing_publication_metadata_remains_unknown_and_plain_text_does_not_become_a_date_claim():
    """Do not invent a publication date from HTTP headers, text prose, canonical hints or trusted fetch time."""
    client = AuthoredStaticClient(
        {
            URL: PublicResponse(
                200,
                (
                    ("content-type", "text/plain"),
                    ("date", "Wed, 21 Oct 2026 00:00:00 GMT"),
                    ("last-modified", "Tue, 20 Oct 2026 00:00:00 GMT"),
                ),
                b"Published yesterday2026-10-20.",
                "8.8.8.8",
            )
        }
    )
    result = await ObservedWebSource(static_client=client).read(URL, "static")
    assert result.dates == () and result.page.title is None


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["auto", "STATIC", "browser", ""])
async def test_unrequested_source_mode_is_rejected_without_fallback(mode):
    """Reject unsupported routing before consulting either a static or native resource client."""
    client = AuthoredStaticClient({})
    with pytest.raises(WebEvidenceError, match="evidence_invalid"):
        await ObservedWebSource(static_client=client).read(URL, mode)
    assert not client.calls


@pytest.mark.asyncio
async def test_observer_cancel_waits_for_underlying_client_cleanup_without_partial_metadata():
    """Join accepted fetch cleanup before cancellation returns and never issue a partial observed page."""
    entered, release, cleanup = asyncio.Event(), asyncio.Event(), asyncio.Event()

    class HeldClient:
        """Retain an authored original-client cancellation boundary with no real socket or public request."""

        async def get(self, url):
            """Hold delegated cleanup until the test explicitly acknowledges resource release."""
            entered.set()
            try:
                await asyncio.Event().wait()
            finally:
                cleanup.set()
                await release.wait()

    source = ObservedWebSource(static_client=HeldClient())
    task = asyncio.create_task(source.read(URL, "static"))
    await entered.wait()
    task.cancel()
    await cleanup.wait()
    task.cancel()
    assert not task.done()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.asyncio
async def test_source_cannot_swallow_cancel_and_publish_a_reusable_snapshot():
    """Require explicit cancellation ownership even if a trusted source mistakenly suppresses its CancelledError."""
    from uuid import uuid4

    from test_web_evidence import observation, service

    current, source, _ = service()
    entered = asyncio.Event()

    async def suppress(url, mode):
        """Model a faulty trusted source that returns valid evidence after its owning acquisition was cancelled."""
        entered.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            return observation(url)

    source.read = suppress
    task = asyncio.create_task(current.read(uuid4(), URL))
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert (
        not current.cache and not current.operations and not current.admission.locked()
    )
