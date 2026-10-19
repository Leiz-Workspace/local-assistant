"""Expose strict authenticated localhost memory management with owner controls and content-free failures."""

import logging
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.exc import SQLAlchemyError
from starlette.responses import JSONResponse, Response

from apps.api.routes.conversations import require_local_client
from apps.api.routes.files import Principal
from src.application.services.memory_contract import MemoryPolicyError

logger = logging.getLogger(__name__)
HEADERS = {"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"}
JsonUUID = Annotated[UUID, Field(strict=False)]


class MemoryRoute(APIRoute):
    """Keep validation/auth failures private without echoing invalid private memory text."""

    def get_route_handler(self):
        """Wrap only memory routes rather than changing accepted application-wide exception behavior."""
        original = super().get_route_handler()

        async def protected(request):
            """Sanitize request validation and retain private headers on successful or rejected memory requests."""
            try:
                response = await original(request)
            except RequestValidationError:
                logger.warning("memory_request_validation_failed")
                response = JSONResponse(
                    dict(detail=dict(code="memory_input_invalid")),
                    status_code=422,
                    headers=HEADERS,
                )
            except HTTPException as error:
                raise HTTPException(
                    error.status_code,
                    detail=error.detail,
                    headers={**(error.headers or {}), **HEADERS},
                ) from None
            response.headers.update(HEADERS)
            return response

        return protected


router = APIRouter(
    prefix="/memory",
    tags=["Memory management"],
    dependencies=[Depends(require_local_client)],
    route_class=MemoryRoute,
)


class StrictInput(BaseModel):
    """Reject unknown caller identity, provenance, model and coercible primitive inputs."""

    model_config = ConfigDict(extra="forbid", strict=True)


class SettingsInput(StrictInput):
    """Require explicit owner flags and expected epoch without accepting a principal override."""

    expected_revision: int = Field(ge=0)
    enabled: bool
    extraction_enabled: bool = False


class ConsentInput(StrictInput):
    """Request one bounded class/scope receipt under an explicitly expected enabled owner epoch."""

    kind: Literal["session", "episodic", "preference", "project"]
    scope_id: JsonUUID | None = None
    expected_revision: int = Field(ge=1)
    seconds: int | None = Field(default=None, ge=1, le=31536000)
    allow_extraction: bool = False


class CreateInput(StrictInput):
    """Accept only explicit receipt-bound literal manual text and optional shorter retention."""

    consent_id: JsonUUID
    text: str = Field(min_length=1, max_length=4096)
    seconds: int | None = Field(default=None, ge=1, le=31536000)


class EditInput(StrictInput):
    """Require the current record version and new literal text without source/producer overrides."""

    expected_version: int = Field(ge=1)
    text: str = Field(min_length=1, max_length=4096)


async def get_memory_service(request: Request):
    """Require enabled management and translate policy/storage errors without private driver diagnostics."""
    service = getattr(request.app.state, "memory_service", None)
    if service is None or service.closing:
        raise HTTPException(
            503, detail=dict(code="memory_unavailable"), headers=HEADERS
        )
    try:
        yield service
    except MemoryPolicyError as error:
        if error.code in {"memory_not_found", "memory_scope_not_found"}:
            status = 404
        elif error.code in {"memory_disabled", "memory_extraction_disabled"}:
            status = 403
        elif error.code in {"memory_conflict", "memory_consent_inactive"}:
            status = 409
        elif error.code in {"memory_limit", "memory_consent_limit"}:
            status = 429
        elif error.code == "memory_unavailable":
            status = 503
        else:
            status = 422
        raise HTTPException(
            status, detail=dict(code=error.code), headers=HEADERS
        ) from None
    except (SQLAlchemyError, ValueError, TypeError, KeyError, RuntimeError, OSError):
        logger.warning("memory_management_failed_safely")
        raise HTTPException(
            503, detail=dict(code="memory_unavailable"), headers=HEADERS
        ) from None


def private_result(value, *, status=200):
    """Encode bounded owner data with private delivery headers rather than exposing database objects."""
    return JSONResponse(jsonable_encoder(value), status_code=status, headers=HEADERS)


@router.get("/settings")
async def inspect_settings(principal: Principal, service=Depends(get_memory_service)):
    """Inspect owner settings even while owner memory use remains disabled."""
    return private_result(await service.run(principal, "settings"))


@router.put("/settings")
async def configure_settings(
    body: SettingsInput, principal: Principal, service=Depends(get_memory_service)
):
    """Apply explicit settings compare-and-swap without turning old consent epochs back on."""
    return private_result(
        await service.run(principal, "configure", **body.model_dump())
    )


@router.post("/consents", status_code=201)
async def grant_consent(
    body: ConsentInput, principal: Principal, service=Depends(get_memory_service)
):
    """Issue one explicit receipt with declared class defaults and server-owned principal identity."""
    values = body.model_dump()
    if values["seconds"] is None:
        values["seconds"] = 3600 if body.kind == "session" else 2592000
    return private_result(await service.run(principal, "grant", **values), status=201)


@router.delete("/consents/{consent_id}")
async def revoke_consent(
    consent_id: UUID, principal: Principal, service=Depends(get_memory_service)
):
    """Revoke an owned receipt independently of the owner's current enablement state."""
    return private_result(await service.run(principal, "revoke", consent_id))


@router.get("/records")
async def list_records(
    principal: Principal,
    limit: int = Query(default=50, ge=1, le=100),
    after: UUID | None = None,
    service=Depends(get_memory_service),
):
    """List bounded owned metadata while keeping private full text in explicit per-record inspection."""
    return private_result(
        dict(records=await service.run(principal, "list", limit=limit, after=after))
    )


@router.post("/records", status_code=201)
async def create_record(
    body: CreateInput, principal: Principal, service=Depends(get_memory_service)
):
    """Capture one manual literal under current consent without accepting generated provenance."""
    return private_result(
        await service.run(
            principal, "create_manual", body.consent_id, body.text, seconds=body.seconds
        ),
        status=201,
    )


@router.get("/records/{record_id}")
async def inspect_record(
    record_id: UUID, principal: Principal, service=Depends(get_memory_service)
):
    """Inspect only an owned bounded record, including when consent or owner use was disabled."""
    return private_result(await service.run(principal, "inspect", record_id))


@router.patch("/records/{record_id}")
async def edit_record(
    record_id: UUID,
    body: EditInput,
    principal: Principal,
    service=Depends(get_memory_service),
):
    """Edit exact manual content with active consent and a matching record version."""
    return private_result(
        await service.run(
            principal,
            "edit_manual",
            record_id,
            body.text,
            expected_version=body.expected_version,
        )
    )


@router.delete("/records/{record_id}", status_code=204)
async def delete_record(
    record_id: UUID,
    principal: Principal,
    expected_version: int = Query(ge=1),
    service=Depends(get_memory_service),
):
    """Hard-delete an owned expected version while preserving controls for disabled owners."""
    await service.run(principal, "delete", record_id, expected_version=expected_version)
    return Response(status_code=204, headers=HEADERS)
