"""Exercise independent-connection races, leases, cancellation and transactional failures."""

import asyncio
import logging
import os
from dataclasses import replace

import pytest
import pytest_asyncio
from sqlalchemy import delete, select

from src.application.ports.inference import CompletionResult, InferenceFailure
from src.application.services.conversation_manager import (
    ConversationError,
    ConversationManager,
)
from src.infrastructure.database.connection import (
    create_database_engine,
    create_session_factory,
)
from src.infrastructure.models.conversation_model import ConversationModel
from src.infrastructure.models.inference_run_model import InferenceRunModel
from src.infrastructure.models.message_model import MessageModel
from src.infrastructure.repositories.conversation_repository import (
    PostgresConversationRepository,
)
from src.infrastructure.repositories.inference_run_repository import (
    PostgresInferenceRunRepository,
)

logger = logging.getLogger(__name__)
MODEL = "qwen3.5-9b-core"


class ControlledInference:
    """Pause inference after reservation to expose races without timing guesses."""

    def __init__(self, *, blocked=False, result=None):
        """Initialize deterministic inference gates and the completed response."""
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        if not blocked:
            self.release.set()
        self.calls = 0
        self.contexts = []
        self.result = result or CompletionResult(
            content="Verified reply",
            model_id=MODEL,
            preset_selected="fast",
            finish_reason="stop",
        )

    async def complete(self, *, messages, **parameters):
        """Record context and await the explicit release gate without any DB session."""
        self.calls += 1
        self.contexts.append(messages)
        self.started.set()
        logger.info("controlled_inference_started calls=%d", self.calls)
        await self.release.wait()
        return self.result


@pytest_asyncio.fixture
async def database():
    """Use the existing app database and clean only conversations created by this fixture."""
    if not os.environ.get("DATABASE_URL"):
        pytest.skip("DATABASE_URL not configured")
    engine = create_database_engine()
    factory = create_session_factory(engine)
    identifiers = []

    async def create():
        """Create an isolated active conversation in a committed transaction."""
        async with factory() as session, session.begin():
            value = await PostgresConversationRepository(session).create(
                title="D15-T06 isolation test", preset_default="fast"
            )
            identifiers.append(value.id)
            return value.id

    try:
        yield engine, factory, create
    finally:
        async with factory() as session, session.begin():
            for model in (InferenceRunModel, MessageModel):
                await session.execute(
                    delete(model).where(model.conversation_id.in_(identifiers))
                )
            await session.execute(
                delete(ConversationModel).where(ConversationModel.id.in_(identifiers))
            )
        await engine.dispose()
        logger.info("hardening_database_cleanup conversations=%d", len(identifiers))


def send(manager, identifier, key="first"):
    """Send one fixed request so key equality is the only concurrency variable."""
    return manager.send_message(
        conversation_id=identifier,
        content="Hello",
        profile="core",
        preset="fast",
        model_id=MODEL,
        request_key=key,
    )


