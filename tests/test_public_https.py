"""Verify pinned HTTPS request/framing/budget/cleanup behavior with controlled raw-byte streams and no external request."""

import asyncio
import logging
import socket
import ssl

import pytest

from src.application.services.web_fetch_policy import WebFetchError
from src.infrastructure import public_https as module
from src.infrastructure.public_https import PublicHTTPSClient

logger = logging.getLogger(__name__)


class FixtureReader:
    """Return authored raw HTTP bytes in bounded fragments with optional controlled read blocking."""

    def __init__(self, raw, size=8192):
        """Retain private raw bytes and read/cleanup barriers without opening a socket."""
        self.raw, self.size, self.reads = raw, size, 0
        self.started, self.release = asyncio.Event(), None

    async def read(self, maximum):
        """Consume at most the requested byte count or wait for an explicit test release."""
        self.reads += 1
        self.started.set()
        if self.release is not None:
            await self.release.wait()
        value, self.raw = (
            self.raw[: min(maximum, self.size)],
            self.raw[min(maximum, self.size) :],
        )
        return value


class FixtureWriter:
    """Record an authored TCP pin and exact outgoing bytes while exposing joined close/abort state."""

    def __init__(self, peer="8.8.8.8"):
        """Create inert write and closure observations for one controlled connection."""
        self.peer, self.raw = peer, bytearray()
        self.closed = self.aborted = False
        self.closing_started, self.close_release = asyncio.Event(), None
        self.transport = self

    def get_extra_info(self, name):
        """Expose only the authored socket peer used by the production pin check."""
        return (self.peer, 443) if name == "peername" else None

    def write(self, raw):
        """Retain exact request bytes without emitting their private target to logs."""
        self.raw.extend(raw)

    async def drain(self):
        """Complete the controlled write without touching a network transport."""
        await asyncio.sleep(0)

    def close(self):
        """Mark closure requested before the join barrier can be released."""
        self.closing_started.set()

    async def wait_closed(self):
        """Hold cleanup ownership until the test explicitly permits closure."""
        if self.close_release is not None:
            await self.close_release.wait()
        self.closed = True

    def abort(self):
        """Acknowledge forced transport closure and release any controlled graceful-close wait."""
        self.aborted = self.closed = True
        if self.close_release is not None:
            self.close_release.set()


def response_bytes(
    body=b"<html><body>Atlas G-17.</body></html>", *, status=b"200 OK", headers=None
):
    """Build one authored strict HTTP message without hiding any malformed-field mutations from tests."""
    fields = (
        headers
        if headers is not None
        else [
            (b"Content-Type", b"text/html"),
            (b"Content-Length", str(len(body)).encode()),
        ]
    )
    return (
        b"HTTP/1.1 "
        + status
        + b"\r\n"
        + b"\r\n".join(key + b": " + value for key, value in fields)
        + b"\r\n\r\n"
        + body
    )


