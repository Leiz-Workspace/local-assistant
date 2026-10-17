from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.entities.inference_run import InferenceRun
from src.infrastructure.models.conversation_model import ConversationModel
from src.infrastructure.models.message_model import MessageModel
from src.infrastructure.models.inference_run_model import InferenceRunModel


VALID_REQUESTED_PRESETS = {
    "auto", "fast", "balanced", "deep", "unlimited",
}

VALID_SELECTED_PRESETS = {
    "fast", "balanced", "deep", "unlimited",
}


class PostgresInferenceRunRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_pending(
        self,
        *,
        conversation_id: UUID,
        user_message_id: UUID,
        preset_requested: str,
        preset_selected: str,
        model_id: str,
    ) -> InferenceRun:
        if preset_requested not in VALID_REQUESTED_PRESETS:
            raise ValueError("Invalid requested preset")

        if preset_selected not in VALID_SELECTED_PRESETS:
            raise ValueError("Invalid selected preset")

        conversation = await self.session.scalar(
            select(ConversationModel)
            .where(
                ConversationModel.id == conversation_id,
                ConversationModel.status == "active",
                ConversationModel.deleted_at.is_(None),
            )
            .with_for_update()
        )

        if conversation is None:
            raise ValueError(
                "Conversation does not exist or is not active"
            )

        user_message = await self.session.scalar(
            select(MessageModel).where(
                MessageModel.id == user_message_id,
                MessageModel.conversation_id == conversation_id,
                MessageModel.role == "user",
            )
        )

        if user_message is None:
            raise ValueError(
                "User message must belong to the same conversation"
            )

        model = InferenceRunModel(
            conversation_id=conversation_id,
            user_message_id=user_message_id,
            assistant_message_id=None,
            preset_requested=preset_requested,
            preset_selected=preset_selected,
            model_id=model_id,
            status="pending",
            metadata_={},
        )

        self.session.add(model)
        await self.session.flush()
        await self.session.refresh(model)
        return model.to_entity()

    async def get(
        self,
        run_id: UUID,
    ) -> InferenceRun | None:
        model = await self.session.get(
            InferenceRunModel,
            run_id,
        )
        return model.to_entity() if model else None

    async def get_pending(
        self,
        conversation_id: UUID,
    ) -> InferenceRun | None:
        model = await self.session.scalar(
            select(InferenceRunModel).where(
                InferenceRunModel.conversation_id == conversation_id,
                InferenceRunModel.status == "pending",
            )
        )
        return model.to_entity() if model else None

    async def get_by_user_message_id(
        self,
        user_message_id: UUID,
    ) -> InferenceRun | None:
        model = await self.session.scalar(
            select(InferenceRunModel)
            .where(
                InferenceRunModel.user_message_id == user_message_id
            )
            .order_by(
                InferenceRunModel.started_at.desc(),
                InferenceRunModel.id.desc(),
            )
            .limit(1)
        )
        return model.to_entity() if model else None

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
        model = await self.session.scalar(
            select(InferenceRunModel)
            .where(
                InferenceRunModel.id == run_id,
                InferenceRunModel.status == "pending",
            )
            .with_for_update()
        )

        if model is None:
            return None

        if finish_reason != "stop":
            raise ValueError(
                "Only verified stop completions can be persisted"
            )

        if (
            preset_selected is not None
            and preset_selected not in VALID_SELECTED_PRESETS
        ):
            raise ValueError("Invalid selected preset")

        assistant_message = await self.session.scalar(
            select(MessageModel).where(
                MessageModel.id == assistant_message_id,
                MessageModel.conversation_id == model.conversation_id,
                MessageModel.role == "assistant",
            )
        )

        if assistant_message is None:
            raise ValueError(
                "Assistant message must belong to the same conversation"
            )

        for name, value in {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "reasoning_tokens": reasoning_tokens,
            "latency_ms": latency_ms,
        }.items():
            if value is not None and value < 0:
                raise ValueError(f"{name} cannot be negative")

        if preset_selected is not None:
            model.preset_selected = preset_selected

        model.assistant_message_id = assistant_message_id
        model.finish_reason = finish_reason
        model.input_tokens = input_tokens
        model.output_tokens = output_tokens
        model.reasoning_tokens = reasoning_tokens
        model.latency_ms = latency_ms
        model.status = "completed"
        model.completed_at = datetime.now(timezone.utc)

        await self.session.flush()
        return model.to_entity()

    async def fail(
        self,
        run_id: UUID,
        *,
        error_code: str,
    ) -> InferenceRun | None:
        if not error_code or len(error_code) > 100:
            raise ValueError("Invalid error_code")

        model = await self.session.scalar(
            select(InferenceRunModel)
            .where(
                InferenceRunModel.id == run_id,
                InferenceRunModel.status == "pending",
            )
            .with_for_update()
        )

        if model is None:
            return None

        model.status = "failed"
        model.error_code = error_code
        model.completed_at = datetime.now(timezone.utc)

        await self.session.flush()
        return model.to_entity()
