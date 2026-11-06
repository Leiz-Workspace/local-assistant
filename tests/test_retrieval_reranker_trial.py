"""Verify evaluation-only source-held ranking, strict replies and joined nonqueued process admission."""

import asyncio
import copy
import json
import os
import sys
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

from scripts import retrieval_reranker_trial as trial
from scripts.qwen_reranker_trial_worker import validate_request
from src.application.services.file_storage_policy import StoragePolicyError


@pytest.fixture
def hits():
    """Provide synthetic source rows for protocol tests without representing real retrieval quality."""
    return [
        dict(
            point_id=str(i),
            text="source " + str(i),
            score=0.9 - i / 10,
            source_sha256="filehash",
            provenance={"owner_id": "test-owner"},
        )
        for i in range(3)
    ]


def reply(request):
    """Create explicit fake scores for identity/protocol testing, never retained as benchmark evidence."""
    old = json.loads(
        (trial.ROOT / "docs/evidence/d27-t02-reranker-comparison.json").read_text()
    )
    return dict(
        profile_sha256=request["profile_sha256"],
        model_fingerprint=old["actual_worker"]["model_fingerprint"],
        rows=[
            dict(
                id=row["id"],
                text_sha256=row["text_sha256"],
                score=0.5,
                tokens=64,
                logits=[0, 0],
            )
            for row in request["candidates"]
        ],
        model_initialization_seconds=1.0,
        worker_wall_seconds=2.0,
        peak_rss_mib=1500.0,
        cpu_seconds=3.0,
        gpu_allocation_bytes=0,
    )


def test_request_exact_chunk_binding(hits):
    """Bind actual chunk text separately from immutable whole-file source hashes and reject text drift."""
    request = trial.build_request("query", hits)
    assert request["candidates"][0]["text_sha256"] != hits[0]["source_sha256"]
    assert validate_request(request) is request
    request["candidates"][0]["text"] += " changed"
    with pytest.raises(ValueError, match="source_invalid"):
        validate_request(request)


@pytest.mark.parametrize(
    "fault",
    ["missing", "duplicate", "empty", "overflow", "query", "extra", "hash", "id"],
)
def test_invalid_request_rejected(hits, fault):
    """Reject oversized, duplicate, incomplete and wrong-identity input before model loading."""
    request = trial.build_request("query", hits)
    if fault == "missing":
        request.pop("query")
    elif fault == "duplicate":
        request["candidates"][1] = copy.deepcopy(request["candidates"][0])
    elif fault == "empty":
        request["candidates"] = []
    elif fault == "overflow":
        request["candidates"] *= 4
    elif fault == "query":
        request["query"] = "x" * 4097
    elif fault == "extra":
        request["candidates"][0]["untrusted_label"] = True
    elif fault == "hash":
        request["profile_sha256"] = "changed"
    else:
        request["candidates"][0]["id"] = None
    with pytest.raises(ValueError):
        validate_request(request)


@pytest.mark.parametrize(
    "fault",
    [
        "profile",
        "fingerprint",
        "missing",
        "duplicate",
        "foreign",
        "hash",
        "score",
        "bool_score",
        "nan",
        "logits",
        "tokens",
        "bool_tokens",
        "cpu",
        "ram",
        "wall",
        "init",
        "gpu",
        "bool_gpu",
        "extra",
    ],
)
def test_invalid_reply_rejected(hits, fault):
    """Reject incomplete source accounting and invalid identity, scores, tokens or actual resource fields."""
    request = trial.build_request("query", hits)
    result = reply(request)
    row = result["rows"][0]
    if fault == "profile":
        result["profile_sha256"] = "changed"
    elif fault == "fingerprint":
        result["model_fingerprint"] = "changed"
    elif fault == "missing":
        result["rows"].pop()
    elif fault == "duplicate":
        result["rows"][1] = copy.deepcopy(row)
    elif fault == "foreign":
        row["id"] = "unknown"
    elif fault == "hash":
        row["text_sha256"] = "unknown"
    elif fault == "score":
        row["score"] = 0.9
    elif fault == "bool_score":
        row["score"] = True
    elif fault == "nan":
        row["score"] = float("nan")
    elif fault == "logits":
        row["logits"] = [float("nan"), 0]
    elif fault == "tokens":
        row["tokens"] = 513
    elif fault == "bool_tokens":
        row["tokens"] = True
    elif fault == "cpu":
        result["cpu_seconds"] = 121
    elif fault == "ram":
        result["peak_rss_mib"] = 4097
    elif fault == "wall":
        result["worker_wall_seconds"] = float("inf")
    elif fault == "init":
        result["model_initialization_seconds"] = True
    elif fault == "gpu":
        result["gpu_allocation_bytes"] = 1
    elif fault == "bool_gpu":
        result["gpu_allocation_bytes"] = False
    else:
        row["text"] = "forged"
    with pytest.raises(ValueError):
        trial.validate_reply(request, result)


