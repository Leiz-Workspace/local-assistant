"""Verify anonymous browser target scope and owned-operation fences without real browser or public network activity."""

import asyncio
import hashlib
import logging
from types import SimpleNamespace

import pytest

from src.application.ports.browser import BrowserHTTPResponse
from src.application.services.browser_policy import BrowserError
from src.application.services.web_fetch_policy import WebFetchError
from src.infrastructure.readonly_browser import BrowserSession, ReadOnlyBrowser

logger = logging.getLogger(__name__)


@pytest.mark.asyncio
@pytest.mark.parametrize("same_context", [False, True])
async def test_unowned_targets_are_never_resumed_or_given_resources(
    same_context, monkeypatch
):
    """Close bootstrap pages quietly outside the owned context and reject same-context popup/worker authority."""
    session = BrowserSession("https://example.org/", SimpleNamespace(fault=None), None)
    session.context, session.target = "owned-context", "owned-page"
    pending, calls = [], []

    def retain(coroutine):
        """Capture the fixed deny handler without starting a CDP reader or native process."""
        pending.append(coroutine)

    async def command(method, params=None, **options):
        """Acknowledge only fixed target-close behavior without a network or arbitrary command endpoint."""
        calls.append((method, params))
        return dict(success=True)

    monkeypatch.setattr(session.channel, "spawn_handler", retain)
    monkeypatch.setattr(session.channel, "call", command)
    session.event(
        dict(
            method="Target.attachedToTarget",
            params=dict(
                targetInfo=dict(
                    targetId="other-page",
                    type="page",
                    browserContextId="owned-context"
                    if same_context
                    else "default-context",
                )
            ),
        )
    )
    assert len(pending) == 1
    if same_context:
        with pytest.raises(BrowserError, match="browser_navigation_denied"):
            await pending[0]
    else:
        assert await pending[0] is None
    assert calls == [("Target.closeTarget", dict(targetId="other-page"))]


def test_owned_page_autoattach_does_not_close_or_resume_it(monkeypatch):
    """Retain only the known page target while policy installation controls its explicit debugger resume."""
    session = BrowserSession("https://example.org/", SimpleNamespace(fault=None), None)
    session.context, session.target = "owned-context", "owned-page"

    def forbidden(pending):
        """Fail if an owned target is mistaken for a popup or granted an implicit resume."""
        pending.close()
        raise AssertionError("owned_target_changed")

    monkeypatch.setattr(session.channel, "spawn_handler", forbidden)
    session.event(
        dict(
            method="Target.attachedToTarget",
            params=dict(
                targetInfo=dict(
                    targetId="owned-page", type="page", browserContextId="owned-context"
                )
            ),
        )
    )


@pytest.mark.asyncio
async def test_controller_constructor_invalid_url_busy_and_shutdown_do_not_start_native_work(
    monkeypatch,
):
    """Deny invalid/concurrent/closed admission before resource acquisition and join only the owned active caller."""
    browser = ReadOnlyBrowser(resources=object(), worker_factory=object())
    entered = asyncio.Event()

    async def wait(url):
        """Hold one authored operation without acquiring real native or network resources."""
        entered.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(browser, "run", wait)
    with pytest.raises(BrowserError):
        await browser.navigate("http://127.0.0.1/")
    assert not browser.operations and not browser.admission.locked()
    task = asyncio.create_task(browser.navigate("https://example.org/"))
    await entered.wait()
    with pytest.raises(BrowserError, match="browser_busy"):
        await browser.navigate("https://example.org/second")
    await browser.shutdown()
    assert (
        task.cancelled() and not browser.operations and not browser.admission.locked()
    )
    with pytest.raises(BrowserError, match="browser_closed"):
        await browser.navigate("https://example.org/")


