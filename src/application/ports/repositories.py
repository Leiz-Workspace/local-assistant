from __future__ import annotations

from typing import Any, Protocol
from uuid import UUID

from src.domain.entities.conversation import Conversation
from src.domain.entities.message import Message
from src.domain.entities.inference_run import InferenceRun


class ConversationRepositoryPort(Protocol):
    async def create(
        self,
        *,
        title: str | None = None,
        profile: str = "core",
        preset_default: str = "balanced",
        metadata: dict[str, Any] | None = None,
    ) -> Conversation:
        ...

    async def get(
        self,
        conversation_id: UUID,
        *,
        include_deleted: bool = False,
    ) -> Conversation | None:
        ...

    async def lock_active(
        self,
        conversation_id: UUID,
    ) -> Conversation | None:
        ...

    async def list(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        include_archived: bool = False,
    ) -> list[Conversation]:
        ...

    async def update(
        self,
        conversation_id: UUID,
        *,
        title: str | None = None,
        preset_default: str | None = None,
    ) -> Conversation | None:
        ...

    async def archive(
        self,
        conversation_id: UUID,
    ) -> Conversation | None:
        ...

    async def soft_delete(
        self,
        conversation_id: UUID,
    ) -> bool:
        ...


class MessageRepositoryPort(Protocol):
    async def append(
        self,
        *,
        conversation_id: UUID,
        role: str,
        content: str,
        request_key: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Message:
        ...

    async def get(
        self,
        message_id: UUID,
    ) -> Message | None:
        ...

    async def get_by_request_key(
        self,
        conversation_id: UUID,
        request_key: str,
    ) -> Message | None:
        ...

    async def list(
        self,
        conversation_id: UUID,
        *,
        limit: int = 100,
        after_sequence: int = 0,
    ) -> list[Message]:
        ...


class InferenceRunRepositoryPort(Protocol):
    async def create_pending(
        self,
        *,
        conversation_id: UUID,
        user_message_id: UUID,
        preset_requested: str,
        preset_selected: str,
        model_id: str,
    ) -> InferenceRun:
        ...

    async def get(
        self,
        run_id: UUID,
    ) -> InferenceRun | None:
        ...

    async def get_pending(
        self,
        conversation_id: UUID,
    ) -> InferenceRun | None:
        ...

    async def get_by_user_message_id(
        self,
        user_message_id: UUID,
    ) -> InferenceRun | None:
        ...

    async def complete(
        self,
        run_id: UUID,
        *,
        assistant_message_id: UUID,
        finish_reason: str,
        preset_selected: str | None = None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        reasoning_tokens: int | None = None,
        latency_ms: int | None = None,
    ) -> InferenceRun | None:
        ...

    async def fail(
        self,
        run_id: UUID,
        *,
        error_code: str,
    ) -> InferenceRun | None:
        ...
