"""Initial conversation persistence schema.

Revision ID: 0001
Revises:
Create Date: 2026-10-16
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


SCHEMA = "assistant"
APP_ROLE = "local_assistant_app"


def upgrade() -> None:
    # ------------------------------------------------------
    # 1. Conversations
    # ------------------------------------------------------

    op.create_table(
        "conversations",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "title",
            sa.String(length=200),
            nullable=True,
        ),
        sa.Column(
            "profile",
            sa.String(length=32),
            nullable=False,
            server_default="core",
        ),
        sa.Column(
            "preset_default",
            sa.String(length=32),
            nullable=False,
            server_default="balanced",
        ),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default="active",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "deleted_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "metadata",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.CheckConstraint(
            "profile IN ('core', 'unrestricted')",
            name="ck_conversations_profile",
        ),
        sa.CheckConstraint(
            "preset_default IN "
            "('auto', 'fast', 'balanced', 'deep', 'unlimited')",
            name="ck_conversations_preset",
        ),
        sa.CheckConstraint(
            "status IN ('active', 'archived')",
            name="ck_conversations_status",
        ),
        schema=SCHEMA,
    )

    op.create_index(
        "ix_conversations_status_updated_at",
        "conversations",
        ["status", "updated_at"],
        schema=SCHEMA,
    )

    op.create_index(
        "ix_conversations_deleted_at",
        "conversations",
        ["deleted_at"],
        schema=SCHEMA,
    )

    # ------------------------------------------------------
    # 2. Messages
    # ------------------------------------------------------

    op.create_table(
        "messages",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "conversation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "assistant.conversations.id",
                ondelete="CASCADE",
            ),
            nullable=False,
        ),
        sa.Column(
            "sequence",
            sa.BigInteger(),
            nullable=False,
        ),
        sa.Column(
            "role",
            sa.String(length=16),
            nullable=False,
        ),
        sa.Column(
            "content",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "request_key",
            sa.String(length=128),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "metadata",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.UniqueConstraint(
            "conversation_id",
            "sequence",
            name="uq_messages_conversation_sequence",
        ),
        sa.UniqueConstraint(
            "conversation_id",
            "request_key",
            name="uq_messages_conversation_request_key",
        ),
        sa.CheckConstraint(
            "role IN ('system', 'user', 'assistant')",
            name="ck_messages_role",
        ),
        sa.CheckConstraint(
            "sequence >= 1",
            name="ck_messages_sequence",
        ),
        schema=SCHEMA,
    )

    op.create_index(
        "ix_messages_conversation_created_at",
        "messages",
        ["conversation_id", "created_at"],
        schema=SCHEMA,
    )

    # ------------------------------------------------------
    # 3. Inference runs
    # ------------------------------------------------------

    op.create_table(
        "inference_runs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "conversation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "assistant.conversations.id",
                ondelete="CASCADE",
            ),
            nullable=False,
        ),
        sa.Column(
            "user_message_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "assistant.messages.id",
                ondelete="RESTRICT",
            ),
            nullable=False,
        ),
        sa.Column(
            "assistant_message_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "assistant.messages.id",
                ondelete="RESTRICT",
            ),
            nullable=True,
        ),
        sa.Column(
            "preset_requested",
            sa.String(length=32),
            nullable=False,
        ),
        sa.Column(
            "preset_selected",
            sa.String(length=32),
            nullable=False,
        ),
        sa.Column(
            "model_id",
            sa.String(length=200),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default="pending",
        ),
        sa.Column(
            "input_tokens",
            sa.Integer(),
            nullable=True,
        ),
        sa.Column(
            "output_tokens",
            sa.Integer(),
            nullable=True,
        ),
        sa.Column(
            "reasoning_tokens",
            sa.Integer(),
            nullable=True,
        ),
        sa.Column(
            "latency_ms",
            sa.Integer(),
            nullable=True,
        ),
        sa.Column(
            "finish_reason",
            sa.String(length=64),
            nullable=True,
        ),
        sa.Column(
            "error_code",
            sa.String(length=100),
            nullable=True,
        ),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "completed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "metadata",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.CheckConstraint(
            "preset_requested IN "
            "('auto', 'fast', 'balanced', 'deep', 'unlimited')",
            name="ck_inference_runs_preset_requested",
        ),
        sa.CheckConstraint(
            "preset_selected IN "
            "('fast', 'balanced', 'deep', 'unlimited')",
            name="ck_inference_runs_preset_selected",
        ),
        sa.CheckConstraint(
            "status IN "
            "('pending', 'completed', 'failed', 'interrupted')",
            name="ck_inference_runs_status",
        ),
        sa.CheckConstraint(
            "input_tokens IS NULL OR input_tokens >= 0",
            name="ck_inference_runs_input_tokens",
        ),
        sa.CheckConstraint(
            "output_tokens IS NULL OR output_tokens >= 0",
            name="ck_inference_runs_output_tokens",
        ),
        sa.CheckConstraint(
            "reasoning_tokens IS NULL OR reasoning_tokens >= 0",
            name="ck_inference_runs_reasoning_tokens",
        ),
        sa.CheckConstraint(
            "latency_ms IS NULL OR latency_ms >= 0",
            name="ck_inference_runs_latency",
        ),
        schema=SCHEMA,
    )

    op.create_index(
        "ix_inference_runs_conversation_started_at",
        "inference_runs",
        ["conversation_id", "started_at"],
        schema=SCHEMA,
    )

    op.create_index(
        "ix_inference_runs_user_message_id",
        "inference_runs",
        ["user_message_id"],
        schema=SCHEMA,
    )

    op.create_index(
        "ix_inference_runs_assistant_message_id",
        "inference_runs",
        ["assistant_message_id"],
        schema=SCHEMA,
    )

    # Only one pending inference per conversation.
    # Application transactions must still handle contention.
    op.create_index(
        "uq_inference_runs_one_pending_per_conversation",
        "inference_runs",
        ["conversation_id"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
        schema=SCHEMA,
    )

    # ------------------------------------------------------
    # 4. Runtime permissions
    # ------------------------------------------------------

    op.execute(
        sa.text(
            "GRANT SELECT, INSERT, UPDATE, DELETE "
            "ON ALL TABLES IN SCHEMA assistant "
            "TO local_assistant_app"
        )
    )

    # Future tables created by the migrator should receive
    # the same runtime DML privileges by default.
    op.execute(
        sa.text(
            "ALTER DEFAULT PRIVILEGES "
            "FOR ROLE local_assistant_migrator "
            "IN SCHEMA assistant "
            "GRANT SELECT, INSERT, UPDATE, DELETE "
            "ON TABLES TO local_assistant_app"
        )
    )


def downgrade() -> None:
    op.drop_index(
        "uq_inference_runs_one_pending_per_conversation",
        table_name="inference_runs",
        schema=SCHEMA,
    )

    op.drop_index(
        "ix_inference_runs_assistant_message_id",
        table_name="inference_runs",
        schema=SCHEMA,
    )

    op.drop_index(
        "ix_inference_runs_user_message_id",
        table_name="inference_runs",
        schema=SCHEMA,
    )

    op.drop_index(
        "ix_inference_runs_conversation_started_at",
        table_name="inference_runs",
        schema=SCHEMA,
    )

    op.drop_table("inference_runs", schema=SCHEMA)

    op.drop_index(
        "ix_messages_conversation_created_at",
        table_name="messages",
        schema=SCHEMA,
    )

    op.drop_table("messages", schema=SCHEMA)

    op.drop_index(
        "ix_conversations_deleted_at",
        table_name="conversations",
        schema=SCHEMA,
    )

    op.drop_index(
        "ix_conversations_status_updated_at",
        table_name="conversations",
        schema=SCHEMA,
    )

    op.drop_table("conversations", schema=SCHEMA)

    op.execute(
        sa.text(
            "ALTER DEFAULT PRIVILEGES "
            "FOR ROLE local_assistant_migrator "
            "IN SCHEMA assistant "
            "REVOKE SELECT, INSERT, UPDATE, DELETE "
            "ON TABLES FROM local_assistant_app"
        )
    )
