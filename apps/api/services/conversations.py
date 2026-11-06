"""Compose persistent conversation operations using the existing PostgreSQL layer."""

import logging
from uuid import UUID

from apps.api.core.model_config import get_model_profile
from src.application.services.conversation_manager import (
    ConversationError,
    ConversationManager,
)
from src.infrastructure.inference.llama_adapter import LlamaInferenceAdapter
from src.infrastructure.repositories.conversation_repository import (
    PostgresConversationRepository,
)
from src.infrastructure.repositories.inference_run_repository import (
    PostgresInferenceRunRepository,
)
from src.infrastructure.repositories.message_repository import PostgresMessageRepository

logger = logging.getLogger(__name__)


class ConversationService:
    """Expose transactional CRUD and delegate persistent inference to the manager."""

    def __init__(
        self, session_factory, inference=None, *, principal_id: UUID | None = None
    ):
        """Retain the application pool and compose the established inference manager."""
        self.principal_id = principal_id
        self.session_factory = session_factory
        self.manager = ConversationManager(
            session_factory=session_factory,
            principal_id=principal_id,
            inference=inference if inference is not None else LlamaInferenceAdapter(),
        )

    @staticmethod
    def require_conversation(conversation):
        """Map missing or deleted records to a stable application error."""
        if conversation is None:
            raise ConversationError(
                "Conversation not found.",
                code="conversation_not_found",
                status_code=404,
            )
        return conversation

    async def create(self, **values):
        """Commit a new conversation without invoking inference."""
        async with self.session_factory() as session, session.begin():
            result = await PostgresConversationRepository(session).create(
                **values, **self._scope()
            )
        logger.info("conversation_created conversation_id=%s", result.id)
        return result

    async def list(self, **pagination):
        """List visible conversations using the repository archive policy."""
        async with self.session_factory() as session, session.begin():
            result = await PostgresConversationRepository(session).list(
                **pagination, **self._scope()
            )
        logger.info("conversations_listed count=%d", len(result))
        return result

    async def get(self, conversation_id: UUID):
        """Read a conversation while hiding soft-deleted records."""
        async with self.session_factory() as session, session.begin():
            result = self.require_conversation(
                await PostgresConversationRepository(session).get(
                    conversation_id, **self._scope()
                )
            )
        logger.info("conversation_read conversation_id=%s", conversation_id)
        return result

    async def history(self, conversation_id: UUID, **pagination):
        """Return sequence-ordered history only for a visible conversation."""
        async with self.session_factory() as session, session.begin():
            self.require_conversation(
                await PostgresConversationRepository(session).get(
                    conversation_id, **self._scope()
                )
            )
            result = await PostgresMessageRepository(session).list(
                conversation_id, **pagination
            )
        logger.info(
            "conversation_history_read conversation_id=%s count=%d",
            conversation_id,
            len(result),
        )
        return result

    async def mutate(self, conversation_id: UUID, action: str, **values):
        """Serialize lifecycle mutations against inference reservation and reject busy runs."""
        async with self.session_factory() as session, session.begin():
            repository = PostgresConversationRepository(session)
            conversation = self.require_conversation(
                await repository.get(conversation_id, **self._scope())
            )
            if conversation.status == "active":
                self.require_conversation(
                    await repository.lock_active(conversation_id, **self._scope())
                )
            if await PostgresInferenceRunRepository(session).get_pending(
                conversation_id
            ):
                raise ConversationError(
                    "Another inference is pending for this conversation.",
                    code="conversation_busy",
                    status_code=409,
                )
            if action == "update":
                result = self.require_conversation(
                    await repository.update(conversation_id, **values, **self._scope())
                )
            elif action == "archive":
                result = self.require_conversation(
                    await repository.archive(conversation_id, **self._scope())
                )
            elif action == "delete":
                result = await repository.soft_delete(conversation_id, **self._scope())
                if not result:
                    self.require_conversation(None)
            else:
                raise ValueError("Unsupported conversation mutation")
        logger.info(
            "conversation_mutated conversation_id=%s action=%s", conversation_id, action
        )
        return result

    async def send(self, conversation_id: UUID, **values):
        """Resolve stored profile and default preset before invoking persistent chat."""
        conversation = await self.get(conversation_id)
        config = get_model_profile(conversation.profile)
        values["preset"] = values.get("preset") or conversation.preset_default
        logger.info("conversation_send_started conversation_id=%s", conversation_id)
        result = await self.manager.send_message(
            conversation_id=conversation_id,
            profile=conversation.profile,
            model_id=config["model_id"],
            **values,
        )
        logger.info(
            "conversation_send_completed conversation_id=%s run_id=%s cached=%s",
            conversation_id,
            result.inference_run_id,
            result.cached,
        )
        return result

    def _scope(self) -> dict:
        """Pass authenticated ownership into every conversation repository operation."""
        return {} if self.principal_id is None else {"owner_id": self.principal_id}

    def for_owner(self, principal_id: UUID):
        """Bind a fresh request-scoped service to an authenticated principal."""
        return ConversationService(
            self.session_factory, self.manager.inference, principal_id=principal_id
        )
