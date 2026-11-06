"""Check isolated request-cost evidence, complete pair identity and actual optional CPU/resource boundaries."""

import asyncio
import copy
import json
import os
import sys
from pathlib import Path

import pytest

from scripts import reranker_request_probe as probe
from scripts.qwen_reranker_runtime import yes_probability
from scripts.reranker_comparison import build_request


@pytest.fixture
def result():
    """Build clearly synthetic protocol evidence using the retained model identity, never benchmark it."""
    previous = json.loads(
        (probe.ROOT / "docs/evidence/d27-t02-reranker-comparison.json").read_text()
    )
    query = build_request()["queries"][0]
    pair = {"tokens": 64, "logits": [0.0, 0.0], "score": 0.5}
    request = {
        "seconds": 1.0,
        "pairs": [{"document_id": doc["id"], **pair} for doc in query["documents"]],
    }
    return {
        "description": "TEST FIXTURE ONLY",
        "model_fingerprint": previous["actual_worker"]["model_fingerprint"],
        "profile_sha256": previous["profile_sha256"],
        "query_id": query["id"],
        "first_request": copy.deepcopy(request),
        "warm_requests": [copy.deepcopy(request) for _ in range(3)],
        "boundary_512": {**pair, "tokens": 512, "seconds": 1.0},
        "boundary_513_rejected": True,
        "worker_start_to_first_request_seconds": 5.0,
        "model_initialization_seconds": 2.0,
        "peak_worker_rss_mib": 1600.0,
        "worker_cpu_seconds": 20.0,
        "gpu_allocation_bytes": 0,
        "http_e2e_measured": False,
        "concurrent_core_measured": False,
        "adoption_approved": False,
    }


def test_protocol_accepts_only_complete_scoped_result(result):
    """Accept complete protocol rows while preserving explicit unmeasured HTTP/concurrency flags."""
    assert probe.validate_result(result) is result
    assert result["http_e2e_measured"] is False


@pytest.mark.parametrize(
    "fault,error",
    [
        ("fingerprint", "identity"),
        ("profile", "identity"),
        ("query", "identity"),
        ("rss", "budget"),
        ("cpu", "budget"),
        ("gpu", "budget"),
        ("nan", "resource"),
        ("bool_ram", "resource"),
        ("http", "scope"),
        ("concurrency", "scope"),
        ("adoption", "scope"),
        ("overflow", "scope"),
        ("warm_count", "scope"),
        ("pair_count", "pairs"),
        ("order", "pairs"),
        ("timing", "pairs"),
        ("logits", "logits"),
        ("score", "pair"),
        ("tokens", "pair"),
        ("boundary", "boundary"),
    ],
)
def test_corrupted_result_rejected(result, fault, error):
    """Reject altered identity, missing pairs, false scope claims and invalid resources or scores."""
    row = result["first_request"]["pairs"][0]
    if fault in ("fingerprint", "profile", "query"):
        result[
            {
                "fingerprint": "model_fingerprint",
                "profile": "profile_sha256",
                "query": "query_id",
            }[fault]
        ] = "changed"
    elif fault in ("rss", "cpu", "gpu"):
        result[
            {
                "rss": "peak_worker_rss_mib",
                "cpu": "worker_cpu_seconds",
                "gpu": "gpu_allocation_bytes",
            }[fault]
        ] = {"rss": 4097, "cpu": 121, "gpu": 1}[fault]
    elif fault == "nan":
        result["worker_cpu_seconds"] = float("nan")
    elif fault == "bool_ram":
        result["peak_worker_rss_mib"] = True
    elif fault in ("http", "concurrency", "adoption"):
        result[
            {
                "http": "http_e2e_measured",
                "concurrency": "concurrent_core_measured",
                "adoption": "adoption_approved",
            }[fault]
        ] = True
    elif fault == "overflow":
        result["boundary_513_rejected"] = False
    elif fault == "warm_count":
        result["warm_requests"].pop()
    elif fault == "pair_count":
        result["first_request"]["pairs"].pop()
    elif fault == "order":
        result["first_request"]["pairs"].reverse()
    elif fault == "timing":
        result["first_request"]["seconds"] = float("inf")
    elif fault == "logits":
        row["logits"] = [float("nan"), 0]
    elif fault == "score":
        row["score"] = 0.9
    elif fault == "tokens":
        row["tokens"] = 513
    else:
        result["boundary_512"]["tokens"] = 511
    with pytest.raises(ValueError, match=error):
        probe.validate_result(result)


