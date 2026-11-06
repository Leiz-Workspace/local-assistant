"""Expose bounded local owner-only concrete proposals/status and separately approved single-file application."""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from starlette.responses import JSONResponse

from apps.api.routes.approvals import HEADERS
from apps.api.routes.conversations import require_local_client
from apps.api.routes.files import Principal
from apps.api.routes.workspaces import WorkspaceRoute
from src.application.services.approvals import ApprovalError
from src.application.services.workspace_policy import WorkspaceAccessError

logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/workspaces",
    route_class=WorkspaceRoute,
    tags=["Approved patches"],
    dependencies=[Depends(require_local_client)],
)


class ProposalInput(BaseModel):
    """Accept only scoped path, exact original digest and complete replacement without client authority overrides."""

    model_config = ConfigDict(extra="forbid", strict=True)
    path: str = Field(min_length=1, max_length=1024)
    expected_sha256: str = Field(
        pattern=r"^[a-f0-9]{64}$", min_length=64, max_length=64
    )
    replacement: str = Field(max_length=8192)


class ApplyInput(BaseModel):
    """Bind only the linked existing approval UUID without permitting changes to reviewed text, path or scope."""

    model_config = ConfigDict(extra="forbid", strict=True)
    approval_id: str = Field(
        pattern=r"^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$",
        min_length=36,
        max_length=36,
    )


async def get_patch_service(request: Request):
    """Require explicit enablement and return stable private error codes instead of native path/source diagnostics."""
    service = getattr(request.app.state, "patch_service", None)
    if service is None or service.closing:
        raise HTTPException(503, detail=dict(code="patch_unavailable"))
    try:
        yield service
    except (WorkspaceAccessError, ApprovalError) as error:
        raise HTTPException(error.status_code, detail=dict(code=error.code)) from None
    except (OSError, ValueError, TypeError, KeyError, RuntimeError):
        logger.warning("patch_request_failed_safely")
        raise HTTPException(503, detail=dict(code="patch_unavailable")) from None


@router.post("/{workspace_id}/patches")
async def propose_patch(
    workspace_id: UUID,
    body: ProposalInput,
    principal: Principal,
    service=Depends(get_patch_service, scope="function"),
):
    """Prepare a full diff and pending review using reads only; this endpoint never applies an edit."""
    return JSONResponse(
        await service.propose(principal, workspace_id, **body.model_dump()),
        headers=HEADERS,
    )


@router.get("/{workspace_id}/patches/{proposal_id}")
async def review_patch(
    workspace_id: UUID,
    proposal_id: UUID,
    principal: Principal,
    service=Depends(get_patch_service, scope="function"),
):
    """Return owner-only historical proposal/receipt without claiming that current source still matches it."""
    return JSONResponse(
        await service.review(principal, workspace_id, proposal_id), headers=HEADERS
    )


@router.post("/{workspace_id}/patches/{proposal_id}/apply")
async def apply_patch(
    workspace_id: UUID,
    proposal_id: UUID,
    body: ApplyInput,
    principal: Principal,
    service=Depends(get_patch_service, scope="function"),
):
    """Apply exactly one already-approved unchanged native proposal and return its recorded commit outcome."""
    return JSONResponse(
        await service.apply(
            principal, workspace_id, proposal_id, UUID(body.approval_id)
        ),
        headers=HEADERS,
    )
