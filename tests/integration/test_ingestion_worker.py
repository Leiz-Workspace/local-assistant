"""Verify source-held ingestion workers, durable retry/fencing and repeat cleanup on real PostgreSQL/Qdrant."""

import asyncio
import json
import os
from pathlib import Path
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import text
from test_file_http import body, declaration
from test_file_http import owned_service as owned_service

from apps.api.services.ingestion import IngestionService
from src.application.services.file_storage_policy import StoragePolicyError
from src.infrastructure.qdrant_ingestion import QdrantIngestion
from src.infrastructure.qwen_embedding import EncodedBatch, QwenEmbedding

ROOT = Path(__file__).resolve().parents[2]


class UnitEncoder:
    """Provide explicit unit-axis vectors for transaction/fault tests without claiming model-quality results."""

    async def encode(self, plan):
        """Return complete deterministic injected vectors/counts for a trusted source plan."""
        return EncodedBatch(
            plan.model_fingerprint,
            tuple(1 for _ in plan.points),
            tuple(tuple([1.0] + [0.0] * 1023) for _ in plan.points),
        )


class CapturingEncoder(QwenEmbedding):
    """Capture one actual immutable encoding for a later controlled late-writer simulation."""

    async def encode(self, plan):
        """Run the real pinned CPU worker and retain only test-local plan/batch references."""
        batch = await super().encode(plan)
        self.plan, self.batch = plan, batch
        return batch


@pytest_asyncio.fixture
async def worker_context(owned_service):
    """Create only a fresh removable owned vector probe and clean the test owners' journal rows first."""
    if not os.environ.get("LOCAL_ASSISTANT_QDRANT_PROBE_KEY"):
        pytest.skip("explicit existing Qdrant acceptance credential not configured")
    files, owners = owned_service
    selected = json.loads((ROOT / "configs/embedding-selected.json").read_text())
    key = os.environ["LOCAL_ASSISTANT_QDRANT_PROBE_KEY"]
    owner = uuid4()
    name = "la_d25_probe_" + uuid4().hex
    services = []

    async def create(*, encoder=None, background=False):
        """Start the real worker repository/namespace guard and one explicitly owned probe adapter."""
        vector = QdrantIngestion(selected, owner, key, physical_name=name)
        service = IngestionService(
            files, selected, vector, encoder=encoder, interval=0.02, heartbeat=0.03
        )
        services.append(service)
        await service.start(background=background)
        return service

    try:
        yield dict(
            files=files,
            owners=owners,
            selection=selected,
            key=key,
            owner=owner,
            name=name,
            create=create,
            services=services,
        )
    finally:
        for service in reversed(services):
            await service.shutdown()
        inspector = QdrantIngestion(selected, owner, key, physical_name=name)
        try:
            if await inspector.owned() is not None:
                await inspector.request("DELETE", inspector.path)
        finally:
            await inspector.close()
        async with files.journal.sessions() as session, session.begin():
            for table in ("ingestion_heads", "ingestion_jobs"):
                await session.execute(
                    text(f"DELETE FROM assistant.{table} WHERE owner_id IN (:a,:b)"),
                    dict(a=owners[0], b=owners[1]),
                )


async def upload(context, data=b"private worker source"):
    """Persist an actual verified private blob through the accepted source service."""
    files = context["files"]
    owner = context["owners"][0]
    row = await files.reserve(owner, **declaration(data))
    await files.upload(owner, row["id"], body(data))
    return owner, row["id"]


def injected_preflight(plan):
    """Return explicit fault-test counts only; the actual model integration uses real token preflight."""
    return tuple(1 for _ in plan.points)


