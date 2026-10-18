"""Expose private source-bound document chunks without caching or indexing content."""

import logging
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response

from apps.api.routes.conversations import require_local_client
from apps.api.routes.files import Principal, Service
from apps.api.services.chunks import chunk_operation
from src.application.services.document_chunks import MAX_REPLY_BYTES, canonical
from src.application.services.file_storage_policy import StoragePolicyError

logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/files", tags=["Chunks"], dependencies=[Depends(require_local_client)]
)


class ChunkResponse(Response):
    """Keep the source lock and admission alive until response completion."""

    def __init__(self, context, payload):
        """Serialize bounded metadata and content with private response headers."""
        self.context = context
        data = canonical(payload).encode("utf-8")
        if len(data) > MAX_REPLY_BYTES:
            raise StoragePolicyError("chunk_limits_exceeded", 413)
        super().__init__(
            data,
            media_type="application/json",
            headers={
                "Cache-Control": "private, no-store",
                "X-Content-Type-Options": "nosniff",
            },
        )

    async def __call__(self, scope, receive, send):
        """Release resources even if delivery is cancelled or fails."""
        try:
            await super().__call__(scope, receive, send)
        finally:
            await self.context.__aexit__(None, None, None)
            logger.info("file_chunk_response_closed")


async def chunk_response(service, principal, file_id, **options):
    """Transfer context ownership to the response and close on construction errors."""
    context = chunk_operation(service, principal, file_id, **options)
    _, payload = await context.__aenter__()
    try:
        return ChunkResponse(context, payload)
    except BaseException:
        await context.__aexit__(None, None, None)
        raise


@router.post("/{file_id}/chunks")
async def create_chunks(
    file_id: UUID,
    principal: Principal,
    service: Service,
    max_bytes: int = Query(2048, ge=256, le=8192),
    source: Literal["auto", "ocr"] = "auto",
    page: int = Query(1, ge=1, le=1000),
    ocr_mode: Literal["auto", "ocr", "vlm"] = "auto",
):
    """Chunk only an authenticated ready source using server-derived provenance and access labels."""
    return await chunk_response(
        service,
        principal,
        file_id,
        max_bytes=max_bytes,
        source=source,
        page=page,
        ocr_mode=ocr_mode,
    )
