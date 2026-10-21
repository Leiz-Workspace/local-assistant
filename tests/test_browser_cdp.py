"""Exercise finite CDP admission, complete-frame bounds and joined cancellation using private authored pipes only."""

import asyncio
import inspect
import logging
from types import SimpleNamespace

import pytest

from src.application.services.browser_policy import BrowserError
from src.infrastructure import browser_cdp
from src.infrastructure.browser_cdp import CDPChannel

logger = logging.getLogger(__name__)


class AuthoredWriter:
    """Capture authored commands without opening native processes or any network connection."""

    def __init__(self):
        """Prepare an empty command transcript for deterministic bounded protocol assertions."""
        self.frames = []

    def write(self, raw):
        """Retain complete authored bytes without emitting them into audit logs."""
        self.frames.append(raw)

    async def drain(self):
        """Yield once to model a real pipe without introducing unowned tasks."""
        await asyncio.sleep(0)


def channel():
    """Build an inert channel over a bounded authored reader and writer, with no native transport claim."""
    process = SimpleNamespace(
        stdout=asyncio.StreamReader(limit=2097153), stdin=AuthoredWriter()
    )
    return CDPChannel(SimpleNamespace(process=process, fault=None), lambda event: None)


async def spin_until(predicate):
    """Wait a finite number of loop turns for an authored asynchronous protocol boundary."""
    for _ in range(100):
        if predicate():
            return
        await asyncio.sleep(0)
    raise AssertionError("authored_protocol_boundary_not_reached")


@pytest.mark.asyncio
async def test_constructor_is_inert_and_only_matching_reply_completes_command():
    """Require exact native-reply ownership and consume all reader/future resources on closure."""
    item = channel()
    assert item.reader is None and not item.pending and not item.handlers
    item.start()
    task = asyncio.create_task(item.call("Browser.getVersion"))
    await spin_until(lambda: item.worker.process.stdin.frames)
    item.worker.process.stdout.feed_data(b'{"id":1,"result":{"product":"authored"}}\0')
    assert await task == dict(product="authored")
    await item.close()
    assert item.reader.done() and not item.pending
    logger.info("browser_authored_cdp_reply_ownership_verified")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "method,params,session",
    [
        ("Runtime.evaluate", dict(expression="write()"), None),
        ("Page.printToPDF", {}, None),
        ("Browser.getVersion", [], None),
        ("Browser.getVersion", {}, ""),
        ("Browser.getVersion", {}, True),
        ("Browser.getVersion", dict(value=float("nan")), None),
        ("Browser.getVersion", dict(value="\ud800"), None),
        ("Browser.getVersion", dict(value="x" * 2097152), None),
    ],
)
async def test_arbitrary_commands_invalid_json_and_oversized_frames_never_reach_pipe(
    method, params, session
):
    """Deny page executable methods and malformed/oversized trusted commands before native I/O."""
    item = channel()
    with pytest.raises(BrowserError):
        await item.call(method, params, session=session)
    assert not item.worker.process.stdin.frames and not item.pending
    await item.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "raw",
    [
        b"[]\0",
        b'{"id":true,"result":{}}\0',
        b'{"id":-1,"result":{}}\0',
        b'{"id":1,"result":{}}\0',
        b'{"method":"a","method":"b"}\0',
        b'{"method":"event","params":NaN}\0',
        b'{"method":1,"params":{}}\0',
        b'{"method":"event","params":[]}\0',
        b'{"method":"event","params":"\xff"}\0',
        b"x" * 2097153 + b"\0",
    ],
)
async def test_malformed_native_frames_fail_without_raw_content_logging(raw, caplog):
    """Reject malformed complete native frames, including unknown IDs and duplicate keys, with finite diagnostics."""
    item = channel()
    item.start()
    item.worker.process.stdout.feed_data(raw)
    await asyncio.wait_for(item.failed.wait(), 1)
    assert isinstance(item.error, BrowserError)
    assert "params" not in caplog.text and "NaN" not in caplog.text
    await item.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("direction", ["input", "output"])
async def test_total_direction_budget_is_enforced_before_additional_private_frames(
    direction,
):
    """Stop cumulative CDP traffic at16MiB per direction rather than admitting many individually valid large frames."""
    item = channel()
    if direction == "input":
        item.input_bytes = 16777216
        item.start()
        item.worker.process.stdout.feed_data(b'{"method":"event"}\0')
        await asyncio.wait_for(item.failed.wait(), 1)
    else:
        item.output_bytes = 16777216
        with pytest.raises(BrowserError, match="browser_resource_limit"):
            await item.call("Browser.getVersion")
        assert not item.worker.process.stdin.frames
    assert item.error.code == "browser_resource_limit"
    await item.close()


