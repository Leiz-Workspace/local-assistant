"""Measure isolated authenticated ASGI retrieval/ranking and bounded CORE traffic using existing owned resources."""

import asyncio
import hashlib
import json
import logging
import os
import threading
import time
from pathlib import Path

import httpx
import numpy as np
import pytest
from test_file_http import owned_service as owned_service
from test_ingestion_http import upload, wait_job
from test_ingestion_worker import worker_context as worker_context
from test_retrieval import indexed
from test_retrieval_http import retrieval_client as retrieval_client
from test_retrieval_reranker_trial import reply

from scripts.retrieval_reranker_trial import (
    ROOT,
    TrialReranker,
    TrialRetrievalService,
    build_request,
)
from src.application.services.file_storage_policy import StoragePolicyError

logger = logging.getLogger(__name__)


@pytest.fixture(autouse=True)
def actual_trial_flag():
    """Require the existing explicit local model evaluation flag for shared-service trial execution."""
    if os.environ.get("LOCAL_ASSISTANT_EMBEDDING_COMPARE_LIVE") != "1":
        pytest.skip("explicit existing actual model evaluation flag required")


@pytest.fixture
def trial_client(retrieval_client):
    """Inject only one test instance and restore unchanged dense routing before actual app shutdown."""
    client, auth = retrieval_client
    dense = client.app.state.retrieval_service
    trial = TrialRetrievalService(dense)
    assert trial.reranker.admission is dense.ingestion.encoder.admission
    client.app.state.retrieval_service = trial
    try:
        yield client, auth, dense, trial
    finally:
        client.app.state.retrieval_service = dense


def timed_search(client, headers, query, *, expected_files, ranking):
    """Measure authenticated ASGI response completion including real model/source/final-fence work."""
    started = time.monotonic()
    response = client.post(
        "/api/v1/retrieval/search", headers=headers, json=dict(query=query, top_k=10)
    )
    ended = time.monotonic()
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "private, no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    data = response.json()
    assert {row["file_id"] for row in data["hits"]} == expected_files
    if ranking:
        assert data["ranking"] == "evaluation_only_qwen_batch4"
        assert [
            (-row["reranker_score"], row["point_id"]) for row in data["hits"]
        ] == sorted((-row["reranker_score"], row["point_id"]) for row in data["hits"])
    assert ended - started <= 90
    return dict(
        seconds=ended - started,
        start_monotonic=started,
        end_monotonic=ended,
        response_bytes=len(response.content),
        response_sha256=hashlib.sha256(response.content).hexdigest(),
        hits=[
            {key: row[key] for key in ("point_id", "file_id", "source_sha256", "score")}
            | ({"reranker_score": row["reranker_score"]} if ranking else {})
            for row in data["hits"]
        ],
    )


def core_request(client):
    """Time one explicitly bounded existing CORE completion without retaining prompts or generated text."""
    started = time.monotonic()
    response = client.post(
        "http://127.0.0.1:8080/v1/chat/completions",
        json=dict(
            model="qwen3.5-9b-core",
            messages=[dict(role="user", content="Return OK.")],
            temperature=0,
            max_tokens=16,
            stream=False,
            chat_template_kwargs=dict(enable_thinking=False),
        ),
    )
    response.raise_for_status()
    payload = response.json()
    assert len(payload["choices"]) == 1 and payload["usage"]["completion_tokens"] <= 16
    return dict(
        seconds=time.monotonic() - started,
        start_monotonic=started,
        end_monotonic=time.monotonic(),
        completion_tokens=payload["usage"]["completion_tokens"],
    )


def core_traffic(stop, started, rows, errors):
    """Run at most120 sequential CORE requests,90s admission window and10s per-call timeout."""
    try:
        with httpx.Client(
            trust_env=False, timeout=10, follow_redirects=False
        ) as client:
            deadline = time.monotonic() + 90
            started.set()
            for _ in range(120):
                if stop.is_set() or time.monotonic() >= deadline:
                    break
                rows.append(core_request(client))
                if stop.wait(0.5):
                    break
    except Exception as exc:
        errors.append(type(exc).__name__)
        logger.warning("trial_core_traffic_failed category=%s", type(exc).__name__)
    finally:
        started.set()


