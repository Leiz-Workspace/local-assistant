"""Serve fixed local recording assets with no upload, model execution or server-side audio storage."""

import ipaddress
import logging
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse

logger = logging.getLogger(__name__)
ROOT = Path(__file__).with_name("static")
ASSETS = {
    "/": ("index.html", "text/html"),
    "/recorder.mjs": ("recorder.mjs", "text/javascript"),
    "/page.mjs": ("page.mjs", "text/javascript"),
    "/capture-worklet.js": ("capture-worklet.js", "text/javascript"),
}
app = FastAPI(openapi_url=None, docs_url=None, redoc_url=None)


@app.middleware("http")
async def local_surface(request: Request, call_next):
    """Reject remote/proxied/cross-origin access and constrain the optional UI to fixed same-origin assets."""
    try:
        host = urlsplit("http://" + request.headers.get("host", ""))
        hostname = host.hostname
        local_host = (
            hostname == "localhost" or ipaddress.ip_address(hostname).is_loopback
        )
        allowed = (
            request.client is not None
            and ipaddress.ip_address(request.client.host).is_loopback
            and local_host
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
            and request.headers.get("sec-fetch-site", "none") in {"none", "same-origin"}
            and (
                "origin" not in request.headers
                or request.headers["origin"] == str(request.base_url).rstrip("/")
            )
        )
    except (TypeError, ValueError):
        allowed = False
    if not allowed:
        logger.warning("recording_surface_denied")
        response = JSONResponse({"code": "local_access_required"}, status_code=403)
    else:
        response = await call_next(request)
    response.headers.update(
        {
            "Content-Security-Policy": "default-src 'none'; script-src 'self'; worker-src 'self'; media-src blob:; connect-src 'self'; style-src 'unsafe-inline'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'",
            "Permissions-Policy": "microphone=(self), camera=(), geolocation=()",
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "Referrer-Policy": "no-referrer",
        }
    )
    return response


@app.get("/{asset:path}")
async def static_asset(asset: str):
    """Serve only packaged recorder resources, never arbitrary user paths or captured media."""
    value = ASSETS.get("/" + asset)
    if value is None:
        logger.warning("recording_asset_missing")
        return JSONResponse({"code": "not_found"}, status_code=404)
    logger.info("recording_asset_served asset=%s", value[0])
    return FileResponse(ROOT / value[0], media_type=value[1])
