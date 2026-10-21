"""Observe one isolated dynamic-text page using finite trusted CDP policy and host-only verified resource fulfillment."""

import asyncio
import base64
import hashlib
import json
import logging
from dataclasses import asdict
from urllib.parse import urljoin

from src.application.ports.browser import (
    BrowserHTTPResponse,
    BrowserPage,
    BrowserResource,
)
from src.application.services.browser_policy import (
    BrowserError,
    browser_url,
    fulfillment_headers,
    request_policy,
    resource_representation,
    snapshot_text,
)
from src.application.services.web_fetch_policy import header_map, public_address
from src.application.services.web_fetch_tasks import finish_owned, spawn_owned
from src.infrastructure.browser_cdp import CDPChannel
from src.infrastructure.browser_resources import BrowserResourceClient
from src.infrastructure.browser_runtime import NativeBrowserWorker
from src.infrastructure.public_https import REDIRECT_STATUSES

logger = logging.getLogger(__name__)


class BrowserSession:
    """Bind one anonymous page/context to a finite native command policy and operation-owned resource budget."""

    def __init__(self, url, worker, resources):
        """Prepare inert trusted state without launching a page, fetching a resource or publishing source content."""
        self.url, self.worker, self.resources = url, worker, resources
        self.channel = CDPChannel(worker, self.event)
        self.context = self.target = self.session = self.main_frame = None
        self.expected_document, self.served_document = url, None
        self.loader = None
        self.loaded_ids = set()
        self.loaded = asyncio.Event()
        self.attempts = self.total_bytes = self.blocked = self.redirects = 0
        self.records = []
        logger.info("browser_session_initialized")

    def event(self, value):
        """Dispatch only fixed trusted event behavior without executing page-provided methods, code or actions."""
        method, params = value["method"], value.get("params", {})
        if method == "Browser.downloadWillBegin":
            self.channel.fail(BrowserError("browser_download_denied"))
        elif method == "Target.attachedToTarget":
            info = params.get("targetInfo", {})
            known_kind = (
                info.get("type")
                if info.get("type")
                in {
                    "page",
                    "tab",
                    "iframe",
                    "worker",
                    "service_worker",
                    "shared_worker",
                    "background_page",
                }
                else "other"
            )
            logger.info(
                "browser_attached_target type=%s same_context=%s owned=%s",
                known_kind,
                info.get("browserContextId") == self.context,
                info.get("targetId") == self.target,
            )
            if info.get("targetId") != self.target:
                self.channel.spawn_handler(
                    self.reject_target(
                        info.get("targetId"),
                        violation=info.get("browserContextId") == self.context,
                    )
                )
        elif value.get("sessionId") == self.session:
            if method == "Page.frameAttached" or (
                method
                in {"Page.frameRequestedNavigation", "Page.frameScheduledNavigation"}
                and self.served_document is not None
            ):
                self.channel.fail(BrowserError("browser_navigation_denied"))
            elif method == "Fetch.requestPaused":
                self.channel.spawn_handler(self.fulfill(params))
            elif (
                method == "Page.lifecycleEvent"
                and params.get("name") == "load"
                and params.get("frameId") == self.main_frame
            ):
                loader = params.get("loaderId")
                if type(loader) is not str or len(self.loaded_ids) >= 32:
                    self.channel.fail(BrowserError("browser_event_limit"))
                    return
                self.loaded_ids.add(loader)
                if loader == self.loader:
                    self.loaded.set()
            elif method == "Page.javascriptDialogOpening":
                self.channel.spawn_handler(self.dismiss_dialog())
            elif method == "Inspector.targetCrashed":
                self.channel.fail(BrowserError("browser_runtime_unavailable"))

    async def reject_target(self, target, *, violation=True):
        """Close an unowned popup/worker/frame target without resuming it or granting a host resource channel."""
        if type(target) is not str or not 1 <= len(target) <= 256:
            raise BrowserError("browser_protocol_invalid")
        await self.channel.call("Target.closeTarget", dict(targetId=target))
        if violation:
            raise BrowserError("browser_navigation_denied")
        logger.info("browser_bootstrap_target_closed")

    async def dismiss_dialog(self):
        """Dismiss native JavaScript dialogs without rendering their untrusted text or accepting an action."""
        await self.channel.call(
            "Page.handleJavaScriptDialog", dict(accept=False), session=self.session
        )
        logger.info("browser_dialog_denied")

    async def fulfill(self, params):
        """Supply only complete host-verified GET resource bytes, never forwarding page credentials or write methods."""
        identifier = params.get("requestId")
        if (
            type(identifier) is not str
            or not 1 <= len(identifier) <= 256
            or "responseStatusCode" in params
        ):
            raise BrowserError("browser_protocol_invalid")
        decision = request_policy(params, self.main_frame, self.expected_document)
        if decision is None:
            self.blocked += 1
            await self.channel.call(
                "Fetch.failRequest",
                dict(requestId=identifier, errorReason="BlockedByClient"),
                session=self.session,
            )
            return
        if self.attempts >= 32:
            raise BrowserError("browser_resource_limit")
        url, kind = decision
        self.attempts += 1
        response = await self.resources.get(url, kind)
        if (
            type(response) is not BrowserHTTPResponse
            or response.url != url
            or type(response.status) is not int
            or type(response.body) is not bytes
            or len(response.body) > 1048576
        ):
            raise BrowserError("browser_protocol_invalid")
        public_address(response.pinned_address)
        values = header_map(response.headers)
        if response.status in REDIRECT_STATUSES:
            self.redirects += 1
            if self.redirects > 3:
                raise BrowserError("browser_resource_limit")
            location = values.get("location")
            if not location or len(location) > 2048 or location != location.strip():
                raise BrowserError("browser_navigation_denied")
            try:
                following = browser_url(urljoin(url, location))
            except (ValueError, BrowserError):
                raise BrowserError("browser_navigation_denied") from None
            if kind == "Document":
                self.expected_document = following
            self.records.append(
                BrowserResource(
                    url,
                    kind,
                    response.status,
                    "redirect",
                    0,
                    hashlib.sha256(b"").hexdigest(),
                    response.pinned_address,
                )
            )
            await self.channel.call(
                "Fetch.fulfillRequest",
                dict(
                    requestId=identifier,
                    responseCode=response.status,
                    responseHeaders=[dict(name="Location", value=following)],
                    body="",
                ),
                session=self.session,
            )
            logger.info("browser_protocol_redirect_fulfilled")
            return
        if response.status != 200:
            raise BrowserError("browser_resource_failed")
        media, encoding = resource_representation(response.headers, kind)
        response.body.decode(encoding, errors="strict")
        self.total_bytes += len(response.body)
        if self.total_bytes > 8388608:
            raise BrowserError("browser_resource_limit")
        if kind == "Document":
            self.served_document = url
            self.expected_document = None
        self.records.append(
            BrowserResource(
                url,
                kind,
                200,
                media,
                len(response.body),
                hashlib.sha256(response.body).hexdigest(),
                response.pinned_address,
            )
        )
        await self.channel.call(
            "Fetch.fulfillRequest",
            dict(
                requestId=identifier,
                responseCode=200,
                responseHeaders=fulfillment_headers(
                    response.headers, media, len(response.body)
                ),
                body=base64.b64encode(response.body).decode("ascii"),
            ),
            session=self.session,
        )
        logger.info("browser_verified_resource_fulfilled bytes=%d", len(response.body))

    async def setup(self):
        """Create one anonymous owned page, deny permissions/downloads and install interception before its first navigation."""
        self.channel.start()
        version = await self.channel.call("Browser.getVersion")
        if version.get("product") != self.worker.config["expected_product"]:
            raise BrowserError("browser_runtime_unavailable")
        self.context = (
            await self.channel.call(
                "Target.createBrowserContext", dict(disposeOnDetach=True)
            )
        )["browserContextId"]
        await self.channel.call(
            "Browser.setDownloadBehavior",
            dict(behavior="deny", browserContextId=self.context, eventsEnabled=True),
        )
        for name in (
            "geolocation",
            "notifications",
            "camera",
            "microphone",
            "clipboard-read",
            "clipboard-write",
        ):
            await self.channel.call(
                "Browser.setPermission",
                dict(
                    permission=dict(name=name),
                    setting="denied",
                    browserContextId=self.context,
                ),
            )
        self.target = (
            await self.channel.call(
                "Target.createTarget",
                dict(url="about:blank", browserContextId=self.context),
            )
        )["targetId"]
        self.session = (
            await self.channel.call(
                "Target.attachToTarget", dict(targetId=self.target, flatten=True)
            )
        )["sessionId"]
        await self.channel.call(
            "Target.setAutoAttach",
            dict(autoAttach=True, waitForDebuggerOnStart=True, flatten=True),
        )
        await self.channel.call("Page.enable", session=self.session)
        await self.channel.call(
            "Page.setLifecycleEventsEnabled", dict(enabled=True), session=self.session
        )
        await self.channel.call("Network.enable", session=self.session)
        await self.channel.call(
            "Network.setCacheDisabled", dict(cacheDisabled=True), session=self.session
        )
        await self.channel.call(
            "Network.setBypassServiceWorker", dict(bypass=True), session=self.session
        )
        await self.channel.call(
            "Fetch.enable",
            dict(patterns=[dict(urlPattern="*", requestStage="Request")]),
            session=self.session,
        )
        await self.channel.call(
            "Target.setAutoAttach",
            dict(autoAttach=True, waitForDebuggerOnStart=True, flatten=True),
            session=self.session,
        )
        await self.channel.call("Runtime.runIfWaitingForDebugger", session=self.session)
        tree = await self.channel.call("Page.getFrameTree", session=self.session)
        self.main_frame = tree["frameTree"]["frame"]["id"]
        logger.info("browser_page_policy_installed")

    async def observe(self):
        """Navigate once, observe a bounded post-load text snapshot and reject any native/source/policy drift."""
        await self.setup()
        navigation = await self.channel.call(
            "Page.navigate", dict(url=self.url), session=self.session
        )
        self.loader = navigation.get("loaderId")
        if (
            navigation.get("errorText")
            or type(self.loader) is not str
            or navigation.get("frameId") != self.main_frame
        ):
            raise BrowserError("browser_navigation_denied")
        if self.loader in self.loaded_ids:
            self.loaded.set()
        await self.channel.wait_event(self.loaded)
        await asyncio.sleep(0.25)
        for _ in range(40):
            if not self.channel.handlers:
                break
            if self.channel.error:
                raise self.channel.error
            await asyncio.sleep(0.05)
        if self.channel.handlers:
            raise BrowserError("browser_timeout")
        snapshot = await self.channel.call(
            "DOMSnapshot.captureSnapshot", dict(computedStyles=[]), session=self.session
        )
        if self.channel.error:
            raise self.channel.error
        if self.served_document is None:
            raise BrowserError("browser_source_drift")
        final, title, text = snapshot_text(snapshot, self.served_document)
        result = BrowserPage(
            self.url,
            final,
            title,
            text,
            hashlib.sha256(text.encode()).hexdigest(),
            tuple(self.records),
            self.blocked,
        )
        if (
            len(
                json.dumps(asdict(result), ensure_ascii=False, allow_nan=False).encode()
            )
            > 262144
        ):
            raise BrowserError("browser_text_limit")
        logger.info("browser_dynamic_text_observed bytes=%d", len(text.encode()))
        return result