class Dense:
    """Model source-reader lifetime for isolated wrapper faults without simulating model quality."""

    def __init__(self, hits):
        """Create independently observable admission, ownership and final-fence state."""
        self.hits = hits
        self.closing = False
        self.held = False
        self.changed = False
        self.validations = 0
        self.admission = asyncio.Lock()
        self.ingestion = SimpleNamespace(
            encoder=SimpleNamespace(admission=asyncio.Lock())
        )

    @asynccontextmanager
    async def operation(self, owner, query, **options):
        """Keep reader state and nonqueued admission until response context closes."""
        if self.admission.locked():
            raise StoragePolicyError("retrieval_busy", 429)
        if self.closing:
            raise StoragePolicyError("retrieval_unavailable", 503)
        await self.admission.acquire()
        self.held = True
        try:
            yield (
                dict(hits=copy.deepcopy(self.hits), candidate_limit=50, top_k=10),
                ["retained"],
            )
        finally:
            self.held = False
            self.admission.release()

    async def validate(self, owner, retained):
        """Reject changed source state while exposing the exact retained reader lifetime."""
        assert self.held and retained == ["retained"]
        self.validations += 1
        if self.changed:
            raise StoragePolicyError("retrieval_source_changed", 409)

    async def shutdown(self):
        """Mark the underlying lifecycle as closing for delegation verification."""
        self.closing = True


class Ranker:
    """Supply controlled pair logits while inspecting live source ownership in wrapper tests."""

    def __init__(self, dense, *, change=False, corrupt=False):
        """Retain only explicit protocol fault switches."""
        self.dense = dense
        self.change = change
        self.corrupt = corrupt
        self.calls = 0

    async def rank(self, query, hits):
        """Require held source readers and return ascending synthetic per-ID relevance."""
        self.calls += 1
        assert self.dense.held
        result = reply(trial.build_request(query, hits))
        from scripts.qwen_reranker_runtime import yes_probability

        for i, row in enumerate(result["rows"]):
            row.update(score=yes_probability([0, i]), logits=[0, i])
        if self.corrupt:
            result["rows"][0]["id"] = "foreign"
        self.dense.changed = self.change
        return result


@pytest.mark.asyncio
async def test_ranking_reader_lifetime_original_fields_and_final_fence(hits):
    """Retain readers through delivery, preserve source/dense fields and reject changes after yield."""
    original = copy.deepcopy(hits)
    dense = Dense(hits)
    ranker = Ranker(dense)
    service = trial.TrialRetrievalService(dense, reranker=ranker)
    async with service.operation("owner", "query", top_k=2) as (data, retained):
        assert dense.held and dense.validations == 2
        assert [row["point_id"] for row in data["hits"]] == ["2", "1"]
        assert data["hits"][0]["score"] == original[2]["score"]
        assert data["hits"][0]["text"] == original[2]["text"]
        assert data["hits"][0]["provenance"] == original[2]["provenance"]
        assert data["top_k"] == 2 and len(service.observations) == 1
        dense.changed = True
        with pytest.raises(StoragePolicyError):
            await service.validate("owner", retained)
    assert not dense.held and not dense.admission.locked() and hits == original
    await service.shutdown()
    assert service.closing


