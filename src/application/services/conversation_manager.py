"""Coordinate leased, transactional conversation inference and safe replay."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from dataclasses import dataclass
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
)

from src.application.ports.inference import (
    CompletionResult,
    InferenceFailure,
    InferencePort,
)
from src.application.services.conversation_context import select_whole_turns
from src.infrastructure.repositories.conversation_repository import (
    PostgresConversationRepository,
)
from src.infrastructure.repositories.inference_run_repository import (
    PostgresInferenceRunRepository,
)
from src.infrastructure.repositories.message_repository import (
    PostgresMessageRepository,
)

logger = logging.getLogger(__name__)

VALID_PRESETS = {
    "auto",
    "fast",
    "balanced",
    "deep",
    "unlimited",
}


class ConversationError(Exception):
    """Carry stable application error codes and HTTP status semantics."""

    def __init__(
        self,
        message: str,
        *,
        code: str,
        status_code: int,
    ) -> None:
        """Attach the safe application code and status to an operation failure."""
        super().__init__(message)
        self.code = code
        self.status_code = status_code


@dataclass(frozen=True, slots=True)
class ConversationReply:
    """Return persisted message identities, selected runtime and replay status."""

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
    """Carry the committed reservation and selected model context."""

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
        lease_seconds: float = 120,
        heartbeat_seconds: float = 30,
        principal_id: UUID | None = None,
    ) -> None:
        """Initialize the configured dependencies and execution limits."""
        if max_history_messages < 1:
            raise ValueError("max_history_messages must be positive")

        if not 0 < heartbeat_seconds < lease_seconds:
            raise ValueError(
                "heartbeat_seconds must be positive and shorter than lease_seconds"
            )
        self.principal_id = principal_id
        self.owner_id = str(uuid4())
        self.lease_seconds = lease_seconds
        self.heartbeat_seconds = heartbeat_seconds
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
        """Hash all generation-affecting parameters for deterministic request replay."""
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

        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

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
        """Lock the conversation and atomically reserve a leased user inference."""
        fingerprint = self._fingerprint(
            content=content,
            profile=profile,
            preset=preset,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        async with self.session_factory() as session:
            async with session.begin():
                conversations = PostgresConversationRepository(session)
                messages = PostgresMessageRepository(session)
                runs = PostgresInferenceRunRepository(session)

                # Lock BEFORE checking request_key. Concurrent calls
                # for the same conversation must serialize here.
                conversation = await conversations.lock_active(
                    conversation_id, **self._principal_scope()
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
                        stored_fingerprint = existing.metadata.get(
                            "request_fingerprint"
                        )

                        if stored_fingerprint != fingerprint:
                            raise ConversationError(
                                "Idempotency key was reused with "
                                "different request parameters.",
                                code="idempotency_conflict",
                                status_code=409,
                            )

                        previous = await runs.get_by_user_message_id(existing.id)

                        if previous is None:
                            raise ConversationError(
                                "Existing request has no inference run.",
                                code="inconsistent_request_state",
                                status_code=409,
                            )

                        if (
                            previous.status == "completed"
                            and previous.assistant_message_id is not None
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
                                preset_requested=(previous.preset_requested),
                                preset_selected=(previous.preset_selected),
                                model_id=previous.model_id,
                                cached=True,
                            )

                        # An existing pending/failed/interrupted
                        # request must not invoke the LLM again
                        # under the same idempotency key.
                        raise ConversationError(
                            "This request already exists and is not completed.",
                            code="request_already_exists",
                            status_code=409,
                        )

                # Only one inference may be pending per
                # conversation, regardless of request_key.
                pending = await runs.get_pending(conversation_id)

                if pending is not None:
                    raise ConversationError(
                        "Another inference is pending for this conversation.",
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
                provisional_preset = "balanced" if preset == "auto" else preset

                run = await runs.create_pending(
                    conversation_id=conversation_id,
                    user_message_id=user_message.id,
                    preset_requested=preset,
                    preset_selected=provisional_preset,
                    model_id=model_id,
                )

                await runs.claim_lease(run.id, self.owner_id, self.lease_seconds)
                history = await messages.list_for_context(
                    conversation_id,
                    limit=self.max_history_messages,
                )
                if not history or history[-1].id != user_message.id:
                    raise ConversationError(
                        "Conversation history is inconsistent.",
                        code="inconsistent_history",
                        status_code=500,
                    )
                context = select_whole_turns(
                    [
                        {"role": message.role, "content": message.content}
                        for message in history
                    ],
                    self.max_history_messages,
                )
                logger.info(
                    "conversation_run_reserved conversation_id=%s run_id=%s",
                    conversation_id,
                    run.id,
                )

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
        """Fence ownership and atomically persist the verified assistant response."""
        if completion.finish_reason != "stop" or not completion.content.strip():
            raise InferenceFailure(
                "Cannot persist an incomplete model answer.",
                code="incomplete_completion",
            )

        async with self.session_factory() as session:
            async with session.begin():
                messages = PostgresMessageRepository(session)
                runs = PostgresInferenceRunRepository(session)

                conversations = PostgresConversationRepository(session)
                conversation = await conversations.lock_active(
                    conversation_id, **self._principal_scope()
                )
                if conversation is None or not await runs.require_live_lease(
                    reserved.run_id, self.owner_id
                ):
                    raise ConversationError(
                        "Inference ownership or conversation state changed.",
                        code="inference_state_conflict",
                        status_code=409,
                    )
                pending = await runs.get(reserved.run_id)

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
                    reasoning_tokens=(completion.reasoning_tokens),
                    latency_ms=completion.latency_ms,
                )

                if completed is None:
                    raise ConversationError(
                        "Failed to complete inference run.",
                        code="inference_state_conflict",
                        status_code=409,
                    )

                logger.info(
                    "conversation_run_completed conversation_id=%s run_id=%s",
                    conversation_id,
                    reserved.run_id,
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
        """Record a failed inference using an independent committed transaction."""
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
        """Validate, reserve, infer and finalize one idempotent conversation turn."""
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

        if request_key is not None and (not request_key or len(request_key) > 128):
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

        if max_tokens is not None and not (1 <= max_tokens <= 32768):
            raise ConversationError(
                "max_tokens must be between 1 and 32768.",
                code="invalid_max_tokens",
                status_code=422,
            )

        await self.recover_expired(conversation_id)
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
            completion = await self._run_inference(
                reserved.run_id,
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

            if completion.preset_selected not in {
                "fast",
                "balanced",
                "deep",
                "unlimited",
            } or (preset != "auto" and completion.preset_selected != preset):
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

        except asyncio.CancelledError:
            logger.warning("conversation_request_cancelled run_id=%s", reserved.run_id)
            try:
                await asyncio.shield(
                    self._interrupt(reserved.run_id, "request_cancelled")
                )
            except Exception:
                logger.error(
                    "conversation_interruption_persistence_failed run_id=%s",
                    reserved.run_id,
                )
            raise
        except Exception as exc:
            logger.warning(
                "conversation_run_failed run_id=%s type=%s",
                reserved.run_id,
                type(exc).__name__,
            )
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
                logger.error(
                    "conversation_failure_persistence_failed run_id=%s", reserved.run_id
                )
                # Preserve the original error; the committed lease enables later recovery.

            raise

    async def recover_expired(self, conversation_id: UUID) -> bool:
        """Commit safe expiry recovery separately so a replay conflict cannot undo it."""
        async with self.session_factory() as session, session.begin():
            conversations = PostgresConversationRepository(session)
            if (
                await conversations.lock_active(
                    conversation_id, **self._principal_scope()
                )
                is None
            ):
                return False
            return await PostgresInferenceRunRepository(session).expire_pending(
                conversation_id
            )

    async def _interrupt(self, run_id: UUID, code: str) -> None:
        """Mark a cancelled owned reservation interrupted in a separate transaction."""
        async with self.session_factory() as session, session.begin():
            await PostgresInferenceRunRepository(session).interrupt(
                run_id, error_code=code
            )

    async def _heartbeat(self, run_id: UUID) -> None:
        """Renew the run lease using short independent transactions during inference."""
        while True:
            await asyncio.sleep(self.heartbeat_seconds)
            async with self.session_factory() as session, session.begin():
                valid = await PostgresInferenceRunRepository(session).renew_lease(
                    run_id,
                    self.owner_id,
                    self.lease_seconds,
                )
            if not valid:
                raise InferenceFailure(
                    "Inference lease lost.", code="lease_lost", status_code=503
                )

    async def _run_inference(self, run_id: UUID, **parameters) -> CompletionResult:
        """Stop inference on heartbeat loss and always await cancellation of child tasks."""
        heartbeat = asyncio.create_task(self._heartbeat(run_id))
        inference = asyncio.create_task(self.inference.complete(**parameters))
        try:
            done, _ = await asyncio.wait(
                {heartbeat, inference}, return_when=asyncio.FIRST_COMPLETED
            )
            if heartbeat in done:
                try:
                    heartbeat.result()
                except Exception as error:
                    raise InferenceFailure(
                        "Inference lease could not be renewed.",
                        code="lease_lost",
                        status_code=503,
                    ) from error
            return await inference
        finally:
            for task in (heartbeat, inference):
                if not task.done():
                    task.cancel()
            await asyncio.gather(heartbeat, inference, return_exceptions=True)

    def _principal_scope(self) -> dict:
        """Keep conversation authorization separate from inference lease ownership."""
        return {} if self.principal_id is None else {"owner_id": self.principal_id}
