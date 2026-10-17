"""Provide validated localhost-only REST contracts for persistent conversations."""

import ipaddress
import logging
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy.exc import SQLAlchemyError

from apps.api.core.model_config import ModelConfigError
from apps.api.runtime.presets import RuntimePreset
from apps.api.services.conversations import ConversationService
from src.application.ports.inference import InferenceFailure
from src.application.services.conversation_manager import ConversationError

logger = logging.getLogger(__name__)


async def require_local_client(request: Request) -> None:
    """Deny external peers, browser origins and proxied requests until ownership exists."""
    try:
        local = (
            request.client is not None
            and ipaddress.ip_address(request.client.host).is_loopback
        )
    except ValueError:
        local = False
    proxy_headers = {"forwarded", "x-forwarded-for", "x-forwarded-host", "x-real-ip"}
    if (
        not local
        or "origin" in request.headers
        or proxy_headers.intersection(request.headers)
    ):
        logger.warning("conversation_access_denied")
        raise HTTPException(
            403,
            detail={
                "code": "local_access_required",
                "message": "Direct localhost API access required.",
            },
        )


async def get_service(request: Request) -> AsyncIterator[ConversationService]:
    """Inject application resources and sanitize conversation-specific failures."""
    service = getattr(request.app.state, "conversation_service", None)
    if service is None:
        logger.warning("conversation_storage_unavailable")
        raise HTTPException(
            503,
            detail={
                "code": "storage_unavailable",
                "message": "Conversation storage is not configured.",
            },
        )
    try:
        yield service
    except (ConversationError, InferenceFailure) as exc:
        logger.warning(
            "conversation_operation_failed code=%s status=%s", exc.code, exc.status_code
        )
        raise HTTPException(
            exc.status_code,
            detail={
                "code": exc.code,
                "message": "Conversation operation could not be completed.",
            },
        ) from None
    except ModelConfigError:
        logger.error("conversation_model_configuration_failed")
        raise HTTPException(
            503,
            detail={
                "code": "model_configuration_error",
                "message": "Model configuration unavailable.",
            },
        ) from None
    except SQLAlchemyError:
        logger.error("conversation_database_operation_failed")
        raise HTTPException(
            503,
            detail={
                "code": "storage_unavailable",
                "message": "Conversation storage unavailable.",
            },
        ) from None


Service = Annotated[ConversationService, Depends(get_service)]
router = APIRouter(
    prefix="/conversations",
    tags=["Conversations"],
    dependencies=[Depends(require_local_client)],
)


class Contract(BaseModel):
    """Reject unknown inputs and serialize domain attributes without internal metadata."""

    model_config = ConfigDict(
        extra="forbid",
        from_attributes=True,
        str_strip_whitespace=True,
        allow_inf_nan=False,
    )


class ConversationCreate(Contract):
    """Validate conversation identity and initial runtime defaults."""

    title: str | None = Field(default=None, min_length=1, max_length=200)
    profile: Literal["core", "unrestricted"] = "core"
    preset_default: RuntimePreset = RuntimePreset.BALANCED


class ConversationUpdate(Contract):
    """Accept only nonempty updates to editable conversation defaults."""

    title: str | None = Field(default=None, min_length=1, max_length=200)
    preset_default: RuntimePreset | None = None

    @model_validator(mode="after")
    def validate_changes(self):
        """Reject empty patches and explicit null values for editable fields."""
        if not self.model_fields_set or any(
            getattr(self, name) is None for name in self.model_fields_set
        ):
            raise ValueError("Provide a non-null title or preset_default")
        return self


class MessageSend(Contract):
    """Validate generation parameters and preserve message whitespace exactly."""

    model_config = ConfigDict(
        extra="forbid", allow_inf_nan=False, str_strip_whitespace=False
    )
    content: str = Field(min_length=1)
    preset: RuntimePreset | None = None
    request_key: str | None = Field(default=None, min_length=1, max_length=128)
    temperature: float = Field(default=0.7, ge=0, le=2)
    max_tokens: int | None = Field(default=None, ge=1, le=32768)

    @model_validator(mode="after")
    def validate_content(self):
        """Reject blank messages without modifying fingerprint-sensitive input."""
        if not self.content.strip():
            raise ValueError("Message content must not be blank")
        return self


class ConversationView(Contract):
    """Expose public conversation fields while excluding internal metadata."""

    id: UUID
    title: str | None
    profile: str
    preset_default: str
    status: str
    created_at: datetime
    updated_at: datetime


class MessageView(Contract):
    """Expose transcript content without fingerprints or reasoning metadata."""

    model_config = ConfigDict(from_attributes=True, str_strip_whitespace=False)
    id: UUID
    conversation_id: UUID
    sequence: int
    role: str
    content: str
    created_at: datetime


class ReplyView(Contract):
    """Expose persisted inference identity and replay status without reasoning traces."""

    model_config = ConfigDict(from_attributes=True, str_strip_whitespace=False)
    conversation_id: UUID
    user_message_id: UUID
    assistant_message_id: UUID
    inference_run_id: UUID
    content: str
    preset_requested: str
    preset_selected: str
    model_id: str
    cached: bool


@router.post("", response_model=ConversationView, status_code=201)
async def create_conversation(body: ConversationCreate, service: Service):
    """Create a persistent conversation with validated model defaults."""
    return await service.create(**body.model_dump(mode="json"))


@router.get("", response_model=list[ConversationView])
async def list_conversations(
    service: Service,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    include_archived: bool = False,
):
    """List active conversations by default with bounded offset pagination."""
    return await service.list(
        limit=limit, offset=offset, include_archived=include_archived
    )


@router.get("/{conversation_id}", response_model=ConversationView)
async def get_conversation(conversation_id: UUID, service: Service):
    """Read a visible conversation by UUID."""
    return await service.get(conversation_id)


@router.patch("/{conversation_id}", response_model=ConversationView)
async def update_conversation(
    conversation_id: UUID, body: ConversationUpdate, service: Service
):
    """Update title or default preset on an active conversation."""
    return await service.mutate(
        conversation_id, "update", **body.model_dump(mode="json", exclude_unset=True)
    )


@router.get("/{conversation_id}/messages", response_model=list[MessageView])
async def list_messages(
    conversation_id: UUID,
    service: Service,
    limit: int = Query(100, ge=1, le=500),
    after_sequence: int = Query(0, ge=0),
):
    """Read ascending message sequences after an exclusive cursor."""
    return await service.history(
        conversation_id, limit=limit, after_sequence=after_sequence
    )


@router.post("/{conversation_id}/messages", response_model=ReplyView)
async def send_message(conversation_id: UUID, body: MessageSend, service: Service):
    """Persist a user turn and return the completed or cached assistant answer."""
    return await service.send(conversation_id, **body.model_dump(mode="json"))


@router.post("/{conversation_id}/archive", response_model=ConversationView)
async def archive_conversation(conversation_id: UUID, service: Service):
    """Archive an idle conversation while retaining readable history."""
    return await service.mutate(conversation_id, "archive")


@router.delete("/{conversation_id}", status_code=204)
async def delete_conversation(conversation_id: UUID, service: Service):
    """Soft-delete an idle conversation and hide its transcript from subsequent reads."""
    await service.mutate(conversation_id, "delete")
    return Response(status_code=204)
