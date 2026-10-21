"""Carry bounded trusted CDP commands/events through an owned network-none worker without raw-content logging."""

import asyncio
import json
import logging

from src.application.services.browser_policy import BrowserError
from src.application.services.search_pipeline import unique_pairs
from src.application.services.web_fetch_tasks import finish_owned, spawn_owned

logger = logging.getLogger(__name__)
METHODS = frozenset(
    {
        "Browser.getVersion",
        "Browser.setDownloadBehavior",
        "Browser.setPermission",
        "Browser.close",
        "Target.createBrowserContext",
        "Target.createTarget",
        "Target.setAutoAttach",
        "Target.setDiscoverTargets",
        "Target.closeTarget",
        "Target.attachToTarget",
        "Target.disposeBrowserContext",
        "Page.enable",
        "Page.setLifecycleEventsEnabled",
        "Page.navigate",
        "Page.getFrameTree",
        "Page.handleJavaScriptDialog",
        "DOMSnapshot.captureSnapshot",
        "Runtime.runIfWaitingForDebugger",
        "Fetch.enable",
        "Fetch.failRequest",
        "Fetch.fulfillRequest",
        "Network.enable",
        "Network.setCacheDisabled",
        "Network.setBypassServiceWorker",
    }
)


def reject_constant(value):
    """Reject nonfinite JSON tokens without reflecting their contents or accepting private native diagnostics."""
    raise ValueError("nonfinite_cdp_value")


