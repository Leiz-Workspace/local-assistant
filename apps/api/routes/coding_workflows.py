"""Expose local owner-only finite coding proposals, separate approved edit/check actions and truthful private workflow history."""

import logging
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from starlette.responses import JSONResponse

from apps.api.routes.approvals import HEADERS
from apps.api.routes.checks import CheckRunInput, SelectedSourceInput
from apps.api.routes.conversations import require_local_client
from apps.api.routes.files import Principal
from apps.api.routes.workspaces import WorkspaceRoute
from src.application.services.approvals import ApprovalError
from src.application.services.workspace_policy import WorkspaceAccessError

logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/workspaces",
    route_class=WorkspaceRoute,
    tags=["Reviewed coding workflows"],
    dependencies=[Depends(require_local_client)],
)


class WorkflowProposalInput(BaseModel):
    """Select a bounded issue, fixed existing target/test hashes and finite profile without supplying commands or model routing."""

    model_config = ConfigDict(extra="forbid", strict=True)
    issue: str = Field(min_length=1, max_length=2048)
    target: SelectedSourceInput
    tests: list[SelectedSourceInput] = Field(min_length=1, max_length=3)
    profile: Literal["python_unittest", "ruff_check"]


class WorkflowStepInput(BaseModel):
    """Require an explicit empty capture action without accepting changed paths, code, budgets or approvals."""

    model_config = ConfigDict(extra="forbid", strict=True)


async def get_coding_workflow_service(request: Request):
    """Require separate enablement and map private domain errors before response transmission can lose acknowledgement."""
    service = getattr(request.app.state, "coding_workflow_service", None)
    if service is None or service.closing:
        raise HTTPException(503, detail=dict(code="workflow_unavailable"))
    try:
        yield service
    except (WorkspaceAccessError, ApprovalError) as error:
        raise HTTPException(error.status_code, detail=dict(code=error.code)) from None
    except (OSError, ValueError, TypeError, KeyError, RuntimeError):
        logger.warning("coding_workflow_request_failed_safely")
        raise HTTPException(503, detail=dict(code="workflow_unavailable")) from None


@router.post("/{workspace_id}/coding-workflows")
async def propose_workflow(
    workspace_id: UUID,
    body: WorkflowProposalInput,
    principal: Principal,
    service=Depends(get_coding_workflow_service, scope="function"),
):
    """Generate one source-selected untrusted full-file proposal and pending checkpoint-backed review without applying or running it."""
    return JSONResponse(
        await service.propose(principal, workspace_id, **body.model_dump()),
        headers=HEADERS,
    )


@router.get("/{workspace_id}/coding-workflows")
async def list_workflows(
    workspace_id: UUID,
    principal: Principal,
    service=Depends(get_coding_workflow_service, scope="function"),
):
    """List bounded own workflow identities and states without exposing foreign source/model contents."""
    return JSONResponse(
        dict(workflows=await service.list(principal, workspace_id)), headers=HEADERS
    )


@router.get("/{workspace_id}/coding-workflows/{workflow_id}")
async def read_workflow(
    workspace_id: UUID,
    workflow_id: UUID,
    principal: Principal,
    service=Depends(get_coding_workflow_service, scope="function"),
):
    """Return private last-observed component/model receipts without recovering grants or asserting current workspace correctness."""
    return JSONResponse(
        await service.read(principal, workspace_id, workflow_id), headers=HEADERS
    )


@router.post("/{workspace_id}/coding-workflows/{workflow_id}/apply")
async def apply_workflow(
    workspace_id: UUID,
    workflow_id: UUID,
    body: CheckRunInput,
    principal: Principal,
    service=Depends(get_coding_workflow_service, scope="function"),
):
    """Explicitly attempt only the exact already-approved linked file edit once, retaining actual commit or uncertainty evidence."""
    return JSONResponse(
        await service.apply(
            principal, workspace_id, workflow_id, UUID(body.approval_id)
        ),
        headers=HEADERS,
    )


@router.post("/{workspace_id}/coding-workflows/{workflow_id}/checks")
async def propose_workflow_checks(
    workspace_id: UUID,
    workflow_id: UUID,
    body: WorkflowStepInput,
    principal: Principal,
    service=Depends(get_coding_workflow_service, scope="function"),
):
    """Capture a known applied target plus unchanged selected tests and publish a different pending check review without execution."""
    return JSONResponse(
        await service.propose_checks(principal, workspace_id, workflow_id),
        headers=HEADERS,
    )


@router.post("/{workspace_id}/coding-workflows/{workflow_id}/run-checks")
async def run_workflow_checks(
    workspace_id: UUID,
    workflow_id: UUID,
    body: CheckRunInput,
    principal: Principal,
    service=Depends(get_coding_workflow_service, scope="function"),
):
    """Explicitly run only the separately approved linked immutable snapshot and return observation-based non-quality summary."""
    return JSONResponse(
        await service.run_checks(
            principal, workspace_id, workflow_id, UUID(body.approval_id)
        ),
        headers=HEADERS,
    )
