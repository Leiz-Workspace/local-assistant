"""Expose owner-scoped one-page OCR/native/local-vision results with private provenance and uncertainty."""

import json
import logging
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response

from apps.api.routes.conversations import require_local_client
from apps.api.routes.files import Principal, Service
from src.application.services.file_storage_policy import StoragePolicyError
from src.application.services.ocr_contract import MAX_REPLY_BYTES

logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/files", tags=["OCR"], dependencies=[Depends(require_local_client)]
)


class OcrResponse(Response):
    """Retain the admitted page operation and source lock until delivery or cancellation completes."""

    def __init__(self, context, row, page):
        """Attach immutable source/page provenance while never exposing internal raster bytes."""
        self.context = context
        payload = dict(
            page,
            file_id=str(row["id"]),
            sha256=row["actual_sha256"],
            content_trust="untrusted",
            locator=f"file:{row['id']}#page={page['page_number']}",
        )
        data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode(
            "utf-8"
        )
        if len(data) > MAX_REPLY_BYTES:
            raise StoragePolicyError("ocr_limits_exceeded", 413)
        super().__init__(
            data,
            media_type="application/json",
            headers={
                "Cache-Control": "private, no-store",
                "X-Content-Type-Options": "nosniff",
            },
        )

    async def __call__(self, scope, receive, send):
        """Release the held admission/source even when the client disappears during response delivery."""
        try:
            await super().__call__(scope, receive, send)
        finally:
            await self.context.__aexit__(None, None, None)
            logger.info("file_ocr_response_closed")


async def ocr_response(service, principal, file_id, number=1, mode="auto"):
    """Transfer operation ownership to its response and close it on construction failure."""
    context = service.ocr_operation(principal, file_id, number=number, mode=mode)
    row, page = await context.__aenter__()
    try:
        return OcrResponse(context, row, page)
    except BaseException:
        await context.__aexit__(None, None, None)
        raise


@router.post("/{file_id}/ocr")
async def recognize_page(
    file_id: UUID,
    principal: Principal,
    service: Service,
    page: int = Query(1, ge=1, le=1000),
    mode: Literal["auto", "ocr", "vlm"] = "auto",
):
    """Extract one owned PDF/image page with explicit OCR/VLM mode and bounded source locators."""
    return await ocr_response(service, principal, file_id, page, mode)
