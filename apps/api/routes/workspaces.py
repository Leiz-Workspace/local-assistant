"""Expose strict authenticated local read-only workspace snapshots with final source fences and private responses."""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.routing import APIRoute
from starlette.responses import JSONResponse

from apps.api.routes.conversations import require_local_client
from apps.api.routes.files import Principal
from src.application.services.workspace_policy import WorkspaceAccessError
from src.application.services.workspace_requests import parse_workspace_json
from src.application.services.workspace_tool_contracts import (
    DirectoryInput,
    ReadInput,
    SearchInput,
)

logger = logging.getLogger(__name__)


class WorkspaceRoute(APIRoute):
    """Bound incoming workspace JSON bytes before parsing rather than trusting Content-Length or field limits."""

    def get_route_handler(self):
        """Wrap only this router's POST requests in a bounded stream replay for the existing FastAPI handler."""
        original = super().get_route_handler()

        async def bounded(request):
            """Collect at most16KiB of request data and reject oversized streams before opening workspace roots."""
            if request.method != "POST":
                return await original(request)
            chunks, length = [], 0
            async for chunk in request.stream():
                length += len(chunk)
                if length > 16384:
                    logger.warning("workspace_request_bytes_rejected")
                    raise HTTPException(
                        413, detail=dict(code="workspace_request_limit")
                    )
                chunks.append(chunk)
            raw = b"".join(chunks)
            try:
                parse_workspace_json(raw)
            except WorkspaceAccessError as error:
                raise HTTPException(
                    error.status_code, detail=dict(code=error.code)
                ) from None

            async def replay():
                """Replay the already bounded complete request body exactly once to the normal JSON parser."""
                return dict(type="http.request", body=raw, more_body=False)

            return await original(Request(request.scope, receive=replay))

        return bounded


router = APIRouter(
    prefix="/workspaces",
    route_class=WorkspaceRoute,
    tags=["Workspace reads"],
    dependencies=[Depends(require_local_client)],
)


async def get_workspace_service(request: Request):
    """Require explicit startup and normalize filesystem failures without exposing private native diagnostics."""
    service = getattr(request.app.state, "workspace_service", None)
    if service is None or service.closing:
        raise HTTPException(503, detail=dict(code="workspace_unavailable"))
    try:
        yield service
    except WorkspaceAccessError as error:
        raise HTTPException(error.status_code, detail=dict(code=error.code)) from None
    except (OSError, ValueError, TypeError, KeyError, RuntimeError):
        logger.warning("workspace_request_failed_safely")
        raise HTTPException(503, detail=dict(code="workspace_unavailable")) from None


class WorkspaceResponse(JSONResponse):
    """Own snapshot authorization through final pre-header byte checks and joined response completion."""

    def __init__(self, context, service, snapshot):
        """Serialize only bounded verified payload while retaining the source context for delivery."""
        self.context = context
        self.service = service
        self.snapshot = snapshot
        super().__init__(
            snapshot.payload,
            headers={
                "Cache-Control": "private, no-store",
                "X-Content-Type-Options": "nosniff",
            },
        )
        if len(self.body) > 512 * 1024:
            raise WorkspaceAccessError("workspace_response_limit", 413)

    async def __call__(self, scope, receive, send):
        """Authorize current bytes before headers and always join retained resources after delivery/error."""
        try:
            try:
                await self.service.validate(self.snapshot)
            except WorkspaceAccessError as error:
                logger.warning("workspace_delivery_fenced")
                response = JSONResponse(
                    dict(detail=dict(code=error.code)),
                    status_code=error.status_code,
                    headers={
                        "Cache-Control": "private, no-store",
                        "X-Content-Type-Options": "nosniff",
                    },
                )
                await response(scope, receive, send)
                return
            except (OSError, ValueError, TypeError, KeyError, RuntimeError):
                logger.warning("workspace_delivery_failed_safely")
                response = JSONResponse(
                    dict(detail=dict(code="workspace_unavailable")),
                    status_code=503,
                    headers={
                        "Cache-Control": "private, no-store",
                        "X-Content-Type-Options": "nosniff",
                    },
                )
                await response(scope, receive, send)
                return
            await super().__call__(scope, receive, send)
        finally:
            await self.context.__aexit__(None, None, None)


async def respond(service, principal, identifier, operation, parameters):
    """Transfer one entered service context to its response or close it if serialization fails."""
    context = service.operation(principal, identifier, operation, parameters)
    snapshot = await context.__aenter__()
    try:
        return WorkspaceResponse(context, service, snapshot)
    except BaseException:
        await context.__aexit__(None, None, None)
        raise


@router.get("/{workspace_id}")
async def discover_workspace(
    workspace_id: UUID, principal: Principal, service=Depends(get_workspace_service)
):
    """Discover only an explicitly owned configured root without inspecting repository instructions."""
    return await respond(service, principal, workspace_id, "discover", {})


@router.post("/{workspace_id}/inventory")
async def inventory_workspace(
    workspace_id: UUID,
    body: DirectoryInput,
    principal: Principal,
    service=Depends(get_workspace_service),
):
    """Return bounded admitted regular-file metadata under an optional relative directory."""
    return await respond(
        service, principal, workspace_id, "inventory", body.model_dump()
    )


@router.post("/{workspace_id}/read")
async def read_workspace(
    workspace_id: UUID,
    body: ReadInput,
    principal: Principal,
    service=Depends(get_workspace_service),
):
    """Return exact source-line text and raw-file hashes for an owned bounded relative file."""
    return await respond(service, principal, workspace_id, "read", body.model_dump())


@router.post("/{workspace_id}/search")
async def search_workspace(
    workspace_id: UUID,
    body: SearchInput,
    principal: Principal,
    service=Depends(get_workspace_service),
):
    """Return literal source matches with hash-bound native line/Unicode column provenance."""
    return await respond(service, principal, workspace_id, "search", body.model_dump())


@router.post("/{workspace_id}/symbols")
async def workspace_symbols(
    workspace_id: UUID,
    body: DirectoryInput,
    principal: Principal,
    service=Depends(get_workspace_service),
):
    """Return bounded lexical Python def/class hints without executing or importing untrusted code."""
    return await respond(service, principal, workspace_id, "symbols", body.model_dump())
