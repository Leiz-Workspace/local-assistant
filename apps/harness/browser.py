"""Serve pinned upstream UI assets through a separate loopback session and finite streaming gateway."""

import asyncio
import base64
import contextlib
import hashlib
import json
import logging
import mimetypes
import os
import re
import secrets
import time
from pathlib import Path

import httpx

from fastapi import HTTPException, Request, Response
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
)

from apps.api.core.conversation_auth import load_principals
from apps.api.core.model_config import ModelConfigError, get_model_profile
from apps.api.voice_routes import local_browser
from apps.harness.assets import ASSETS, PIN, VERSION
from apps.harness.inference import IncompleteCompletion
from apps.harness.routes import ClosingStreamingResponse
from apps.branding.identity import brand_index, resource
from src.application.services.special_literals import (
    SpecialLiteralsStale,
    require_current_binding,
)

LOGGER = logging.getLogger(__name__)
STATIC = Path(__file__).with_name("static")
PRODUCT_TYPES = {".js": "text/javascript", ".css": "text/css"}


def product_assets(root=STATIC / "aevra"):
    """List the product shell's own modules once; nothing outside that folder is served."""
    return {
        "/aevra/" + path.relative_to(root).as_posix(): path
        for path in sorted(root.rglob("*"))
        if path.suffix in PRODUCT_TYPES and path.is_file() and not path.is_symlink()
    }


COOKIE = "assistant_harness_session"
BODY_SECONDS = 10
SECURITY = {
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "microphone=(), camera=(), geolocation=()",
}


class BrowserSessions:
    """Keep short-lived one-use pairings and revocable browser cookies in this process only."""

    def __init__(self, *, clock=time.monotonic):
        """Initialize empty bounded session stores without credentials or persistent grants."""
        self.clock, self.pairings, self.sessions = clock, {}, {}

    def prune(self):
        """Expire capabilities without extending their original lifetime on use."""
        now = self.clock()
        self.pairings = {
            key: value for key, value in self.pairings.items() if value[2] > now
        }
        self.sessions = {
            key: value for key, value in self.sessions.items() if value[2] > now
        }

    def pairing(self, owner, digest):
        """Mint a single 60-second bootstrap capability from an already-authenticated host call."""
        self.prune()
        if len(self.pairings) >= 32:
            raise HTTPException(429, detail={"code": "pairing_capacity"})
        code = secrets.token_urlsafe(32)
        self.pairings[hashlib.sha256(code.encode()).hexdigest()] = (
            owner,
            digest,
            self.clock() + 60,
        )
        LOGGER.info("harness_browser_pairing_created")
        return code

    def exchange(self, code):
        """Consume one exact bootstrap capability and issue a fresh half-hour cookie."""
        self.prune()
        if not isinstance(code, str) or len(code) > 128:
            raise HTTPException(401, detail={"code": "pairing_required"})
        row = self.pairings.pop(hashlib.sha256(code.encode()).hexdigest(), None)
        if row is None:
            raise HTTPException(401, detail={"code": "pairing_required"})
        return self.create_session(*row[:2])

    def create_session(self, owner, digest):
        """Issue a short-lived HttpOnly session for an already verified local principal binding."""
        self.prune()
        # Evict the session closest to expiry so repeated bootstraps cannot lock the owner out.
        while len(self.sessions) >= 64:
            del self.sessions[min(self.sessions, key=lambda key: self.sessions[key][2])]
        token = secrets.token_urlsafe(32)
        self.sessions[hashlib.sha256(token.encode()).hexdigest()] = (
            owner,
            digest,
            self.clock() + 1800,
        )
        LOGGER.info("harness_browser_session_created")
        return token

    def revoke(self, request):
        """Forget the session behind the presented cookie, if any."""
        self.sessions.pop(
            hashlib.sha256(request.cookies.get(COOKIE, "").encode()).hexdigest(), None
        )

    def owner(self, request):
        """Revalidate both cookie expiry and the original digest binding against current app authentication."""
        self.prune()
        value = request.cookies.get(COOKIE, "")
        row = self.sessions.get(hashlib.sha256(value.encode()).hexdigest())
        try:
            principals = load_principals(Path(os.environ["ASSISTANT_AUTH_FILE"]))
            valid = row is not None and principals.get(row[1]) == row[0]
        except (OSError, ValueError, KeyError, TypeError):
            valid = False
        if not valid or len(request.headers.getlist("cookie")) > 1:
            raise HTTPException(401, detail={"code": "ui_session_required"})
        return row[0]