def https_fixture(
    raw=None, *, addresses=("8.8.8.8", "1.1.1.1"), peer="8.8.8.8", size=8192
):
    """Bind controlled DNS and connection ports while preserving every real policy/framing/cleanup branch."""
    reader, writer = (
        FixtureReader(response_bytes() if raw is None else raw, size),
        FixtureWriter(peer),
    )
    resolved, connected = [], []

    async def resolve(host):
        """Return the complete authored DNS set and retain the one requested hostname."""
        resolved.append(host)
        return addresses

    async def connect(host, pin):
        """Record selected-IP/original-host arguments without performing a real TLS handshake."""
        connected.append((host, pin))
        return reader, writer

    return (
        PublicHTTPSClient(resolver=resolve, connector=connect),
        reader,
        writer,
        resolved,
        connected,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("size", [1, 7, 8192])
async def test_complete_request_preserves_target_host_pin_and_owned_close(size, caplog):
    """Handle header/body fragmentation without premature EOF, credentials, URL logging or address retries."""
    caplog.set_level(logging.DEBUG)
    client, _, writer, resolved, connected = https_fixture(size=size)
    result = await client.get(
        "https://Example.org/private-path?token=PRIVATE-TOKEN-FIXTURE"
    )
    assert (
        result.status == 200 and result.body == b"<html><body>Atlas G-17.</body></html>"
    )
    assert resolved == ["example.org"] and connected == [("example.org", "8.8.8.8")]
    assert writer.raw.startswith(
        b"GET /private-path?token=PRIVATE-TOKEN-FIXTURE HTTP/1.1\r\n"
    )
    assert (
        b"Host: example.org\r\n" in writer.raw
        and b"Accept-Encoding: identity\r\n" in writer.raw
    )
    assert (
        b"Authorization" not in writer.raw
        and b"Cookie" not in writer.raw
        and writer.closed
    )
    assert (
        "private-path" not in caplog.text and "PRIVATE-TOKEN-FIXTURE" not in caplog.text
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "raw,code",
    [
        (
            b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nContent-Length: 4\r\n\r\nx",
            "web_fetch_http_invalid",
        ),
        (
            response_bytes(
                b"x",
                headers=[
                    (b"Content-Type", b"text/plain"),
                    (b"Content-Length", b"1"),
                    (b"Content-Length", b"1"),
                ],
            ),
            "web_fetch_http_invalid",
        ),
        (
            response_bytes(
                b"x",
                headers=[
                    (b"Content-Type", b"text/plain"),
                    (b"Content-Length", b"1"),
                    (b"Content-Length", b"2"),
                ],
            ),
            "web_fetch_http_invalid",
        ),
        (
            response_bytes(
                b"x",
                headers=[
                    (b"Content-Type", b"text/plain"),
                    (b"Content-Length", b"1"),
                    (b"Transfer-Encoding", b"chunked"),
                ],
            ),
            "web_fetch_http_invalid",
        ),
        (
            response_bytes(
                b"x",
                headers=[
                    (b"Content-Type", b"text/plain"),
                    (b"Content-Type", b"text/html"),
                ],
            ),
            "web_fetch_http_invalid",
        ),
        (
            response_bytes(
                b"x",
                headers=[
                    (b"Content-Type", b"text/plain"),
                    (b"Content-Encoding", b"gzip"),
                ],
            ),
            "web_fetch_encoding_unsupported",
        ),
        (
            response_bytes(b"x", headers=[(b"Content-Type", b"application/pdf")]),
            "web_fetch_media_unsupported",
        ),
        (
            response_bytes(
                b"x",
                headers=[
                    (b"Content-Type", b"text/plain"),
                    (b"Content-Length", b"1048577"),
                ],
            ),
            "web_fetch_body_limit",
        ),
        (
            response_bytes(
                b"x",
                headers=[(b"Content-Type", b"text/plain"), (b"X-Large", b"x" * 16384)],
            ),
            "web_fetch_header_limit",
        ),
        (
            response_bytes(
                b"x", headers=[(b"Content-Type", b"text/plain")] + [(b"X", b"y")] * 128
            ),
            "web_fetch_header_limit",
        ),
        (
            response_bytes(b"x", status=b"403 private-provider-error"),
            "web_fetch_http_status",
        ),
        (
            response_bytes(
                b"1\r\nx\r\n0\r\nX-Trailer: private\r\n\r\n",
                headers=[
                    (b"Content-Type", b"text/plain"),
                    (b"Transfer-Encoding", b"chunked"),
                ],
            ),
            "web_fetch_http_invalid",
        ),
        (
            response_bytes(
                b"1\r\nx\r\n",
                headers=[
                    (b"Content-Type", b"text/plain"),
                    (b"Transfer-Encoding", b"chunked"),
                ],
            ),
            "web_fetch_http_invalid",
        ),
        (
            response_bytes(b"x" * 1048577, headers=[(b"Content-Type", b"text/plain")]),
            "web_fetch_body_limit",
        ),
        (
            b"HTTP/1.1 101 Switching Protocols\r\nConnection: Upgrade\r\nUpgrade: websocket\r\n\r\n",
            "web_fetch_http_invalid",
        ),
        (
            b"HTTP/1.1 103 Early Hints\r\nX: y\r\n\r\n" * 4 + response_bytes(),
            "web_fetch_http_invalid",
        ),
    ],
)
async def test_invalid_framing_representation_and_limits_close_once(raw, code):
    """Refuse malformed, duplicate, oversized, compressed or upgraded responses without retries or partial evidence."""
    client, _, writer, resolved, connected = https_fixture(raw)
    with pytest.raises(WebFetchError, match=code):
        await client.get("https://example.org/private")
    assert writer.closed and len(connected) == len(resolved) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "raw,expected",
    [
        (
            response_bytes(
                b"plain until EOF", headers=[(b"Content-Type", b"text/plain")]
            ),
            b"plain until EOF",
        ),
        (
            response_bytes(
                b"3\r\nabc\r\n2\r\nde\r\n0\r\n\r\n",
                headers=[
                    (b"Content-Type", b"text/plain"),
                    (b"Transfer-Encoding", b"chunked"),
                ],
            ),
            b"abcde",
        ),
        (
            b"HTTP/1.1 103 Early Hints\r\nX: y\r\n\r\n" * 3
            + response_bytes(
                b"x",
                headers=[(b"Content-Type", b"text/plain"), (b"Content-Length", b"1")],
            ),
            b"x",
        ),
    ],
)
async def test_supported_close_chunked_and_informational_framing(raw, expected):
    """Recognize complete h11 bodies and bounded informational replies without treating an empty prefix as EOF."""
    client, _, writer, _, _ = https_fixture(raw, size=7)
    assert (await client.get("https://example.org/")).body == expected and writer.closed