async def stored(factory, identifier):
    """Read committed transcript and run state through a fresh database session."""
    async with factory() as session:
        messages = (
            await session.scalars(
                select(MessageModel)
                .where(MessageModel.conversation_id == identifier)
                .order_by(MessageModel.sequence)
            )
        ).all()
        runs = (
            await session.scalars(
                select(InferenceRunModel)
                .where(InferenceRunModel.conversation_id == identifier)
                .order_by(InferenceRunModel.started_at)
            )
        ).all()
        return messages, runs


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "second_key,code",
    [("first", "request_already_exists"), ("different", "conversation_busy")],
)
async def test_cross_connection_requests(database, second_key, code):
    """Allow exactly one inference and reserve unique sequences across manager instances."""
    engine, factory, create = database
    identifier = await create()
    inference = ControlledInference(blocked=True)
    first = ConversationManager(session_factory=factory, inference=inference)
    second = ConversationManager(session_factory=factory, inference=inference)
    task = asyncio.create_task(send(first, identifier))
    try:
        await asyncio.wait_for(inference.started.wait(), 5)
        assert engine.pool.checkedout() == 0
        logger.info("pool_during_inference checked_out=%d", engine.pool.checkedout())
        with pytest.raises(ConversationError) as error:
            await asyncio.wait_for(send(second, identifier, second_key), 5)
        assert error.value.code == code
        messages, runs = await stored(factory, identifier)
        assert len(messages) == len(runs) == 1
        assert runs[0].status == "pending"
        assert inference.calls == 1
        inference.release.set()
        reply = await task
        replay = await send(second, identifier)
        assert (
            replay.cached and replay.assistant_message_id == reply.assistant_message_id
        )
        messages, runs = await stored(factory, identifier)
        assert [item.sequence for item in messages] == [1, 2]
        assert runs[0].status == "completed"
    finally:
        inference.release.set()
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_cancellation_is_interrupted(database):
    """Persist cancellation and prevent implicit retry under the same idempotency key."""
    _, factory, create = database
    identifier = await create()
    inference = ControlledInference(blocked=True)
    manager = ConversationManager(session_factory=factory, inference=inference)
    task = asyncio.create_task(send(manager, identifier))
    await asyncio.wait_for(inference.started.wait(), 5)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    messages, runs = await stored(factory, identifier)
    assert len(messages) == len(runs) == 1
    assert runs[0].status == "interrupted"
    assert runs[0].error_code == "request_cancelled"
    with pytest.raises(ConversationError):
        await send(manager, identifier)
    assert inference.calls == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "change,code",
    [
        ({"finish_reason": "length"}, "incomplete_completion"),
        ({"model_id": "different"}, "model_mismatch"),
        ({"preset_selected": "deep"}, "preset_mismatch"),
    ],
)
async def test_invalid_completion_never_commits(database, change, code):
    """Keep user input and a failed run while rejecting incomplete or mismatched output."""
    _, factory, create = database
    identifier = await create()
    inference = ControlledInference()
    inference.result = replace(inference.result, **change)
    manager = ConversationManager(session_factory=factory, inference=inference)
    with pytest.raises(InferenceFailure) as error:
        await send(manager, identifier)
    assert error.value.code == code
    messages, runs = await stored(factory, identifier)
    assert [item.role for item in messages] == ["user"]
    assert runs[0].status == "failed" and runs[0].error_code == code
    assert runs[0].assistant_message_id is None


@pytest.mark.asyncio
async def test_finalization_failure_rolls_back_assistant(database, monkeypatch):
    """Roll back an inserted assistant if completion update fails in the same transaction."""
    _, factory, create = database
    identifier = await create()

    async def fail_complete(self, *args, **kwargs):
        """Inject failure after assistant insertion but before run completion."""
        raise RuntimeError("Injected finalization fault")

    monkeypatch.setattr(PostgresInferenceRunRepository, "complete", fail_complete)
    manager = ConversationManager(
        session_factory=factory, inference=ControlledInference()
    )
    with pytest.raises(RuntimeError, match="Injected"):
        await send(manager, identifier)
    messages, runs = await stored(factory, identifier)
    assert [item.role for item in messages] == ["user"]
    assert runs[0].status == "failed"
    assert runs[0].assistant_message_id is None


@pytest.mark.asyncio
async def test_reservation_failure_rolls_back_user(database, monkeypatch):
    """Rollback user insertion if pending-run creation fails before reservation commit."""
    _, factory, create = database
    identifier = await create()

    async def fail_reservation(self, **kwargs):
        """Inject a fault between user insertion and pending-run creation."""
        raise RuntimeError("Injected reservation fault")

    monkeypatch.setattr(
        PostgresInferenceRunRepository, "create_pending", fail_reservation
    )
    inference = ControlledInference()
    manager = ConversationManager(session_factory=factory, inference=inference)
    with pytest.raises(RuntimeError, match="Injected"):
        await send(manager, identifier)
    messages, runs = await stored(factory, identifier)
    assert messages == runs == []
    assert inference.calls == 0


