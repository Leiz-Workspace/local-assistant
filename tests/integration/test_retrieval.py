"""Verify real source/SQL/Qdrant retrieval authorization, stale generations and response-lifetime recovery."""

import asyncio
from dataclasses import replace
from uuid import uuid4

import pytest
from test_file_http import owned_service as owned_service
from test_ingestion_worker import UnitEncoder, injected_preflight, upload
from test_ingestion_worker import worker_context as worker_context

from apps.api.services.retrieval import RetrievalService
from src.application.services.file_storage_policy import StoragePolicyError
from src.infrastructure.repositories.ingestion_journal import PostgresIngestionJournal

VECTOR = tuple([1.0] + [0.0] * 1023)


class UnitQuery:
    """Inject a unit query for lifecycle faults without representing model-quality evidence."""

    async def encode(self, query):
        """Return a deterministic vector matching the independently injected ingestion fixture."""
        return VECTOR


async def indexed(context, monkeypatch):
    """Create a real immutable source, journal generation and actual Qdrant unit-vector points."""
    from apps.api.services import ingestion

    monkeypatch.setattr(ingestion, "preflight_plan", injected_preflight)
    worker = await context["create"](encoder=UnitEncoder())
    owner, file_id = await upload(context, b"private-retrieval-marker verified source")
    job = await worker.admit(owner, file_id)
    assert (await worker.process(owner, job["id"]))["state"] == "ready"
    return worker, RetrievalService(worker, encoder=UnitQuery()), owner, file_id, job


@pytest.mark.asyncio
async def test_scoped_rehydration_foreign_owner_root_and_narrowing(
    worker_context, monkeypatch
):
    """Return only exact current source bytes/provenance and omit other owners, roots or file scopes."""
    worker, search, owner, file_id, job = await indexed(worker_context, monkeypatch)
    async with search.operation(owner, "query", top_k=1) as (data, retained):
        assert len(data["hits"]) == 1 and len(retained) == 1
        hit = data["hits"][0]
        assert hit["text"] == "private-retrieval-marker verified source"
        assert (
            hit["provenance"]["owner_id"] == str(owner)
            and hit["content_trust"] == "untrusted"
        )
        assert (
            hit["file_id"] == str(file_id)
            and hit["provenance"]["index_generation"] == job["generation"]
        )
    async with search.operation(worker_context["owners"][1], "query") as (data, _):
        assert data["hits"] == []
    async with search.operation(owner, "query", file_ids=[uuid4()]) as (data, _):
        assert data["hits"] == []
    search.journal = PostgresIngestionJournal(worker.journal.sessions, uuid4())
    async with search.operation(owner, "query") as (data, _):
        assert data["hits"] == []
    await search.shutdown()


@pytest.mark.asyncio
async def test_deleted_source_hidden_before_vector_cleanup_and_fenced_during_delivery(
    worker_context, monkeypatch
):
    """Fence a retained response immediately after SQL deletion while stale physical points remain."""
    worker, search, owner, file_id, job = await indexed(worker_context, monkeypatch)
    async with search.operation(owner, "query") as (data, retained):
        assert data["hits"]
        assert await worker.files.delete(owner, file_id) is False
        with pytest.raises(StoragePolicyError):
            await search.validate(owner, retained)
    assert await worker.vectors.owned() is not None
    async with search.operation(owner, "query") as (data, _):
        assert data["hits"] == []
    await worker.sweep()
    await search.shutdown()


@pytest.mark.asyncio
async def test_superseded_generation_and_final_delivery_recheck(
    worker_context, monkeypatch
):
    """Exclude stale candidates and fail final delivery after a new generation commits on the same source."""
    worker, search, owner, file_id, job = await indexed(worker_context, monkeypatch)
    stale = await search.vectors.search(
        owner, worker.files.storage.namespace_id, VECTOR, top_k=1
    )
    async with search.operation(owner, "query") as (data, retained):
        replacement = await worker.admit(owner, file_id, max_bytes=512)
        assert replacement["id"] != job["id"]
        assert (await worker.process(owner, replacement["id"]))["state"] == "ready"
        with pytest.raises(StoragePolicyError):
            await search.validate(owner, retained)

    async def old_candidates(*args, **kwargs):
        """Inject previously real returned points to isolate the SQL-generation fence."""
        return stale

    monkeypatch.setattr(search.vectors, "search", old_candidates)
    async with search.operation(owner, "query") as (data, _):
        assert data["hits"] == []
    await search.shutdown()