@pytest.mark.asyncio
async def test_cancelled_command_retains_bounded_late_reply_tombstone_until_consumed():
    """Consume a known cancelled reply without treating it as a new command or leaking a future exception."""
    item = channel()
    item.start()
    task = asyncio.create_task(item.call("Browser.getVersion"))
    await spin_until(lambda: item.pending)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert item.pending[1].cancelled()
    item.worker.process.stdout.feed_data(b'{"id":1,"result":{}}\0')
    await spin_until(lambda: not item.pending)
    assert item.error is None
    await item.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("limit", ["pending", "commands", "events"])
async def test_command_and_event_admission_has_no_overflow_queue(limit):
    """Refuse beyond64 pending commands or4096 commands/events without granting another pipe request."""
    item = channel()
    if limit == "events":
        item.events = 4096
        item.start()
        item.worker.process.stdout.feed_data(b'{"method":"event"}\0')
        await asyncio.wait_for(item.failed.wait(), 1)
        assert item.error.code == "browser_event_limit"
    else:
        if limit == "pending":
            item.pending = {
                index: asyncio.get_running_loop().create_future() for index in range(64)
            }
        else:
            item.identifier = 4096
        with pytest.raises(BrowserError, match="browser_event_limit"):
            await item.call("Browser.getVersion")
        assert not item.worker.process.stdin.frames
    await item.close()


@pytest.mark.asyncio
async def test_handler_limit_closes_unadmitted_coroutine_and_joins_admitted_tasks():
    """Retain at mosteight handler tasks and close the ninth coroutine without starting its body."""
    item = channel()
    entered = []

    async def wait():
        """Record admitted work then block until the owned channel cancels it."""
        entered.append(True)
        await asyncio.Event().wait()

    for _ in range(8):
        item.spawn_handler(wait())
    await spin_until(lambda: len(entered) == 8)
    pending = wait()
    item.spawn_handler(pending)
    assert inspect.getcoroutinestate(pending) == inspect.CORO_CLOSED
    assert len(entered) == 8 and item.error.code == "browser_event_limit"
    tasks = set(item.handlers)
    await item.close()
    assert all(task.done() for task in tasks) and not item.handlers


@pytest.mark.asyncio
async def test_waiter_dispatch_failure_joins_already_created_waiter(monkeypatch):
    """Join the first temporary lifecycle waiter if dispatch of the failure waiter is unavailable."""
    item, created = channel(), []

    def dispatch(pending):
        """Inject only the second waiter task-creation failure while closing its unadmitted coroutine."""
        if created:
            pending.close()
            raise RuntimeError("authored_dispatch_failure")
        task = asyncio.create_task(pending)
        created.append(task)
        return task

    monkeypatch.setattr(browser_cdp, "spawn_owned", dispatch)
    with pytest.raises(RuntimeError, match="authored_dispatch_failure"):
        await item.wait_event(asyncio.Event())
    assert created[0].done()


@pytest.mark.asyncio
async def test_repeated_cancellation_waits_for_handler_cleanup_acknowledgment():
    """Keep channel closure pending until an owned cancellation-resistant handler actually releases its resources."""
    item = channel()
    entered, cleanup, release = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def owned():
        """Model a host resource whose cancellation cleanup must finish before native removal can proceed."""
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            cleanup.set()
            await release.wait()

    item.spawn_handler(owned())
    await entered.wait()
    closing = asyncio.create_task(item.close())
    await cleanup.wait()
    closing.cancel()
    await asyncio.sleep(0)
    closing.cancel()
    assert not closing.done()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await closing
    assert not item.handlers


@pytest.mark.asyncio
async def test_close_dispatch_failure_still_joins_reader_and_reports_failure(
    monkeypatch,
):
    """Use direct owned cleanup when a cleanup task cannot be created, without pretending the dispatch succeeded."""
    item = channel()
    item.start()

    def unavailable(pending):
        """Reject a cleanup dispatch and close its coroutine before direct fallback joins the reader."""
        pending.close()
        raise RuntimeError("authored_dispatch_failure")

    monkeypatch.setattr(browser_cdp, "spawn_owned", unavailable)
    with pytest.raises(BrowserError, match="browser_protocol_invalid"):
        await item.close()
    assert item.reader.done() and item.closed
