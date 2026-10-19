"""Expose strict authenticated local retrieval while retaining source readers through bounded response delivery."""

import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.exc import SQLAlchemyError
from starlette.responses import JSONResponse, Response

from apps.api.routes.conversations import require_local_client
from apps.api.routes.files import Principal
from src.application.services.document_chunks import canonical
from src.application.services.file_storage_policy import StoragePolicyError
from src.infrastructure.local_blob_storage import BlobStorageError

logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/retrieval",
    tags=["Retrieval"],
    dependencies=[Depends(require_local_client)],
)
HEADERS = {"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"}


class SearchInput(BaseModel):
    """Accept only bounded query text, top-k and UUID scope narrowing without caller ACL/filter fields."""

    model_config = ConfigDict(extra="forbid", strict=True)
    query: str = Field(min_length=1, max_length=4096)
    top_k: int = Field(default=5, ge=1, le=10)
    file_ids: list[Annotated[UUID, Field(strict=False)]] | None = Field(
        default=None, min_length=1, max_length=16, strict=False
    )


async def get_retrieval_service(request: Request):
    """Require explicit opt-in and sanitize fixed policy/database/source failures without leaking diagnostics."""
    service = getattr(request.app.state, "retrieval_service", None)
    if service is None or service.closing:
        raise HTTPException(503, detail=dict(code="retrieval_unavailable"))
    try:
        yield service
    except StoragePolicyError as error:
        raise HTTPException(error.status_code, detail=dict(code=error.code)) from None
    except (
        SQLAlchemyError,
        BlobStorageError,
        OSError,
        ValueError,
        RuntimeError,
        TimeoutError,
    ):
        logger.warning("retrieval_request_failed_safely")
        raise HTTPException(503, detail=dict(code="retrieval_unavailable")) from None


class RetrievalResponse(Response):
    """Retain source ownership until delivery ends and authorize again before any response headers."""

    def __init__(self, context, service, owner, payload, retained):
        """Serialize only bounded rehydrated source results while preserving the live operation context."""
        self.context, self.service, self.owner, self.retained = (
            context,
            service,
            owner,
            retained,
        )
        data = canonical(payload).encode()
        if len(data) > 1024**2:
            raise StoragePolicyError("retrieval_reply_limit", 413)
        super().__init__(data, media_type="application/json", headers=HEADERS)

    async def __call__(self, scope, receive, send):
        """Fail closed before headers on changed source/generation and always join/release retained resources."""
        try:
            try:
                await self.service.validate(self.owner, self.retained)
            except (
                StoragePolicyError,
                SQLAlchemyError,
                BlobStorageError,
                OSError,
                ValueError,
                RuntimeError,
            ):
                logger.warning("retrieval_delivery_fenced")
                response = JSONResponse(
                    dict(detail=dict(code="retrieval_source_changed")),
                    status_code=409,
                    headers=HEADERS,
                )
                await response(scope, receive, send)
                return
            await super().__call__(scope, receive, send)
        finally:
            await self.context.__aexit__(None, None, None)
            logger.info("retrieval_response_closed")


@router.post("/search")
async def search_sources(
    body: SearchInput, principal: Principal, service=Depends(get_retrieval_service)
):
    """Search only current authenticated private sources without adding retrieved text to model context."""
    context = service.operation(
        principal, body.query, top_k=body.top_k, file_ids=body.file_ids
    )
    payload, retained = await context.__aenter__()
    try:
        return RetrievalResponse(context, service, principal, payload, retained)
    except BaseException:
        await context.__aexit__(None, None, None)
        raise
