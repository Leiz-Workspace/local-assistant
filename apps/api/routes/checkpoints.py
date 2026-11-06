"""Expose owner-only private checkpoint history/recovery observations and fresh approval-required byte rollback proposals."""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from starlette.responses import JSONResponse

from apps.api.routes.approvals import HEADERS
from apps.api.routes.conversations import require_local_client
from apps.api.routes.files import Principal
from apps.api.routes.patches import get_patch_service
from apps.api.routes.workspaces import WorkspaceRoute
from apps.api.services.checkpoint_patches import CheckpointPatchService

logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/workspaces",
    route_class=WorkspaceRoute,
    tags=["Private source checkpoints"],
    dependencies=[Depends(require_local_client)],
)


class RollbackInput(BaseModel):
    """Require the current source digest only; historical path/restoration bytes remain server-verified checkpoint data."""

    model_config = ConfigDict(extra="forbid", strict=True)
    expected_sha256: str = Field(
        pattern=r"^[a-f0-9]{64}$", min_length=64, max_length=64
    )


async def get_checkpoint_service(service=Depends(get_patch_service, scope="function")):
    """Require explicit durable composition without creating a private root or enabling checkpoints on ephemeral D40 services."""
    if (
        not isinstance(service, CheckpointPatchService)
        or service.checkpoint_store.storage.closing
    ):
        raise HTTPException(503, detail=dict(code="checkpoint_unavailable"))
    return service


@router.get("/{workspace_id}/checkpoints")
async def list_checkpoints(
    workspace_id: UUID, principal: Principal, service=Depends(get_checkpoint_service)
):
    """List only own bounded durable snapshot metadata without exposing foreign source or recovered grants."""
    return JSONResponse(
        dict(
            checkpoints=await service.checkpoints(principal, workspace_id),
            recovered_approvals=False,
        ),
        headers=HEADERS,
    )


@router.get("/{workspace_id}/checkpoints/{checkpoint_id}")
async def read_checkpoint(
    workspace_id: UUID,
    checkpoint_id: UUID,
    principal: Principal,
    service=Depends(get_checkpoint_service),
):
    """Return verified historical bytes and journal evidence without claiming current source observation."""
    return JSONResponse(
        await service.checkpoint(principal, workspace_id, checkpoint_id),
        headers=HEADERS,
    )


@router.get("/{workspace_id}/checkpoints/{checkpoint_id}/recovery")
async def inspect_checkpoint(
    workspace_id: UUID,
    checkpoint_id: UUID,
    principal: Principal,
    service=Depends(get_checkpoint_service),
):
    """Observe current scoped byte hashes only; restart inspection never edits or recovers an approval grant."""
    return JSONResponse(
        await service.inspect_recovery(principal, workspace_id, checkpoint_id),
        headers=HEADERS,
    )


@router.post("/{workspace_id}/checkpoints/{checkpoint_id}/rollback")
async def propose_rollback(
    workspace_id: UUID,
    checkpoint_id: UUID,
    body: RollbackInput,
    principal: Principal,
    service=Depends(get_checkpoint_service),
):
    """Prepare full byte-restoration diff and a new pending approval without automatically changing source or permissions."""
    logger.info(
        "checkpoint_rollback_proposal_requested checkpoint_id=%s", checkpoint_id
    )
    return JSONResponse(
        await service.rollback(
            principal, workspace_id, checkpoint_id, body.expected_sha256
        ),
        headers=HEADERS,
    )
