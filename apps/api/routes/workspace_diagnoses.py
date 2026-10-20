"""Expose authenticated source-backed manual diagnosis plans with no execution or source-write authority."""

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
    tags=["Workspace diagnosis"],
    dependencies=[Depends(require_local_client)],
)


class DiagnosisInput(BaseModel):
    """Accept only a bounded symptom and explicit selected source lines without execution or model controls."""

    model_config = ConfigDict(extra="forbid", strict=True)
    symptom: str = Field(min_length=1, max_length=4096)
    sources: list[ReadInput] = Field(min_length=1, max_length=3)


async def get_diagnosis_service(request: Request):
    """Require enabled diagnosis and sanitize source/model/backend errors without private diagnostics."""
    service = getattr(request.app.state, "workspace_diagnosis_service", None)
    if service is None or service.closing:
        raise HTTPException(503, detail=dict(code="diagnosis_unavailable"))
    try:
        yield service
    except WorkspaceAccessError as error:
        raise HTTPException(error.status_code, detail=dict(code=error.code)) from None
    except InferenceFailure as error:
        code, status = (
            ("diagnosis_context_limit", 422)
            if error.code == "context_overflow"
            else ("diagnosis_model_unavailable", 503)
        )
        logger.warning("workspace_diagnosis_inference_failed_safely")
        raise HTTPException(status, detail=dict(code=code)) from None
    except (OSError, ValueError, TypeError, KeyError, RuntimeError, TimeoutError):
        logger.warning("workspace_diagnosis_request_failed_safely")
        raise HTTPException(503, detail=dict(code="diagnosis_unavailable")) from None


@router.post("/{workspace_id}/diagnose")
async def diagnose_workspace(
    workspace_id: UUID,
    body: DiagnosisInput,
    principal: Principal,
    service=Depends(get_diagnosis_service),
):
    """Retain native source/model ownership until the manual diagnostic plan passes the final delivery fence."""
    context = service.operation(
        principal,
        workspace_id,
        body.symptom,
        [row.model_dump() for row in body.sources],
    )
    evidence = await context.__aenter__()
    try:
        return WorkspaceResponse(context, service, evidence)
    except BaseException:
        await context.__aexit__(None, None, None)
        raise