@pytest.mark.asyncio
async def test_actual_source_qwen_publication_replay_replacement_delete_and_late_write(
    worker_context,
):
    """Exercise real source/Qwen/Qdrant/journal publication and repair a late terminal write after restart."""
    if os.environ.get("LOCAL_ASSISTANT_EMBEDDING_COMPARE_LIVE") != "1":
        pytest.skip("explicit actual Qwen integration flag not configured")
    context = worker_context
    capture = CapturingEncoder()
    service = await context["create"](encoder=capture)
    owner, file_id = await upload(context)
    first = await service.admit(owner, file_id)
    assert (await service.process(owner, first["id"]))["state"] == "ready"
    assert (await service.admit(owner, file_id))["id"] == first["id"]
    newer = await service.admit(owner, file_id, max_bytes=512)
    assert newer["id"] != first["id"]
    assert (await service.process(owner, newer["id"]))["state"] == "ready"
    assert (await service.journal.get(owner, first["id"]))["state"] == "tombstone"
    assert (await service.journal.active(owner, file_id, service.model))["id"] == newer[
        "id"
    ]
    assert await context["files"].delete(owner, file_id)
    assert await service.journal.active(owner, file_id, service.model) is None
    for _ in range(3):
        await service.sweep()
    assert (await service.journal.get(owner, newer["id"]))[
        "cleanup_done_at"
    ] is not None
    plan, batch = capture.plan, capture.batch
    await service.shutdown()
    late = QdrantIngestion(
        context["selection"],
        context["owner"],
        context["key"],
        physical_name=context["name"],
    )
    try:
        await late.upsert(plan, batch)
    finally:
        await late.close()
    restarted = await context["create"](encoder=UnitEncoder())
    for _ in range(3):
        await restarted.sweep()
    assert (
        await restarted.vectors.request(
            "POST", restarted.vectors.path + "/points/count", dict(exact=True)
        )
    )["result"]["count"] == 0
    assert await restarted.journal.active(owner, file_id, restarted.model) is None


@pytest.mark.asyncio
async def test_namespace_guard_refuses_duplicate_worker_without_releasing_first(
    worker_context,
):
    """Use real session advisory locks to reject overlapping workers for the same namespace/model."""
    first = await worker_context["create"](encoder=UnitEncoder())
    with pytest.raises(StoragePolicyError, match="already_running"):
        await worker_context["create"](encoder=UnitEncoder())
    await first.guard.check()


@pytest.mark.asyncio
async def test_uncertain_upsert_ack_retries_same_ids(worker_context, monkeypatch):
    """Keep partially written points invisible until a later complete verified publication succeeds."""
    from apps.api.services import ingestion as module

    monkeypatch.setattr(module, "preflight_plan", injected_preflight)
    service = await worker_context["create"](encoder=UnitEncoder())
    owner, file_id = await upload(worker_context)
    job = await service.admit(owner, file_id)
    original = service.vectors.upsert
    once = True

    async def uncertain(plan, batch):
        """Lose exactly one acknowledgement after the actual vector write/verification completed."""
        nonlocal once
        result = await original(plan, batch)
        if once:
            once = False
            raise RuntimeError("controlled_lost_ack")
        return result

    monkeypatch.setattr(service.vectors, "upsert", uncertain)
    assert (await service.process(owner, job["id"]))["state"] == "pending"
    assert await service.journal.active(owner, file_id, service.model) is None
    async with service.journal.sessions() as session, session.begin():
        await session.execute(
            text(
                "UPDATE assistant.ingestion_jobs SET next_attempt_at=clock_timestamp()-interval '1 second' WHERE id=:id"
            ),
            dict(id=job["id"]),
        )
    assert (await service.process(owner, job["id"]))["state"] == "ready"
    assert (
        await service.vectors.request(
            "POST", service.vectors.path + "/points/count", dict(exact=True)
        )
    )["result"]["count"] == len(job["point_ids"])


@pytest.mark.asyncio
async def test_lost_publication_ack_reads_durable_ready_state(
    worker_context, monkeypatch
):
    """Resolve a post-commit response loss without reviving a cleared lease or retrying a ready job."""
    from apps.api.services import ingestion as module

    monkeypatch.setattr(module, "preflight_plan", injected_preflight)
    service = await worker_context["create"](encoder=UnitEncoder())
    owner, file_id = await upload(worker_context)
    job = await service.admit(owner, file_id)
    original = service.journal.publish

    async def lost_ack(*args):
        """Commit the real SQL publication and then lose its caller acknowledgement."""
        await original(*args)
        raise RuntimeError("controlled_publish_ack_loss")

    monkeypatch.setattr(service.journal, "publish", lost_ack)
    result = await service.process(owner, job["id"])
    assert (
        result["state"] == "ready"
        and result["attempts"] == 1
        and result["lease_token"] is None
    )
    assert (await service.journal.active(owner, file_id, service.model))["id"] == job[
        "id"
    ]


