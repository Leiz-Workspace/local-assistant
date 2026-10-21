"""Exercise real loopback TLS/HTTP with disposable certificates; authored pin views do not replace the separate actual-public gate."""

import asyncio
import logging
import socket
import ssl
import subprocess
from contextlib import asynccontextmanager

import pytest
from test_public_https import response_bytes

from src.application.services.web_fetch_policy import WebFetchError
from src.infrastructure import public_https as module
from src.infrastructure.public_https import PublicHTTPSClient, close_writer
from src.infrastructure.web_fetch import BoundedWebFetcher

logger = logging.getLogger(__name__)


@pytest.fixture(scope="module")
def tls_material(tmp_path_factory):
    """Generate one disposable private test certificate without adding any system trust or dependency."""
    directory = tmp_path_factory.mktemp("d49-tls")
    directory.chmod(0o700)
    key, certificate = directory / "key.pem", directory / "certificate.pem"
    result = subprocess.run(
        [
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-keyout",
            str(key),
            "-out",
            str(certificate),
            "-days",
            "1",
            "-subj",
            "/CN=example.org",
            "-addext",
            "subjectAltName=DNS:example.org",
        ],
        capture_output=True,
    )
    assert result.returncode == 0
    key.chmod(0o600)
    logger.info("web_fetch_test_tls_material_created")
    return key, certificate


def tls_contexts(material):
    """Create a test server and verifying client that trusts only the disposable certificate."""
    key, certificate = material
    server = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server.load_cert_chain(certificate, key)
    client = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    client.load_verify_locations(cafile=str(certificate))
    return server, client


@asynccontextmanager
async def tls_server(context, raw):
    """Run an owned ephemeral loopback TLS socket, retaining requests/SNI and joining every accepted handler."""
    requests, sni, tasks = [], [], set()

    def observed_sni(ssl_object, server_name, server_context):
        """Observe the actual TLS ClientHello hostname without logging any request target or certificate key."""
        sni.append(server_name)

    async def handle(reader, writer):
        """Read one bounded actual HTTP request and send authored bytes before joined socket cleanup."""
        task = asyncio.current_task()
        tasks.add(task)
        try:
            request = await reader.readuntil(b"\r\n\r\n")
            requests.append(request)
            writer.write(raw)
            await writer.drain()
        except (asyncio.IncompleteReadError, ConnectionError, ssl.SSLError):
            logger.info("web_fetch_test_tls_peer_closed")
        finally:
            writer.close()
            try:
                await asyncio.wait_for(writer.wait_closed(), 1)
            except Exception:
                writer.transport.abort()
            tasks.discard(task)

    context.set_servername_callback(observed_sni)
    server = await asyncio.start_server(
        handle,
        "127.0.0.1",
        0,
        ssl=context,
        ssl_handshake_timeout=3,
        ssl_shutdown_timeout=1,
        limit=16384,
    )
    port = server.sockets[0].getsockname()[1]
    try:
        yield port, requests, sni
    finally:
        server.close()
        await server.wait_closed()
        remaining = list(tasks)
        for task in remaining:
            task.cancel()
        await asyncio.gather(*remaining, return_exceptions=True)
        assert not tasks
        logger.info("web_fetch_test_tls_server_joined")


class AuthoredPeerView:
    """Delegate a real loopback TLS writer while explicitly authoring only the public peer observation for framing tests."""

    def __init__(self, writer, pin):
        """Retain the real socket and clearly separate its actual loopback address from the authored test pin."""
        self.writer, self.pin = writer, pin
        self.transport = writer.transport

    def get_extra_info(self, name):
        """Return the authored pin only for this controlled positive framing seam; all other socket metadata remains real."""
        return (
            (self.pin, 443) if name == "peername" else self.writer.get_extra_info(name)
        )

    def write(self, raw):
        """Forward exact request bytes through the actual verifying TLS session."""
        return self.writer.write(raw)

    async def drain(self):
        """Join actual socket write backpressure."""
        await self.writer.drain()

    def close(self):
        """Request actual TLS transport closure."""
        self.writer.close()

    async def wait_closed(self):
        """Join actual TLS socket shutdown before the request releases capacity."""
        await self.writer.wait_closed()


