"""Map ordered transcript records to domain entities."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from src.domain.entities.message import Message
from src.infrastructure.models.base import Base


class MessageModel(Base):
    """Map ordered transcript records to domain entities."""

    __tablename__ = "messages"
    __table_args__ = (
        UniqueConstraint(
            "conversation_id",
            "sequence",
            name="uq_messages_conversation_sequence",
        ),
        UniqueConstraint(
            "conversation_id",
            "request_key",
            name="uq_messages_conversation_request_key",
        ),
        Index(
            "ix_messages_conversation_created_at",
            "conversation_id",
            "created_at",
        ),
        {"schema": "assistant"},
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )

    conversation_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "assistant.conversations.id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )

    sequence: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )

    role: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
    )

    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    request_key: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.current_timestamp(),
    )

    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )

    def to_entity(self) -> Message:
        """Convert persisted columns without exposing ORM state."""
        return Message(
            id=self.id,
            conversation_id=self.conversation_id,
            sequence=self.sequence,
            role=self.role,
            content=self.content,
            request_key=self.request_key,
            created_at=self.created_at,
            metadata=dict(self.metadata_),
        )
