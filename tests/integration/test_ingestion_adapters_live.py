"""Verify actual Qwen embeddings and owned Qdrant generations using an isolated removable acceptance probe."""

import json
import os
from pathlib import Path
from uuid import UUID, uuid4

import httpx
import pytest

from scripts.qdrant_embedding_design import inventory, snapshot_digest
from src.application.services.document_chunks import (
    ChunkSource,
    build_chunks,
    text_unit,
)
from src.application.services.ingestion_contract import plan_ingestion
from src.infrastructure.qdrant_ingestion import QdrantIngestion
from src.infrastructure.qwen_embedding import QwenEmbedding

ROOT = Path(__file__).resolve().parents[2]


def make_plan(selection, *, max_bytes=256, owner=None, count=10):
    """Build actual trusted D22 output while varying only a declared generation/source scope."""
    owner = owner or UUID(int=71)
    namespace, file_id = UUID(int=72), UUID(int=73)
    source = ChunkSource(owner, namespace, file_id, "d" * 64, "utf8-text-v1")
    row = dict(
        id=file_id,
        owner_id=owner,
        state="ready",
        deleted_at=None,
        actual_sha256=source.sha256,
        policy_snapshot={"_storage_namespace": str(namespace)},
    )
    view = build_chunks(
        source,
        [
            text_unit(
                f"source#{index}", f"Tài liệu riêng cho kiểm thử generation {index}."
            )
            for index in range(count)
        ],
        max_bytes,
    )
    return plan_ingestion(row, owner, namespace, view, selection)


@pytest.mark.asyncio
async def test_actual_cpu_qwen_owned_vectors_retry_and_generation_delete():
    """Prove actual model identity, stored vector equality, idempotent writes and exact-scope deletion."""
    if os.environ.get(
        "LOCAL_ASSISTANT_EMBEDDING_COMPARE_LIVE"
    ) != "1" or not os.environ.get("LOCAL_ASSISTANT_QDRANT_PROBE_KEY"):
        pytest.skip("explicit actual Qwen/Qdrant acceptance credentials not configured")
    selected_path = ROOT / "configs/embedding-selected.json"
    before_selected = selected_path.read_bytes()
    selection = json.loads(before_selected)
    plan = make_plan(selection)
    batch = await QwenEmbedding().encode(plan)
    assert batch.model_fingerprint == selection["runtime"]["fingerprint"]
    assert len(batch.vectors) == 10 and len(batch.vectors[0]) == 1024
    key = os.environ["LOCAL_ASSISTANT_QDRANT_PROBE_KEY"]
    with httpx.Client(
        base_url="http://127.0.0.1:6333",
        headers={"api-key": key},
        trust_env=False,
        follow_redirects=False,
        timeout=10,
    ) as inspector:
        before = inventory(inspector)
    owner = uuid4()
    name = "la_d25_probe_" + uuid4().hex
    adapter = QdrantIngestion(selection, owner, key, physical_name=name)
    try:
        await adapter.ensure()
        expected = [point.point_id for point in plan.points]
        assert await adapter.upsert(plan, batch) == expected
        assert await adapter.upsert(plan, batch) == expected
        newer = make_plan(selection, max_bytes=512)
        await adapter.upsert(newer, batch)
        foreign = make_plan(selection, owner=UUID(int=79))
        await adapter.upsert(foreign, batch)
        await adapter.delete(plan)
        await adapter.delete(plan)
        assert await adapter.verify(newer, batch) == [
            point.point_id for point in newer.points
        ]
        assert await adapter.verify(foreign, batch) == [
            point.point_id for point in foreign.points
        ]
        count = (
            await adapter.request(
                "POST", adapter.path + "/points/count", dict(exact=True)
            )
        )["result"]["count"]
        assert count == 20
        await adapter.delete(newer)
        await adapter.delete(foreign)
        assert (
            await adapter.request(
                "POST", adapter.path + "/points/count", dict(exact=True)
            )
        )["result"]["count"] == 0
    finally:
        try:
            if await adapter.owned() is not None:
                await adapter.request("DELETE", adapter.path)
        finally:
            await adapter.close()
    with httpx.Client(
        base_url="http://127.0.0.1:6333",
        headers={"api-key": key},
        trust_env=False,
        follow_redirects=False,
        timeout=10,
    ) as inspector:
        after = inventory(inspector)
    assert before == after and snapshot_digest(before) == snapshot_digest(after)
    assert selected_path.read_bytes() == before_selected


