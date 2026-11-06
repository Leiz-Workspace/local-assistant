"""Expose owner-authenticated optional voice APIs and a distinct same-origin browser boundary."""

import asyncio
import hashlib
import ipaddress
import json
import logging
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse

from apps.api.core.conversation_auth import authenticate_principal
from apps.api.routes.conversations import require_local_client
from apps.api.voice_identity import Actor, IdentityDenied
from src.application.services.voice_pipeline import VoiceError
from src.infrastructure.voice.audio import decode_wave

LOGGER = logging.getLogger(__name__)
COOKIE = "assistant_voice_session"
STATIC = Path(__file__).parent.parent / "web/voice"
HEADERS = {
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
    "Permissions-Policy": "microphone=(self), camera=(), geolocation=()",
    "Content-Security-Policy": "default-src 'none'; script-src 'self'; worker-src 'self'; connect-src 'self'; media-src blob:; style-src 'unsafe-inline'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'",
}


def strict_object(raw):
    """Reject duplicate JSON keys before interpreting pairing or cancellation capabilities."""

    def pairs(items):
        """Require every object field to have exactly one unambiguous value."""
        value = {}
        for key, item in items:
            if key in value:
                raise ValueError("duplicate_key")
            value[key] = item
        return value

    return json.loads(raw, object_pairs_hook=pairs)


def local_browser(request, *, mutation=False):
    """Enforce direct loopback Host/peer and same-origin CSRF checks without weakening old APIs."""
    try:
        value = urlsplit("http://" + request.headers.get("host", ""))
        local = (
            value.hostname == "localhost"
            or ipaddress.ip_address(value.hostname).is_loopback
        )
        valid = (
            request.client
            and ipaddress.ip_address(request.client.host).is_loopback
            and local
            and value.port == request.url.port
            and value.username is None
            and value.password is None
            and not value.path
            and not value.query
            and not value.fragment
            and len(request.headers.getlist("host")) == 1
            and len(request.headers.getlist("origin")) <= 1
            and not request.url.query
            and not {
                "forwarded",
                "x-forwarded-for",
                "x-forwarded-host",
                "x-real-ip",
            }.intersection(request.headers)
        )
        origin = request.headers.get("origin")
        if origin is not None and origin != str(request.base_url).rstrip("/"):
            valid = False
        site = request.headers.get("sec-fetch-site", "none")
        navigation = (
            request.method == "GET"
            and request.url.path == "/voice"
            and request.headers.get("sec-fetch-mode") == "navigate"
        )
        if site not in {"none", "same-origin"} and not navigation:
            valid = False
        if mutation and (
            origin != str(request.base_url).rstrip("/")
            or request.headers.get("x-voice-submit") != "1"
        ):
            valid = False
    except (ValueError, TypeError):
        valid = False
    if not valid:
        LOGGER.warning("voice_browser_boundary_denied")
        raise HTTPException(403, detail={"code": "local_session_required"})


async def bounded_body(request, limit):
    """Read at most the declared body bytes and reject ambiguous length/encoding before native work."""
    lengths = request.headers.getlist("content-length")
    if (
        len(lengths) > 1
        or len(request.headers.getlist("content-type")) > 1
        or request.headers.get("content-encoding", "identity") != "identity"
    ):
        raise VoiceError("invalid_input")
    if lengths and (
        len(lengths[0]) > 10
        or not lengths[0].isascii()
        or not lengths[0].isdigit()
        or int(lengths[0]) > limit
    ):
        raise VoiceError("invalid_input")
    data = bytearray()
    try:
        async with asyncio.timeout(10):
            async for chunk in request.stream():
                if len(data) + len(chunk) > limit:
                    raise VoiceError("invalid_input")
                data.extend(chunk)
    except TimeoutError:
        raise VoiceError("timeout") from None
    if lengths and int(lengths[0]) != len(data):
        raise VoiceError("invalid_input")
    return bytes(data)


def operation_id(value):
    """Accept only canonical random operation identifiers without path or authority semantics."""
    try:
        if type(value) is not str or len(value) != 36 or str(UUID(value)) != value:
            raise ValueError()
    except (ValueError, AttributeError, TypeError):
        raise VoiceError("invalid_input") from None
    return value


