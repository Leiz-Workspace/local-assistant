"""Exercise the exact cached network-none browser worker/CDP/container lifecycle with owned blank or authored resources."""

import asyncio
import json
import logging

import pytest

from src.application.ports.browser import BrowserHTTPResponse
from src.application.services.browser_policy import BrowserError
from src.infrastructure.browser_runtime import NativeBrowserWorker
from src.infrastructure.readonly_browser import ReadOnlyBrowser

logger = logging.getLogger(__name__)


async def command(worker, identifier, method, params=None):
    """Send a finite trusted blank-page CDP command and retain only its matching complete native reply."""
    raw = (
        json.dumps(dict(id=identifier, method=method, params=params or {})).encode()
        + b"\0"
    )
    worker.process.stdin.write(raw)
    await worker.process.stdin.drain()
    async with asyncio.timeout(10):
        while True:
            frame = await worker.process.stdout.readuntil(b"\0")
            assert len(frame) <= 2097152
            value = json.loads(frame[:-1])
            if value.get("id") == identifier:
                assert "error" not in value
                return value["result"]


@pytest.mark.asyncio
async def test_actual_cached_worker_pipe_version_download_deny_and_exact_retirement(
    tmp_path,
):
    """Verify real source-snapshot/container/CDP confinement and acknowledged removal without public navigation or models."""
    worker = NativeBrowserWorker(root=tmp_path / "jobs")
    try:
        await worker.start()
        version = await command(worker, 1, "Browser.getVersion")
        assert version["product"] == "Chrome/149.0.7827.155"
        assert (
            await command(
                worker,
                2,
                "Browser.setDownloadBehavior",
                dict(behavior="deny", eventsEnabled=True),
            )
            == {}
        )
        await command(worker, 3, "Browser.close")
        await asyncio.wait_for(worker.process.wait(), 10)
        assert worker.process.returncode == 0
    finally:
        await worker.close()
    assert worker.retired and worker.closed and worker.fault is None
    assert (
        not worker.directory.exists()
        and not list(worker.root.iterdir())
        and worker.stderr_bytes <= 65536
    )
    logger.info("browser_native_blank_pipe_and_retirement_verified")


class AuthoredResources:
    """Supply explicit synthetic HTTPS-shaped page/script bytes to a real network-none browser without a public-network claim."""

    def __init__(self, pages):
        """Bind complete authored responses and empty host-call observations."""
        self.pages, self.calls = pages, []

    async def get(self, url, kind):
        """Return only an explicitly authored fixture resource, rejecting unknown page-selected targets."""
        self.calls.append((url, kind))
        body, media = self.pages[url]
        return BrowserHTTPResponse(
            url, 200, (("content-type", media),), body, "8.8.8.8"
        )


@pytest.mark.asyncio
async def test_actual_network_none_browser_renders_authored_inline_javascript_and_retires(
    tmp_path,
):
    """Require actual native JavaScript/layout output and exact container cleanup using authored resource bytes, no public TLS claim."""
    url = "https://example.org/dynamic"
    resources = AuthoredResources(
        {
            url: (
                b'<!doctype html><html><head><title>Dynamic fixture</title></head><body><p id="message">Loading</p><script>setTimeout(function(){document.getElementById("message").textContent="Native dynamic G-17.";},50);</script></body></html>',
                "text/html",
            )
        }
    )
    workers = []

    def factory():
        """Create and retain only an owned actual native worker under the isolated test job root."""
        worker = NativeBrowserWorker(root=tmp_path / "jobs")
        workers.append(worker)
        return worker

    browser = ReadOnlyBrowser(resources=resources, worker_factory=factory)
    result = await browser.navigate(url)
    assert (
        result.title == "Dynamic fixture"
        and "Native dynamic G-17." in result.text
        and "Loading" not in result.text
    )
    assert (
        result.final_url == url
        and result.browser_direct_network is False
        and result.semantic_validation is False
    )
    assert resources.calls == [(url, "Document")]
    assert all(
        worker.retired and worker.closed and not worker.directory.exists()
        for worker in workers
    )
    assert not browser.operations and not browser.admission.locked()


def authored_browser(tmp_path, resources):
    """Bind real native workers to a private test root and retain exact handles for retirement assertions."""
    workers = []

    def factory():
        """Create only an operation-owned cached native worker without changing any accepted running service."""
        worker = NativeBrowserWorker(root=tmp_path / "jobs")
        workers.append(worker)
        return worker

    return ReadOnlyBrowser(resources=resources, worker_factory=factory), workers


def require_retired(browser, workers):
    """Require confirmed native removal and empty known job roots before a controlled observation is accepted."""
    assert workers and all(
        worker.retired
        and worker.closed
        and not worker.directory.exists()
        and not list(worker.root.iterdir())
        for worker in workers
    )
    assert not browser.operations and not browser.admission.locked()
    logger.info("browser_authored_native_case_retirement_verified")