def test_request_preserves_batch_alignment():
    """Verify exact 4+4+2 batching and runtime tuple alignment independently of inference."""
    seen = []

    class Model:
        """Expose predictable tuple scores for batch-accounting verification only."""

        def score_batch(self, query, documents):
            """Return unique count markers in the exact supplied order."""
            seen.append(list(documents))
            return [(0.5, int(text) + 1, (0, 0)) for text in documents]

    query = {
        "text": "query",
        "documents": [{"id": str(i), "text": str(i)} for i in range(10)],
    }
    result = probe.score_request(Model(), query)
    assert list(map(len, seen)) == [4, 4, 2]
    assert [row["tokens"] for row in result["pairs"]] == list(range(1, 11))


def test_request_refuses_dropped_model_rows():
    """Fail closed when a runtime omits an expected candidate pair."""

    class Model:
        """Inject a missing model result for a bounded protocol failure."""

        def score_batch(self, query, documents):
            """Return no results to exercise complete-pair validation."""
            return []

    with pytest.raises(ValueError, match="pairs_incomplete"):
        probe.score_request(Model(), build_request()["queries"][0])


@pytest.mark.parametrize("timeout", [0, -1, 181, float("nan"), True])
@pytest.mark.asyncio
async def test_invalid_timeout_rejected(timeout):
    """Reject unsupported process budgets before launching any worker."""
    with pytest.raises(ValueError, match="timeout_invalid"):
        await probe.run_probe(timeout=timeout)


@pytest.mark.asyncio
async def test_actual_isolated_request_resource_probe():
    """Measure real CPU model startup, warm requests and full512 forward with original frozen source inputs."""
    if os.environ.get("LOCAL_ASSISTANT_EMBEDDING_COMPARE_LIVE") != "1":
        pytest.skip("explicit existing actual model-evaluation flag required")
    report = await probe.run_probe()
    path = Path("data/backups/d27-t03-latest-request-probe.json")
    path.touch(mode=0o600, exist_ok=True)
    path.chmod(0o600)
    path.write_text(json.dumps(report, indent=2) + "\n")
    assert report["boundary_512"]["tokens"] == 512
    assert (
        abs(
            report["boundary_512"]["score"]
            - yes_probability(report["boundary_512"]["logits"])
        )
        <= 1e-7
    )
    assert not report["http_e2e_measured"] and not report["concurrent_core_measured"]
    assert report["parent_total_probe_seconds"] <= 185
    await asyncio.sleep(0)


@pytest.mark.parametrize("mode", ["cancel", "launch_gap", "timeout"])
@pytest.mark.asyncio
async def test_owned_process_join_and_secret_free_environment(monkeypatch, mode):
    """Interrupt a real controlled subprocess and verify joined cancellation without credential inheritance."""
    original = asyncio.create_subprocess_exec
    launched = asyncio.Event()
    children = []

    def frozen():
        """Bypass only artifact verification for a controlled process-protocol fault."""
        return None

    async def launch(*args, **kwargs):
        """Run an owned sleeper with the real adapter environment instead of model inference."""
        assert "VAULT_TOKEN" not in kwargs["env"]
        assert "DATABASE_URL" not in kwargs["env"]
        child = await original(
            sys.executable, "-c", "import time; time.sleep(30)", **kwargs
        )
        children.append(child)
        launched.set()
        if mode == "launch_gap":
            await asyncio.sleep(0.05)
        return child

    monkeypatch.setenv("VAULT_TOKEN", "TEST-ONLY-SECRET")
    monkeypatch.setenv("DATABASE_URL", "TEST-ONLY-SECRET")
    monkeypatch.setattr(probe, "verify_freeze", frozen)
    monkeypatch.setattr(probe.asyncio, "create_subprocess_exec", launch)
    task = asyncio.create_task(
        probe.run_probe(timeout=0.01 if mode == "timeout" else 180)
    )
    await launched.wait()
    if mode != "timeout":
        task.cancel()
    with pytest.raises((asyncio.CancelledError, TimeoutError)):
        await task
    assert children[0].returncode is not None
    with pytest.raises(ProcessLookupError):
        os.kill(children[0].pid, 0)
