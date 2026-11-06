"""Expose separately enabled local owner cancellation and one explicit immutable proposal retry without accepting action/model overrides."""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from starlette.responses import JSONResponse

from apps.api.routes.approvals import HEADERS
from apps.api.routes.coding_workflows import (
    WorkflowStepInput,
    get_coding_workflow_service,
)
from apps.api.routes.conversations import require_local_client
from apps.api.routes.files import Principal
from apps.api.routes.workspaces import WorkspaceRoute
from apps.api.services.controlled_coding_workflows import (
    ControlledCodingWorkflowService,
)

logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/workspaces",
    route_class=WorkspaceRoute,
    tags=["Workflow controls"],
    dependencies=[Depends(require_local_client)],
)


async def get_controlled_workflow_service(
    service=Depends(get_coding_workflow_service, scope="function"),
):
    """Require the explicitly selected controller and reuse private domain failure mapping before response transmission."""
    if not isinstance(service, ControlledCodingWorkflowService):
        raise HTTPException(503, detail=dict(code="workflow_controls_unavailable"))
    return service


@router.post("/{workspace_id}/coding-workflows/{workflow_id}/cancel")
async def cancel_workflow(
    workspace_id: UUID,
    workflow_id: UUID,
    body: WorkflowStepInput,
    principal: Principal,
    service=Depends(get_controlled_workflow_service, scope="function"),
):
    """Signal and join only the owned exact workflow and retain committed edit/check receipts with explicit cleanup status."""
    logger.info("workflow_cancel_requested workflow_id=%s", workflow_id)
    return JSONResponse(
        await service.cancel(principal, workspace_id, workflow_id), headers=HEADERS
    )


@router.post("/{workspace_id}/coding-workflows/{workflow_id}/retry-proposal")
async def retry_workflow_proposal(
    workspace_id: UUID,
    workflow_id: UUID,
    body: WorkflowStepInput,
    principal: Principal,
    service=Depends(get_controlled_workflow_service, scope="function"),
):
    """Create one distinct source-fenced proposal from unchanged original options only after a component-free failed attempt."""
    logger.info("workflow_proposal_retry_requested workflow_id=%s", workflow_id)
    return JSONResponse(
        await service.retry_proposal(principal, workspace_id, workflow_id),
        headers=HEADERS,
    )