class ReadOnlyBrowser:
    """Own one nonqueued anonymous dynamic-page operation until every host resource, pipe and container is retired."""

    def __init__(self, *, resources=None, worker_factory=None):
        """Bind inert trusted seams without creating jobs, starting a browser/model or opening a network connection."""
        self.resources = resources if resources is not None else BrowserResourceClient()
        self.worker_factory = (
            worker_factory if worker_factory is not None else NativeBrowserWorker
        )
        self.admission = asyncio.Lock()
        self.operations = set()
        self.closing = False
        logger.info("readonly_browser_initialized")

    async def run(self, url):
        """Retain a source-bound result only after confirmed CDP/resource/native cleanup, preserving uncertainty as a failure."""
        worker = self.worker_factory()
        session = None
        try:
            async with asyncio.timeout(30):
                await worker.start()
                session = BrowserSession(url, worker, self.resources)
                result = await session.observe()
        finally:
            try:
                if session is not None:
                    await session.channel.close()
            finally:
                await worker.close()
        if session.channel.error:
            raise session.channel.error
        if worker.fault is not None:
            raise worker.fault
        return result

    async def navigate(self, url):
        """Admit an explicit public URL only and join owned cancellation before allowing another operation."""
        url = browser_url(url)
        if self.closing:
            raise BrowserError("browser_closed")
        if self.admission.locked():
            raise BrowserError("browser_busy")
        await self.admission.acquire()
        caller, task = asyncio.current_task(), None
        try:
            self.operations.add(caller)
            task = spawn_owned(self.run(url))
            try:
                return await asyncio.shield(task)
            except asyncio.CancelledError:
                task.cancel()
                try:
                    await finish_owned(task)
                except BrowserError as error:
                    if error.code == "browser_cleanup_uncertain":
                        self.closing = True
                    logger.info(
                        "readonly_browser_cancelled_operation_joined code=%s",
                        error.code,
                    )
                except BaseException:
                    logger.info("readonly_browser_cancelled_operation_joined")
                raise
        except asyncio.CancelledError:
            raise
        except BrowserError as error:
            if error.code == "browser_cleanup_uncertain":
                self.closing = True
            logger.info("readonly_browser_operation_rejected code=%s", error.code)
            raise
        except TimeoutError:
            raise BrowserError("browser_timeout") from None
        except Exception:
            raise BrowserError("browser_internal") from None
        finally:
            self.operations.discard(caller)
            self.admission.release()
            logger.info("readonly_browser_operation_closed")

    async def shutdown(self):
        """Reject new operations and join only owned browser callers without touching shared models/services."""
        self.closing = True
        tasks = [task for task in self.operations if task is not asyncio.current_task()]
        for task in tasks:
            task.cancel()
        for task in tasks:
            try:
                await finish_owned(task)
            except BaseException:
                logger.info("readonly_browser_shutdown_request_joined")
        logger.info("readonly_browser_shutdown_complete")
