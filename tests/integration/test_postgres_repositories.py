from __future__ import annotations

import os

import pytest
from sqlalchemy import select

from src.infrastructure.database.connection import (
    check_database_connection,
    create_database_engine,
    create_session_factory,
    transactional_session,
)
from src.infrastructure.models.conversation_model import ConversationModel
from src.infrastructure.repositories.conversation_repository import (
    PostgresConversationRepository,
)
from src.infrastructure.repositories.message_repository import (
    PostgresMessageRepository,
)
from src.infrastructure.repositories.inference_run_repository import (
    PostgresInferenceRunRepository,
)


@pytest.mark.asyncio
async def test_postgres_repository_lifecycle() -> None:
    database_url = os.environ.get("DATABASE_URL")

    if not database_url:
        pytest.skip("DATABASE_URL not configured")

    engine = create_database_engine(database_url)
    session_factory = create_session_factory(engine)

    conversation_id = None

    try:
        identity = await check_database_connection(engine)

        assert identity["database"] == "local_assistant"
        assert identity["user"] == "local_assistant_app"
        assert identity["schema"] == "assistant"

        # Transaction 1: Create conversation.
        async with transactional_session(session_factory) as session:
            conversations = PostgresConversationRepository(session)

            conversation = await conversations.create(
                title="D15-T03 integration test",
                profile="core",
                preset_default="balanced",
                metadata={"test": True},
            )

            conversation_id = conversation.id

            assert conversation.status == "active"

        # Transaction 2: Verify persistence and append user message.
        async with transactional_session(session_factory) as session:
            conversations = PostgresConversationRepository(session)
            messages = PostgresMessageRepository(session)

            persisted = await conversations.get(conversation_id)
            assert persisted is not None

            user_message = await messages.append(
                conversation_id=conversation_id,
                role="user",
                content="Hello, PostgreSQL!",
                request_key="d15-t03-user-message",
            )

            assert user_message.sequence == 1

        # Transaction 3: Reserve an inference run.
        async with transactional_session(session_factory) as session:
            runs = PostgresInferenceRunRepository(session)

            run = await runs.create_pending(
                conversation_id=conversation_id,
                user_message_id=user_message.id,
                preset_requested="auto",
                preset_selected="balanced",
                model_id="qwen3.5-9b-core",
            )

            run_id = run.id
            assert run.status == "pending"

        # Transaction 4: Append assistant message and complete run.
        async with transactional_session(session_factory) as session:
            messages = PostgresMessageRepository(session)
            runs = PostgresInferenceRunRepository(session)

            assistant_message = await messages.append(
                conversation_id=conversation_id,
                role="assistant",
                content="PostgreSQL persistence is working.",
            )

            assert assistant_message.sequence == 2

            completed = await runs.complete(
                run_id,
                assistant_message_id=assistant_message.id,
                finish_reason="stop",
                input_tokens=12,
                output_tokens=6,
                latency_ms=250,
            )

            assert completed is not None
            assert completed.status == "completed"
            assert completed.output_tokens == 6

        # Transaction 5: Read committed data.
        async with transactional_session(session_factory) as session:
            messages = PostgresMessageRepository(session)
            runs = PostgresInferenceRunRepository(session)

            history = await messages.list(conversation_id)
            persisted_run = await runs.get(run_id)

            assert [item.sequence for item in history] == [1, 2]
            assert [item.role for item in history] == [
                "user",
                "assistant",
            ]

            assert persisted_run is not None
            assert persisted_run.status == "completed"
            assert persisted_run.assistant_message_id == (
                assistant_message.id
            )

        # Transaction 6: Verify archive / soft delete behavior.
        async with transactional_session(session_factory) as session:
            conversations = PostgresConversationRepository(session)

            archived = await conversations.archive(conversation_id)
            assert archived is not None
            assert archived.status == "archived"

            deleted = await conversations.soft_delete(
                conversation_id
            )
            assert deleted is True

            assert await conversations.get(conversation_id) is None

            assert (
                await conversations.get(
                    conversation_id,
                    include_deleted=True,
                )
                is not None
            )

    finally:
        if conversation_id is not None:
            # Cleanup test records, including dependent messages/runs.
            async with transactional_session(session_factory) as session:
                model = await session.get(
                    ConversationModel,
                    conversation_id,
                )

                if model is not None:
                    await session.delete(model)

        await engine.dispose()
