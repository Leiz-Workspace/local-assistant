from __future__ import annotations

import os
from uuid import UUID

import pytest
from sqlalchemy import delete

from src.application.ports.inference import (
    CompletionResult,
    InferenceFailure,
)
from src.application.services.conversation_manager import (
    ConversationError,
    ConversationManager,
)
from src.infrastructure.database.connection import (
    check_database_connection,
    create_database_engine,
    create_session_factory,
)
from src.infrastructure.models.conversation_model import (
    ConversationModel,
)
from src.infrastructure.models.message_model import MessageModel
from src.infrastructure.models.inference_run_model import (
    InferenceRunModel,
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


MODEL_ID = "qwen3.5-9b-core"


class FakeInference:
    def __init__(
        self,
        *,
        fail: bool = False,
    ) -> None:
        self.fail = fail
        self.calls = 0
        self.contexts: list[list[dict[str, str]]] = []

    async def complete(
        self,
        *,
        profile: str,
        messages: list[dict[str, str]],
        preset: str,
        temperature: float,
        max_tokens: int | None,
    ) -> CompletionResult:
        self.calls += 1
        self.contexts.append(messages)

        if self.fail:
            raise InferenceFailure(
                "Simulated inference failure",
                code="simulated_failure",
            )

        return CompletionResult(
            content="Xin chào! Đây là câu trả lời thử nghiệm.",
            model_id=MODEL_ID,
            preset_selected=(
                "fast" if preset == "auto" else preset
            ),
            finish_reason="stop",
            input_tokens=24,
            output_tokens=12,
            reasoning_tokens=0,
            latency_ms=15,
        )


@pytest.mark.asyncio
async def test_conversation_manager_persistence_and_idempotency():
    url = os.environ.get("DATABASE_URL")

    if not url:
        pytest.skip("DATABASE_URL not configured")

    engine = create_database_engine(url)
    factory = create_session_factory(engine)

    conversation_ids: list[UUID] = []

    try:
        identity = await check_database_connection(engine)
        assert identity["database"] == "local_assistant"
        assert identity["user"] == "local_assistant_app"

        inference = FakeInference()

        manager = ConversationManager(
            session_factory=factory,
            inference=inference,
        )

        async with factory() as session:
            async with session.begin():
                repository = PostgresConversationRepository(
                    session
                )

                conversation = await repository.create(
                    title="D15-T04 idempotency test",
                    profile="core",
                    preset_default="auto",
                )
                conversation_ids.append(conversation.id)

        first = await manager.send_message(
            conversation_id=conversation.id,
            content="Xin chào",
            profile="core",
            preset="auto",
            model_id=MODEL_ID,
            request_key="d15-t04-test-request",
        )

        assert first.cached is False
        assert first.preset_requested == "auto"
        assert first.preset_selected == "fast"
        assert inference.calls == 1

        # Same request must not trigger new inference.
        replay = await manager.send_message(
            conversation_id=conversation.id,
            content="Xin chào",
            profile="core",
            preset="auto",
            model_id=MODEL_ID,
            request_key="d15-t04-test-request",
        )

        assert replay.cached is True
        assert replay.content == first.content
        assert replay.inference_run_id == first.inference_run_id
        assert replay.assistant_message_id == first.assistant_message_id
        assert inference.calls == 1

        # Reusing a key for different content is forbidden.
        with pytest.raises(
            ConversationError,
            match="Idempotency key",
        ):
            await manager.send_message(
                conversation_id=conversation.id,
                content="Một câu hỏi khác",
                profile="core",
                preset="auto",
                model_id=MODEL_ID,
                request_key="d15-t04-test-request",
            )

        assert inference.calls == 1

        # Verify stored data in a new independent transaction.
        async with factory() as session:
            async with session.begin():
                messages = PostgresMessageRepository(session)
                runs = PostgresInferenceRunRepository(session)

                history = await messages.list(conversation.id)
                run = await runs.get(first.inference_run_id)

                assert len(history) == 2
                assert [m.sequence for m in history] == [1, 2]
                assert [m.role for m in history] == [
                    "user",
                    "assistant",
                ]

                assert run is not None
                assert run.status == "completed"
                assert run.preset_requested == "auto"
                assert run.preset_selected == "fast"
                assert run.output_tokens == 12

        # Verify a failed generation never creates an
        # assistant message marked as completed.
        failing = FakeInference(fail=True)

        failing_manager = ConversationManager(
            session_factory=factory,
            inference=failing,
        )

        async with factory() as session:
            async with session.begin():
                repository = PostgresConversationRepository(
                    session
                )
                failed_conversation = await repository.create(
                    title="D15-T04 failure test",
                    profile="core",
                )
                conversation_ids.append(
                    failed_conversation.id
                )

        with pytest.raises(
            InferenceFailure,
            match="Simulated inference failure",
        ):
            await failing_manager.send_message(
                conversation_id=failed_conversation.id,
                content="Trigger failure",
                profile="core",
                preset="balanced",
                model_id=MODEL_ID,
                request_key="d15-t04-failure",
            )

        async with factory() as session:
            async with session.begin():
                messages = PostgresMessageRepository(session)
                runs = PostgresInferenceRunRepository(session)

                history = await messages.list(
                    failed_conversation.id
                )

                assert len(history) == 1
                assert history[0].role == "user"

                failed_run = await runs.get_by_user_message_id(
                    history[0].id
                )

                assert failed_run is not None
                assert failed_run.status == "failed"
                assert failed_run.error_code == "simulated_failure"

    finally:
        if conversation_ids:
            # Explicit cleanup, respecting FK RESTRICT.
            async with factory() as session:
                async with session.begin():
                    await session.execute(
                        delete(InferenceRunModel).where(
                            InferenceRunModel.conversation_id.in_(
                                conversation_ids
                            )
                        )
                    )
                    await session.execute(
                        delete(MessageModel).where(
                            MessageModel.conversation_id.in_(
                                conversation_ids
                            )
                        )
                    )
                    await session.execute(
                        delete(ConversationModel).where(
                            ConversationModel.id.in_(
                                conversation_ids
                            )
                        )
                    )

        await engine.dispose()
