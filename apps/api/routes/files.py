"""Expose authenticated loopback file reservation, raw streaming and owner-only download contracts."""

import asyncio
import json
import logging
from datetime import datetime
from typing import Annotated
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.exc import TimeoutError as PoolTimeout
from starlette.requests import ClientDisconnect

from apps.api.core.conversation_auth import authenticate_principal
from apps.api.routes.conversations import require_local_client
from apps.api.services.files import FileService, file_io
from src.application.services.file_storage_policy import StoragePolicyError
from src.infrastructure.local_blob_storage import BlobStorageError

logger = logging.getLogger(__name__)
Principal = Annotated[UUID, Depends(authenticate_principal)]


async def get_file_service(request: Request):
    """Inject optional storage and sanitize file/DB/OS errors without returning private details."""
    service = getattr(request.app.state, "file_service", None)
    if service is None or service.closing:
        raise HTTPException(503, detail={"code": "file_storage_unavailable"})
    try:
        yield service
    except StoragePolicyError as error:
        raise HTTPException(error.status_code, detail={"code": error.code}) from None
    except TimeoutError:
        logger.warning("file_upload_timed_out")
        raise HTTPException(408, detail={"code": "upload_timeout"}) from None
    except ClientDisconnect:
        logger.warning("file_upload_disconnected")
        raise HTTPException(400, detail={"code": "upload_interrupted"}) from None
    except PoolTimeout:
        telemetry = getattr(request.app.state, "pool_telemetry", None)
        if telemetry is not None:
            telemetry.note_timeout()
        raise HTTPException(503, detail={"code": "pool_timeout"}) from None
    except (SQLAlchemyError, BlobStorageError, OSError):
        logger.error("file_storage_operation_failed")
        raise HTTPException(503, detail={"code": "file_storage_unavailable"}) from None


Service = Annotated[FileService, Depends(get_file_service)]
router = APIRouter(
    prefix="/files", tags=["Files"], dependencies=[Depends(require_local_client)]
)


class FileCreate(BaseModel):
    """Accept only bounded declarations while assigning owner, IDs and storage keys internally."""

    model_config = ConfigDict(extra="forbid", strict=True)
    filename: str
    size_bytes: int
    sha256: str
    request_key: str | None = None


class FileView(BaseModel):
    """Expose provenance without owner overrides, paths, fingerprints or lease/purge tokens."""

    id: UUID
    filename: str = Field(validation_alias="display_name")
    size_bytes: int = Field(validation_alias="declared_size_bytes")
    sha256: str = Field(validation_alias="expected_sha256")
    media_type: str | None = Field(validation_alias="detected_media_type")
    state: str
    created_at: datetime
    verified_at: datetime | None


def content_length(request: Request) -> int | None:
    """Reject duplicate/malformed length hints without trusting them as actual byte counts."""
    values = request.headers.getlist("content-length")
    if not values:
        return None
    if (
        len(values) != 1
        or not values[0].isascii()
        or not values[0].isdecimal()
        or len(values[0]) > 20
    ):
        raise StoragePolicyError("invalid_content_length", 422)
    return int(values[0])


def unique_fields(pairs):
    """Reject duplicate JSON keys rather than accepting ambiguous reservation declarations."""
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate metadata field")
        result[key] = value
    return result


async def reservation_body(request, policy) -> FileCreate:
    """Bound raw JSON before decoding, including chunked requests and disconnected clients."""
    headers = request.headers.getlist("content-type")
    if (
        len(headers) != 1
        or headers[0].partition(";")[0].strip().lower() != "application/json"
    ):
        raise StoragePolicyError("json_metadata_required", 415)
    length = content_length(request)
    if length is not None and length > policy.max_metadata_bytes:
        raise StoragePolicyError("file_metadata_too_large", 413)
    data = bytearray()
    async with asyncio.timeout(policy.idle_seconds):
        async for chunk in request.stream():
            if len(data) + len(chunk) > policy.max_metadata_bytes:
                raise StoragePolicyError("file_metadata_too_large", 413)
            data.extend(chunk)
    try:
        payload = json.loads(data.decode("utf-8"), object_pairs_hook=unique_fields)
        return FileCreate.model_validate(payload)
    except (ValueError, ValidationError, RecursionError):
        raise StoragePolicyError("invalid_file_metadata", 422) from None


