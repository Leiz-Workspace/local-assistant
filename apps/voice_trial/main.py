"""Serve an authenticated loopback research voice UI with explicit submission, finite admission and joined cancellation."""

import asyncio
import contextlib
import hmac
import ipaddress
import json
import logging
import secrets
import time
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse

from apps.voice_trial.audio import MAX_BODY, decode_wave
from src.application.services.voice_pipeline import VoiceError
from src.application.services.web_fetch_tasks import finish_owned, spawn_owned

LOGGER = logging.getLogger(__name__)
STATIC = Path(__file__).with_name("static")
ORIGINAL_STATIC = Path(__file__).parent.parent / "voice/static"
COOKIE = "voice_trial_session"
ASSETS = {
    "/": (STATIC / "index.html", "text/html"),
    "/page.mjs": (STATIC / "page.mjs", "text/javascript"),
    "/trial.mjs": (STATIC / "trial.mjs", "text/javascript"),
    "/recorder.mjs": (ORIGINAL_STATIC / "recorder.mjs", "text/javascript"),
    "/capture-worklet.js": (ORIGINAL_STATIC / "capture-worklet.js", "text/javascript"),
}


def configure_audit():
    """Enable only content-redacted trial lifecycle logs, leaving legacy model fingerprint logs disabled by default."""
    logger = logging.getLogger("apps.voice_trial")
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
        )
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False


def identity(value):
    """Accept a canonical random operation UUID without interpreting client text as paths or authority."""
    try:
        if type(value) is not str or len(value) != 36 or str(UUID(value)) != value:
            raise ValueError()
    except (ValueError, TypeError, AttributeError):
        raise VoiceError("invalid_input") from None
    return value


