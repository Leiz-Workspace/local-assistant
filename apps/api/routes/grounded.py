"""Expose strict authenticated localhost grounded answers with exact source citations and delivery fences."""

import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.exc import SQLAlchemyError

from apps.api.routes.conversations import require_local_client
from apps.api.routes.files import Principal
from apps.api.routes.retrieval import RetrievalResponse
from src.application.ports.inference import InferenceFailure
from src.application.services.file_storage_policy import StoragePolicyError
from src.infrastructure.local_blob_storage import BlobStorageError

logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/grounded",
    tags=["Grounded answers"],
    dependencies=[Depends(require_local_client)],
)


class GroundedInput(BaseModel):
    """Accept bounded query/source narrowing without caller model, ownership or citation metadata."""

    model_config = ConfigDict(extra="forbid", strict=True)
    query: str = Field(min_length=1, max_length=4096)
    top_k: int = Field(default=3, ge=1, le=3)
    file_ids: list[Annotated[UUID, Field(strict=False)]] | None = Field(
        default=None, min_length=1, max_length=16, strict=False
    )


async def get_grounded_service(request: Request):
    """Require explicit startup and sanitize model/source failures without returning any private diagnostics."""
    service = getattr(request.app.state, "grounded_service", None)
    if service is None or service.closing:
        raise HTTPException(503, detail=dict(code="grounded_unavailable"))
    try:
        yield service
    except StoragePolicyError as error:
        raise HTTPException(error.status_code, detail=dict(code=error.code)) from None
    except InferenceFailure as error:
        code, status = (
            ("grounded_context_limit", 422)
            if error.code == "context_overflow"
            else ("grounded_model_unavailable", 503)
        )
        logger.warning("grounded_inference_failed_safely")
        raise HTTPException(status, detail=dict(code=code)) from None
    except (
        SQLAlchemyError,
        BlobStorageError,
        OSError,
        ValueError,
        TypeError,
        KeyError,
        RuntimeError,
        TimeoutError,
    ):
        logger.warning("grounded_request_failed_safely")
        raise HTTPException(503, detail=dict(code="grounded_unavailable")) from None


@router.post("/answer")
async def answer_from_sources(
    body: GroundedInput, principal: Principal, service=Depends(get_grounded_service)
):
    """Retain authorized sources until strict generated citations pass the final pre-header delivery fence."""
    context = service.operation(
        principal, body.query, top_k=body.top_k, file_ids=body.file_ids
    )
    payload, retained = await context.__aenter__()
    try:
        return RetrievalResponse(context, service, principal, payload, retained)
    except BaseException:
        await context.__aexit__(None, None, None)
        raise
