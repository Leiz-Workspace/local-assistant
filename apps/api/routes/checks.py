"""Expose local owner-only finite snapshot proposals, fresh approved execution, cancellation and private historical observations."""

import logging
from typing import Literal
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
    tags=["Approved checks"],
    dependencies=[Depends(require_local_client)],
)


class SelectedSourceInput(BaseModel):
    """Accept only one explicit relative Python path and its expected complete raw source digest."""

    model_config = ConfigDict(extra="forbid", strict=True)
    path: str = Field(min_length=1, max_length=256)
    expected_sha256: str = Field(
        pattern=r"^[a-f0-9]{64}$", min_length=64, max_length=64
    )


class CheckProposalInput(BaseModel):
    """Select only a finite server-owned profile and bounded exact source files without command/resource/environment overrides."""

    model_config = ConfigDict(extra="forbid", strict=True)
    profile: Literal["python_unittest", "ruff_check"]
    files: list[SelectedSourceInput] = Field(min_length=1, max_length=16)


class CheckRunInput(BaseModel):
    """Bind only the linked fresh canonical approval UUID without changing reviewed files, runtime or policy."""

    model_config = ConfigDict(extra="forbid", strict=True)
    approval_id: str = Field(
        pattern=r"^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$",
        min_length=36,
        max_length=36,
    )


class CheckCancelInput(BaseModel):
    """Require an explicit empty cancellation action without accepting source, command or owner mutations."""

    model_config = ConfigDict(extra="forbid", strict=True)


async def get_check_service(request: Request):
    """Require separate enablement and expose stable private errors while ending dependency handling before response delivery."""
    service = getattr(request.app.state, "check_service", None)
    if service is None or service.closing:
        raise HTTPException(503, detail=dict(code="checks_unavailable"))
    try:
        yield service
    except (WorkspaceAccessError, ApprovalError) as error:
        raise HTTPException(error.status_code, detail=dict(code=error.code)) from None
    except (OSError, ValueError, TypeError, KeyError, RuntimeError):
        logger.warning("checks_request_failed_safely")
        raise HTTPException(503, detail=dict(code="checks_unavailable")) from None


@router.post("/{workspace_id}/checks")
async def propose_check(
    workspace_id: UUID,
    body: CheckProposalInput,
    principal: Principal,
    service=Depends(get_check_service, scope="function"),
):
    """Capture selected readonly inputs and a complete pending review without approving or launching any program."""
    return JSONResponse(
        await service.propose(principal, workspace_id, **body.model_dump()),
        headers=HEADERS,
    )


@router.get("/{workspace_id}/checks")
async def list_checks(
    workspace_id: UUID,
    principal: Principal,
    service=Depends(get_check_service, scope="function"),
):
    """List bounded own durable metadata without reconstructing historical execution permission."""
    return JSONResponse(
        dict(jobs=await service.list(principal, workspace_id)), headers=HEADERS
    )


@router.get("/{workspace_id}/checks/{job_id}")
async def read_check(
    workspace_id: UUID,
    job_id: UUID,
    principal: Principal,
    service=Depends(get_check_service, scope="function"),
):
    """Return owner-only actual observations and distinguish known memory receipts from verified persisted state."""
    return JSONResponse(
        await service.read(principal, workspace_id, job_id), headers=HEADERS
    )


@router.post("/{workspace_id}/checks/{job_id}/run")
async def run_check(
    workspace_id: UUID,
    job_id: UUID,
    body: CheckRunInput,
    principal: Principal,
    service=Depends(get_check_service, scope="function"),
):
    """Run exactly one already-approved unchanged finite snapshot and report observations without claiming functional quality."""
    return JSONResponse(
        await service.run(principal, workspace_id, job_id, UUID(body.approval_id)),
        headers=HEADERS,
    )


@router.post("/{workspace_id}/checks/{job_id}/cancel")
async def cancel_check(
    workspace_id: UUID,
    job_id: UUID,
    body: CheckCancelInput,
    principal: Principal,
    service=Depends(get_check_service, scope="function"),
):
    """Cancel only this owner's pending/running job and join native work without deleting durable evidence or undoing a result."""
    return JSONResponse(
        await service.cancel(principal, workspace_id, job_id), headers=HEADERS
    )