class Controller:
    """Own one nonqueued prepare/turn capability and a finite app-wide experimental budget."""

    def __init__(self, factory):
        """Inject model runtime creation while opening neither device nor model at page load."""
        self.factory = factory
        self.state = "idle"
        self.runtime = None
        self.preparation = self.active = None
        self.active_id = None
        self.prepares = self.attempts = 0
        self.seen = set()
        self.cancelled = set()
        self.closed = False

    def status(self):
        """Expose bounded noncontent readiness and quotas without identities, private paths or diagnostics."""
        return dict(
            state=self.state,
            remaining=max(0, 24 - self.attempts),
            preparations_remaining=max(0, 3 - self.prepares),
        )

    async def prepare(self):
        """Start only after an explicit request, never automatically retrying a failed or expired model load."""
        if (
            self.closed
            or self.active is not None
            or self.preparation is not None
            or self.state == "ready"
        ):
            raise VoiceError("busy")
        if self.prepares >= 3 or self.attempts >= 24:
            raise VoiceError("closed")
        self.prepares += 1
        self.state = "preparing"
        self.preparation = spawn_owned(self.load())
        LOGGER.info("trial_prepare_admitted count=%d", self.prepares)

    async def load(self):
        """Publish readiness only after the fixed native group actually loads, joining startup failure cleanup."""
        runtime = self.factory()
        self.runtime = runtime
        try:
            await runtime.start()
            if self.closed:
                raise asyncio.CancelledError()
            self.state = "ready"
        except BaseException:
            await finish_owned(spawn_owned(runtime.close()))
            self.runtime = None
            self.state = "idle" if self.closed else "error"
            LOGGER.warning("trial_prepare_failed")
        finally:
            self.preparation = None

    async def submit(self, request, operation):
        """Reserve admission before reading a bounded body and preserve attempts through error/cancellation."""
        if self.closed or self.state != "ready" or self.active is not None:
            raise VoiceError("busy")
        if self.attempts >= 24 or operation in self.seen or operation in self.cancelled:
            raise VoiceError("closed")
        self.state = "busy"
        self.active_id = operation
        self.attempts += 1
        self.seen.add(operation)
        self.active = spawn_owned(self.execute(request, operation))
        LOGGER.info("trial_submission_admitted count=%d", self.attempts)
        try:
            return await asyncio.shield(self.active)
        except asyncio.CancelledError:
            if self.active:
                self.active.cancel()
                with contextlib.suppress(BaseException):
                    await finish_owned(self.active)
            raise
        finally:
            self.active = self.active_id = None
            if self.state == "busy":
                self.state = "ready" if self.runtime else "idle"

    async def execute(self, request, operation):
        """Read exact explicit audio, cancel disconnects and expose only complete results from the current operation."""
        started = time.monotonic()
        actor = None
        try:
            async with asyncio.timeout(65):
                body = bytearray()
                async for chunk in request.stream():
                    body.extend(chunk)
                    if len(body) > MAX_BODY:
                        raise VoiceError("invalid_input")
                raw = bytes(body)
                body.clear()
                decode_wave(raw)
                actor = spawn_owned(self.runtime.ask(raw, "trial-" + operation))
                while not actor.done():
                    if await request.is_disconnected():
                        raise asyncio.CancelledError()
                    await asyncio.wait({actor}, timeout=0.1)
                value = actor.result()
                if operation in self.cancelled:
                    raise asyncio.CancelledError()
                LOGGER.info("trial_submission_completed count=%d", self.attempts)
                return dict(
                    value, id=operation, server_seconds=time.monotonic() - started
                )
        except VoiceError as error:
            if error.code not in {"no_speech", "invalid_input"}:
                await self.retire()
            raise
        except BaseException as error:
            if actor:
                actor.cancel()
                with contextlib.suppress(BaseException):
                    await finish_owned(actor)
            await self.retire()
            if isinstance(error, asyncio.CancelledError):
                raise
            raise VoiceError(
                "timeout" if isinstance(error, TimeoutError) else "dependency_failed"
            ) from None

    async def cancel(self, operation):
        """Cancel only a matching operation and remember early cancellations so delayed submissions cannot run."""
        if len(self.cancelled) >= 64 and operation not in self.cancelled:
            raise VoiceError("closed")
        self.cancelled.add(operation)
        if self.active_id == operation and self.active:
            self.active.cancel()
            with contextlib.suppress(BaseException):
                await finish_owned(self.active)
        LOGGER.info("trial_cancel_joined matching=%s", self.active_id == operation)

    async def retire(self):
        """Unload exactly this group's resources without automatic replacement or retry."""
        runtime, self.runtime = self.runtime, None
        self.state = "idle"
        if runtime:
            await finish_owned(spawn_owned(runtime.close()))
        LOGGER.info("trial_group_retired")

    async def release(self):
        """Explicitly stop preparation or an active group without permanently closing the web surface."""
        for task in (self.preparation, self.active):
            if task:
                task.cancel()
                with contextlib.suppress(BaseException):
                    await finish_owned(task)
        await self.retire()

    async def watch(self):
        """Check idle and active model guards and release an expired group without accepting another queued request."""
        while not self.closed:
            await asyncio.sleep(1)
            if self.runtime and self.state in {"ready", "busy"}:
                try:
                    self.runtime.health()
                except Exception:
                    if self.active:
                        self.active.cancel()
                        with contextlib.suppress(BaseException):
                            await finish_owned(self.active)
                    await self.retire()

    async def close(self):
        """Join preparation and active operations before retiring the optional research group."""
        self.closed = True
        for task in (self.preparation, self.active):
            if task:
                task.cancel()
                with contextlib.suppress(BaseException):
                    await finish_owned(task)
        await self.retire()
        LOGGER.info("trial_surface_closed")


