"""Own one explicit bounded public fetch through validated redirects and static untrusted evidence extraction."""

import asyncio
import hashlib
import json
import logging
from dataclasses import asdict
from urllib.parse import urljoin

from src.application.ports.web_fetch import FetchedPage, PublicResponse
from src.application.services.web_fetch_policy import (
    WebFetchError,
    header_map,
    public_address,
    public_url,
    representation,
)
from src.application.services.web_fetch_tasks import finish_owned
from src.infrastructure.public_https import REDIRECT_STATUSES, PublicHTTPSClient
from src.infrastructure.static_web_text import extract_static

logger = logging.getLogger(__name__)
TOTAL_SECONDS = 15
create_task = asyncio.create_task


class BoundedWebFetcher:
    """Retain one nonqueued fetch until owned DNS/TLS/request cleanup finishes, without API or model startup."""

    def __init__(self, *, client=None):
        """Bind an inert trusted network port and finite in-memory ownership state without opening a socket."""
        self.client = client if client is not None else PublicHTTPSClient()
        self.admission = asyncio.Lock()
        self.operations = set()
        self.closing = False
        logger.info("web_fetch_service_initialized")

    async def run(self, requested):
        """Fetch at mostfour fully validated hops and bind complete static text to the actual final body/URL."""
        target = public_url(requested)
        redirects, seen = [], set()
        async with asyncio.timeout(TOTAL_SECONDS):
            while True:
                if target.url in seen:
                    raise WebFetchError("web_fetch_redirect_invalid")
                seen.add(target.url)
                response = await self.client.get(target.url)
                if (
                    type(response) is not PublicResponse
                    or type(response.status) is not int
                    or type(response.body) is not bytes
                ):
                    raise WebFetchError("web_fetch_response_invalid")
                public_address(response.pinned_address)
                headers = header_map(response.headers)
                if response.status in REDIRECT_STATUSES:
                    if len(redirects) >= 3:
                        raise WebFetchError("web_fetch_redirect_limit")
                    location = headers.get("location")
                    if (
                        not location
                        or len(location) > 2048
                        or location != location.strip()
                    ):
                        raise WebFetchError("web_fetch_redirect_invalid")
                    try:
                        following = public_url(urljoin(target.url, location))
                    except (WebFetchError, ValueError):
                        raise WebFetchError("web_fetch_redirect_invalid") from None
                    redirects.append((target.url, following.url))
                    target = following
                    logger.info("web_fetch_redirect_validated count=%d", len(redirects))
                    continue
                if response.status != 200:
                    raise WebFetchError("web_fetch_http_status")
                media, encoding = representation(response.headers)
                title, text, canonical = extract_static(
                    response.body, media, encoding, target.url
                )
                result = FetchedPage(
                    requested,
                    target.url,
                    tuple(redirects),
                    media,
                    title,
                    text,
                    hashlib.sha256(response.body).hexdigest(),
                    hashlib.sha256(text.encode()).hexdigest(),
                    canonical,
                )
                encoded = json.dumps(
                    asdict(result), ensure_ascii=False, allow_nan=False
                ).encode()
                if len(encoded) > 262144:
                    raise WebFetchError("web_fetch_text_limit")
                logger.info("web_fetch_evidence_complete bytes=%d", len(encoded))
                return result

    async def fetch(self, url):
        """Own one child operation, joining repeated cancellation and rejecting new work before any network activity."""
        public_url(url)
        if self.closing:
            raise WebFetchError("web_fetch_closed")
        if self.admission.locked():
            raise WebFetchError("web_fetch_busy")
        await self.admission.acquire()
        caller, task = asyncio.current_task(), None
        pending = None
        try:
            self.operations.add(caller)
            pending = self.run(url)
            try:
                task = create_task(pending)
            except BaseException:
                pending.close()
                raise
            try:
                return await asyncio.shield(task)
            except asyncio.CancelledError:
                task.cancel()
                try:
                    await finish_owned(task)
                except BaseException:
                    logger.info("web_fetch_cancelled_operation_joined")
                raise
        except asyncio.CancelledError:
            raise
        except WebFetchError:
            logger.info("web_fetch_operation_rejected")
            raise
        except TimeoutError:
            raise WebFetchError("web_fetch_timeout") from None
        except Exception:
            raise WebFetchError("web_fetch_internal") from None
        finally:
            self.operations.discard(caller)
            self.admission.release()
            logger.info("web_fetch_operation_closed")

    async def shutdown(self):
        """Close admission and cancel/join only owning callers without touching search, models or unrelated resources."""
        self.closing = True
        tasks = [task for task in self.operations if task is not asyncio.current_task()]
        for task in tasks:
            task.cancel()
        for task in tasks:
            try:
                await finish_owned(task)
            except BaseException:
                logger.info("web_fetch_shutdown_request_joined")
        logger.info("web_fetch_shutdown_complete")