def latency_summary(rows):
    """Summarize observed samples descriptively without asserting a production or population SLO."""
    values = [row["seconds"] for row in rows]
    return dict(
        samples=len(values),
        mean_seconds=float(np.mean(values)),
        p50_seconds=float(np.percentile(values, 50)),
        p95_seconds=float(np.percentile(values, 95)),
        max_seconds=max(values),
    )


def test_actual_http_reranking_and_bounded_core_contention(trial_client):
    """Retain real complete request times and source/owner isolation while bounded local CORE traffic overlaps."""
    client, auth, dense, trial = trial_client
    from scripts.reranker_request_probe import load_query

    frozen = load_query()
    query = frozen["text"]
    headers, foreign_headers = auth["headers"]
    expected_files = set()
    bindings = []
    for document in frozen["documents"]:
        identifier = upload(
            client, headers, document["text"].encode(), "trial-" + document["id"]
        )
        admitted = client.post(f"/api/v1/files/{identifier}/index", headers=headers)
        assert (
            admitted.status_code == 202
            and wait_job(client, headers, admitted.json()["id"])["active"]
        )
        expected_files.add(identifier)
        bindings.append(
            dict(
                document_id=document["id"],
                file_id=identifier,
                source_sha256=hashlib.sha256(document["text"].encode()).hexdigest(),
            )
        )
    foreign = upload(
        client,
        foreign_headers,
        frozen["documents"][0]["text"].encode(),
        "trial-foreign",
    )
    admitted = client.post(f"/api/v1/files/{foreign}/index", headers=foreign_headers)
    assert (
        admitted.status_code == 202
        and wait_job(client, foreign_headers, admitted.json()["id"])["active"]
    )
    client.app.state.retrieval_service = dense
    baseline = [
        timed_search(
            client, headers, query, expected_files=expected_files, ranking=False
        )
        for _ in range(3)
    ]
    client.app.state.retrieval_service = trial
    idle = [
        timed_search(
            client, headers, query, expected_files=expected_files, ranking=True
        )
        for _ in range(3)
    ]
    with httpx.Client(trust_env=False, timeout=10, follow_redirects=False) as core:
        core_baseline = [core_request(core) for _ in range(3)]
    stop, started = threading.Event(), threading.Event()
    core_rows = []
    errors = []
    traffic = threading.Thread(
        target=core_traffic, args=(stop, started, core_rows, errors), daemon=True
    )
    traffic.start()
    try:
        assert started.wait(10)
        concurrent = [
            timed_search(
                client, headers, query, expected_files=expected_files, ranking=True
            )
            for _ in range(6)
        ]
    finally:
        stop.set()
        traffic.join(15)
    assert not traffic.is_alive() and not errors and len(core_rows) >= 3
    overlaps = sum(
        any(
            c["start_monotonic"] < r["end_monotonic"]
            and r["start_monotonic"] < c["end_monotonic"]
            for r in concurrent
        )
        for c in core_rows
    )
    assert overlaps >= 3
    assert all(
        any(
            c["start_monotonic"] < r["end_monotonic"]
            and r["start_monotonic"] < c["end_monotonic"]
            for c in core_rows
        )
        for r in concurrent
    )
    before = len(trial.observations)
    narrowed = client.post(
        "/api/v1/retrieval/search",
        headers=headers,
        json=dict(query=query, top_k=3, file_ids=[foreign]),
    )
    assert (
        narrowed.status_code == 200
        and narrowed.json()["hits"] == []
        and len(trial.observations) == before
    )
    own = timed_search(
        client, foreign_headers, query, expected_files={foreign}, ranking=True
    )
    report = dict(
        description="Actual existing authenticated in-process ASGI HTTP path plus isolated evaluation-only reranking and bounded real localhost CORE traffic; no TCP/network or production-load certification, human labels or adoption.",
        query_id=frozen["id"],
        source_bindings=bindings,
        foreign_owner_source_excluded=True,
        narrowed_foreign_scope_empty=True,
        dense_baseline=baseline,
        trial_idle=idle,
        trial_concurrent_core=concurrent,
        core_baseline=core_baseline,
        core_traffic=core_rows,
        overlapped_core_requests=overlaps,
        foreign_owner_own_response=own,
        worker_observations=list(trial.observations),
        summaries=dict(
            dense_asgi=latency_summary(baseline),
            trial_idle_asgi=latency_summary(idle),
            trial_with_core_asgi=latency_summary(concurrent),
            core_idle=latency_summary(core_baseline),
            core_during_trial=latency_summary(core_rows),
        ),
        transport="in_process_ASGI_not_TCP",
        ranking_deployed=False,
        human_quality_validated=False,
        persistent_model_coresidency_measured=False,
        production_load_certified=False,
    )
    output = Path("data/backups/d27-t03-latest-http-trial.json")
    output.touch(mode=0o600, exist_ok=True)
    output.chmod(0o600)
    output.write_text(json.dumps(report, indent=2) + "\n")
    logger.info(
        "trial_http_core_drill_completed candidate_requests=%d core_requests=%d",
        9,
        len(core_rows),
    )


