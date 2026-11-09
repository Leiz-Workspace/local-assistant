"""Expose opt-in authenticated localhost structured excerpt extraction over owner-authorized grounded sources."""

import logging
import re
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy.exc import SQLAlchemyError
from starlette.requests import ClientDisconnect

from apps.api.routes.conversations import require_local_client
from apps.api.routes.files import Principal
from apps.api.routes.retrieval import HEADERS, RetrievalResponse
from src.application.ports.inference import InferenceFailure
from src.application.services.file_storage_policy import StoragePolicyError
from src.application.services.gpu_admission import AdmissionBusy
from src.application.services.workspace_policy import WorkspaceAccessError
from src.application.services.workspace_requests import parse_workspace_json
from src.infrastructure.local_blob_storage import BlobStorageError

logger = logging.getLogger(__name__)
BODY_LIMIT = 16384
NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,63}")
router = APIRouter(
    prefix="/grounded",
    tags=["Grounded extraction"],
    dependencies=[Depends(require_local_client)],
)


class ExtractField(BaseModel):
    """Declare one typed fact and the single owned file that must support it."""

    model_config = ConfigDict(extra="forbid", strict=True)
    name: str = Field(
        min_length=1, max_length=64, pattern=r"^[A-Za-z_][A-Za-z0-9_]{0,63}$"
    )
    type: Literal["string", "integer"]
    file_id: Annotated[UUID, Field(strict=False)]


class ExtractInput(BaseModel):
    """Accept retrieval text and 1-3 field declarations, never model, schema, source or citation overrides."""

    model_config = ConfigDict(extra="forbid", strict=True)
    query: str = Field(min_length=1, max_length=4096)
    fields: list[ExtractField] = Field(min_length=1, max_length=3)

    @model_validator(mode="after")
    def bounded_distinct(self):
        """Require nonblank 4096-byte query text and distinct identifier names and file UUIDs."""
        try:
            size = len(self.query.encode())
        except UnicodeError:
            raise ValueError("query") from None
        names = [row.name for row in self.fields]
        if (
            not self.query.strip()
            or size > 4096
            or any(
                NAME.fullmatch(name) is None or name == "citations" for name in names
            )
            or len(set(names)) != len(names)
            or len({row.file_id for row in self.fields}) != len(self.fields)
        ):
            raise ValueError("extract_contract")
        return self


def request_schema():
    """Describe the strict JSON body in OpenAPI while the handler parses it without echoing input."""
    schema = ExtractInput.model_json_schema()
    definitions = schema.pop("$defs")
    schema["properties"]["fields"]["items"] = definitions["ExtractField"]
    return schema


async def extract_body(request):
    """Read one bounded JSON object, rejecting duplicate keys, nonfinite numbers and contract violations."""
    headers = request.headers.getlist("content-type")
    if (
        len(headers) != 1
        or headers[0].partition(";")[0].strip().lower() != "application/json"
    ):
        raise StoragePolicyError("extract_contract_invalid", 422)
    data = bytearray()
    try:
        async for chunk in request.stream():
            if len(data) + len(chunk) > BODY_LIMIT:
                raise StoragePolicyError("extract_contract_invalid", 422)
            data.extend(chunk)
    except ClientDisconnect:
        raise StoragePolicyError("extract_contract_invalid", 422) from None
    try:
        return ExtractInput.model_validate(parse_workspace_json(bytes(data)))
    except (ValueError, WorkspaceAccessError, RecursionError):
        raise StoragePolicyError("extract_contract_invalid", 422) from None


def failure(status, code):
    """Log and raise one finite extraction failure code without request or source content."""
    logger.warning("grounded_extract_failed code=%s", code)
    return HTTPException(status, detail=dict(code=code), headers=HEADERS)


async def get_extract_service(request: Request):
    """Require the live grounded service and map extraction failures to finite codes, keeping gpu_busy distinct."""
    service = getattr(request.app.state, "grounded_service", None)
    if service is None or service.closing:
        raise failure(503, "grounded_unavailable")
    try:
        yield service
    except StoragePolicyError as error:
        raise failure(error.status_code, error.code) from None
    except AdmissionBusy:
        logger.warning("grounded_extract_gpu_busy")
        raise HTTPException(
            409, detail=dict(code="gpu_busy"), headers=HEADERS
        ) from None
    except InferenceFailure:
        raise failure(503, "extract_model_unavailable") from None
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
        raise failure(503, "grounded_unavailable") from None


@router.post(
    "/extract",
    openapi_extra=dict(
        requestBody=dict(
            required=True,
            content={"application/json": dict(schema=request_schema())},
        )
    ),
)
async def extract_from_sources(
    request: Request, principal: Principal, service=Depends(get_extract_service)
):
    """Retain authorized sources until verified typed facts pass the final pre-header delivery fence."""
    body = await extract_body(request)
    context = service.extraction(
        principal,
        body.query,
        tuple((row.name, row.type, row.file_id) for row in body.fields),
    )
    payload, retained = await context.__aenter__()
    try:
        return RetrievalResponse(context, service, principal, payload, retained)
    except BaseException:
        await context.__aexit__(None, None, None)
        raise
