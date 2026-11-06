"""Verify host-only browser GET media/TLS/pin/close policy with controlled raw streams and no actual network."""

import logging
import ssl
from types import SimpleNamespace

import pytest
from test_public_https import FixtureReader, FixtureWriter, response_bytes

from src.application.services.browser_policy import BrowserError
from src.infrastructure.browser_resources import BrowserResourceClient
from src.infrastructure.public_https import PublicHTTPSClient

logger = logging.getLogger(__name__)


class VerifiedFixtureWriter(FixtureWriter):
    """Expose a clearly authored TLS verification context alongside controlled peer/request/closure state."""

    def __init__(self, *, peer="8.8.8.8", verified=True):
        """Create controlled TLS metadata without claiming that a real handshake occurred."""
        super().__init__(peer)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        if not verified:
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
        self.tls = SimpleNamespace(context=context)

    def get_extra_info(self, name):
        """Return authored TLS metadata only for the controlled unit-test seam."""
        return self.tls if name == "ssl_object" else super().get_extra_info(name)


def resource_fixture(
    body=b"window.fixture = 'dynamic';",
    media="application/javascript",
    *,
    peer="8.8.8.8",
    verified=True,
    extra=(),
):
    """Bind unchanged D49 DNS/connect/framing helpers to authored browser-resource wire bytes."""
    reader = FixtureReader(
        response_bytes(
            body,
            headers=[
                (b"Content-Type", media.encode()),
                (b"Content-Length", str(len(body)).encode()),
                *extra,
            ],
        )
    )
    writer = VerifiedFixtureWriter(peer=peer, verified=verified)
    resolved, connected = [], []

    async def resolve(host):
        """Return the complete authored eligible DNS answer without a system lookup."""
        resolved.append(host)
        return ("8.8.8.8",)

    async def connect(host, pin):
        """Record the original host/public pin and provide a controlled stream without opening a socket."""
        connected.append((host, pin))
        return reader, writer

    network = PublicHTTPSClient(resolver=resolve, connector=connect)
    return BrowserResourceClient(network=network), writer, resolved, connected


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kind,media,body",
    [
        ("Document", "text/html", b"<html><body>Dynamic</body></html>"),
        ("Script", "application/javascript", b"window.answer=17;"),
        ("Stylesheet", "text/css", b"body { color: black; }"),
        ("Fetch", "application/json", b'{"answer":17}'),
    ],
)
async def test_only_fixed_credentialless_gets_publish_complete_verified_bytes(
    kind, media, body, caplog
):
    """Keep original complete resource bytes and fixed Host/pin policy without cookie/header/model authority."""
    caplog.set_level(logging.DEBUG)
    client, writer, resolved, connected = resource_fixture(body, media)
    result = await client.get("https://example.org/private?token=fixture", kind)
    assert (
        result.body == body
        and result.status == 200
        and result.pinned_address == "8.8.8.8"
    )
    assert writer.raw.startswith(b"GET /private?token=fixture HTTP/1.1\r\n")
    assert (
        b"Authorization" not in writer.raw
        and b"Cookie" not in writer.raw
        and b"Accept-Encoding: identity" in writer.raw
    )
    assert (
        writer.closed
        and resolved == ["example.org"]
        and connected == [("example.org", "8.8.8.8")]
    )
    assert "private?token" not in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["Image", "Font", "Media", "Other", None, []])
async def test_unsupported_resource_kinds_have_no_dns_or_connection(kind):
    """Deny unsupported browser resource classes before any host lookup, TLS connection or response allocation."""
    client, writer, resolved, connected = resource_fixture()
    with pytest.raises(BrowserError, match="browser_resource_denied"):
        await client.get("https://example.org/", kind)
    assert not resolved and not connected and not writer.raw


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "peer,verified", [("127.0.0.1", True), ("1.1.1.1", True), ("8.8.8.8", False)]
)
async def test_unverified_or_wrong_peer_is_closed_before_http_transmission(
    peer, verified
):
    """Require both peer pin and TLS certificate/hostname policy before releasing any resource request."""
    client, writer, _, _ = resource_fixture(peer=peer, verified=verified)
    with pytest.raises(BrowserError, match="browser_resource_failed"):
        await client.get("https://example.org/", "Script")
    assert writer.closed and not writer.raw


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "media,extra,code",
    [
        ("image/png", (), "browser_resource_denied"),
        (
            "application/javascript",
            ((b"Content-Encoding", b"gzip"),),
            "browser_resource_denied",
        ),
        (
            "application/javascript",
            ((b"Content-Disposition", b"attachment; filename=private.js"),),
            "browser_download_denied",
        ),
    ],
)
async def test_binary_compressed_or_attachment_bytes_are_not_supplied_to_browser(
    media, extra, code
):
    """Reject unsupported representations and download authority with joined host socket cleanup."""
    client, writer, _, _ = resource_fixture(media=media, extra=extra)
    with pytest.raises(BrowserError, match=code):
        await client.get("https://example.org/", "Script")
    assert writer.closed