@pytest.mark.asyncio
async def test_heartbeat_source_delete_joins_encoding_and_keeps_worker_usable(
    worker_context, monkeypatch
):
    """Fence and join child work while retaining its source reader until cancellation cleanup completes."""
    from apps.api.services import ingestion as module

    monkeypatch.setattr(module, "preflight_plan", injected_preflight)
    started, joined = asyncio.Event(), asyncio.Event()

    class HeldEncoder:
        """Retain a source-bound encoding until heartbeat invalidation cancels it."""

        async def encode(self, plan):
            """Record a joined cancellation instead of returning a partial encoding."""
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                joined.set()

    service = await worker_context["create"](encoder=HeldEncoder())
    owner, file_id = await upload(worker_context)
    job = await service.admit(owner, file_id)
    work = asyncio.create_task(service.process(owner, job["id"]))
    await started.wait()
    await worker_context["files"].delete(owner, file_id)
    result = await asyncio.wait_for(work, timeout=5)
    assert result["state"] == "stale" and joined.is_set()
    assert not worker_context["files"].active
    await worker_context["files"].delete(owner, file_id)
    await service.guard.check()


@pytest.mark.asyncio
async def test_shutdown_joins_background_source_work_before_unlock(
    worker_context, monkeypatch
):
    """Drain a real worker loop while preserving pending durable retry and releasing source/advisory resources."""
    from apps.api.services import ingestion as module

    monkeypatch.setattr(module, "preflight_plan", injected_preflight)
    started, joined = asyncio.Event(), asyncio.Event()

    class HeldEncoder:
        """Represent bounded work owned by the actual worker task during shutdown."""

        async def encode(self, plan):
            """Hold until joined cancellation releases its retained source context."""
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                joined.set()

    service = await worker_context["create"](encoder=HeldEncoder())
    owner, file_id = await upload(worker_context)
    job = await service.admit(owner, file_id)
    service.task = asyncio.create_task(service.run())
    await asyncio.wait_for(started.wait(), timeout=5)
    await service.shutdown()
    assert (
        joined.is_set()
        and not worker_context["files"].active
        and service.guard.connection is None
    )
    assert (await service.journal.get(owner, job["id"]))["state"] == "pending"


def crash_after_upsert(
    root, owner, file_id, job_id, collection_owner, name, connection
):
    """Run an actual worker process until acknowledged staged vectors exist, then await parent SIGKILL."""

    async def run():
        """Use existing app/Qdrant credentials, source root and actual durable namespace ownership."""
        from apps.api.services.files import FileService
        from src.infrastructure.database.connection import (
            create_database_engine,
            create_session_factory,
        )
        from src.infrastructure.local_blob_storage import LocalBlobStorage
        from src.infrastructure.repositories.file_journal import PostgresFileJournal

        class HeldVectors(QdrantIngestion):
            """Pause only activation after the actual generation upsert/verification completed."""

            async def activate(self, plan, batch):
                """Signal the real staged-point boundary without publishing the journal head."""
                connection.send("staged_before_publication")
                await asyncio.Event().wait()

        engine = create_database_engine()
        files = FileService(
            PostgresFileJournal(create_session_factory(engine)), LocalBlobStorage(root)
        )
        selection = json.loads((ROOT / "configs/embedding-selected.json").read_text())
        vectors = HeldVectors(
            selection,
            collection_owner,
            os.environ["LOCAL_ASSISTANT_QDRANT_PROBE_KEY"],
            physical_name=name,
        )
        service = IngestionService(files, selection, vectors, encoder=UnitEncoder())
        await service.start(background=False)
        await service.process(owner, job_id)

    asyncio.run(run())


@pytest.mark.asyncio
async def test_actual_sigkill_after_vector_upsert_recovers_same_ids(
    worker_context, monkeypatch
):
    """Recover a killed source-holding process after real vector writes and before SQL publication."""
    import multiprocessing
    import signal

    from apps.api.services import ingestion as module

    monkeypatch.setattr(module, "preflight_plan", injected_preflight)
    context = worker_context
    service = await context["create"](encoder=UnitEncoder())
    owner, file_id = await upload(context)
    job = await service.admit(owner, file_id)
    await service.shutdown()
    process_context = multiprocessing.get_context("spawn")
    parent, child = process_context.Pipe(duplex=False)
    root = Path(os.readlink(f"/proc/self/fd/{context['files'].storage._root_fd}"))
    process = process_context.Process(
        target=crash_after_upsert,
        args=(
            root,
            owner,
            file_id,
            job["id"],
            context["owner"],
            context["name"],
            child,
        ),
    )
    process.start()
    child.close()
    try:
        ready = await asyncio.to_thread(parent.poll, 20)
        assert ready and parent.recv() == "staged_before_publication"
        os.kill(process.pid, signal.SIGKILL)
        await asyncio.to_thread(process.join, 5)
        assert not process.is_alive() and process.exitcode == -signal.SIGKILL
        assert (await service.journal.get(owner, job["id"]))["state"] == "running"
        assert await service.journal.active(owner, file_id, service.model) is None
        async with service.journal.sessions() as session, session.begin():
            await session.execute(
                text(
                    "UPDATE assistant.ingestion_jobs SET lease_expires_at=clock_timestamp()-interval '1 second' WHERE id=:id"
                ),
                dict(id=job["id"]),
            )
        restarted = await context["create"](encoder=UnitEncoder())
        result = await restarted.process(owner, job["id"])
        assert result["state"] == "ready" and result["attempts"] == 2
        assert (
            await restarted.vectors.request(
                "POST", restarted.vectors.path + "/points/count", dict(exact=True)
            )
        )["result"]["count"] == len(job["point_ids"])
        assert await context["files"].delete(owner, file_id)
        for _ in range(3):
            await restarted.sweep()
    finally:
        if process.is_alive():
            process.kill()
            await asyncio.to_thread(process.join, 5)
        parent.close()