class BlockedRanker:
    """Block only ranking delay to test real SQL/source changes independently of model quality."""

    def __init__(self):
        """Create explicit arrival/release signals for deterministic source lifecycle faults."""
        self.entered = asyncio.Event()
        self.release = asyncio.Event()

    async def rank(self, query, hits):
        """Pause with source readers retained, then return an explicitly synthetic protocol reply."""
        self.entered.set()
        await self.release.wait()
        return reply(build_request(query, hits))


@pytest.mark.parametrize("change", ["delete", "supersede"])
@pytest.mark.asyncio
async def test_actual_source_change_during_ranking_fails_closed(
    worker_context, monkeypatch, change
):
    """Fence changed real owner/source/generation after the ranking delay without returning stale content."""
    worker, dense, owner, file_id, job = await indexed(worker_context, monkeypatch)
    blocked = BlockedRanker()
    trial = TrialRetrievalService(dense, reranker=blocked)

    async def consume():
        """Fail if a stale real source can enter a response after the delayed candidate scoring."""
        async with trial.operation(owner, "query"):
            pytest.fail("stale source must not yield")

    task = asyncio.create_task(consume())
    await asyncio.wait_for(blocked.entered.wait(), 10)
    if change == "delete":
        await worker.files.delete(owner, file_id)
    else:
        replacement = await worker.admit(owner, file_id, max_bytes=512)
        assert replacement["id"] != job["id"]
        assert (await worker.process(owner, replacement["id"]))["state"] == "ready"
    blocked.release.set()
    with pytest.raises(StoragePolicyError) as caught:
        await task
    assert caught.value.status_code == 409
    assert not dense.admission.locked() and not worker.files.active
    await trial.shutdown()


@pytest.mark.parametrize("mode", ["cancel", "shutdown"])
@pytest.mark.asyncio
async def test_actual_trial_model_cancel_and_shutdown_join(
    worker_context, monkeypatch, mode
):
    """Join the actual ranking worker and retained real source resources during cancellation or shutdown."""
    worker, dense, owner, _, _ = await indexed(worker_context, monkeypatch)
    shared = asyncio.Lock()
    ranker = TrialReranker(shared)
    service = TrialRetrievalService(dense, reranker=ranker)
    original = asyncio.create_subprocess_exec
    launched = asyncio.Event()
    children = []

    async def capture(*args, **kwargs):
        """Capture only the real ranking child while leaving source-extraction subprocesses untouched."""
        child = await original(*args, **kwargs)
        if any("qwen_reranker_trial_worker.py" in str(arg) for arg in args):
            children.append(child)
            launched.set()
        return child

    async def consume():
        """Keep source ownership around the actual ranking subprocess until interrupted."""
        async with service.operation(owner, "query"):
            await asyncio.sleep(30)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", capture)
    task = asyncio.create_task(consume())
    await asyncio.wait_for(launched.wait(), 10)
    if mode == "cancel":
        task.cancel()
    else:
        await service.shutdown()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert (
        children[0].returncode is not None
        and not shared.locked()
        and not dense.admission.locked()
        and not worker.files.active
    )
    await service.shutdown()
