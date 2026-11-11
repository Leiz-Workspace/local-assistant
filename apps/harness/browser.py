"""Serve pinned upstream UI assets through a separate loopback session and finite streaming gateway."""

import asyncio
import base64
import hashlib
import json
import logging
import mimetypes
import os
import re
import secrets
import time
from pathlib import Path

from fastapi import HTTPException, Request, Response
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    StreamingResponse,
)

from apps.api.core.conversation_auth import authenticate_principal, load_principals
from apps.api.core.model_config import get_model_profile
from apps.api.routes.conversations import require_local_client
from apps.api.voice_routes import local_browser
from apps.harness.assets import ASSETS, PIN, VERSION
from apps.branding.identity import brand_index, resource

LOGGER = logging.getLogger(__name__)
STATIC = Path(__file__).with_name("static")
COOKIE = "assistant_harness_session"
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
        if row is None or len(self.sessions) >= 64:
            raise HTTPException(401, detail={"code": "pairing_required"})
        token = secrets.token_urlsafe(32)
        self.sessions[hashlib.sha256(token.encode()).hexdigest()] = (
            *row[:2],
            self.clock() + 1800,
        )
        LOGGER.info("harness_browser_session_created")
        return token

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
    async with asyncio.timeout(10):
        async for chunk in request.stream():
            data.extend(chunk)
            if len(data) > limit:
                raise HTTPException(413, detail={"code": "request_limit"})

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
        + "; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self' data:; connect-src 'self'; media-src 'self' blob:; worker-src 'none'; frame-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
    )


def register_browser(app, *, asset_root=ASSETS):
    """Register explicit browser endpoints and assets without proxying native tools or model administration."""
    sessions = BrowserSessions()
    app.state.browser_sessions = sessions

    @app.post("/api/v1/harness/ui-pairings")
    async def pairing(request: Request):
        """Allow only the unchanged direct-loopback bearer boundary to mint a pairing."""
        await require_local_client(request)
        owner = await authenticate_principal(request)
        digest = hashlib.sha256(
            request.headers["authorization"].partition(" ")[2].encode()
        ).hexdigest()
        return {"code": sessions.pairing(owner, digest), "expires_in_seconds": 60}

    @app.middleware("http")
    async def browser_boundary(request, call_next):
        """Keep browser policy separate from existing bearer routes and add restrictive response headers."""
        if request.url.path.startswith(("/api/", "/docs", "/openapi")):
            return await call_next(request)
        try:
            boundary_request = request
            if request.url.path == "/props" and request.url.query:
                if any(
                    key not in {"autoload", "model"} for key in request.query_params
                ):
                    raise HTTPException(403, detail={"code": "unsupported_query"})
                boundary_request = Request({**request.scope, "query_string": b""})
            local_browser(boundary_request)
            if request.method not in {"GET", "HEAD"}:
                if (
                    request.headers.get("origin") != str(request.base_url).rstrip("/")
                    or request.headers.get("x-harness-ui") != "1"
                ):
                    raise HTTPException(403, detail={"code": "ui_csrf_required"})
            public = {
                "/pair/",
                "/harness-pair.js",
                "/harness-bridge.js",
                "/ui/pairings",
            }
            if request.url.path not in public and not request.url.path.startswith(
                "/aevra/brand/"
            ):
                request.state.ui_owner = sessions.owner(request)
            response = await call_next(request)
        except HTTPException as error:
            response = JSONResponse(
                {"detail": error.detail}, status_code=error.status_code
            )
        response.headers.update(SECURITY)
        if "content-security-policy" not in response.headers:
            response.headers["Content-Security-Policy"] = content_policy()
        operation = {
            "/v1/chat/completions": "chat_stream",
            "/props": "properties",
            "/v1/models": "model_list",
            "/tools": "tool_list",
            "/ui/pairings": "pairing_exchange",
            "/ui/logout": "session_logout",
            "/v1/streams/lookup": "stream_lookup",
        }.get(request.url.path, "asset_or_denied")
        LOGGER.info(
            "harness_browser_request operation=%s status=%d principal_id=%s",
            operation,
            response.status_code,
            getattr(request.state, "ui_owner", None),
        )
        return response

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
        """Advertise Aevra's name and supplied icon without enabling service workers or claiming PWA installation."""
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
        sessions.sessions.pop(
            hashlib.sha256(request.cookies.get(COOKIE, "").encode()).hexdigest(), None
        )
        response = JSONResponse({"revoked": True})
        response.delete_cookie(COOKIE)
        return response

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
            ui_settings={"enableMcp": False},
        )

    @app.get("/tools")
    async def tools():
        """Report no browser-executable tools until a typed approval UI is implemented."""
        return []

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

    @app.post("/v1/chat/completions")
    async def chat(request: Request):
        """Translate bounded upstream UI text chat into the application-owned CORE streaming path."""
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

        async def events():
            """Stream real deltas under shared admission and turn failures into safe SSE errors."""
            service = request.app.state.product_harness
            try:
                async with asyncio.timeout(120):
                    async with service.admission:
                        async for chunk in service.inference.stream(
                            normalized, max_tokens=max_tokens
                        ):
                            yield chunk
            except asyncio.CancelledError:
                LOGGER.info("harness_ui_stream_cancelled")
                raise
            except Exception:
                LOGGER.warning("harness_ui_stream_failed")
                yield b'data: {"error":{"code":"inference_unavailable","message":"Local inference could not complete."}}\n\n'
                yield b"data: [DONE]\n\n"

        return StreamingResponse(
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