@pytest.mark.asyncio
async def test_cleanup_uncertainty_poisons_adapter_even_when_original_caller_is_cancelled(
    monkeypatch,
):
    """Retain the closed admission fence after cleanup uncertainty instead of reusing an ambiguous native operation."""
    browser = ReadOnlyBrowser(resources=object(), worker_factory=object())
    entered = asyncio.Event()

    async def uncertain(url):
        """Model a cancellation followed by an explicit native cleanup uncertainty failure."""
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            raise BrowserError("browser_cleanup_uncertain")

    monkeypatch.setattr(browser, "run", uncertain)
    task = asyncio.create_task(browser.navigate("https://example.org/"))
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert browser.closing and not browser.operations and not browser.admission.locked()
    with pytest.raises(BrowserError, match="browser_closed"):
        await browser.navigate("https://example.org/")


@pytest.mark.asyncio
async def test_worker_cleanup_runs_when_cdp_cleanup_raises(monkeypatch):
    """Always execute native removal after a CDP cleanup error, without returning an uncleaned successful result."""
    from src.infrastructure import readonly_browser

    calls = []

    class Worker:
        """Represent an authored acquired native handle with explicit retirement acknowledgment."""

        fault = None

        async def start(self):
            """Record acquisition without opening real processes or paths."""
            calls.append("start")

        async def close(self):
            """Record native cleanup even if the channel cleanup failed first."""
            calls.append("worker_close")

    class Session:
        """Represent an authored observation whose pipe cleanup fails."""

        def __init__(self, *args):
            """Bind a failing private channel without starting a reader."""
            self.channel = self

        async def observe(self):
            """Return an authored value that must never escape failed cleanup."""
            return object()

        async def close(self):
            """Fail CDP cleanup before the mandatory outer native cleanup executes."""
            calls.append("channel_close")
            raise BrowserError("browser_protocol_invalid")

    monkeypatch.setattr(readonly_browser, "BrowserSession", Session)
    browser = ReadOnlyBrowser(resources=object(), worker_factory=Worker)
    with pytest.raises(BrowserError, match="browser_protocol_invalid"):
        await browser.navigate("https://example.org/")
    assert calls == ["start", "channel_close", "worker_close"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "method",
    [
        "Page.frameAttached",
        "Page.frameRequestedNavigation",
        "Page.frameScheduledNavigation",
    ],
)
async def test_native_frame_and_renderer_navigation_events_fail_before_host_fetch(
    method,
):
    """Deny child frames and post-source renderer navigation before a pending native load can stall."""
    session = BrowserSession("https://example.org/", SimpleNamespace(fault=None), None)
    session.session = "owned-session"
    session.served_document = "https://example.org/"
    session.event(dict(method=method, sessionId="owned-session", params={}))
    assert session.channel.error.code == "browser_navigation_denied"
    assert not session.records and session.attempts == 0
    await session.channel.close()


def fixture_session(response):
    """Create one authored resource/session seam that captures fixed native fulfillment without a real TLS claim."""
    calls = []

    class Resources:
        """Return one bounded response to exercise the controller policy only."""

        async def get(self, url, kind):
            """Record the admitted host resource before returning its complete authored bytes."""
            calls.append((url, kind))
            return response

    async def command(method, params=None, **options):
        """Capture fixed private CDP fulfillment without starting native command or reader tasks."""
        calls.append((method, params))
        return {}

    session = BrowserSession(
        "https://example.org/", SimpleNamespace(fault=None), Resources()
    )
    session.main_frame, session.session = "owned-frame", "owned-session"
    session.channel.call = command
    request = dict(
        requestId="known-request",
        frameId="owned-frame",
        resourceType="Document",
        request=dict(url="https://example.org/", method="GET"),
    )
    return session, request, calls