@pytest.mark.parametrize("case", ["digest", "extra_text", "projection"])
@pytest.mark.asyncio
async def test_untrusted_payload_or_projection_never_becomes_source(
    worker_context, monkeypatch, case
):
    """Reject hash/extra-text tampering and reconstructed-generation drift before returning source bytes."""
    worker, search, owner, file_id, job = await indexed(worker_context, monkeypatch)
    if case == "projection":
        from apps.api.services import retrieval

        original = retrieval.plan_ingestion

        def drift(*args, **kwargs):
            """Alter only the reconstructed identity to exercise explicit stale projection refusal."""
            return replace(original(*args, **kwargs), job_id=uuid4())

        monkeypatch.setattr(retrieval, "plan_ingestion", drift)
    else:
        candidates = await search.vectors.search(
            owner, worker.files.storage.namespace_id, VECTOR, top_k=1
        )
        if case == "digest":
            candidates[0]["payload"]["chunk_content_sha256"] = "0" * 64
        else:
            candidates[0]["payload"]["text"] = "forged private text"

        async def bad_candidates(*args, **kwargs):
            """Inject already scoped hostile payload that still needs independent source verification."""
            return candidates

        monkeypatch.setattr(search.vectors, "search", bad_candidates)
    with pytest.raises(StoragePolicyError):
        async with search.operation(owner, "query"):
            pytest.fail("untrusted data returned")
    assert not search.admission.locked() and not search.operations
    assert worker.files._chunk_operations == 0
    await search.shutdown()


@pytest.mark.asyncio
async def test_response_lifetime_busy_and_shutdown_join(worker_context, monkeypatch):
    """Keep admission/source ownership until the response context exits and join it before shutdown returns."""
    worker, search, owner, file_id, job = await indexed(worker_context, monkeypatch)
    ready = asyncio.Event()
    released = asyncio.Event()

    async def hold():
        """Retain a real source response until cancellation and record deterministic cleanup completion."""
        try:
            async with search.operation(owner, "query"):
                ready.set()
                await asyncio.Event().wait()
        finally:
            released.set()

    task = asyncio.create_task(hold())
    await asyncio.wait_for(ready.wait(), 5)
    with pytest.raises(StoragePolicyError) as error:
        async with search.operation(owner, "other"):
            pass
    assert error.value.status_code == 429
    await search.shutdown()
    assert task.done() and released.is_set() and not search.admission.locked()
    assert not search.operations and not worker.files.active


@pytest.mark.asyncio
async def test_cancel_query_releases_admission_and_shutdown_stops_new_work(
    worker_context, monkeypatch
):
    """Cancel owned model work before any candidates/readers and release both service/file task tracking."""
    worker, search, owner, file_id, job = await indexed(worker_context, monkeypatch)
    started = asyncio.Event()
    joined = asyncio.Event()

    class BlockingQuery:
        """Model deterministic cancellation without launching or benchmarking another encoder."""

        async def encode(self, query):
            """Block until task cancellation and confirm cleanup before propagation."""
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                joined.set()

    search.encoder = BlockingQuery()

    async def request():
        """Enter a resource-owning retrieval operation that will be cancelled during encoding."""
        async with search.operation(owner, "query"):
            pass

    task = asyncio.create_task(request())
    await asyncio.wait_for(started.wait(), 5)
    await search.shutdown()
    assert task.done() and joined.is_set() and not search.admission.locked()
    assert not worker.files.active
    with pytest.raises(StoragePolicyError):
        async with search.operation(owner, "query"):
            pass


@pytest.mark.asyncio
async def test_generation_change_during_final_integrity_is_fenced(
    worker_context, monkeypatch
):
    """Use a final single SQL snapshot to catch publication after the earlier per-source check but during I/O."""
    from apps.api.services import retrieval

    worker, search, owner, file_id, job = await indexed(worker_context, monkeypatch)
    async with search.operation(owner, "query") as (data, retained):
        replacement = await worker.admit(owner, file_id, max_bytes=512)
        original = retrieval.file_io
        changed = False

        async def publish_during_verify(function, *args, **kwargs):
            """Commit a legitimate new generation after old-source integrity succeeds."""
            nonlocal changed
            result = await original(function, *args, **kwargs)
            if not changed and getattr(function, "__name__", "") == "verify_integrity":
                changed = True
                assert (await worker.process(owner, replacement["id"]))[
                    "state"
                ] == "ready"
            return result

        monkeypatch.setattr(retrieval, "file_io", publish_during_verify)
        with pytest.raises(StoragePolicyError):
            await search.validate(owner, retained)
        assert changed
    await search.shutdown()
