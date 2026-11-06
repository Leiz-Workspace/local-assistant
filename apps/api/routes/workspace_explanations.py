"""Expose bounded authenticated local source-selected CORE explanations with exact citations and delivery fences."""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from apps.api.routes.conversations import require_local_client
from apps.api.routes.files import Principal
from apps.api.routes.workspaces import WorkspaceResponse, WorkspaceRoute
from src.application.ports.inference import InferenceFailure
from src.application.services.workspace_policy import WorkspaceAccessError
from src.application.services.workspace_tool_contracts import ReadInput

logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/workspaces",
    route_class=WorkspaceRoute,
    tags=["Workspace explanations"],
    dependencies=[Depends(require_local_client)],
)


class ExplanationInput(BaseModel):
    """Accept only a question and explicit source selections without identity, tools, model or budget overrides."""

    model_config = ConfigDict(extra="forbid", strict=True)
    question: str = Field(min_length=1, max_length=4096)
    sources: list[ReadInput] = Field(min_length=1, max_length=3)


async def get_explanation_service(request: Request):
    """Require explicit startup and sanitize source/model/OS failures without private diagnostics."""
    service = getattr(request.app.state, "workspace_explanation_service", None)
    if service is None or service.closing:
        raise HTTPException(503, detail=dict(code="explanation_unavailable"))
    try:
        yield service
    except WorkspaceAccessError as error:
        raise HTTPException(error.status_code, detail=dict(code=error.code)) from None
    except InferenceFailure as error:
        code, status = (
            ("explanation_context_limit", 422)
            if error.code == "context_overflow"
            else ("explanation_model_unavailable", 503)
        )
        logger.warning("workspace_explanation_inference_failed_safely")
        raise HTTPException(status, detail=dict(code=code)) from None
    except (OSError, ValueError, TypeError, KeyError, RuntimeError, TimeoutError):
        logger.warning("workspace_explanation_request_failed_safely")
        raise HTTPException(503, detail=dict(code="explanation_unavailable")) from None


@router.post("/{workspace_id}/explain")
async def explain_workspace(
    workspace_id: UUID,
    body: ExplanationInput,
    principal: Principal,
    service=Depends(get_explanation_service),
):
    """Transfer source/model ownership to the reused private pre-header-fenced workspace response."""
    context = service.operation(
        principal,
        workspace_id,
        body.question,
        [row.model_dump() for row in body.sources],
    )
    evidence = await context.__aenter__()
    try:
        return WorkspaceResponse(context, service, evidence)
    except BaseException:
        await context.__aexit__(None, None, None)
        raise
