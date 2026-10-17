from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
)

from src.application.ports.inference import (
    CompletionResult,
    InferenceFailure,
    InferencePort,
)
from src.infrastructure.repositories.conversation_repository import (
    PostgresConversationRepository,
)
from src.infrastructure.repositories.message_repository import (
    PostgresMessageRepository,
)
from src.infrastructure.repositories.inference_run_repository import (
    PostgresInferenceRunRepository,
)


VALID_PRESETS = {
    "auto", "fast", "balanced", "deep", "unlimited",
}


class ConversationError(Exception):
    def __init__(
        self,
        message: str,
        *,
        code: str,
        status_code: int,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code


@dataclass(frozen=True, slots=True)
class ConversationReply:
    conversation_id: UUID
    user_message_id: UUID
    assistant_message_id: UUID
    inference_run_id: UUID
    content: str
    preset_requested: str
    preset_selected: str
    model_id: str
    cached: bool


@dataclass(frozen=True, slots=True)
class _ReservedRun:
    run_id: UUID
    user_message_id: UUID
    messages: list[dict[str, str]]


class ConversationManager:
    """
    Coordinates persistent conversations and model inference.

    Transaction A:
        Lock conversation.
        Check idempotency.
        Store user message.
        Reserve pending inference.
        Commit.

    Outside transaction:
        Call model gateway.

    Transaction B:
        Store verified assistant message.
        Complete inference run.
        Commit.

    No database transaction is held during inference.
    """

    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        inference: InferencePort,
        max_history_messages: int = 24,
    ) -> None:
        if max_history_messages < 1:
            raise ValueError(
                "max_history_messages must be positive"
            )

        self.session_factory = session_factory
        self.inference = inference
        self.max_history_messages = max_history_messages

    @staticmethod
    def _fingerprint(
        *,
        content: str,
        profile: str,
        preset: str,
        temperature: float,
        max_tokens: int | None,
    ) -> str:
        request = {
            "content": content,
            "profile": profile,
            "preset": preset,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        serialized = json.dumps(
            request,
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        )

        return hashlib.sha256(
            serialized.encode("utf-8")
        ).hexdigest()

    async def _reserve(
        self,
        *,
        conversation_id: UUID,
        content: str,
        request_key: str | None,
        profile: str,
        preset: str,
        temperature: float,
        max_tokens: int | None,
        model_id: str,
    ) -> _ReservedRun | ConversationReply:
        fingerprint = self._fingerprint(
            content=content,
            profile=profile,
            preset=preset,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        async with self.session_factory() as session:
            async with session.begin():
                conversations = PostgresConversationRepository(
                    session
                )
                messages = PostgresMessageRepository(session)
                runs = PostgresInferenceRunRepository(session)

                # Lock BEFORE checking request_key. Concurrent calls
                # for the same conversation must serialize here.
                conversation = await conversations.lock_active(
                    conversation_id
                )

                if conversation is None:
                    raise ConversationError(
                        "Conversation not found or not active.",
                        code="conversation_not_active",
                        status_code=404,
                    )

                if conversation.profile != profile:
                    raise ConversationError(
                        "Requested profile differs from the "
                        "conversation model profile.",
                        code="profile_mismatch",
                        status_code=409,
                    )

                if request_key is not None:
                    existing = await messages.get_by_request_key(
                        conversation_id,
                        request_key,
                    )

                    if existing is not None:
                        stored_fingerprint = (
                            existing.metadata.get(
                                "request_fingerprint"
                            )
                        )

                        if stored_fingerprint != fingerprint:
                            raise ConversationError(
                                "Idempotency key was reused with "
                                "different request parameters.",
                                code="idempotency_conflict",
                                status_code=409,
                            )

                        previous = (
                            await runs.get_by_user_message_id(
                                existing.id
                            )
                        )

                        if previous is None:
                            raise ConversationError(
                                "Existing request has no inference run.",
                                code="inconsistent_request_state",
                                status_code=409,
                            )

                        if (
                            previous.status == "completed"
                            and previous.assistant_message_id
                            is not None
                        ):
                            assistant = await messages.get(
                                previous.assistant_message_id
                            )

                            if assistant is None:
                                raise ConversationError(
                                    "Completed answer is missing.",
                                    code="inconsistent_request_state",
                                    status_code=409,
                                )

                            return ConversationReply(
                                conversation_id=conversation_id,
                                user_message_id=existing.id,
                                assistant_message_id=assistant.id,
                                inference_run_id=previous.id,
                                content=assistant.content,
                                preset_requested=(
                                    previous.preset_requested
                                ),
                                preset_selected=(
                                    previous.preset_selected
                                ),
                                model_id=previous.model_id,
                                cached=True,
                            )

                        # An existing pending/failed/interrupted
                        # request must not invoke the LLM again
                        # under the same idempotency key.
                        raise ConversationError(
                            "This request already exists and "
                            "is not completed.",
                            code="request_already_exists",
                            status_code=409,
                        )

                # Only one inference may be pending per
                # conversation, regardless of request_key.
                pending = await runs.get_pending(
                    conversation_id
                )

                if pending is not None:
                    raise ConversationError(
                        "Another inference is pending for "
                        "this conversation.",
                        code="conversation_busy",
                        status_code=409,
                    )

                user_message = await messages.append(
                    conversation_id=conversation_id,
                    role="user",
                    content=content,
                    request_key=request_key,
                    metadata={
                        "request_fingerprint": fingerprint,
                    },
                )

                # Auto chooses the concrete preset only when
                # LlamaGateway.complete() executes.
                # The existing schema requires a non-null
                # concrete preset while status is pending.
                provisional_preset = (
                    "balanced"
                    if preset == "auto"
                    else preset
                )

                run = await runs.create_pending(
                    conversation_id=conversation_id,
                    user_message_id=user_message.id,
                    preset_requested=preset,
                    preset_selected=provisional_preset,
                    model_id=model_id,
                )

                # Read persisted context and keep the latest
                # complete messages; do not modify DB history.
                history = await messages.list(
                    conversation_id,
                    limit=500,
                )

                if history[-1].id != user_message.id:
                    raise ConversationError(
                        "Conversation history is inconsistent.",
                        code="inconsistent_history",
                        status_code=500,
                    )

                context = [
                    {
                        "role": message.role,
                        "content": message.content,
                    }
                    for message in history
                ]

                # Do not split messages or truncate message text.
                # This is a bounded-history strategy, not an
                # exact token-budget guarantee.
                context = context[
                    -self.max_history_messages:
                ]

                return _ReservedRun(
                    run_id=run.id,
                    user_message_id=user_message.id,
                    messages=context,
                )

    async def _finalize(
        self,
        *,
        conversation_id: UUID,
        reserved: _ReservedRun,
        completion: CompletionResult,
        preset_requested: str,
    ) -> ConversationReply:
        if (
            completion.finish_reason != "stop"
            or not completion.content.strip()
        ):
            raise InferenceFailure(
                "Cannot persist an incomplete model answer.",
                code="incomplete_completion",
            )

        async with self.session_factory() as session:
            async with session.begin():
                messages = PostgresMessageRepository(session)
                runs = PostgresInferenceRunRepository(session)

                pending = await runs.get(
                    reserved.run_id
                )

                if (
                    pending is None
                    or pending.status != "pending"
                    or pending.conversation_id != conversation_id
                ):
                    raise ConversationError(
                        "Inference run is no longer pending.",
                        code="inference_state_conflict",
                        status_code=409,
                    )

                assistant = await messages.append(
                    conversation_id=conversation_id,
                    role="assistant",
                    content=completion.content,
                )

                completed = await runs.complete(
                    reserved.run_id,
                    assistant_message_id=assistant.id,
                    finish_reason=completion.finish_reason,
                    preset_selected=completion.preset_selected,
                    input_tokens=completion.input_tokens,
                    output_tokens=completion.output_tokens,
                    reasoning_tokens=(
                        completion.reasoning_tokens
                    ),
                    latency_ms=completion.latency_ms,
                )

                if completed is None:
                    raise ConversationError(
                        "Failed to complete inference run.",
                        code="inference_state_conflict",
                        status_code=409,
                    )

                return ConversationReply(
                    conversation_id=conversation_id,
                    user_message_id=reserved.user_message_id,
                    assistant_message_id=assistant.id,
                    inference_run_id=reserved.run_id,
                    content=assistant.content,
                    preset_requested=preset_requested,
                    preset_selected=completed.preset_selected,
                    model_id=completed.model_id,
                    cached=False,
                )

    async def _mark_failed(
        self,
        *,
        run_id: UUID,
        code: str,
    ) -> None:
        async with self.session_factory() as session:
            async with session.begin():
                runs = PostgresInferenceRunRepository(session)
                await runs.fail(
                    run_id,
                    error_code=code,
                )

    async def send_message(
        self,
        *,
        conversation_id: UUID,
        content: str,
        profile: str,
        preset: str,
        model_id: str,
        request_key: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> ConversationReply:
        if not content or not content.strip():
            raise ConversationError(
                "Message content must not be empty.",
                code="invalid_content",
                status_code=422,
            )

        if profile not in {"core", "unrestricted"}:
            raise ConversationError(
                "Invalid model profile.",
                code="invalid_profile",
                status_code=422,
            )

        if preset not in VALID_PRESETS:
            raise ConversationError(
                "Invalid runtime preset.",
                code="invalid_preset",
                status_code=422,
            )

        if not model_id or len(model_id) > 200:
            raise ConversationError(
                "Invalid model ID.",
                code="invalid_model",
                status_code=422,
            )

        if request_key is not None and (
            not request_key or len(request_key) > 128
        ):
            raise ConversationError(
                "request_key must be 1–128 characters.",
                code="invalid_request_key",
                status_code=422,
            )

        if not 0 <= temperature <= 2:
            raise ConversationError(
                "temperature must be between 0 and 2.",
                code="invalid_temperature",
                status_code=422,
            )

        if max_tokens is not None and not (
            1 <= max_tokens <= 32768
        ):
            raise ConversationError(
                "max_tokens must be between 1 and 32768.",
                code="invalid_max_tokens",
                status_code=422,
            )

        reserved = await self._reserve(
            conversation_id=conversation_id,
            content=content,
            request_key=request_key,
            profile=profile,
            preset=preset,
            temperature=temperature,
            max_tokens=max_tokens,
            model_id=model_id,
        )

        if isinstance(reserved, ConversationReply):
            return reserved

        try:
            completion = await self.inference.complete(
                profile=profile,
                messages=reserved.messages,
                preset=preset,
                temperature=temperature,
                max_tokens=max_tokens,
            )

            # The adapter and persisted pending run must refer
            # to the same loaded model.
            if completion.model_id != model_id:
                raise InferenceFailure(
                    "Model changed during inference.",
                    code="model_mismatch",
                )

            if (
                completion.preset_selected not in {
                    "fast", "balanced", "deep", "unlimited"
                }
                or (
                    preset != "auto"
                    and completion.preset_selected != preset
                )
            ):
                raise InferenceFailure(
                    "Invalid preset selected by inference.",
                    code="preset_mismatch",
                )

            return await self._finalize(
                conversation_id=conversation_id,
                reserved=reserved,
                completion=completion,
                preset_requested=preset,
            )

        except Exception as exc:
            # Inference failures must not leave a reusable
            # pending reservation where possible.
            code = (
                exc.code
                if isinstance(exc, InferenceFailure)
                else "conversation_processing_error"
            )

            # A separate transaction is required because the
            # original reservation is already committed.
            try:
                await self._mark_failed(
                    run_id=reserved.run_id,
                    code=code,
                )
            except Exception:
                # Preserve the original exception. If recovery
                # fails, the run may remain pending; automated
                # crash recovery belongs to the next hardening
                # phase, not to this happy-path test.
                pass

            raise
