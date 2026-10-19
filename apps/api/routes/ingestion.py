"""Expose explicit authenticated source-index admission and owner-scoped durable job status."""

import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy.exc import SQLAlchemyError

from apps.api.routes.conversations import require_local_client
from apps.api.routes.files import Principal
from apps.api.services.ingestion import IngestionService
from src.application.services.file_storage_policy import StoragePolicyError
from src.infrastructure.local_blob_storage import BlobStorageError

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Ingestion"], dependencies=[Depends(require_local_client)])


async def get_ingestion_service(request: Request):
    """Require opt-in resources and return only fixed safe policy/service failures."""
    service = getattr(request.app.state, "ingestion_service", None)
    if service is None or service.closing:
        raise HTTPException(503, detail=dict(code="ingestion_unavailable"))
    try:
        yield service
    except StoragePolicyError as error:
        raise HTTPException(error.status_code, detail=dict(code=error.code)) from None
    except (
        SQLAlchemyError,
        BlobStorageError,
        OSError,
        ValueError,
        TimeoutError,
        RuntimeError,
    ):
        logger.warning("ingestion_request_failed_safely")
        raise HTTPException(503, detail=dict(code="ingestion_unavailable")) from None


Service = Annotated[IngestionService, Depends(get_ingestion_service)]


async def status(service, row):
    """Report historical job progress separately from current trusted-source generation visibility."""
    active = await service.journal.active(
        row["owner_id"], row["file_id"], row["model_fingerprint"]
    )
    return dict(
        id=str(row["id"]),
        file_id=str(row["file_id"]),
        status=row["state"],
        active=active is not None and active["id"] == row["id"],
        chunk_count=len(row["point_ids"]),
        attempts=row["attempts"],
        error_code=row["error_code"],
        created_at=row["created_at"].isoformat(),
        updated_at=row["updated_at"].isoformat(),
    )


@router.post("/files/{file_id}/index", status_code=202)
async def index_source(
    file_id: UUID,
    principal: Principal,
    service: Service,
    response: Response,
    max_bytes: int = Query(256, ge=256, le=8192),
):
    """Admit only a verified authenticated source using complete actual tokenizer counts and durable replay."""
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    row = await service.admit(principal, file_id, max_bytes=max_bytes)
    return await status(service, row)


@router.get("/ingestion/{job_id}")
async def ingestion_status(
    job_id: UUID, principal: Principal, service: Service, response: Response
):
    """Return only the authenticated owner's namespace-bound durable job metadata without source content."""
    response.headers["Cache-Control"] = "private, no-store"
    row = await service.journal.get(principal, job_id)
    return await status(service, row)