def create_app(factory=None):
    """Create a loopback-only session-authenticated surface with fake-runtime injection for public tests."""
    configure_audit()
    if factory is None:
        from apps.voice_trial.native import NativeRuntime

        factory = NativeRuntime
    controller = Controller(factory)
    token = secrets.token_urlsafe(32)

    @asynccontextmanager
    async def lifespan(app):
        """Own the idle guard and joined shutdown without loading anything merely at service startup."""
        watcher = spawn_owned(controller.watch())
        try:
            yield
        finally:
            watcher.cancel()
            await asyncio.gather(watcher, return_exceptions=True)
            await controller.close()

    app = FastAPI(lifespan=lifespan, openapi_url=None, docs_url=None, redoc_url=None)
    app.state.controller = controller

    @app.middleware("http")
    async def protect(request, call_next):
        """Enforce loopback peer/Host, exact origin, finite API types and a non-URL HttpOnly session capability."""
        try:
            host = urlsplit("http://" + request.headers.get("host", ""))
            local = (
                host.hostname == "localhost"
                or ipaddress.ip_address(host.hostname).is_loopback
            )
            public_navigation = (
                request.method == "GET"
                and request.url.path == "/"
                and request.headers.get("sec-fetch-mode") == "navigate"
                and request.headers.get("sec-fetch-dest") == "document"
            )
            allowed = (
                request.client
                and ipaddress.ip_address(request.client.host).is_loopback
                and local
                and host.username is None
                and host.password is None
                and not host.path
                and not host.query
                and not host.fragment
                and len(request.headers.getlist("host")) == 1
                and not {
                    "forwarded",
                    "x-forwarded-for",
                    "x-forwarded-host",
                    "x-real-ip",
                }.intersection(request.headers)
                and (
                    request.headers.get("sec-fetch-site", "none")
                    in {"none", "same-origin"}
                    or public_navigation
                )
                and not request.url.query
            )
            origin = request.headers.get("origin")
            if origin is not None and origin != str(request.base_url).rstrip("/"):
                allowed = False
            api = request.url.path.startswith("/api/")
            authorized = hmac.compare_digest(request.cookies.get(COOKIE, ""), token)
            if api and not authorized:
                allowed = False
            if request.method == "POST" and (
                origin != str(request.base_url).rstrip("/")
                or request.headers.get("x-voice-submit") != "1"
            ):
                allowed = False
        except (ValueError, TypeError):
            allowed = False
        if not allowed:
            LOGGER.warning("trial_surface_access_denied")
            response = JSONResponse({"code": "local_session_required"}, status_code=403)
        else:
            try:
                response = await call_next(request)
            except Exception:
                LOGGER.warning("trial_surface_request_failed")
                response = JSONResponse({"code": "dependency_failed"}, status_code=503)
        response.headers.update(
            {
                "Cache-Control": "no-store",
                "X-Content-Type-Options": "nosniff",
                "Referrer-Policy": "no-referrer",
                "X-Frame-Options": "DENY",
                "Permissions-Policy": "microphone=(self), camera=(), geolocation=()",
                "Content-Security-Policy": "default-src 'none'; script-src 'self'; worker-src 'self'; connect-src 'self'; media-src blob:; style-src 'unsafe-inline'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'",
            }
        )
        if allowed and request.method == "GET" and request.url.path == "/":
            response.set_cookie(
                COOKIE, token, httponly=True, samesite="strict", path="/"
            )
        return response

    @app.exception_handler(VoiceError)
    async def voice_error(request, error):
        """Expose only finite error codes with no raw recording, transcript or native diagnostic."""
        return JSONResponse(
            {"code": error.code},
            status_code=422 if error.code in {"invalid_input", "no_speech"} else 409,
        )

    @app.get("/api/status")
    async def status():
        """Return readiness without automatically preparing a model group."""
        return controller.status()

    @app.post("/api/prepare")
    async def prepare(request: Request):
        """Admit one explicit empty-body preparation request and return immediately for status polling."""
        async for chunk in request.stream():
            if chunk:
                raise VoiceError("invalid_input")
        await controller.prepare()
        return JSONResponse(controller.status(), status_code=202)

    @app.post("/api/release")
    async def release(request: Request):
        """Explicitly unload only this optional research session and join pending preparation/cancellation."""
        async for chunk in request.stream():
            if chunk:
                raise VoiceError("invalid_input")
        await controller.release()
        return {"code": "released"}

    @app.post("/api/turn")
    async def turn(request: Request):
        """Accept only canonical bounded WAV for a unique explicitly submitted operation."""
        if request.headers.get("content-type") != "audio/wav":
            raise VoiceError("invalid_input")
        operation = identity(request.headers.get("x-voice-id"))
        try:
            return await controller.submit(request, operation)
        except asyncio.CancelledError:
            return JSONResponse({"code": "cancelled"}, status_code=409)

    @app.post("/api/cancel")
    async def cancel(request: Request):
        """Cancel a bounded matching operation even when a bodyless delayed submit has not arrived yet."""
        raw = bytearray()
        async for chunk in request.stream():
            raw.extend(chunk)
            if len(raw) > 128:
                raise VoiceError("invalid_input")
        try:
            value = json.loads(raw)
            if type(value) is not dict or set(value) != {"id"}:
                raise ValueError()
            operation = identity(value["id"])
        except (ValueError, TypeError, KeyError):
            raise VoiceError("invalid_input") from None
        await controller.cancel(operation)
        return {"code": "cancelled"}

    @app.get("/{asset:path}")
    async def static(asset: str):
        """Serve only packaged trial/original capture assets without filesystem traversal or dynamic media storage."""
        value = ASSETS.get("/" + asset)
        if value is None:
            return JSONResponse({"code": "not_found"}, status_code=404)
        LOGGER.info("trial_asset_served name=%s", value[0].name)
        return FileResponse(value[0], media_type=value[1])

    return app


app = create_app()
