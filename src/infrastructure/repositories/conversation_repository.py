"""Persist conversations with optional authenticated ownership filters and lifecycle locking."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select, true
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.entities.conversation import Conversation
from src.infrastructure.models.conversation_model import ConversationModel


class PostgresConversationRepository:
    """Persist owner-scoped conversation records in caller-owned transactions."""

    def __init__(self, session: AsyncSession) -> None:
        """Retain the caller-owned transaction session."""
        self.session = session

    async def create(
        self,
        *,
        title: str | None = None,
        profile: str = "core",
        preset_default: str = "balanced",
        metadata: dict[str, Any] | None = None,
        owner_id: UUID | None = None,
    ) -> Conversation:
        """Create a conversation and assign server-controlled ownership when supplied."""
        model = ConversationModel(
            title=title,
            profile=profile,
            preset_default=preset_default,
            status="active",
            metadata_={
                **(metadata or {}),
                **({"owner_id": str(owner_id)} if owner_id is not None else {}),
            },
        )
        self.session.add(model)
        await self.session.flush()
        await self.session.refresh(model)
        return model.to_entity()

    async def get(
        self,
        conversation_id: UUID,
        *,
        include_deleted: bool = False,
        owner_id: UUID | None = None,
    ) -> Conversation | None:
        """Read a visible conversation constrained to the requested owner."""
        stmt = select(ConversationModel).where(
            ConversationModel.id == conversation_id, self._owner_filter(owner_id)
        )

        if not include_deleted:
            stmt = stmt.where(
                ConversationModel.deleted_at.is_(None), self._owner_filter(owner_id)
            )

        model = await self.session.scalar(stmt)
        return model.to_entity() if model else None

    async def lock_active(
        self,
        conversation_id: UUID,
        *,
        owner_id: UUID | None = None,
    ) -> Conversation | None:
        """
        Lock an active conversation until the caller commits.

        Used to serialize request-key lookup, message append,
        and pending inference reservation.
        """
        model = await self.session.scalar(
            select(ConversationModel)
            .where(
                ConversationModel.id == conversation_id,
                self._owner_filter(owner_id),
                ConversationModel.status == "active",
                ConversationModel.deleted_at.is_(None),
            )
            .with_for_update()
        )
        return model.to_entity() if model else None

    async def list(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        include_archived: bool = False,
        owner_id: UUID | None = None,
    ) -> list[Conversation]:
        """List bounded visible conversations scoped to the requested owner."""
        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")

        if offset < 0:
            raise ValueError("offset must be non-negative")

        stmt = select(ConversationModel).where(
            ConversationModel.deleted_at.is_(None), self._owner_filter(owner_id)
        )

        if not include_archived:
            stmt = stmt.where(ConversationModel.status == "active")

        stmt = (
            stmt.order_by(
                ConversationModel.updated_at.desc(),
                ConversationModel.id.desc(),
            )
            .limit(limit)
            .offset(offset)
        )

        result = await self.session.scalars(stmt)
        return [model.to_entity() for model in result.all()]

    async def update(
        self,
        conversation_id: UUID,
        *,
        title: str | None = None,
        preset_default: str | None = None,
        owner_id: UUID | None = None,
    ) -> Conversation | None:
        """Lock and update an active conversation owned by the caller."""
        model = await self.session.scalar(
            select(ConversationModel)
            .where(
                ConversationModel.id == conversation_id,
                self._owner_filter(owner_id),
                ConversationModel.deleted_at.is_(None),
                ConversationModel.status == "active",
            )
            .with_for_update()
        )

        if model is None:
            return None

        if title is not None:
            model.title = title

        if preset_default is not None:
            model.preset_default = preset_default

        model.updated_at = datetime.now(timezone.utc)
        await self.session.flush()
        return model.to_entity()

    async def archive(
        self,
        conversation_id: UUID,
        *,
        owner_id: UUID | None = None,
    ) -> Conversation | None:
        """Lock and archive a visible conversation owned by the caller."""
        model = await self.session.scalar(
            select(ConversationModel)
            .where(
                ConversationModel.id == conversation_id,
                self._owner_filter(owner_id),
                ConversationModel.deleted_at.is_(None),
            )
            .with_for_update()
        )

        if model is None:
            return None

        model.status = "archived"
        model.updated_at = datetime.now(timezone.utc)
        await self.session.flush()
        return model.to_entity()

    async def soft_delete(
        self,
        conversation_id: UUID,
        *,
        owner_id: UUID | None = None,
    ) -> bool:
        """Lock and hide a visible conversation owned by the caller."""
        model = await self.session.scalar(
            select(ConversationModel)
            .where(
                ConversationModel.id == conversation_id,
                self._owner_filter(owner_id),
                ConversationModel.deleted_at.is_(None),
            )
            .with_for_update()
        )

        if model is None:
            return False

        now = datetime.now(timezone.utc)
        model.deleted_at = now
        model.updated_at = now

        await self.session.flush()
        return True

    @staticmethod
    def _owner_filter(owner_id: UUID | None):
        """Constrain end-user access while allowing explicit trusted maintenance callers."""
        return (
            true()
            if owner_id is None
            else ConversationModel.metadata_["owner_id"].astext == str(owner_id)
        )