@pytest.mark.asyncio
async def test_lease_expiry_fences_old_worker(database):
    """Recover only expired runs and reject an old worker's late finalization."""
    _, factory, create = database
    identifier = await create()
    inference = ControlledInference(blocked=True)
    manager = ConversationManager(session_factory=factory, inference=inference)
    task = asyncio.create_task(send(manager, identifier))
    try:
        await asyncio.wait_for(inference.started.wait(), 5)
        new_worker = ConversationManager(session_factory=factory, inference=inference)
        assert await new_worker.recover_expired(identifier) is False
        async with factory() as session, session.begin():
            run = await session.scalar(
                select(InferenceRunModel).where(
                    InferenceRunModel.conversation_id == identifier
                )
            )
            run.metadata_ = {**run.metadata_, "lease_expires_at": 0}
        assert await new_worker.recover_expired(identifier) is True
        inference.release.set()
        with pytest.raises(ConversationError) as error:
            await task
        assert error.value.code == "inference_state_conflict"
        messages, runs = await stored(factory, identifier)
        assert len(messages) == 1 and runs[0].status == "interrupted"
        with pytest.raises(ConversationError):
            await send(new_worker, identifier)
        reply = await send(new_worker, identifier, "new-key")
        assert reply.cached is False
        assert inference.contexts[-1] == [{"role": "user", "content": "Hello"}]
    finally:
        inference.release.set()
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_heartbeat_extends_lease(database):
    """Keep a live worker valid across the initial lease period without holding a pool slot."""
    engine, factory, create = database
    identifier = await create()
    inference = ControlledInference(blocked=True)
    manager = ConversationManager(
        session_factory=factory,
        inference=inference,
        lease_seconds=1,
        heartbeat_seconds=0.05,
    )
    task = asyncio.create_task(send(manager, identifier))
    try:
        await asyncio.wait_for(inference.started.wait(), 5)
        _, initial = await stored(factory, identifier)
        initial_expiry = initial[0].metadata_["lease_expires_at"]
        await asyncio.sleep(0.25)
        _, renewed = await stored(factory, identifier)
        assert renewed[0].metadata_["lease_expires_at"] > initial_expiry
        assert (
            await ConversationManager(
                session_factory=factory, inference=inference
            ).recover_expired(identifier)
            is False
        )
        inference.release.set()
        assert (await task).cached is False
    finally:
        inference.release.set()
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_context_after_500_messages(database):
    """Read recent complete turns and system instructions beyond the historical first page."""
    _, factory, create = database
    identifier = await create()
    async with factory() as session, session.begin():
        session.add(
            MessageModel(
                conversation_id=identifier,
                sequence=1,
                role="system",
                content="Preserve system",
                metadata_={},
            )
        )
        for index in range(502):
            session.add(
                MessageModel(
                    conversation_id=identifier,
                    sequence=index + 2,
                    role="user" if index % 2 == 0 else "assistant",
                    content=f"History {index}",
                    metadata_={},
                )
            )
    inference = ControlledInference()
    manager = ConversationManager(
        session_factory=factory, inference=inference, max_history_messages=5
    )
    await send(manager, identifier)
    context = inference.contexts[0]
    assert [item["role"] for item in context] == [
        "system",
        "user",
        "assistant",
        "user",
        "assistant",
        "user",
    ]
    assert context[1]["content"] == "History 498"
    assert context[-1]["content"] == "Hello"
    messages, _ = await stored(factory, identifier)
    assert len(messages) == 505


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["update", "archive", "delete"])
async def test_pending_lifecycle_changes_are_rejected(database, action):
    """Reject real repository lifecycle mutations while another manager is generating."""
    from apps.api.services.conversations import ConversationService

    _, factory, create = database
    identifier = await create()
    inference = ControlledInference(blocked=True)
    service = ConversationService(factory, inference=inference)
    task = asyncio.create_task(send(service.manager, identifier))
    try:
        await asyncio.wait_for(inference.started.wait(), 5)
        with pytest.raises(ConversationError) as error:
            await service.mutate(identifier, action)
        assert error.value.code == "conversation_busy"
        inference.release.set()
        await task
        conversation = await service.get(identifier)
        assert conversation.status == "active"
    finally:
        inference.release.set()
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_pool_capacity_is_available_during_many_inferences(database):
    """Run more blocked inferences than pool capacity without holding database connections."""
    engine, factory, create = database
    identifiers = [await create() for _ in range(12)]
    inferences = [ControlledInference(blocked=True) for _ in identifiers]
    tasks = [
        asyncio.create_task(
            send(
                ConversationManager(session_factory=factory, inference=inference),
                identifier,
            )
        )
        for identifier, inference in zip(identifiers, inferences)
    ]
    try:
        await asyncio.wait_for(
            asyncio.gather(*(inference.started.wait() for inference in inferences)), 10
        )
        assert engine.pool.checkedout() == 0
        logger.info(
            "pool_saturation_probe blocked_inferences=12 checked_out=%d",
            engine.pool.checkedout(),
        )
    finally:
        for inference in inferences:
            inference.release.set()
        results = await asyncio.gather(*tasks, return_exceptions=True)
    assert not any(isinstance(result, BaseException) for result in results)


