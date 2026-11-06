"""Expose owner-only local approval review/explicit decision without public request creation, consumption or action execution."""

import logging
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from starlette.responses import JSONResponse

from apps.api.routes.conversations import require_local_client
from apps.api.routes.files import Principal
from apps.api.routes.workspaces import WorkspaceRoute
from src.application.services.approvals import ApprovalError

logger = logging.getLogger(__name__)
HEADERS = {"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"}
router = APIRouter(
    prefix="/approvals",
    route_class=WorkspaceRoute,
    tags=["Explicit approval review"],
    dependencies=[Depends(require_local_client)],
)


class DecisionInput(BaseModel):
    """Accept exactly one explicit human decision and the previously displayed scope/nonce without scope or artifact overrides."""

    model_config = ConfigDict(extra="forbid", strict=True)
    decision: Literal["approve", "reject"]
    scope_digest: str = Field(pattern=r"^[a-f0-9]{64}$", min_length=64, max_length=64)
    review_nonce: str = Field(
        pattern=r"^[A-Za-z0-9_-]{43}$", min_length=43, max_length=43
    )


async def get_approval_store(request: Request):
    """Require explicitly enabled live state and sanitize every approval/native error without sensitive diagnostics."""
    store = getattr(request.app.state, "approval_store", None)
    if store is None or store.closing:
        raise HTTPException(503, detail=dict(code="approval_unavailable"))
    try:
        yield store
    except ApprovalError as error:
        raise HTTPException(error.status_code, detail=dict(code=error.code)) from None
    except (OSError, ValueError, TypeError, KeyError, RuntimeError):
        logger.warning("approval_request_failed_safely")
        raise HTTPException(503, detail=dict(code="approval_unavailable")) from None


@router.get("/{request_id}")
async def review_approval(
    request_id: UUID, principal: Principal, store=Depends(get_approval_store)
):
    """Return a complete private owner-only concrete artifact and server-bound review scope."""
    return JSONResponse(store.review(principal, request_id), headers=HEADERS)


@router.post("/{request_id}/decision")
async def decide_approval(
    request_id: UUID,
    body: DecisionInput,
    principal: Principal,
    store=Depends(get_approval_store),
):
    """Record the explicit decision only; approval itself never executes a command or modifies source."""
    event = store.decide(
        principal, request_id, body.decision, body.scope_digest, body.review_nonce
    )
    return JSONResponse(event, headers=HEADERS)