async def bounded_json(request, limit=262144):
    """Read one finite JSON object with duplicate-key and timeout checks before model work."""
    if (
        request.headers.get("content-type", "").split(";", 1)[0] != "application/json"
        or request.headers.get("content-encoding", "identity") != "identity"
    ):
        raise HTTPException(415, detail={"code": "json_required"})
    data = bytearray()
    try:
        async with asyncio.timeout(BODY_SECONDS):
            async for chunk in request.stream():
                data.extend(chunk)
                if len(data) > limit:
                    raise HTTPException(413, detail={"code": "request_limit"})
    except TimeoutError:
        LOGGER.warning("harness_browser_body_timeout")
        raise HTTPException(408, detail={"code": "request_timeout"}) from None

    def unique(pairs):
        """Reject ambiguous duplicate fields instead of accepting hidden alternate controls."""
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError("duplicate_key")
            value[key] = item
        return value

    try:
        value = json.loads(data, object_pairs_hook=unique)
        if not isinstance(value, dict):
            raise ValueError()
        return value
    except (ValueError, UnicodeError, RecursionError):
        raise HTTPException(422, detail={"code": "invalid_json"}) from None


def content_policy(index=""):
    """Allow packaged inline scripts by hash while denying remote connections, workers and embedded frames."""
    hashes = [
        "'sha256-"
        + base64.b64encode(hashlib.sha256(source.encode()).digest()).decode()
        + "'"
        for source in re.findall(
            r"<script\b[^>]*>(.*?)</script>", index, flags=re.S | re.I
        )
        if source.strip()
    ]
    return (
        "default-src 'none'; script-src 'self' "
        + " ".join(hashes)
        + "; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self' data:; connect-src 'self'; manifest-src 'self'; media-src 'self' blob:; worker-src 'none'; frame-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
    )


FULL_CORE = os.environ.get("Aevra_WEB_FULL_CORE", "0") == "1"
CHAT_ROUTE = "/".join(("", "v1", "chat", "completions"))
UI_STREAM_SECONDS = 120
CORE_PROXY_PATHS = (
    "/health",
    "/props",
    "/slots",
    "/models",
    "/tools",
    "/token",
    "/v1/models",
    "/v1/stream",
    "/v1/catalog.json",
    "/v1/streams/lookup",
)


async def proxy_core(request, path):
    if not FULL_CORE or not any(
        path == item or path.startswith(item + "/") for item in CORE_PROXY_PATHS
    ):
        raise HTTPException(403, detail={"code": "unsupported_capability"})
    try:
        # Same loopback-validated CORE URL as product inference: one source of truth.
        core_base = get_model_profile("core")["base_url"]
    except ModelConfigError:
        raise HTTPException(503, detail={"code": "inference_unavailable"}) from None
    body = await request.body()
    headers = {
        key: value
        for key, value in request.headers.items()
        if key.lower() not in {"host", "cookie", "authorization", "content-length"}
    }
    async with httpx.AsyncClient(
        base_url=core_base, timeout=120, trust_env=False
    ) as client:
        response = await client.request(
            request.method,
            path,
            content=body,
            headers=headers,
            params=request.query_params,
        )
        content = await response.aread()
    response_headers = {
        key: value
        for key, value in response.headers.items()
        if key.lower() not in {"content-length", "transfer-encoding", "connection"}
    }
    return Response(
        content=content,
        status_code=response.status_code,
        headers=response_headers,
        media_type=response.headers.get("content-type"),
    )