class FileDownloadResponse(StreamingResponse):
    """Close locked readers even when response cancellation happens before generator entry."""

    def __init__(self, service, row, reader):
        """Build immutable attachment headers without any internal filesystem pathname."""
        self.service = service
        self.reader = reader
        self.file_id = row["id"]
        super().__init__(
            self.chunks(),
            media_type=row["detected_media_type"],
            headers={
                "Content-Length": str(row["actual_size_bytes"]),
                "Content-Disposition": "attachment; filename*=UTF-8''"
                + quote(row["display_name"], safe=""),
                "X-Content-Type-Options": "nosniff",
                "Cache-Control": "private, no-store",
            },
        )

    async def chunks(self):
        """Stream bounded chunks from the already authorized and locked descriptor."""
        while chunk := await file_io(self.reader.read):
            yield chunk

    async def __call__(self, scope, receive, send):
        """Track the whole response and join file work before releasing its shared lock."""
        task = None
        try:
            task = self.service.track()
            await super().__call__(scope, receive, send)
        finally:
            await file_io(self.reader.close)
            if task is not None:
                self.service.untrack(task)
            logger.info("file_download_closed file_id=%s", self.file_id)


@router.post("", response_model=FileView, status_code=201)
async def reserve_file(request: Request, principal: Principal, service: Service):
    """Commit owner quota reservation before any payload body is accepted."""
    body = await reservation_body(request, service.policy)
    return await service.reserve(principal, **body.model_dump())


@router.put("/{file_id}/content", response_model=FileView)
async def upload_file(
    file_id: UUID, request: Request, principal: Principal, service: Service
):
    """Stream raw bytes without multipart spooling before lease/quota admission."""
    media = request.headers.getlist("content-type")
    if len(media) > 1 or (media and media[0].lower().startswith("multipart/")):
        raise StoragePolicyError("raw_body_required", 415)
    return await service.upload(
        principal,
        file_id,
        request.stream(),
        declared_media=media[0] if media else None,
        content_length=content_length(request),
    )


@router.get("", response_model=list[FileView])
async def list_files(
    principal: Principal,
    service: Service,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """List visible metadata only for the authenticated UUID principal."""
    return await service.journal.list(principal, limit=limit, offset=offset)


@router.get("/{file_id}", response_model=FileView)
async def get_file(file_id: UUID, principal: Principal, service: Service):
    """Read owner metadata without disclosing foreign or terminal resources."""
    return await service.journal.get(principal, file_id)


@router.get("/{file_id}/content")
async def download_file(file_id: UUID, principal: Principal, service: Service):
    """Admit only verified owned ready bytes and stream them as a private attachment."""
    row, reader = await service.open_download(principal, file_id)
    try:
        return FileDownloadResponse(service, row, reader)
    except BaseException:
        await file_io(reader.close)
        raise


@router.delete("/{file_id}")
async def delete_file(file_id: UUID, principal: Principal, service: Service):
    """Return 204 only after physical purge, otherwise honestly report pending cleanup."""
    if await service.delete(principal, file_id):
        return Response(status_code=204)
    return JSONResponse(
        status_code=202, content={"id": str(file_id), "state": "purging"}
    )


@router.post("/{file_id}/extract")
async def extract_file(file_id: UUID, principal: Principal, service: Service):
    """Return untrusted native PDF pages with stable source provenance and private cache policy."""
    result = await service.extract(principal, file_id)
    return JSONResponse(
        result,
        headers={
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )
