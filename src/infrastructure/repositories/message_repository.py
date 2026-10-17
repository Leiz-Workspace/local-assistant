from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.entities.message import Message
from src.infrastructure.models.conversation_model import ConversationModel
from src.infrastructure.models.message_model import MessageModel


class PostgresMessageRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def append(
        self,
        *,
        conversation_id: UUID,
        role: str,
        content: str,
        request_key: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Message:
        if role not in {"system", "user", "assistant"}:
            raise ValueError(f"Unsupported message role: {role}")

        # Serialize sequence allocation within a conversation.
        # Every writer must follow this locking convention.
        conversation = await self.session.scalar(
            select(ConversationModel)
            .where(
                ConversationModel.id == conversation_id,
                ConversationModel.deleted_at.is_(None),
                ConversationModel.status == "active",
            )
            .with_for_update()
        )

        if conversation is None:
            raise ValueError(
                "Conversation does not exist or is not active"
            )

        next_sequence = await self.session.scalar(
            select(
                func.coalesce(
                    func.max(MessageModel.sequence),
                    0,
                ) + 1
            ).where(
                MessageModel.conversation_id == conversation_id
            )
        )

        model = MessageModel(
            conversation_id=conversation_id,
            sequence=int(next_sequence),
            role=role,
            content=content,
            request_key=request_key,
            metadata_=metadata or {},
        )

        self.session.add(model)

        conversation.updated_at = datetime.now(timezone.utc)

        await self.session.flush()
        await self.session.refresh(model)

        return model.to_entity()

    async def get(
        self,
        message_id: UUID,
    ) -> Message | None:
        model = await self.session.get(
            MessageModel,
            message_id,
        )

        return model.to_entity() if model else None

    async def get_by_request_key(
        self,
        conversation_id: UUID,
        request_key: str,
    ) -> Message | None:
        model = await self.session.scalar(
            select(MessageModel).where(
                MessageModel.conversation_id == conversation_id,
                MessageModel.request_key == request_key,
            )
        )

        return model.to_entity() if model else None

    async def list(
        self,
        conversation_id: UUID,
        *,
        limit: int = 100,
        after_sequence: int = 0,
    ) -> list[Message]:
        if not 1 <= limit <= 500:
            raise ValueError("limit must be between 1 and 500")

        if after_sequence < 0:
            raise ValueError(
                "after_sequence must be non-negative"
            )

        stmt = (
            select(MessageModel)
            .where(
                MessageModel.conversation_id == conversation_id,
                MessageModel.sequence > after_sequence,
            )
            .order_by(MessageModel.sequence.asc())
            .limit(limit)
        )

        result = await self.session.scalars(stmt)

        return [model.to_entity() for model in result.all()]