@pytest.mark.asyncio
async def test_actual_encoder_cancellation_reaps_owned_process(monkeypatch):
    """Kill and join a real isolated encoder launch without leaving a live process group or busy slot."""
    import asyncio

    from src.infrastructure import qwen_embedding as module

    if os.environ.get("LOCAL_ASSISTANT_EMBEDDING_COMPARE_LIVE") != "1":
        pytest.skip("explicit actual encoder cancellation flag not configured")
    selection = json.loads((ROOT / "configs/embedding-selected.json").read_text())
    plan = make_plan(selection)
    original = asyncio.create_subprocess_exec
    launched = asyncio.Event()
    children = []

    async def capture(*args, **kwargs):
        """Capture only the actual child handle while preserving real subprocess isolation."""
        child = await original(*args, **kwargs)
        children.append(child)
        launched.set()
        return child

    monkeypatch.setattr(module.asyncio, "create_subprocess_exec", capture)
    adapter = QwenEmbedding()
    work = asyncio.create_task(adapter.encode(plan))
    await launched.wait()
    work.cancel()
    with pytest.raises(asyncio.CancelledError):
        await work
    assert children[0].returncode is not None and not adapter.admission.locked()
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            fields = (entry / "stat").read_text().rsplit(")", 1)[1].split()
        except (OSError, IndexError):
            continue
        assert int(fields[2]) != children[0].pid or fields[0] == "Z"


def encoder_parent_process(plan, connection):
    """Run an API-side encoding parent and report only its owned launcher PID to a kill-test controller."""
    import asyncio

    from src.infrastructure import qwen_embedding as module

    async def run():
        """Start the actual offline encoder and retain its normal cancellation/resource implementation."""
        original = asyncio.create_subprocess_exec

        async def capture(*args, **kwargs):
            """Expose only the owned process-group identifier, never source content or credentials."""
            child = await original(*args, **kwargs)
            connection.send(child.pid)
            return child

        module.asyncio.create_subprocess_exec = capture
        await QwenEmbedding().encode(plan)

    asyncio.run(run())


@pytest.mark.asyncio
async def test_actual_parent_sigkill_terminates_encoder_process_group():
    """Verify pidfd supervision stops model children even when their API-side parent dies abruptly."""
    import asyncio
    import multiprocessing
    import signal

    if os.environ.get("LOCAL_ASSISTANT_EMBEDDING_COMPARE_LIVE") != "1":
        pytest.skip("explicit actual encoder crash flag not configured")
    selection = json.loads((ROOT / "configs/embedding-selected.json").read_text())
    plan = make_plan(selection, count=200)
    context = multiprocessing.get_context("spawn")
    parent, child = context.Pipe(duplex=False)
    process = context.Process(target=encoder_parent_process, args=(plan, child))
    group = None

    def members():
        """Read only live group members and resident page counts for the owned fault-test group."""
        result = []
        for entry in Path("/proc").iterdir():
            if not entry.name.isdigit():
                continue
            try:
                fields = (entry / "stat").read_text().rsplit(")", 1)[1].split()
                if int(fields[2]) == group and fields[0] != "Z":
                    pages = int((entry / "statm").read_text().split()[1])
                    result.append((int(entry.name), pages))
            except (OSError, ValueError, IndexError):
                continue
        return result

    process.start()
    child.close()
    try:
        assert await asyncio.to_thread(parent.poll, 10)
        group = parent.recv()
        for _ in range(200):
            if any(
                pages * os.sysconf("SC_PAGE_SIZE") > 64 * 1024**2
                for pid, pages in members()
            ):
                break
            await asyncio.sleep(0.05)
        else:
            raise AssertionError(
                "encoder never reached supervised model initialization"
            )
        os.kill(process.pid, signal.SIGKILL)
        await asyncio.to_thread(process.join, 5)
        assert process.exitcode == -signal.SIGKILL
        for _ in range(100):
            if not members():
                break
            await asyncio.sleep(0.05)
        assert not members()
    finally:
        if process.is_alive():
            process.kill()
            await asyncio.to_thread(process.join, 5)
        if group is not None:
            try:
                os.killpg(group, signal.SIGKILL)
            except ProcessLookupError:
                pass
        parent.close()