def routes(service, identities):
    """Build additive machine/BFF routes sharing the same authenticated application service."""
    router = APIRouter()

    async def actor_for(request):
        """Resolve browser sessions or existing bearer credentials before receiving request bodies."""
        if request.url.path.startswith("/ui/voice/"):
            local_browser(request, mutation=request.method != "GET")
            if request.headers.getlist("authorization"):
                raise IdentityDenied("authentication_required")
            actor = identities.resolve(request.cookies.get(COOKIE))
        else:
            await require_local_client(request)
            local_browser(request)
            principal = await authenticate_principal(request)
            token = request.headers["authorization"].partition(" ")[2]
            actor = Actor(principal, hashlib.sha256(token.encode()).hexdigest())
            if not identities.valid(actor):
                raise IdentityDenied("authentication_required")
        return actor

    @router.post("/api/v1/voice/pairing")
    async def pairing(request: Request):
        """Issue an expiring single-use UI grant only to a valid local bearer operator."""
        actor = await actor_for(request)
        if await bounded_body(request, 0):
            raise VoiceError("invalid_input")
        return JSONResponse(
            {"code": identities.issue(actor), "expires_seconds": 120}, headers=HEADERS
        )

    @router.post("/ui/voice/pair")
    async def pair(request: Request):
        """Redeem an explicit temporary code without placing permanent bearer credentials in the browser."""
        local_browser(request, mutation=True)
        if request.headers.get(
            "content-type"
        ) != "application/json" or request.headers.getlist("authorization"):
            raise VoiceError("invalid_input")
        try:
            value = strict_object(await bounded_body(request, 256))
            if type(value) is not dict or set(value) != {"code"}:
                raise ValueError()
        except (ValueError, RecursionError):
            raise VoiceError("invalid_input") from None
        cookie = identities.redeem(value["code"])
        response = JSONResponse({"code": "paired"}, headers=HEADERS)
        response.set_cookie(
            COOKIE,
            cookie,
            httponly=True,
            samesite="strict",
            max_age=900,
            path="/ui/voice",
        )
        return response

    @router.get("/api/v1/voice/status")
    @router.get("/ui/voice/status", include_in_schema=False)
    async def status(request: Request):
        """Return only owner-visible readiness and remaining finite budgets without loading models."""
        return JSONResponse(service.status(await actor_for(request)), headers=HEADERS)

    @router.post("/api/v1/voice/prepare")
    @router.post("/ui/voice/prepare", include_in_schema=False)
    async def prepare(request: Request):
        """Prepare only after authentication and an explicit empty-body operator action."""
        actor = await actor_for(request)
        service.authorize(actor)
        await bounded_body(request, 0)
        await service.prepare(actor)
        return JSONResponse(service.status(actor), status_code=202, headers=HEADERS)

    @router.post("/api/v1/voice/release")
    @router.post("/ui/voice/release", include_in_schema=False)
    async def release(request: Request):
        """Close only the authenticated owner's native session and promptly release joined GPU residency."""
        actor = await actor_for(request)
        service.authorize(actor)
        await bounded_body(request, 0)
        await service.release(actor)
        return JSONResponse({"code": "released"}, headers=HEADERS)

    @router.post("/api/v1/voice/turn")
    @router.post("/ui/voice/turn", include_in_schema=False)
    async def turn(request: Request):
        """Admit a bounded canonical WAV only after stable identity, readiness and quota checks."""
        actor = await actor_for(request)
        if (
            request.headers.get("content-type") != "audio/wav"
            or len(request.headers.getlist("x-voice-id")) != 1
        ):
            raise VoiceError("invalid_input")
        operation = operation_id(request.headers.get("x-voice-id"))

        async def read_body():
            """Bind body admission to the already reserved owner operation."""
            raw = await bounded_body(request, 640044)
            decode_wave(raw)
            return raw

        try:
            value = await service.submit(
                actor, operation, read_body, request.is_disconnected
            )
            return JSONResponse(value, headers=HEADERS)
        except asyncio.CancelledError:
            return JSONResponse({"code": "cancelled"}, status_code=409, headers=HEADERS)

    @router.post("/api/v1/voice/cancel")
    @router.post("/ui/voice/cancel", include_in_schema=False)
    async def cancel(request: Request):
        """Remember early cancellation and join matching work only for the authenticated owner."""
        actor = await actor_for(request)
        service.authorize(actor)
        if request.headers.get("content-type") != "application/json":
            raise VoiceError("invalid_input")
        try:
            value = strict_object(await bounded_body(request, 128))
            if type(value) is not dict or set(value) != {"id"}:
                raise ValueError()
            operation = operation_id(value["id"])
        except (ValueError, RecursionError):
            raise VoiceError("invalid_input") from None
        await service.cancel(actor, operation)
        return JSONResponse({"code": "cancelled"}, headers=HEADERS)

    @router.get("/voice", include_in_schema=False)
    async def page(request: Request):
        """Serve a passive main-app voice page that requires pairing before preparation or capture."""
        local_browser(request)
        LOGGER.info("voice_page_served")
        return FileResponse(
            STATIC / "index.html", headers=HEADERS, media_type="text/html"
        )

    @router.get("/voice/assets/{asset}", include_in_schema=False)
    async def asset(request: Request, asset: str):
        """Serve only packaged static dependencies with no filesystem traversal or persistent user media."""
        local_browser(request)
        paths = {
            "page.mjs": STATIC / "page.mjs",
            "session.mjs": STATIC / "session.mjs",
            "recorder.mjs": STATIC / "recorder.mjs",
            "capture-worklet.js": STATIC / "capture-worklet.js",
        }
        if asset not in paths:
            raise HTTPException(404)
        LOGGER.info("voice_asset_served name=%s", asset)
        return FileResponse(paths[asset], headers=HEADERS, media_type="text/javascript")

    return router