class CDPChannel:
    """Own one bounded pipe reader, finite command futures and nonqueued event-handler tasks."""

    def __init__(self, worker, on_event):
        """Bind trusted worker/callback objects without creating tasks or exposing an arbitrary command endpoint."""
        self.worker, self.on_event = worker, on_event
        self.pending, self.handlers = {}, set()
        self.identifier, self.events = 0, 0
        self.input_bytes = self.output_bytes = 0
        self.reader = None
        self.closed = False
        self.error = None
        self.failed = asyncio.Event()
        self.write_lock = asyncio.Lock()
        logger.info("browser_cdp_channel_initialized")

    def start(self):
        """Start exactly one owned CDP reader after native worker acquisition has completed."""
        self.reader = spawn_owned(self.read())
        logger.info("browser_cdp_reader_started")

    def fail(self, error):
        """Publish only the first finite failure and release pending trusted callers without leaking native error bodies."""
        if self.closed or self.error is not None:
            return
        self.error = (
            error
            if isinstance(error, BrowserError)
            else BrowserError("browser_protocol_invalid")
        )
        self.failed.set()
        for future in self.pending.values():
            if not future.done():
                future.set_exception(self.error)
        logger.info("browser_cdp_failed code=%s", self.error.code)

    async def call(self, method, params=None, *, session=None):
        """Send only a finite trusted command with a complete2MiB frame and at most64 pending futures."""
        if self.closed or self.error is not None or self.worker.fault is not None:
            raise self.error or self.worker.fault or BrowserError("browser_closed")
        if (
            type(method) is not str
            or method not in METHODS
            or (params is not None and type(params) is not dict)
        ):
            raise BrowserError("browser_protocol_invalid")
        if len(self.pending) >= 64 or self.identifier >= 4096:
            raise BrowserError("browser_event_limit")
        self.identifier += 1
        identifier = self.identifier
        payload = dict(id=identifier, method=method, params=params or {})
        if session is not None:
            if type(session) is not str or not 1 <= len(session) <= 256:
                raise BrowserError("browser_protocol_invalid")
            payload["sessionId"] = session
        try:
            raw = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode()
            if len(raw) > 2097152:
                raise BrowserError("browser_resource_limit")
        except (ValueError, UnicodeError):
            raise BrowserError("browser_protocol_invalid") from None
        future = asyncio.get_running_loop().create_future()
        self.pending[identifier] = future
        try:
            async with self.write_lock:
                self.output_bytes += len(raw) + 1
                if self.output_bytes > 16777216:
                    self.fail(BrowserError("browser_resource_limit"))
                    raise self.error
                self.worker.process.stdin.write(raw + b"\0")
                await self.worker.process.stdin.drain()
            logger.info("browser_cdp_command_sent")
            return await future
        except asyncio.CancelledError:
            if future.done() and not future.cancelled():
                future.exception()
            else:
                future.cancel()
            raise
        except BaseException:
            self.pending.pop(identifier, None)
            if future.done() and not future.cancelled():
                future.exception()
            elif not future.done():
                future.cancel()
            raise

    async def read(self):
        """Validate every complete native frame and dispatch only fixed callbacks, never page-generated methods or scripts."""
        try:
            while True:
                raw = await self.worker.process.stdout.readuntil(b"\0")
                self.input_bytes += len(raw)
                if len(raw) - 1 > 2097152 or self.input_bytes > 16777216:
                    raise BrowserError("browser_resource_limit")
                value = json.loads(
                    raw[:-1],
                    object_pairs_hook=unique_pairs,
                    parse_constant=reject_constant,
                )
                if type(value) is not dict:
                    raise BrowserError("browser_protocol_invalid")
                if "id" in value:
                    identifier = value["id"]
                    if type(identifier) is not int or identifier not in self.pending:
                        raise BrowserError("browser_protocol_invalid")
                    future = self.pending.pop(identifier)
                    if future.cancelled() or future.done():
                        continue
                    if "error" in value or type(value.get("result")) is not dict:
                        future.set_exception(BrowserError("browser_protocol_invalid"))
                    else:
                        future.set_result(value["result"])
                else:
                    self.events += 1
                    if self.events > 4096:
                        raise BrowserError("browser_event_limit")
                    if (
                        type(value.get("method")) is not str
                        or type(value.get("params", {})) is not dict
                    ):
                        raise BrowserError("browser_protocol_invalid")
                    self.on_event(value)
        except asyncio.CancelledError:
            raise
        except BrowserError as error:
            self.fail(error)
        except Exception:
            self.fail(BrowserError("browser_protocol_invalid"))

    def spawn_handler(self, pending):
        """Admit at mosteight owned event handlers without queueing extra native resource requests."""
        if self.closed or len(self.handlers) >= 8:
            pending.close()
            if not self.closed:
                self.fail(BrowserError("browser_event_limit"))
            return

        async def handle():
            """Retain handler ownership and convert only finite failures into the channel's first error."""
            try:
                await pending
            except asyncio.CancelledError:
                raise
            except BrowserError as error:
                self.fail(error)
            except Exception:
                self.fail(BrowserError("browser_protocol_invalid"))
            finally:
                self.handlers.discard(asyncio.current_task())

        try:
            task = spawn_owned(handle())
        except BaseException:
            pending.close()
            raise
        self.handlers.add(task)

    async def wait_event(self, event):
        """Wait for a trusted lifecycle signal or the first protocol failure, joining both temporary waiters."""
        ready = failed = None
        try:
            ready = spawn_owned(event.wait())
            failed = spawn_owned(self.failed.wait())
            await asyncio.wait([ready, failed], return_when=asyncio.FIRST_COMPLETED)
            if self.error is not None:
                raise self.error
        finally:
            for task in (ready, failed):
                if task is None:
                    continue
                if not task.done():
                    task.cancel()
                try:
                    await finish_owned(task)
                except BaseException:
                    logger.info("browser_cdp_lifecycle_waiter_joined")

    async def close_owned(self):
        """Stop dispatch and join only owned resource/reader tasks before native container removal."""
        self.closed = True
        tasks = list(self.handlers)
        if self.reader is not None:
            tasks.append(self.reader)
        for task in tasks:
            task.cancel()
        for task in tasks:
            try:
                await finish_owned(task)
            except BaseException:
                logger.info("browser_cdp_owned_task_joined")
        for future in self.pending.values():
            if not future.done():
                future.cancel()
            elif not future.cancelled():
                future.exception()
        self.pending.clear()
        logger.info("browser_cdp_channel_closed")

    async def close(self):
        """Join closure despite repeated caller cancellation before another operation can reuse native admission."""
        if self.closed:
            return
        try:
            task = spawn_owned(self.close_owned())
        except BaseException:
            await self.close_owned()
            raise BrowserError("browser_protocol_invalid") from None
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            await finish_owned(task)
            raise
