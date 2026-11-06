"""Map inference lifecycle records to domain entities."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from src.domain.entities.inference_run import InferenceRun
from src.infrastructure.models.base import Base


class InferenceRunModel(Base):
    """Map inference lifecycle records to domain entities."""

    __tablename__ = "inference_runs"
    __table_args__ = (
        Index(
            "ix_inference_runs_conversation_started_at",
            "conversation_id",
            "started_at",
        ),
        Index(
            "ix_inference_runs_user_message_id",
            "user_message_id",
        ),
        Index(
            "ix_inference_runs_assistant_message_id",
            "assistant_message_id",
        ),
        Index(
            "uq_inference_runs_one_pending_per_conversation",
            "conversation_id",
            unique=True,
            postgresql_where=text("status = 'pending'"),
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

    user_message_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "assistant.messages.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )

    assistant_message_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "assistant.messages.id",
            ondelete="RESTRICT",
        ),
        nullable=True,
    )

    preset_requested: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )

    preset_selected: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )

    model_id: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default="pending",
    )

    input_tokens: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    output_tokens: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    reasoning_tokens: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    latency_ms: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    finish_reason: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )

    error_code: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.current_timestamp(),
    )

    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )

    def to_entity(self) -> InferenceRun:
        """Convert persisted columns without exposing ORM state."""
        return InferenceRun(
            id=self.id,
            conversation_id=self.conversation_id,
            user_message_id=self.user_message_id,
            assistant_message_id=self.assistant_message_id,
            preset_requested=self.preset_requested,
            preset_selected=self.preset_selected,
            model_id=self.model_id,
            status=self.status,
            started_at=self.started_at,
            completed_at=self.completed_at,
            input_tokens=self.input_tokens,
            output_tokens=self.output_tokens,
            reasoning_tokens=self.reasoning_tokens,
            latency_ms=self.latency_ms,
            finish_reason=self.finish_reason,
            error_code=self.error_code,
            metadata=dict(self.metadata_),
        )