@pytest.mark.asyncio
async def test_actual_worker_crash_and_lease_recovery(database):
    """Kill a disposable worker process and recover its expired lease without replaying it."""
    import sys

    _, factory, create = database
    identifier = await create()
    worker_source = '''
"""Hold a test inference in a disposable worker until the parent kills it."""
import asyncio
import sys
from src.application.services.conversation_manager import ConversationManager
from src.infrastructure.database.connection import create_database_engine, create_session_factory

class BlockedInference:
    """Signal committed reservation and hold the model phase indefinitely."""
    async def complete(self, **parameters):
        """Notify the parent only after reservation commit and await cancellation."""
        print("INFERENCE_READY", flush=True)
        await asyncio.Event().wait()

async def main():
    """Use the app credential inherited in memory and create one leased run."""
    from uuid import UUID
    engine = create_database_engine()
    try:
        manager = ConversationManager(session_factory=create_session_factory(engine), inference=BlockedInference(), lease_seconds=1, heartbeat_seconds=0.1)
        await manager.send_message(conversation_id=UUID(sys.argv[1]), content="Hello", profile="core", preset="fast", model_id="qwen3.5-9b-core", request_key="first")
    finally:
        await engine.dispose()

asyncio.run(main())
'''
    environment = {
        key: value for key, value in os.environ.items() if not key.startswith("VAULT_")
    }
    worker = await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        worker_source,
        str(identifier),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
        env=environment,
    )
    try:
        assert (
            await asyncio.wait_for(worker.stdout.readline(), 10) == b"INFERENCE_READY\n"
        )
        worker.kill()
        await worker.wait()
        logger.info("disposable_worker_killed exit_code=%s", worker.returncode)
        await asyncio.sleep(1.1)
        inference = ControlledInference()
        manager = ConversationManager(session_factory=factory, inference=inference)
        assert await manager.recover_expired(identifier) is True
        messages, runs = await stored(factory, identifier)
        assert len(messages) == 1 and runs[0].status == "interrupted"
        assert runs[0].error_code == "lease_expired"
        with pytest.raises(ConversationError):
            await send(manager, identifier)
        assert inference.calls == 0
        await send(manager, identifier, "after-crash")
        assert inference.calls == 1
    finally:
        if worker.returncode is None:
            worker.kill()
            await worker.wait()


@pytest.mark.asyncio
async def test_live_tokenizer_overflow_is_persisted_as_failure(database):
    """Exercise real 32K template/tokenizer rejection without truncating the current input."""
    if os.environ.get("LOCAL_ASSISTANT_LIVE_E2E") != "1":
        pytest.skip("LOCAL_ASSISTANT_LIVE_E2E not enabled")
    from src.infrastructure.inference.llama_adapter import LlamaInferenceAdapter

    _, factory, create = database
    identifier = await create()
    manager = ConversationManager(
        session_factory=factory, inference=LlamaInferenceAdapter()
    )
    content = "x " * 40000
    with pytest.raises(InferenceFailure) as error:
        await manager.send_message(
            conversation_id=identifier,
            content=content,
            profile="core",
            preset="fast",
            model_id=MODEL,
            max_tokens=512,
        )
    assert error.value.code == "context_overflow"
    assert error.value.status_code == 422
    messages, runs = await stored(factory, identifier)
    assert len(messages) == 1 and messages[0].content == content
    assert runs[0].status == "failed"
    assert runs[0].assistant_message_id is None


