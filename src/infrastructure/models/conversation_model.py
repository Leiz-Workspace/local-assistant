"""Map persistent conversation records to domain entities."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import DateTime, Index, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from src.domain.entities.conversation import Conversation
from src.infrastructure.models.base import Base


class ConversationModel(Base):
    """Map persistent conversation records to domain entities."""

    __tablename__ = "conversations"
    __table_args__ = (
        Index(
            "ix_conversations_status_updated_at",
            "status",
            "updated_at",
        ),
        Index(
            "ix_conversations_deleted_at",
            "deleted_at",
        ),
        {"schema": "assistant"},
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )

    title: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
    )

    profile: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        server_default="core",
    )

    preset_default: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        server_default="balanced",
    )

    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default="active",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.current_timestamp(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.current_timestamp(),
    )

    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )

    def to_entity(self) -> Conversation:
        """Convert persisted columns without exposing ORM state."""
        return Conversation(
            id=self.id,
            title=self.title,
            profile=self.profile,
            preset_default=self.preset_default,
            status=self.status,
            created_at=self.created_at,
            updated_at=self.updated_at,
            deleted_at=self.deleted_at,
            metadata=dict(self.metadata_),
        )