@pytest.mark.asyncio
async def test_total_wire_budget_catches_chunk_extension_overhead():
    """Bound wire overhead even when decoded body bytes and each individual chunk extension are small."""
    raw = response_bytes(
        (b"1;" + b"x" * 2000 + b"\r\nx\r\n") * 1100 + b"0\r\n\r\n",
        headers=[(b"Content-Type", b"text/plain"), (b"Transfer-Encoding", b"chunked")],
    )
    client, reader, writer, _, _ = https_fixture(raw)
    with pytest.raises(WebFetchError, match="web_fetch_body_limit"):
        await client.get("https://example.org/")
    assert writer.closed and reader.raw and module.MAX_WIRE_BYTES == 2097152


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "addresses",
    [("8.8.8.8", "127.0.0.1"), ("3fff::1",), ("8.8.8.8",) * 64 + ("1.1.1.1",)],
)
async def test_entire_dns_answer_is_checked_before_any_connection(addresses):
    """Refuse mixed/special/oversized answers before selecting a convenient public prefix."""
    client, _, writer, resolved, connected = https_fixture(addresses=addresses)
    with pytest.raises(WebFetchError):
        await client.get("https://example.org/")
    assert resolved == ["example.org"] and not connected and not writer.raw


@pytest.mark.asyncio
@pytest.mark.parametrize("peer", ["1.1.1.1", "127.0.0.1"])
async def test_actual_peer_drift_is_closed_before_request_transmission(peer):
    """Refuse a mismatched or private socket peer rather than trusting DNS alone."""
    client, _, writer, _, _ = https_fixture(peer=peer)
    with pytest.raises(WebFetchError):
        await client.get("https://example.org/")
    assert writer.closed and not writer.raw