@pytest.mark.asyncio
@pytest.mark.parametrize("second_key", ["first", "different"])
async def test_simultaneous_reservation_race(database, second_key, monkeypatch):
    """Race two transaction-A paths and require one winner before releasing inference."""
    _, factory, create = database
    from sqlalchemy import func

    original_lock = PostgresConversationRepository.lock_active
    backends = set()
    barrier = asyncio.Event()
    arrivals = 0

    async def lock_across_backends(repository, conversation_id):
        """Hold the first two DB transactions at a barrier before row-lock contention."""
        nonlocal arrivals
        arrivals += 1
        if arrivals <= 2:
            backend = await repository.session.scalar(select(func.pg_backend_pid()))
            backends.add(backend)
            if len(backends) == 2:
                barrier.set()
            await asyncio.wait_for(barrier.wait(), 5)
        return await original_lock(repository, conversation_id)

    monkeypatch.setattr(
        PostgresConversationRepository, "lock_active", lock_across_backends
    )
    identifier = await create()
    inference = ControlledInference(blocked=True)
    managers = [
        ConversationManager(session_factory=factory, inference=inference)
        for _ in range(2)
    ]
    tasks = [
        asyncio.create_task(send(manager, identifier, key))
        for manager, key in zip(managers, ["first", second_key])
    ]
    try:
        done, pending = await asyncio.wait(
            tasks, timeout=5, return_when=asyncio.FIRST_COMPLETED
        )
        assert len(backends) == 2
        assert len(done) == len(pending) == 1
        assert isinstance(next(iter(done)).exception(), ConversationError)
        assert inference.calls == 1
        messages, runs = await stored(factory, identifier)
        assert len(messages) == len(runs) == 1
        inference.release.set()
        results = await asyncio.gather(*tasks, return_exceptions=True)
        assert sum(isinstance(result, ConversationError) for result in results) == 1
        messages, _ = await stored(factory, identifier)
        assert [item.sequence for item in messages] == [1, 2]
    finally:
        inference.release.set()
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


@pytest.mark.asyncio
async def test_legacy_pending_without_owner_is_not_recovered(database):
    """Leave pre-lease reservations unchanged because their worker ownership is unknown."""
    from src.infrastructure.repositories.message_repository import (
        PostgresMessageRepository,
    )

    _, factory, create = database
    identifier = await create()
    async with factory() as session, session.begin():
        user = await PostgresMessageRepository(session).append(
            conversation_id=identifier, role="user", content="Legacy request"
        )
        await PostgresInferenceRunRepository(session).create_pending(
            conversation_id=identifier,
            user_message_id=user.id,
            preset_requested="fast",
            preset_selected="fast",
            model_id=MODEL,
        )
    manager = ConversationManager(
        session_factory=factory, inference=ControlledInference()
    )
    assert await manager.recover_expired(identifier) is False
    _, runs = await stored(factory, identifier)
    assert runs[0].status == "pending" and runs[0].metadata_ == {}


@pytest.mark.asyncio
async def test_heartbeat_loss_cancels_inference(database):
    """Stop the active inference if the owned reservation can no longer renew its lease."""
    _, factory, create = database
    identifier = await create()
    inference = ControlledInference(blocked=True)
    manager = ConversationManager(
        session_factory=factory,
        inference=inference,
        lease_seconds=2,
        heartbeat_seconds=0.05,
    )
    task = asyncio.create_task(send(manager, identifier))
    try:
        await asyncio.wait_for(inference.started.wait(), 5)
        async with factory() as session, session.begin():
            run = await session.scalar(
                select(InferenceRunModel)
                .where(InferenceRunModel.conversation_id == identifier)
                .with_for_update()
            )
            run.metadata_ = {**run.metadata_, "lease_expires_at": 0}
        with pytest.raises(InferenceFailure) as error:
            await asyncio.wait_for(task, 5)
        assert error.value.code == "lease_lost"
        messages, runs = await stored(factory, identifier)
        assert len(messages) == 1 and runs[0].status == "failed"
        assert runs[0].error_code == "lease_lost"
    finally:
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)