@pytest.mark.asyncio
async def test_document_complete_bytes_are_source_bound_and_cookie_authority_is_dropped():
    """Hash the actual complete authored response, retain actual source URL and discard source cookie headers."""
    response = BrowserHTTPResponse(
        "https://example.org/",
        200,
        (("content-type", "text/html"), ("set-cookie", "private=denied")),
        b"<p>Complete.</p>",
        "8.8.8.8",
    )
    session, request, calls = fixture_session(response)
    await session.fulfill(request)
    assert session.served_document == response.url and session.expected_document is None
    assert session.records[0].body_sha256 == hashlib.sha256(response.body).hexdigest()
    assert all(
        row["name"].lower() != "set-cookie" for row in calls[-1][1]["responseHeaders"]
    )
    await session.channel.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mutation",
    [
        "request_limit",
        "bytes_limit",
        "source_url",
        "body_type",
        "body_limit",
        "private_pin",
        "status",
        "invalid_utf8",
        "attachment",
    ],
)
async def test_controller_rejects_resource_budget_provenance_and_representation_drift(
    mutation,
):
    """Refuse complete-resource drift and overflow before a native response body is supplied."""
    from dataclasses import replace

    response = BrowserHTTPResponse(
        "https://example.org/",
        200,
        (("content-type", "text/html"),),
        b"<p>Complete.</p>",
        "8.8.8.8",
    )
    changes = {
        "source_url": dict(url="https://example.org/unfetched"),
        "body_type": dict(body="invalid"),
        "body_limit": dict(body=b"x" * 1048577),
        "private_pin": dict(pinned_address="127.0.0.1"),
        "status": dict(status=404),
        "invalid_utf8": dict(body=b"\xff"),
        "attachment": dict(
            headers=(
                ("content-type", "text/html"),
                ("content-disposition", "attachment"),
            )
        ),
    }
    session, request, calls = fixture_session(
        replace(response, **changes.get(mutation, {}))
    )
    if mutation == "request_limit":
        session.attempts = 32
    elif mutation == "bytes_limit":
        session.total_bytes = 8388608
    expected_error = (
        WebFetchError
        if mutation == "private_pin"
        else UnicodeDecodeError
        if mutation == "invalid_utf8"
        else BrowserError
    )
    with pytest.raises(expected_error):
        await session.fulfill(request)
    assert not any(call[0] == "Fetch.fulfillRequest" for call in calls)
    if mutation == "request_limit":
        assert not calls
    await session.channel.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "location,denied",
    [
        ("/final", False),
        ("https://127.0.0.1/", True),
        ("http://example.org/", True),
        ("https://user:password@example.org/", True),
    ],
)
async def test_http_document_redirect_revalidates_target_before_native_navigation(
    location, denied
):
    """Permit only an explicitly source-served public HTTPS redirect while refusing private, downgrade or credential authority."""
    response = BrowserHTTPResponse(
        "https://example.org/", 302, (("location", location),), b"", "8.8.8.8"
    )
    session, request, calls = fixture_session(response)
    if denied:
        with pytest.raises(BrowserError, match="browser_navigation_denied"):
            await session.fulfill(request)
        assert not session.records and len(calls) == 1
    else:
        await session.fulfill(request)
        assert session.expected_document == "https://example.org/final"
        assert session.served_document is None and session.records[0].status == 302
    await session.channel.close()


@pytest.mark.asyncio
async def test_operation_dispatch_failure_closes_coroutine_and_releases_admission(
    monkeypatch,
):
    """Close an unadmitted operation coroutine and release the per-adapter slot after task dispatch failure."""
    import inspect

    from src.infrastructure import readonly_browser

    pending = []

    def unavailable(coroutine):
        """Inject dispatch failure after closing the never-started browser operation."""
        pending.append(coroutine)
        coroutine.close()
        raise RuntimeError("authored_dispatch_failure")

    monkeypatch.setattr(readonly_browser, "spawn_owned", unavailable)
    browser = ReadOnlyBrowser(resources=object(), worker_factory=object())
    with pytest.raises(BrowserError, match="browser_internal"):
        await browser.navigate("https://example.org/")
    assert inspect.getcoroutinestate(pending[0]) == inspect.CORO_CLOSED
    assert not browser.operations and not browser.admission.locked()
