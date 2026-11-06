"""Fetch a single public pinned HTTPS hop with strict bounded h11 framing and joined resolver/socket ownership."""

import asyncio
import logging
import socket
import ssl

import h11

from src.application.ports.web_fetch import PublicResponse
from src.application.services.web_fetch_policy import (
    WebFetchError,
    header_map,
    public_address,
    public_answers,
    public_url,
    representation,
)
from src.application.services.web_fetch_tasks import finish_owned, spawn_owned

logger = logging.getLogger(__name__)
STAGE_SECONDS = 3
CLOSE_SECONDS = 1
MAX_WIRE_BYTES = 2097152
REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})


async def system_lookup(host):
    """Resolve only TCP addresses through the system resolver, rejecting unsupported or oversized raw answer sets."""
    rows = await asyncio.get_running_loop().getaddrinfo(
        host,
        443,
        family=socket.AF_UNSPEC,
        type=socket.SOCK_STREAM,
        proto=socket.IPPROTO_TCP,
    )
    if not 1 <= len(rows) <= 64 or any(
        row[0] not in {socket.AF_INET, socket.AF_INET6} for row in rows
    ):
        raise WebFetchError("web_fetch_dns_invalid")
    return tuple(row[4][0] for row in rows)


def system_tls_context():
    """Load explicit system CA paths without environment proxy, CA override, client credentials or TLS key logging."""
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    paths = ssl.get_default_verify_paths()
    context.load_verify_locations(
        cafile=paths.openssl_cafile, capath=paths.openssl_capath
    )
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.set_alpn_protocols(["http/1.1"])
    logger.info("web_fetch_tls_context_created")
    return context


async def open_pinned_tls(host, address):
    """Connect once to a validated numeric pin while verifying the original hostname with explicit system trust."""
    pin = public_address(address)
    async with asyncio.timeout(STAGE_SECONDS):
        return await asyncio.open_connection(
            host=pin,
            port=443,
            family=socket.AF_INET6 if ":" in pin else socket.AF_INET,
            ssl=system_tls_context(),
            server_hostname=host,
            ssl_handshake_timeout=STAGE_SECONDS,
            ssl_shutdown_timeout=CLOSE_SECONDS,
            limit=16384,
        )


async def abort_writer(writer):
    """Abort the known transport and join its queued closure callback without constructing another task."""
    writer.transport.abort()
    loop = asyncio.get_running_loop()
    retired = loop.create_future()
    loop.call_soon(retired.set_result, None)
    await finish_owned(retired)
    logger.info("web_fetch_socket_aborted")


async def close_writer(writer):
    """Close an owned TLS writer, abort a failed shutdown and join cleanup despite repeated caller cancellation."""

    try:
        writer.close()
    except Exception:
        await abort_writer(writer)
        raise WebFetchError("web_fetch_internal") from None

    async def close():
        """Bound graceful TLS shutdown and finish the transport's abort callback before reporting closure."""
        try:
            async with asyncio.timeout(CLOSE_SECONDS):
                await writer.wait_closed()
        except Exception:
            await abort_writer(writer)
        logger.info("web_fetch_socket_closed")

    try:
        task = spawn_owned(close())
    except BaseException:
        await abort_writer(writer)
        raise WebFetchError("web_fetch_internal") from None
    try:
        await asyncio.shield(task)
    except asyncio.CancelledError:
        await finish_owned(task)
        raise