@pytest.mark.asyncio
async def test_busy_source_deferral_does_not_consume_model_attempt(
    worker_context, monkeypatch
):
    """Preserve retry budget under source-processing backpressure without extending the durable deadline."""
    from contextlib import asynccontextmanager

    from apps.api.services import ingestion as module

    monkeypatch.setattr(module, "preflight_plan", injected_preflight)
    service = await worker_context["create"](encoder=UnitEncoder())
    owner, file_id = await upload(worker_context)
    job = await service.admit(owner, file_id)

    @asynccontextmanager
    async def busy(*args, **kwargs):
        """Return the same bounded source-slot conflict as an overlapping native extraction."""
        raise StoragePolicyError("chunk_processing_busy", 429)
        yield

    monkeypatch.setattr(module, "chunk_operation", busy)
    deferred = await service.process(owner, job["id"])
    assert (
        deferred["state"] == "pending"
        and deferred["attempts"] == 0
        and deferred["deadline_at"] == job["deadline_at"]
    )


@pytest.mark.asyncio
async def test_cancelled_guard_check_does_not_release_live_namespace(
    worker_context, monkeypatch
):
    """Shield and join control-connection checks so request cancellation cannot drop the worker lock."""
    service = await worker_context["create"](encoder=UnitEncoder())
    started, release = asyncio.Event(), asyncio.Event()
    original = service.guard._check

    async def held():
        """Delay one actual backend check while cancellation targets its caller."""
        started.set()
        await release.wait()
        await original()

    monkeypatch.setattr(service.guard, "_check", held)
    check = asyncio.create_task(service.guard.check())
    await started.wait()
    check.cancel()
    await asyncio.sleep(0)
    assert not check.done()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await check
    monkeypatch.setattr(service.guard, "_check", original)
    await service.guard.check()
    with pytest.raises(StoragePolicyError, match="already_running"):
        await worker_context["create"](encoder=UnitEncoder())


@pytest.mark.asyncio
async def test_reconstructed_processor_drift_is_terminal_before_encoding(
    worker_context, monkeypatch
):
    """Refuse a valid but different reconstructed projection instead of rewriting old identities to fit it."""
    from unittest.mock import AsyncMock

    from apps.api.services import ingestion as module
    from src.application.services.document_chunks import (
        ChunkSource,
        build_chunks,
        text_unit,
    )

    monkeypatch.setattr(module, "preflight_plan", injected_preflight)
    encoder = UnitEncoder()
    service = await worker_context["create"](encoder=encoder)
    owner, file_id = await upload(worker_context)
    job = await service.admit(owner, file_id)
    original = module.plan_ingestion

    def changed(row, principal, namespace, view, selection):
        """Produce legitimate D22 chunks under a changed extractor identity without altering source bytes."""
        source = ChunkSource(
            principal, namespace, row["id"], row["actual_sha256"], "processor-v2"
        )
        replacement = build_chunks(
            source,
            [text_unit(view["chunks"][0]["locator"], view["chunks"][0]["text"])],
            view["max_bytes"],
        )
        return original(row, principal, namespace, replacement, selection)

    action = AsyncMock(side_effect=AssertionError("changed projection must not encode"))
    monkeypatch.setattr(encoder, "encode", action)
    monkeypatch.setattr(module, "plan_ingestion", changed)
    result = await service.process(owner, job["id"])
    assert result["state"] == "stale" and result["error_code"] == "source_changed"
    action.assert_not_called()
    assert (
        await service.vectors.request(
            "POST", service.vectors.path + "/points/count", dict(exact=True)
        )
    )["result"]["count"] == 0