@pytest.mark.asyncio
async def test_redirect_is_returned_without_following_or_consuming_its_body():
    """Keep redirect authority at the outer validator instead of automatic transport following/cookie processing."""
    raw = response_bytes(
        b"x" * 100000,
        status=b"302 Found",
        headers=[(b"Location", b"https://127.0.0.1/private")],
    )
    client, reader, writer, _, connected = https_fixture(raw)
    result = await client.get("https://example.org/")
    assert (
        result.status == 302
        and result.body == b""
        and reader.raw
        and writer.closed
        and len(connected) == 1
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error,code",
    [
        (
            ssl.SSLCertVerificationError("private-certificate-fixture"),
            "web_fetch_tls_failed",
        ),
        (OSError("private-socket-fixture"), "web_fetch_transport_failed"),
    ],
)
async def test_connection_diagnostics_are_sanitized_without_fallback(
    error, code, caplog
):
    """Retain one failed pin attempt while hiding transport exception text and refusing another address."""
    caplog.set_level(logging.DEBUG)
    calls = []

    async def resolve(host):
        """Return two eligible pins to prove that a failure does not select a second address."""
        return ("8.8.8.8", "1.1.1.1")

    async def connect(host, pin):
        """Fail the first actual connection seam with a deliberately private diagnostic."""
        calls.append(pin)
        raise error

    with pytest.raises(WebFetchError, match=code):
        await PublicHTTPSClient(resolver=resolve, connector=connect).get(
            "https://example.org/private"
        )
    assert (
        calls == ["8.8.8.8"]
        and "private-certificate-fixture" not in caplog.text
        and "private-socket-fixture" not in caplog.text
    )


def test_system_tls_ignores_environment_key_logging_and_ca_override(
    monkeypatch, tmp_path
):
    """Use explicit system trust and hostname verification without creating an environment-selected TLS secret log."""
    log = tmp_path / "forbidden-tls-keylog"
    monkeypatch.setenv("SSLKEYLOGFILE", str(log))
    monkeypatch.setenv("SSL_CERT_FILE", str(tmp_path / "missing-ca"))
    context = module.system_tls_context()
    assert context.verify_mode == ssl.CERT_REQUIRED and context.check_hostname
    assert context.keylog_filename is None and not log.exists()


@pytest.mark.asyncio
async def test_failed_graceful_shutdown_aborts_before_returning_evidence(monkeypatch):
    """Retain socket ownership through a bounded graceful-close failure and acknowledge abort before success returns."""
    monkeypatch.setattr(module, "CLOSE_SECONDS", 0.01)
    client, _, writer, _, _ = https_fixture()
    writer.close_release = asyncio.Event()
    assert (await client.get("https://example.org/")).status == 200
    assert writer.closed and writer.aborted


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["resolve", "connect", "close"])
async def test_network_task_creation_failure_closes_coroutine_and_known_socket(
    stage, monkeypatch
):
    """Keep unstarted DNS/connect/close coroutines and already known sockets owned when task construction fails."""
    from src.application.services import web_fetch_tasks

    captured = []

    def fail(pending):
        """Inject a scoped network-task factory failure without changing the event loop's own task constructor."""
        captured.append(pending)
        raise RuntimeError("private-network-task-create")

    monkeypatch.setattr(web_fetch_tasks, "create_task", fail)
    client, _, writer, resolved, connected = https_fixture()
    with pytest.raises((RuntimeError, WebFetchError)):
        if stage == "resolve":
            await client.resolve("example.org")
        elif stage == "connect":
            await client.connect("example.org", "8.8.8.8")
        else:
            await module.close_writer(writer)
    assert len(captured) == 1 and captured[0].cr_frame is None
    assert not resolved and not connected
    if stage == "close":
        assert writer.closed and writer.aborted


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "count,family,valid",
    [
        (1, socket.AF_INET, True),
        (0, socket.AF_INET, False),
        (65, socket.AF_INET, False),
        (1, socket.AF_UNIX, False),
    ],
)
async def test_system_lookup_enforces_tcp_and_complete_raw_answer_bounds(
    count, family, valid, monkeypatch
):
    """Validate system resolver records without filtering an unsupported family or overbudget raw tail."""
    calls = []

    async def resolve(host, port, **options):
        """Return authored system-level getaddrinfo records without sending a DNS packet."""
        calls.append((host, port, options))
        return [
            (family, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("8.8.8.8", 443))
        ] * count

    monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", resolve)
    if valid:
        assert await module.system_lookup("example.org") == ("8.8.8.8",)
    else:
        with pytest.raises(WebFetchError, match="web_fetch_dns_invalid"):
            await module.system_lookup("example.org")
    assert calls == [
        (
            "example.org",
            443,
            dict(
                family=socket.AF_UNSPEC,
                type=socket.SOCK_STREAM,
                proto=socket.IPPROTO_TCP,
            ),
        )
    ]