class WireReader:
    """Keep one request's raw-wire budget separate from framing normalization and body limits."""

    def __init__(self, reader):
        """Bind one owned TLS reader and an initially empty wire counter."""
        self.reader = reader
        self.received = 0

    async def read(self):
        """Read at most8192bytes under a stage deadline and reject the complete2MiB wire ceiling."""
        async with asyncio.timeout(STAGE_SECONDS):
            chunk = await self.reader.read(8192)
        self.received += len(chunk)
        if self.received > MAX_WIRE_BYTES:
            raise WebFetchError("web_fetch_body_limit")
        return chunk

    async def head(self, connection, initial=b""):
        """Bound and validate original CRLF headers before h11 can coalesce equal Content-Length fields."""
        raw = bytearray(initial)
        while True:
            boundary = raw.find(b"\r\n\r\n")
            if boundary >= 0:
                end = boundary + 4
                if end > 16384:
                    raise WebFetchError("web_fetch_header_limit")
                lines = bytes(raw[:boundary]).split(b"\r\n")[1:]
                headers = []
                for line in lines:
                    if line.startswith((b" ", b"\t")) or b":" not in line:
                        raise WebFetchError("web_fetch_http_invalid")
                    name, value = line.split(b":", 1)
                    headers.append(
                        (name.decode("ascii"), value.strip(b" \t").decode("ascii"))
                    )
                header_map(tuple(headers))
                connection.receive_data(bytes(raw[:end]))
                event = connection.next_event()
                if type(event) not in {h11.Response, h11.InformationalResponse}:
                    raise WebFetchError("web_fetch_http_invalid")
                return event, bytes(raw[end:]), tuple(headers)
            if len(raw) > 16384:
                raise WebFetchError("web_fetch_header_limit")
            chunk = await self.read()
            if not chunk:
                raise WebFetchError("web_fetch_http_invalid")
            raw.extend(chunk)

    async def body(self, connection, initial):
        """Collect a complete at-most1MiB framed body, denying trailers, early EOF and protocol upgrades."""
        if initial:
            connection.receive_data(initial)
        body = bytearray()
        while True:
            event = connection.next_event()
            if event is h11.NEED_DATA:
                connection.receive_data(await self.read())
            elif type(event) is h11.Data:
                body.extend(event.data)
                if len(body) > 1048576:
                    raise WebFetchError("web_fetch_body_limit")
            elif type(event) is h11.EndOfMessage:
                if event.headers:
                    raise WebFetchError("web_fetch_http_invalid")
                logger.info("web_fetch_body_complete bytes=%d", len(body))
                return bytes(body)
            else:
                raise WebFetchError("web_fetch_http_invalid")


class PublicHTTPSClient:
    """Own one-hop DNS/pin/TLS/framing with trusted test seams and no implicit URL, credential or retry authority."""

    def __init__(self, *, resolver=None, connector=None):
        """Bind inert trusted dependencies without resolving a hostname, loading a model or opening a socket."""
        self.resolver = resolver if resolver is not None else system_lookup
        self.connector = connector if connector is not None else open_pinned_tls
        logger.info("web_fetch_https_client_constructed")

    async def resolve(self, host):
        """Shield system DNS and retain its ownership until completion even when caller deadlines/cancellation fire."""
        task = spawn_owned(self.resolver(host))
        try:
            async with asyncio.timeout(STAGE_SECONDS):
                values = await asyncio.shield(task)
        except BaseException:
            try:
                await finish_owned(task)
            except BaseException:
                logger.info("web_fetch_dns_joined_after_failure")
            raise
        return public_answers(values)[0]

    async def connect(self, host, pin):
        """Recover and close a late unreturned TLS writer before propagating caller cancellation."""
        task = spawn_owned(self.connector(host, pin))
        try:
            return await asyncio.shield(task)
        except BaseException:
            try:
                _, writer = await finish_owned(task)
                await close_writer(writer)
            except BaseException:
                logger.info("web_fetch_unreturned_connection_joined")
            raise

    async def get(self, url):
        """Perform exactly one verified HTTPS GET, returning bounded complete evidence or a finite sanitized error."""
        target = public_url(url)
        writer = None
        try:
            pin = await self.resolve(target.host)
            reader, writer = await self.connect(target.host, pin)
            peer = writer.get_extra_info("peername")
            if not peer or public_address(peer[0]) != pin:
                raise WebFetchError("web_fetch_peer_invalid")
            connection = h11.Connection(h11.CLIENT, max_incomplete_event_size=16384)
            request = h11.Request(
                method=b"GET",
                target=target.target,
                headers=[
                    (b"Host", target.host.encode("ascii")),
                    (b"User-Agent", b"LocalAssistantResearch/0.1"),
                    (b"Accept", b"text/html, text/plain"),
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
                    raise WebFetchError("web_fetch_http_invalid")
            if event.status_code in REDIRECT_STATUSES:
                logger.info("web_fetch_redirect_received")
                return PublicResponse(event.status_code, headers, b"", pin)
            if event.status_code != 200:
                raise WebFetchError("web_fetch_http_status")
            representation(headers)
            body = await wire.body(connection, initial)
            logger.info("web_fetch_https_complete")
            return PublicResponse(200, headers, body, pin)
        except asyncio.CancelledError:
            logger.info("web_fetch_https_cancelled")
            raise
        except WebFetchError:
            logger.info("web_fetch_https_rejected")
            raise
        except TimeoutError:
            raise WebFetchError("web_fetch_timeout") from None
        except ssl.SSLError:
            raise WebFetchError("web_fetch_tls_failed") from None
        except (h11.ProtocolError, UnicodeError):
            raise WebFetchError("web_fetch_http_invalid") from None
        except Exception:
            raise WebFetchError("web_fetch_transport_failed") from None
        finally:
            if writer is not None:
                await close_writer(writer)