def register_browser(app, *, asset_root=ASSETS):
    """Register explicit browser endpoints and assets without proxying native tools or model administration."""
    sessions = BrowserSessions()
    shell = product_assets()
    # The bearer-authenticated pairing route lives in the harness API router.
    app.state.browser_sessions = sessions

    @app.middleware("http")
    async def browser_boundary(request, call_next):
        """Keep browser policy separate from existing bearer routes and add restrictive response headers."""
        api_request = request.url.path.startswith("/api/v1/harness")
        if (
            request.url.path.startswith("/api/") and not api_request
        ) or request.url.path.startswith(("/docs", "/openapi")):
            return await call_next(request)
        try:
            if api_request:
                browser_call = (
                    request.headers.get("x-harness-ui") == "1"
                    and "authorization" not in request.headers
                )
                # Browser calls without a cookie get 401 so the UI can re-establish its session.
                if request.cookies.get(COOKIE) or browser_call:
                    local_browser(Request({**request.scope, "query_string": b""}))
                    if request.method not in {"GET", "HEAD"} and (
                        request.headers.get("origin")
                        != str(request.base_url).rstrip("/")
                        or request.headers.get("x-harness-ui") != "1"
                    ):
                        raise HTTPException(403, detail={"code": "ui_csrf_required"})
                    request.state.ui_owner = sessions.owner(request)
            else:
                boundary_request = request
                if request.url.query and request.url.path != "/props":
                    raise HTTPException(403, detail={"code": "unsupported_query"})
                if request.url.path == "/props" and request.url.query:
                    if any(
                        key not in {"autoload", "model"} for key in request.query_params
                    ):
                        raise HTTPException(403, detail={"code": "unsupported_query"})
                    boundary_request = Request({**request.scope, "query_string": b""})
                local_browser(boundary_request)
                if request.url.path == "/v1/chat/completions":
                    request.state.ui_chat = True
                if request.method not in {"GET", "HEAD"}:
                    if (
                        request.headers.get("origin")
                        != str(request.base_url).rstrip("/")
                        or request.headers.get("x-harness-ui") != "1"
                    ):
                        raise HTTPException(403, detail={"code": "ui_csrf_required"})
                public = {
                    "/",
                    "/pair/",
                    "/harness-pair.js",
                    "/aevra-app/",
                    "/harness-bridge.js",
                    "/ui/pairings",
                    "/ui/session/bootstrap",
                    "/healthz",
                    # Name and icon only; browsers fetch the manifest without cookies.
                    "/aevra/manifest.webmanifest",
                }
                if (
                    request.url.path not in public
                    and request.url.path not in shell
                    and not request.url.path.startswith("/aevra/brand/")
                ):
                    request.state.ui_owner = sessions.owner(request)
            response = await call_next(request)
        except HTTPException as error:
            response = JSONResponse(
                {"detail": error.detail}, status_code=error.status_code
            )
        if api_request:
            if (
                response.status_code >= 400
                and getattr(request.state, "ui_owner", None) is None
            ):
                LOGGER.warning(
                    "harness_browser_api_denied method=%s status=%d",
                    request.method,
                    response.status_code,
                )
            return response
        response.headers.update(SECURITY)
        if "content-security-policy" not in response.headers:
            response.headers["Content-Security-Policy"] = content_policy()
        operation = {
            CHAT_ROUTE: "chat_stream",
            "/props": "properties",
            "/v1/models": "model_list",
            "/tools": "tool_list",
            "/ui/pairings": "pairing_exchange",
            "/ui/logout": "session_logout",
            "/ui/session/bootstrap": "session_bootstrap",
            "/v1/streams/lookup": "stream_lookup",
        }.get(request.url.path, "asset_or_denied")
        LOGGER.info(
            "harness_browser_request operation=%s status=%d principal_id=%s",
            operation,
            response.status_code,
            getattr(request.state, "ui_owner", None),
        )
        return response

    @app.get("/healthz")
    async def web_health():
        """Report that the Aevra web process is ready without probing or restarting CORE."""
        return {"status": "ok", "service": "aevra-web"}

    @app.get("/")
    async def aevra_root():
        """Serve the owned Aevra product UI, independent of the pinned compatibility bundle."""
        return FileResponse(STATIC / "aevra/index.html", media_type="text/html")

    @app.get("/aevra-app/")
    async def aevra_app():
        """Serve the same static Aevra shell; every data request still needs a session."""
        return FileResponse(STATIC / "aevra/index.html", media_type="text/html")

    @app.get("/pair/")
    async def pair_page():
        """Serve a fixed bootstrap page with no credential or model content."""
        return FileResponse(STATIC / "pair.html", media_type="text/html")

    @app.get("/harness-pair.js")
    async def pairing_script():
        """Serve the owned one-use pairing script."""
        return FileResponse(STATIC / "pair.js", media_type="text/javascript")

    @app.get("/harness-bridge.js")
    async def bridge_script():
        """Serve the same-origin request adapter before upstream application code."""
        return FileResponse(STATIC / "bridge.js", media_type="text/javascript")

    @app.get("/aevra/brand/{name}")
    async def brand_resource(name: str):
        """Serve only verified fixed owner-supplied Aevra logo resources, including during pairing."""
        try:
            data = resource(name)
        except (ValueError, OSError, KeyError, TypeError):
            raise HTTPException(
                404, detail={"code": "brand_resource_unavailable"}
            ) from None
        return Response(
            data, media_type=mimetypes.guess_type(name)[0] or "application/octet-stream"
        )

    @app.get("/aevra/brand.js")
    async def brand_script():
        """Apply product chrome without editing upstream assets or user conversation content."""
        return FileResponse(STATIC / "brand.js", media_type="text/javascript")

    @app.get("/aevra/brand.css")
    async def brand_style():
        """Expose the small owned branding stylesheet independently of the pinned chat design."""
        return FileResponse(STATIC / "brand.css", media_type="text/css")

    @app.get("/aevra/manifest.webmanifest")
    async def app_manifest():
        """Publish Aevra's name and icon (no user data) so browsers can label and install the app; no service worker."""
        return Response(
            json.dumps(
                dict(
                    name="Aevra",
                    short_name="Aevra",
                    id="/",
                    start_url="/",
                    display="standalone",
                    background_color="#171923",
                    theme_color="#171923",
                    icons=[
                        dict(
                            src="/aevra/brand/icon.png",
                            sizes="512x512",
                            type="image/png",
                        )
                    ],
                )
            ),
            media_type="application/manifest+json",
        )

    @app.get("/aevra/{asset:path}")
    async def product_asset(asset: str):
        """Serve one listed product-shell module; registered after the fixed /aevra routes."""
        path = shell.get("/aevra/" + asset)
        if path is None:
            raise HTTPException(404, detail={"code": "not_found"})
        return FileResponse(path, media_type=PRODUCT_TYPES[path.suffix])

    @app.post("/ui/session/bootstrap")
    async def bootstrap_session(request: Request):
        """Create a browser session for the local web container without exposing a bearer token."""
        if os.environ.get("ASSISTANT_WEB_AUTO_SESSION") != "1":
            raise HTTPException(403, detail={"code": "auto_session_disabled"})
        local_browser(request)
        try:
            principals = load_principals(Path(os.environ["ASSISTANT_AUTH_FILE"]))
        except (OSError, ValueError, KeyError, TypeError):
            raise HTTPException(503, detail={"code": "auth_unavailable"}) from None
        if len(principals) != 1:
            raise HTTPException(403, detail={"code": "single_local_principal_required"})
        digest, owner = next(iter(principals.items()))
        sessions.revoke(request)
        token = sessions.create_session(owner, digest)
        response = JSONResponse({"authenticated": True})
        response.set_cookie(
            COOKIE, token, httponly=True, samesite="strict", max_age=1800, path="/"
        )
        return response

    @app.post("/ui/pairings")
    async def exchange_pairing(request: Request):
        """Exchange one bootstrap nonce for a non-script-readable session cookie."""
        body = await bounded_json(request, 1024)
        if set(body) != {"code"}:
            raise HTTPException(422, detail={"code": "invalid_pairing"})
        token = sessions.exchange(body["code"])
        response = JSONResponse({"paired": True})
        response.set_cookie(
            COOKIE, token, httponly=True, samesite="strict", max_age=1800, path="/"
        )
        return response

    @app.post("/ui/logout")
    async def logout(request: Request):
        """Revoke the current UI session without altering shared API credentials."""
        sessions.revoke(request)
        response = JSONResponse({"revoked": True})
        response.delete_cookie(COOKIE)
        return response

    @app.api_route(
        "/models/{path:path}", methods=["GET", "POST", "DELETE", "PUT", "PATCH"]
    )
    async def core_models(request: Request, path: str):
        return await proxy_core(request, "/models" + ("/" + path if path else ""))

    @app.api_route("/slots", methods=["GET"])
    async def core_slots(request: Request):
        return await proxy_core(request, "/slots")

    @app.api_route("/token", methods=["POST"])
    async def core_token(request: Request):
        return await proxy_core(request, "/token")

    @app.api_route("/health", methods=["GET"])
    async def core_health(request: Request):
        return await proxy_core(request, "/health")

    @app.api_route("/v1/catalog.json", methods=["GET"])
    async def core_catalog(request: Request):
        return await proxy_core(request, "/v1/catalog.json")

    @app.api_route("/v1/stream", methods=["GET", "POST"])
    async def core_stream(request: Request):
        return await proxy_core(request, "/v1/stream")

    @app.get("/v1/models")
    async def models():
        """Expose only the configured CORE model without triggering load or download."""
        return {
            "object": "list",
            "data": [
                {
                    "id": get_model_profile("core")["model_id"],
                    "object": "model",
                    "owned_by": "local",
                }
            ],
        }

    @app.get("/props")
    async def props():
        """Advertise the finite text-only surface rather than native router/tool capabilities."""
        return dict(
            default_generation_settings=dict(
                n_ctx=32768,
                params=dict(
                    n_predict=4096, max_tokens=4096, temperature=0.7, stream=True
                ),
            ),
            total_slots=1,
            model_path=get_model_profile("core")["model_id"],
            role="model",
            modalities=dict(vision=False, audio=False, video=False),
            chat_template="",
            bos_token="",
            eos_token="",
            build_info="Aevra pinned llama-ui gateway",
            cors_proxy_enabled=False,
            ui_settings={
                "enableMcp": False,
                "enableModelManagement": False,
                "enableSlotMetrics": True,
            },
            endpoint_models="/v1/models",
            endpoint_slots="/slots",
            endpoint_stream="/v1/stream",
            endpoint_stream_lookup="/v1/streams/lookup",
        )

    @app.get("/slots")
    async def slots():
        """Expose read-only slot state for the pinned UI without model administration."""
        return {
            "slots": [
                {"id": 0, "state": "idle", "prompt_tokens": 0, "tokens_predicted": 0}
            ]
        }

    @app.get("/v1/catalog.json")
    async def catalog():
        """Return a local-only catalog containing the configured model, never remote catalog data."""
        profile = get_model_profile("core")
        return {
            "models": [
                {
                    "id": profile["model_id"],
                    "name": profile["model_id"],
                    "source": "local",
                }
            ]
        }

    @app.get("/tools")
    async def tools(request: Request):
        """Expose CORE tools only in explicit full-core compatibility mode."""
        if FULL_CORE:
            return await proxy_core(request, "/tools")
        return []

    @app.get("/v1/stream")
    async def stream_metadata():
        """Report that resumable stream history is not enabled by this product gateway."""
        return {"enabled": False, "resumable": False}

    @app.post("/v1/streams/lookup")
    async def stream_lookup(request: Request):
        """Report no resumable sessions because this gateway cancels work on disconnect."""
        body = await bounded_json(request, 16384)
        identifiers = body.get("conversation_ids")
        if (
            set(body) != {"conversation_ids"}
            or not isinstance(identifiers, list)
            or len(identifiers) > 64
            or any(
                not isinstance(value, str) or len(value) > 256 for value in identifiers
            )
        ):
            raise HTTPException(422, detail={"code": "invalid_stream_lookup"})
        return []

    @app.post("/" + "v1/chat/completions")
    async def chat(request: Request):
        """Translate product chat, or proxy full llama UI chat when explicitly enabled."""
        if FULL_CORE:
            return await proxy_core(request, CHAT_ROUTE)
        body = await bounded_json(request)
        if body.get("model") not in (None, get_model_profile("core")["model_id"]):
            raise HTTPException(422, detail={"code": "unapproved_model"})
        if any(body.get(key) for key in ("tools", "functions", "function_call")):
            raise HTTPException(422, detail={"code": "browser_tools_not_supported"})
        if body.get("tool_choice", "none") not in ("auto", "none", None):
            raise HTTPException(422, detail={"code": "unsupported_tool_choice"})
        messages = body.get("messages")
        if not isinstance(messages, list) or not 1 <= len(messages) <= 256:
            raise HTTPException(422, detail={"code": "invalid_messages"})
        normalized = []
        for message in messages:
            if not isinstance(message, dict) or message.get("role") not in {
                "system",
                "user",
                "assistant",
            }:
                raise HTTPException(422, detail={"code": "text_only"})
            content = message.get("content")
            if isinstance(content, list) and all(
                isinstance(part, dict)
                and part.get("type") == "text"
                and isinstance(part.get("text"), str)
                for part in content
            ):
                content = "\n".join(part["text"] for part in content)
            if not isinstance(content, str) or not content.strip():
                raise HTTPException(422, detail={"code": "text_only"})
            normalized.append({"role": message["role"], "content": content})
        max_tokens = body.get("max_tokens", 4096)
        if max_tokens is None or max_tokens in (-1, 0):
            max_tokens = 4096
        if type(max_tokens) is not int or not 512 <= max_tokens <= 4096:
            raise HTTPException(422, detail={"code": "invalid_output_budget"})
        if body.get("stream") is not True:
            raise HTTPException(422, detail={"code": "stream_required"})
        try:
            require_current_binding()
        except SpecialLiteralsStale as error:
            raise HTTPException(503, detail={"code": error.code}) from None

        async def events():
            """Stream real deltas under shared admission and turn failures into safe SSE errors."""
            # The pinned UI ignores SSE error events and saves whatever it has as a
            # complete answer on [DONE]. A failed stream therefore ends right after
            # its error event: the UI then asks to resume, gets 403 and shows an error.
            service = request.app.state.product_harness
            # One 120 s deadline for admission, preparation and every upstream read; it
            # never spans a yield, so expiry always ends in an error frame.
            deadline = asyncio.get_running_loop().time() + UI_STREAM_SECONDS
            acquired = False
            try:
                async with asyncio.timeout_at(deadline):
                    await service.admission.acquire()
                acquired = True
                async with contextlib.aclosing(
                    service.inference.stream(
                        normalized, max_tokens=max_tokens, deadline=deadline
                    )
                ) as chunks:
                    async for chunk in chunks:
                        yield chunk
            except IncompleteCompletion:
                LOGGER.warning("harness_ui_stream_incomplete")
                yield b'data: {"error":{"code":"incomplete_completion","message":"The answer stopped before it was complete."}}\n\n'
            except (asyncio.CancelledError, GeneratorExit):
                LOGGER.info("harness_ui_stream_cancelled")
                raise
            except SpecialLiteralsStale as error:
                LOGGER.warning("harness_ui_stream_failed code=%s", error.code)
                yield (
                    b'data: {"error":{"code":"special_literals_stale",'
                    b'"message":"Local inference is refused for this model."}}\n\n'
                )
            except Exception:
                LOGGER.warning("harness_ui_stream_failed")
                yield b'data: {"error":{"code":"inference_unavailable","message":"Local inference could not complete."}}\n\n'
            finally:
                if acquired:
                    service.admission.release()

        return ClosingStreamingResponse(
            events(),
            media_type="text/event-stream",
            headers={"X-Accel-Buffering": "no", **SECURITY},
        )

    @app.api_route(
        "/{asset:path}", methods=["GET", "HEAD", "POST", "PUT", "DELETE", "PATCH"]
    )
    async def asset(asset: str, request: Request):
        """Serve only verified packaged assets and reject every non-allowlisted native API surface."""
        name = asset or "index.html"
        aliases = {
            "favicon.ico": "favicon.ico",
            "favicon-dark.ico": "favicon.ico",
            "favicon.svg": "icon.svg",
            "favicon-dark.svg": "icon.svg",
            "apple-touch-icon-180x180.png": "icon.png",
            "pwa-192x192.png": "icon.png",
            "pwa-512x512.png": "icon.png",
        }
        if request.method in {"GET", "HEAD"} and name in aliases:
            LOGGER.info("aevra_upstream_icon_replaced")
            return Response(
                resource(aliases[name]), media_type=mimetypes.guess_type(name)[0]
            )
        blocked = {"models", "slots", "tools", "cors-proxy", "v1", "ui", "api"}
        if (
            request.method not in {"GET", "HEAD"}
            or name.split("/")[0] in blocked
            or name in {"receipt.json", "sw.js", "service-worker.js"}
        ):
            raise HTTPException(403, detail={"code": "unsupported_capability"})
        root = Path(asset_root)
        try:
            receipt = json.loads((root / "receipt.json").read_text())
            if receipt.get("source_pin") != PIN or receipt.get("version") != VERSION:
                raise ValueError("ui_pin_mismatch")
            expected = receipt["files"].get(name)
            target = root / name
            data = (
                target.read_bytes()
                if expected is not None
                and target.resolve().is_relative_to(root.resolve())
                and not target.is_symlink()
                else None
            )
            if (
                expected is None
                or data is None
                or hashlib.sha256(data).hexdigest() != expected
            ):
                raise ValueError()
        except (OSError, ValueError, KeyError, TypeError):
            raise HTTPException(
                404 if root.exists() else 503,
                detail={"code": "verified_ui_assets_required"},
            ) from None
        LOGGER.info("harness_ui_asset_served")
        if name == "index.html":
            text = brand_index(data.decode())
            return HTMLResponse(
                text, headers={"Content-Security-Policy": content_policy(text)}
            )
        media_type = mimetypes.guess_type(name)[0] or "application/octet-stream"
        return Response(data, media_type=media_type)
