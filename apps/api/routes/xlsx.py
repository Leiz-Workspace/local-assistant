"""Expose owned bounded workbook inspection and immutable formula-preserving XLSX rewrites."""

import asyncio
import hashlib
import json
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response

from apps.api.routes.conversations import require_local_client
from apps.api.routes.files import Principal, Service, content_length, unique_fields
from src.application.services.file_storage_policy import StoragePolicyError
from src.application.services.xlsx_contract import (
    CACHE_STATUS,
    MAX_PLAN_BYTES,
    MAX_READ_BYTES,
    XLSX_MEDIA,
    XLSX_VERSION,
    validate_plan,
)

logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/files", tags=["XLSX"], dependencies=[Depends(require_local_client)]
)


class XlsxResponse(Response):
    """Retain the XLSX slot and locked source until response delivery ends or is cancelled."""

    def __init__(self, context, row, result, operation):
        """Build a private structured workbook inspection or bounded rewritten attachment."""
        self.context = context
        headers = {
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        }
        if operation == "read":
            payload = dict(
                result,
                file_id=str(row["id"]),
                sha256=row["actual_sha256"],
                content_trust="untrusted",
            )
            for sheet in payload["sheets"]:
                sheet["locator"] = f"file:{row['id']}#sheet={sheet['sheet_id']}"
                for cell in sheet["cells"]:
                    cell["locator"] = sheet["locator"] + "&cell=" + cell["cell"]
            content = json.dumps(
                payload, ensure_ascii=False, separators=(",", ":")
            ).encode("utf-8")
            if len(content) > MAX_READ_BYTES:
                raise StoragePolicyError("xlsx_limits_exceeded", 413)
            media = "application/json"
        else:
            content = result
            media = XLSX_MEDIA
            headers.update(
                {
                    "Content-Disposition": f'attachment; filename="edited-{row["id"]}.xlsx"',
                    "X-Source-File-ID": str(row["id"]),
                    "X-Source-SHA256": row["actual_sha256"],
                    "X-Xlsx-Processor": XLSX_VERSION,
                    "X-Formula-Cache-Status": CACHE_STATUS,
                    "X-Content-SHA256": hashlib.sha256(content).hexdigest(),
                }
            )
        super().__init__(content, media_type=media, headers=headers)

    async def __call__(self, scope, receive, send):
        """Close the async operation even if a client disconnects during a large reply."""
        try:
            await super().__call__(scope, receive, send)
        finally:
            await self.context.__aexit__(None, None, None)
            logger.info("file_xlsx_response_closed")


async def xlsx_response(service, principal, file_id, operation, plan=None):
    """Transfer the admitted operation to its response while closing it on construction failure."""
    context = service.xlsx_operation(principal, file_id, operation=operation, plan=plan)
    row, result = await context.__aenter__()
    try:
        return XlsxResponse(context, row, result, operation)
    except BaseException:
        await context.__aexit__(None, None, None)
        raise


async def xlsx_rewrite_body(request, policy):
    """Bound and validate a strict edit plan before accepting any XML or source mutation."""
    media = request.headers.getlist("content-type")
    if (
        len(media) != 1
        or media[0].partition(";")[0].strip().lower() != "application/json"
    ):
        raise StoragePolicyError("json_metadata_required", 415)
    length = content_length(request)
    if length is not None and length > MAX_PLAN_BYTES:
        raise StoragePolicyError("xlsx_edits_too_large", 413)
    data = bytearray()
    try:
        async with asyncio.timeout(policy.idle_seconds):
            async for chunk in request.stream():
                if len(data) + len(chunk) > MAX_PLAN_BYTES:
                    raise StoragePolicyError("xlsx_edits_too_large", 413)
                data.extend(chunk)
    except TimeoutError:
        raise StoragePolicyError("xlsx_request_timeout", 408) from None
    try:
        return validate_plan(
            json.loads(data.decode("utf-8"), object_pairs_hook=unique_fields)
        ).model_dump()
    except (ValueError, UnicodeError, RecursionError):
        raise StoragePolicyError("invalid_xlsx_edits", 422) from None


@router.post("/{file_id}/xlsx/read")
async def read_xlsx(file_id: UUID, principal: Principal, service: Service):
    """Inspect an owned ready XLSX with sheet/cell/style and formula provenance."""
    return await xlsx_response(service, principal, file_id, "read")


@router.post("/{file_id}/xlsx/rewrite")
async def rewrite_xlsx(
    file_id: UUID, request: Request, principal: Principal, service: Service
):
    """Download a verified formula-preserving literal rewrite without mutating or persisting the source."""
    plan = await xlsx_rewrite_body(request, service.policy)
    return await xlsx_response(service, principal, file_id, "rewrite", plan)