@pytest.mark.parametrize("fault", ["changed", "corrupt"])
@pytest.mark.asyncio
async def test_no_delivery_on_post_model_source_or_reply_failure(hits, fault):
    """Reject changed source state or a forged candidate before yielding any response payload."""
    dense = Dense(hits)
    service = trial.TrialRetrievalService(
        dense,
        reranker=Ranker(dense, change=fault == "changed", corrupt=fault == "corrupt"),
    )
    with pytest.raises((StoragePolicyError, ValueError)):
        async with service.operation("owner", "query"):
            pytest.fail("must not yield")
    assert not dense.held and not dense.admission.locked()


@pytest.mark.asyncio
async def test_empty_result_skips_model_and_no_queue(hits):
    """Avoid empty model requests and retain normal response-lifetime nonqueued admission."""
    dense = Dense([])
    ranker = Ranker(dense)
    service = trial.TrialRetrievalService(dense, reranker=ranker)
    async with service.operation("owner", "query") as (data, _):
        assert data["hits"] == [] and ranker.calls == 0
        with pytest.raises(StoragePolicyError) as caught:
            async with service.operation("owner", "query"):
                pass
        assert caught.value.status_code == 429


@pytest.mark.asyncio
async def test_shared_embedding_slot_not_queued(monkeypatch, hits):
    """Refuse a ranking child when the actual shared model slot is occupied."""

    def verified():
        """Bypass only disk freeze checks in an admission-only unit test."""
        return None

    monkeypatch.setattr(trial, "verify_freeze", verified)
    admission = asyncio.Lock()
    await admission.acquire()
    with pytest.raises(StoragePolicyError) as caught:
        await trial.TrialReranker(admission).rank("query", hits)
    assert caught.value.status_code == 429 and admission.locked()
    admission.release()


@pytest.mark.parametrize("mode", ["cancel", "launch_gap", "timeout"])
@pytest.mark.asyncio
async def test_actual_owned_child_join_before_slot_release(monkeypatch, hits, mode):
    """Join a real controlled subprocess on every interrupt and exclude operator credentials."""
    original = asyncio.create_subprocess_exec
    launched = asyncio.Event()
    children = []
    admission = asyncio.Lock()

    def verified():
        """Bypass only artifact checks for a controlled subprocess-protocol fault."""
        return None

    async def launch(*args, **kwargs):
        """Replace only inference with a real owned sleeper while preserving launch/env/pipe handling."""
        assert (
            admission.locked()
            and "VAULT_TOKEN" not in kwargs["env"]
            and "DATABASE_URL" not in kwargs["env"]
        )
        child = await original(
            sys.executable, "-c", "import time; time.sleep(30)", **kwargs
        )
        children.append(child)
        launched.set()
        if mode == "launch_gap":
            await asyncio.sleep(0.05)
        return child

    monkeypatch.setenv("VAULT_TOKEN", "TEST-ONLY")
    monkeypatch.setenv("DATABASE_URL", "TEST-ONLY")
    monkeypatch.setattr(trial, "verify_freeze", verified)
    monkeypatch.setattr(trial.asyncio, "create_subprocess_exec", launch)
    service = trial.TrialReranker(admission, timeout=0.02 if mode == "timeout" else 90)
    task = asyncio.create_task(service.rank("query", hits))
    await launched.wait()
    if mode != "timeout":
        task.cancel()
    with pytest.raises((asyncio.CancelledError, StoragePolicyError)):
        await task
    assert children[0].returncode is not None and not admission.locked()
    with pytest.raises(ProcessLookupError):
        os.kill(children[0].pid, 0)


@pytest.mark.parametrize("timeout", [0, -1, 91, True, float("nan")])
def test_invalid_timeout(timeout):
    """Reject invalid process wall budgets before admission or subprocess creation."""
    with pytest.raises(ValueError):
        trial.TrialReranker(asyncio.Lock(), timeout=timeout)