@pytest.mark.asyncio
async def test_real_tls_sni_host_framing_and_text_with_authored_peer_view(
    tls_material, caplog
):
    """Verify real TLS/Host/body/text transport while disclosing that the positive public-pin view is authored."""
    caplog.set_level(logging.DEBUG)
    server_context, client_context = tls_contexts(tls_material)
    async with tls_server(server_context, response_bytes()) as (port, requests, sni):
        calls, sockets = [], []

        async def resolve(host):
            """Supply an eligible authored DNS result without changing the production public-address policy."""
            return ("8.8.8.8",)

        async def connect(host, pin):
            """Dial the explicit test socket with the original TLS hostname and record its real loopback peer."""
            reader, writer = await asyncio.open_connection(
                "127.0.0.1",
                port,
                ssl=client_context,
                server_hostname=host,
                ssl_shutdown_timeout=1,
            )
            assert writer.get_extra_info("peername")[0] == "127.0.0.1"
            sockets.append(writer.get_extra_info("socket"))
            calls.append((host, pin))
            return reader, AuthoredPeerView(writer, pin)

        current = BoundedWebFetcher(
            client=PublicHTTPSClient(resolver=resolve, connector=connect)
        )
        result = await current.fetch("https://example.org/source?private=tls-fixture")
        assert (
            result.text == "Atlas G-17."
            and result.final_url == "https://example.org/source?private=tls-fixture"
        )
        assert len(requests) == 1 and requests[0].startswith(
            b"GET /source?private=tls-fixture HTTP/1.1\r\n"
        )
        assert (
            b"Host: example.org\r\n" in requests[0]
            and sni == ["example.org"]
            and calls == [("example.org", "8.8.8.8")]
        )
        assert not current.operations and not current.admission.locked()
        assert len(sockets) == 1 and sockets[0].fileno() == -1
    assert "private=tls-fixture" not in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["hostname", "ca"])
async def test_real_tls_certificate_fences_before_any_http_request(
    tls_material, failure
):
    """Reject an actual wrong-host or untrusted certificate without disabling verification or transmitting HTTP."""
    server_context, client_context = tls_contexts(tls_material)
    if failure == "ca":
        client_context = module.system_tls_context()
    host = "wrong.example.org" if failure == "hostname" else "example.org"
    async with tls_server(server_context, response_bytes()) as (port, requests, sni):

        async def resolve(name):
            """Provide a public DNS seam so the actual TLS trust fence is the tested failure."""
            return ("8.8.8.8",)

        async def connect(name, pin):
            """Use the actual test endpoint with certificate/hostname verification still required."""
            return await asyncio.open_connection(
                "127.0.0.1",
                port,
                ssl=client_context,
                server_hostname=name,
                ssl_shutdown_timeout=1,
            )

        with pytest.raises(WebFetchError, match="web_fetch_tls_failed"):
            await PublicHTTPSClient(resolver=resolve, connector=connect).get(
                "https://" + host + "/"
            )
        assert requests == [] and sni == [host]


@pytest.mark.asyncio
async def test_real_loopback_peer_is_denied_without_an_authored_peer_view(tls_material):
    """Prove actual socket peer inspection blocks loopback even after an eligible DNS seam and valid TLS handshake."""
    server_context, client_context = tls_contexts(tls_material)
    async with tls_server(server_context, response_bytes()) as (port, requests, sni):

        async def resolve(host):
            """Return an eligible public address so the actual connected peer must still be checked."""
            return ("8.8.8.8",)

        async def connect(host, pin):
            """Return the real loopback writer without replacing its peer metadata."""
            return await asyncio.open_connection(
                "127.0.0.1",
                port,
                ssl=client_context,
                server_hostname=host,
                ssl_shutdown_timeout=1,
            )

        with pytest.raises(WebFetchError, match="web_fetch_address_denied"):
            await PublicHTTPSClient(resolver=resolve, connector=connect).get(
                "https://example.org/"
            )
        assert requests == [] and sni == ["example.org"]


@pytest.mark.asyncio
async def test_production_numeric_dial_arguments_preserve_actual_sni(
    tls_material, monkeypatch
):
    """Check the real production dial signature and SNI through a disclosed loopback/CA-only connector seam."""
    server_context, client_context = tls_contexts(tls_material)
    original = asyncio.open_connection
    observed = []
    async with tls_server(server_context, response_bytes()) as (port, requests, sni):

        async def redirected(**options):
            """Observe exact production pin/family/trust arguments before explicitly substituting the owned TLS test endpoint/CA."""
            assert (
                options["host"] == "8.8.8.8"
                and options["port"] == 443
                and options["family"] == socket.AF_INET
            )
            assert (
                options["ssl"].verify_mode == ssl.CERT_REQUIRED
                and options["ssl"].check_hostname
            )
            assert (
                options["ssl"].keylog_filename is None
                and options["server_hostname"] == "example.org"
            )
            assert options["limit"] == 16384
            observed.append(True)
            options.update(host="127.0.0.1", port=port, ssl=client_context)
            return await original(**options)

        monkeypatch.setattr(module.asyncio, "open_connection", redirected)
        _, writer = await module.open_pinned_tls("example.org", "8.8.8.8")
        await close_writer(writer)
        assert observed == [True] and sni == ["example.org"] and requests == []