@pytest.mark.asyncio
async def test_actual_browser_external_script_stylesheet_and_json_get(tmp_path):
    """Require real native script/GET execution through host fulfillment while preserving source cookies as denied authority."""
    url = "https://example.org/dynamic"
    resources = AuthoredResources(
        {
            url: (
                b'<title>External fixture</title><link rel="stylesheet" href="/style.css"><p id="message">Loading</p><script src="/app.js"></script>',
                "text/html",
            ),
            "https://example.org/style.css": (b"p {color: black}", "text/css"),
            "https://example.org/app.js": (
                b'fetch("/data.json").then(r=>r.json()).then(d=>{document.getElementById("message").textContent=d.message;});',
                "application/javascript",
            ),
            "https://example.org/data.json": (
                b'{"message":"Native external G-18."}',
                "application/json",
            ),
        }
    )
    browser, workers = authored_browser(tmp_path, resources)
    result = await browser.navigate(url)
    assert "Native external G-18." in result.text and "Loading" not in result.text
    assert set(resources.calls) == {
        (url, "Document"),
        ("https://example.org/style.css", "Stylesheet"),
        ("https://example.org/app.js", "Script"),
        ("https://example.org/data.json", "XHR"),
    }
    assert len(resources.calls) == 4 and len(result.resources) == 4
    require_retired(browser, workers)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "script",
    [
        'fetch("/write",{method:"POST",body:"denied"}).catch(()=>{});',
        'fetch("http://127.0.0.1/private").catch(()=>{});',
        'fetch("https://127.0.0.1/private").catch(()=>{});',
        'window.location="https://example.org/other";',
        'history.replaceState(null,"","/unfetched");',
        'document.getElementById("form").submit();',
    ],
)
async def test_actual_native_page_cannot_grant_write_private_or_new_document_authority(
    tmp_path, script
):
    """Reject forbidden host request/provenance attempts or let native security block them, never forwarding a second host request."""
    url = "https://example.org/dynamic"
    body = (
        '<title>Denied fixture</title><p>Original source.</p><form id="form" method="post" action="https://example.org/write"></form><script>'
        + script
        + "</script>"
    ).encode()
    resources = AuthoredResources({url: (body, "text/html")})
    browser, workers = authored_browser(tmp_path, resources)
    try:
        result = await browser.navigate(url)
    except BrowserError as error:
        assert error.code in {
            "browser_navigation_denied",
            "browser_source_drift",
            "browser_method_denied",
            "browser_url_denied",
        }
    else:
        assert "Original source." in result.text and result.final_url == url
        assert script.startswith('fetch("http://127.')
    assert resources.calls == [(url, "Document")]
    require_retired(browser, workers)


@pytest.mark.asyncio
async def test_actual_native_csp_blocks_decorative_worker_and_socket_egress(
    tmp_path,
):
    """Exercise native local CSP and zero-network confinement without silently granting a host resource for side effects."""
    url = "https://example.org/dynamic"
    body = b"""<title>CSP fixture</title><p>Read only source.</p>
<img src="https://example.org/image.png">
<script>
try {new Worker("https://example.org/worker.js");} catch(error) {}
try {new WebSocket("wss://example.org/socket");} catch(error) {}
</script>"""
    resources = AuthoredResources({url: (body, "text/html")})
    browser, workers = authored_browser(tmp_path, resources)
    result = await browser.navigate(url)
    assert "Read only source." in result.text
    assert resources.calls == [(url, "Document")]
    assert all(resource.kind == "Document" for resource in result.resources)
    require_retired(browser, workers)


@pytest.mark.asyncio
async def test_actual_native_frame_creation_is_explicitly_denied_before_load_can_stall(
    tmp_path,
):
    """Reject native child-frame creation even when source/local CSP prevents a remote frame resource request."""
    url = "https://example.org/dynamic"
    resources = AuthoredResources(
        {
            url: (
                b'<title>Frame fixture</title><p>Original.</p><iframe src="https://example.org/frame"></iframe>',
                "text/html",
            )
        }
    )
    browser, workers = authored_browser(tmp_path, resources)
    with pytest.raises(BrowserError, match="browser_navigation_denied"):
        await browser.navigate(url)
    assert resources.calls == [(url, "Document")]
    require_retired(browser, workers)


class HeldResources:
    """Retain an authored resource cancellation boundary until an explicit test cleanup acknowledgment is released."""

    def __init__(self):
        """Create finite entry/cancellation/release signals without public requests or native processes."""
        self.entered, self.cancelled, self.release = (
            asyncio.Event(),
            asyncio.Event(),
            asyncio.Event(),
        )

    async def get(self, url, kind):
        """Model an unpreemptible host resource cleanup that must be joined before releasing native admission."""
        self.entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            self.cancelled.set()
            await self.release.wait()


@pytest.mark.asyncio
async def test_actual_native_repeated_cancellation_holds_admission_until_resource_and_container_retire(
    tmp_path,
):
    """Keep a real container operation busy until the owned resource acknowledges cleanup despite repeated caller cancellation."""
    resources = HeldResources()
    browser, workers = authored_browser(tmp_path, resources)
    task = asyncio.create_task(browser.navigate("https://example.org/dynamic"))
    await asyncio.wait_for(resources.entered.wait(), 10)
    task.cancel()
    await asyncio.wait_for(resources.cancelled.wait(), 10)
    task.cancel()
    with pytest.raises(BrowserError, match="browser_busy"):
        await browser.navigate("https://example.org/second")
    assert not task.done() and not workers[0].retired
    resources.release.set()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, 10)
    require_retired(browser, workers)


@pytest.mark.asyncio
async def test_actual_native_unexpected_container_kill_fails_and_retires_exact_owned_job(
    tmp_path,
):
    """Detect actual CDP EOF after killing only the known owned native container and acknowledge its removal."""
    resources = HeldResources()
    browser, workers = authored_browser(tmp_path, resources)
    task = asyncio.create_task(browser.navigate("https://example.org/dynamic"))
    await asyncio.wait_for(resources.entered.wait(), 10)
    worker = workers[0]
    resources.release.set()
    code, _, _ = await worker.command("kill", "--signal=KILL", worker.container_id)
    assert code == 0
    with pytest.raises(BrowserError, match="browser_protocol_invalid"):
        await asyncio.wait_for(task, 10)
    assert resources.cancelled.is_set()
    require_retired(browser, workers)
