"""Expose strict authenticated local search with bounded input/output, finite errors and response-owned admission."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from pydantic import BaseModel, ConfigDict, Field
from starlette.responses import JSONResponse

from apps.api.core.conversation_auth import authenticate_principal
from apps.api.routes.conversations import require_local_client
from src.application.services.web_search_policy import ERROR_STATUS, WebSearchError
from src.application.services.workspace_policy import WorkspaceAccessError
from src.application.services.workspace_requests import parse_workspace_json

logger = logging.getLogger(__name__)
PRIVATE_HEADERS = {
    "Cache-Control": "private, no-store",
    "X-Content-Type-Options": "nosniff",
}


def private_error(status, code, headers=None):
    """Return only known error identifiers with private headers and no raw inputs or diagnostics."""
    known = set(ERROR_STATUS) | {
        "local_access_required",
        "auth_unavailable",
        "authentication_required",
    }
    if type(code) is not str or code not in known:
        code = "web_search_unavailable"
    logger.info("web_search_http_rejected code=%s", code)
    return JSONResponse(
        dict(detail=dict(code=code)),
        status_code=status,
        headers={**(headers or {}), **PRIVATE_HEADERS},
    )


class WebSearchRoute(APIRoute):
    """Authenticate before collecting at most2048bytes and replay only strict unambiguous JSON."""

    def get_route_handler(self):
        """Wrap this router's handler without changing the accepted authentication or shared routers."""
        original = super().get_route_handler()

        async def bounded(request):
            """Enforce origin/identity/media/stream limits before the normal framework validation and service call."""
            try:
                await require_local_client(request)
                request.state.web_search_principal = await authenticate_principal(
                    request
                )
                if (
                    request.headers.get("content-type", "")
                    .split(";", 1)[0]
                    .lower()
                    .strip()
                    != "application/json"
                    or request.headers.get("content-encoding", "identity").lower()
                    != "identity"
                ):
                    raise WebSearchError("web_search_media_type")
                chunks, length = [], 0
                async for chunk in request.stream():
                    length += len(chunk)
                    if length > 2048:
                        raise WebSearchError("web_search_request_limit")
                    chunks.append(chunk)
                raw = b"".join(chunks)
                try:
                    parse_workspace_json(raw)
                except WorkspaceAccessError:
                    raise WebSearchError("web_search_json_invalid") from None

                async def replay():
                    """Replay exactly the bounded body without retaining an unread client stream."""
                    return dict(type="http.request", body=raw, more_body=False)

                return await original(Request(request.scope, receive=replay))
            except HTTPException as error:
                code = (
                    error.detail.get("code", "web_search_unavailable")
                    if isinstance(error.detail, dict)
                    else "web_search_unavailable"
                )
                return private_error(error.status_code, code, error.headers)
            except RequestValidationError:
                return private_error(422, "web_search_request_invalid")
            except WebSearchError as error:
                headers = (
                    {"Retry-After": str(error.retry_after)}
                    if error.retry_after is not None
                    else None
                )
                return private_error(error.status_code, error.code, headers)
            except Exception:
                return private_error(503, "web_search_unavailable")

        return bounded


router = APIRouter(prefix="/web", route_class=WebSearchRoute, tags=["Web search"])


class WebSearchInput(BaseModel):
    """Accept only an explicit string query without identity, provider, source or model authority."""

    model_config = ConfigDict(extra="forbid", strict=True)
    query: str = Field(min_length=1, max_length=512)


async def get_web_search_service(request: Request):
    """Require the explicitly initialized live optional service without triggering startup or provider fallback."""
    service = getattr(request.app.state, "web_search_service", None)
    if service is None or service.closing:
        raise WebSearchError("web_search_unavailable")
    return service


class WebSearchResponse(JSONResponse):
    """Own one entered search context through bounded private response completion or send failure."""

    def __init__(self, context, payload):
        """Serialize at most64KiB while leaving context closure to response delivery or constructor failure handling."""
        self.context = context
        super().__init__(payload, headers=PRIVATE_HEADERS)
        if len(self.body) > 65536:
            raise WebSearchError("web_search_response_limit")

    async def __call__(self, scope, receive, send):
        """Close the joined operation in finally after header/body completion, cancellation or send error."""
        try:
            await super().__call__(scope, receive, send)
        finally:
            await self.context.__aexit__(None, None, None)


@router.post("/search")
async def search_web(
    request: Request, body: WebSearchInput, service=Depends(get_web_search_service)
):
    """Enter one authenticated explicit-query operation and transfer its admission lease to the private response."""
    context = service.operation(request.state.web_search_principal, body.query)
    payload = await context.__aenter__()
    try:
        return WebSearchResponse(context, payload)
    except BaseException:
        await context.__aexit__(None, None, None)
        raise
