"""Broker only host-verified bounded HTTPS GET text resources for a browser with no direct network."""

import asyncio
import logging
import ssl

import h11

from src.application.ports.browser import BrowserHTTPResponse
from src.application.services.browser_policy import (
    ALLOWED_KINDS,
    BrowserError,
    browser_url,
    resource_representation,
)
from src.application.services.web_fetch_policy import (
    WebFetchError,
    public_address,
    public_url,
)
from src.infrastructure.public_https import (
    REDIRECT_STATUSES,
    STAGE_SECONDS,
    PublicHTTPSClient,
    WireReader,
    close_writer,
)

logger = logging.getLogger(__name__)


class BrowserResourceClient:
    """Use unchanged D49 DNS/TLS/pin/framing ownership for a separate finite browser text-media allowlist."""

    def __init__(self, *, network=None):
        """Bind an inert trusted network seam without opening a connection, reading credentials or starting a browser/model."""
        self.network = network if network is not None else PublicHTTPSClient()
        logger.info("browser_resource_client_constructed")

    async def get(self, url, kind):
        """Make one fixed credentialless GET, closing the actual TLS writer before publishing complete bounded resource bytes."""
        if type(kind) is not str or kind not in ALLOWED_KINDS:
            raise BrowserError("browser_resource_denied")
        target = public_url(browser_url(url))
        writer = None
        try:
            pin = await self.network.resolve(target.host)
            reader, writer = await self.network.connect(target.host, pin)
            peer = writer.get_extra_info("peername")
            tls = writer.get_extra_info("ssl_object")
            if (
                not peer
                or public_address(peer[0]) != pin
                or tls is None
                or not tls.context.check_hostname
                or tls.context.verify_mode != ssl.CERT_REQUIRED
            ):
                raise BrowserError("browser_resource_failed")
            connection = h11.Connection(h11.CLIENT, max_incomplete_event_size=16384)
            request = h11.Request(
                method=b"GET",
                target=target.target,
                headers=[
                    (b"Host", target.host.encode("ascii")),
                    (b"User-Agent", b"LocalAssistantReadOnlyBrowser/0.1"),
                    (
                        b"Accept",
                        b"text/html, text/plain, text/css, application/javascript, text/javascript, application/json",
                    ),
                    (b"Accept-Encoding", b"identity"),
                    (b"Connection", b"close"),
                ],
            )
            writer.write(connection.send(request) + connection.send(h11.EndOfMessage()))
            async with asyncio.timeout(STAGE_SECONDS):
                await writer.drain()
            wire, initial, informational = WireReader(reader), b"", 0
            while True:
                event, initial, headers = await wire.head(connection, initial)
                if type(event) is h11.Response:
                    break
                informational += 1
                if event.status_code == 101 or informational > 3:
                    raise BrowserError("browser_resource_failed")
            if event.status_code in REDIRECT_STATUSES:
                logger.info("browser_resource_redirect_received")
                return BrowserHTTPResponse(
                    target.url, event.status_code, headers, b"", pin
                )
            if event.status_code != 200:
                raise BrowserError("browser_resource_failed")
            _, encoding = resource_representation(headers, kind)
            body = await wire.body(connection, initial)
            body.decode(encoding, errors="strict")
            logger.info("browser_resource_fetched bytes=%d", len(body))
            return BrowserHTTPResponse(target.url, 200, headers, body, pin)
        except asyncio.CancelledError:
            logger.info("browser_resource_cancelled")
            raise
        except BrowserError:
            raise
        except TimeoutError:
            raise BrowserError("browser_timeout") from None
        except (WebFetchError, h11.ProtocolError, ssl.SSLError, UnicodeError):
            raise BrowserError("browser_resource_failed") from None
        except Exception:
            raise BrowserError("browser_resource_failed") from None
        finally:
            if writer is not None:
                await close_writer(writer)
