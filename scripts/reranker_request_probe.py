"""Measure isolated CPU request startup, warm ten-pair cost and actual 512-token forward without API adoption."""
# /// script
# requires-python = ">=3.12,<3.13"
# dependencies = ["torch==2.10.0+cpu", "transformers==4.57.6", "numpy==2.5.4", "httpx==0.28.1", "typing-extensions==4.15.0"]
# [tool.uv.sources]
# torch = { index = "pytorch-cpu" }
# [[tool.uv.index]]
# name = "pytorch-cpu"
# url = "https://download.pytorch.org/whl/cpu"
# explicit = true
# ///

import asyncio
import hashlib
import json
import logging
import math
import os
import resource
import shutil
import signal
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
logger = logging.getLogger(__name__)
WORKER = Path(__file__).resolve()
FREEZE = ROOT / "docs/evidence/d27-t03-request-probe-freeze.json"


def verify_freeze():
    """Reject execution drift from the separately frozen resource-only probe before inference."""
    execution = json.loads(
        (ROOT / "docs/evidence/d27-t02-execution-manifest.json").read_text()
    )
    if execution["scope"] != "EVALUATION_ONLY_NO_ADOPTION":
        raise ValueError("request_probe_parent_manifest_invalid")
    for name, expected_hash in execution["sha256"].items():
        if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != expected_hash:
            raise ValueError("request_probe_parent_source_changed")
    freeze = json.loads(FREEZE.read_text())
    expected = {
        "scripts/reranker_request_probe.py",
        "scripts/reranker_request_probe.py.lock",
        "tests/test_reranker_request_probe.py",
        "docs/evidence/d27-t02-reranker-comparison.json",
        "docs/evidence/d27-t02-execution-manifest.json",
    }
    if (
        freeze["scope"] != "RESOURCE_ONLY_NO_NEW_RELEVANCE_INFERENCE"
        or set(freeze["sha256"]) != expected
    ):
        raise ValueError("request_probe_freeze_invalid")
    for name, digest in freeze["sha256"].items():
        if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != digest:
            raise ValueError("request_probe_source_changed")
    logger.info("request_probe_freeze_verified")


def load_query():
    """Read only the first unchanged diagnostic query and its ten hash-verified source candidates."""
    corpus = json.loads((ROOT / "tests/fixtures/retrieval/d27-corpus.json").read_text())
    baseline = json.loads(
        (ROOT / "docs/evidence/d27-retrieval-baseline.json").read_text()
    )
    query = corpus["queries"][0]
    documents = {row["id"]: row["text"] for row in corpus["documents"]}
    ranking = next(
        row["ranking"] for row in baseline["queries"] if row["query_id"] == query["id"]
    )
    if len(ranking) != 10 or len({row["document_id"] for row in ranking}) != 10:
        raise ValueError("request_probe_candidates_invalid")
    for row in ranking:
        if (
            hashlib.sha256(documents[row["document_id"]].encode()).hexdigest()
            != row["source_sha256"]
        ):
            raise ValueError("request_probe_source_hash_invalid")
    logger.info("request_probe_source_query_verified")
    return {
        "id": query["id"],
        "text": query["text"],
        "documents": [
            {"id": row["document_id"], "text": documents[row["document_id"]]}
            for row in ranking
        ],
    }


def pair_result(value):
    """Name the unchanged runtime tuple fields without changing model scores or counts."""
    score, tokens, logits = value
    return {"score": score, "tokens": tokens, "logits": list(logits)}


def score_request(model, query):
    """Time one ten-candidate request with the unchanged batch4 contract and complete pair accounting."""
    started = time.perf_counter()
    rows = []
    for offset in range(0, 10, 4):
        documents = query["documents"][offset : offset + 4]
        scores = model.score_batch(query["text"], [row["text"] for row in documents])
        if len(scores) != len(documents):
            raise ValueError("request_probe_pairs_incomplete")
        rows.extend(
            dict(document_id=document["id"], **pair_result(score))
            for document, score in zip(documents, scores, strict=True)
        )
    logger.info("request_probe_request_completed pairs=%d", len(rows))
    return {"seconds": time.perf_counter() - started, "pairs": rows}


def measure(started):
    """Measure fresh-worker import/load/first request separately from three warm requests and stress-only input."""
    from scripts.qwen_reranker_runtime import QwenRerankerCpu, pair_tokens, profile

    query = load_query()
    load_started = time.perf_counter()
    model = QwenRerankerCpu(profile())
    load_seconds = time.perf_counter() - load_started
    first = score_request(model, query)
    first_complete = time.perf_counter() - started
    warm = [score_request(model, query) for _ in range(3)]
    boundary = next(
        (
            count
            for count in range(350, 513)
            if len(
                pair_tokens(model.tokenizer, " x" * count, "document", max_tokens=4096)
            )
            == 512
        ),
        None,
    )
    if boundary is None:
        raise ValueError("request_probe_boundary_missing")
    boundary_started = time.perf_counter()
    long_pair = pair_result(model.score(" x" * boundary, "document"))
    boundary_seconds = time.perf_counter() - boundary_started
    if long_pair["tokens"] != 512:
        raise ValueError("request_probe_boundary_invalid")
    try:
        model.score(" x" * (boundary + 1), "document")
    except ValueError as exc:
        if str(exc) != "reranker_pair_token_limit":
            raise
    else:
        raise ValueError("request_probe_overflow_accepted")
    usage = resource.getrusage(resource.RUSAGE_SELF)
    logger.info("request_probe_resource_measurement_complete")
    return {
        "description": "Actual isolated worker cost on an old diagnostic query plus meaningless stress tokens; no HTTP, embedding, source retrieval, concurrent-service measurement or human quality claim.",
        "model_fingerprint": model.fingerprint,
        "profile_sha256": hashlib.sha256(
            (ROOT / "configs/reranker-qwen-batch4-evaluation.json").read_bytes()
        ).hexdigest(),
        "query_id": query["id"],
        "first_request": first,
        "worker_start_to_first_request_seconds": first_complete,
        "model_initialization_seconds": load_seconds,
        "warm_requests": warm,
        "boundary_512": {"seconds": boundary_seconds, **long_pair},
        "boundary_513_rejected": True,
        "peak_worker_rss_mib": usage.ru_maxrss / 1024,
        "worker_cpu_seconds": usage.ru_utime + usage.ru_stime,
        "gpu_allocation_bytes": 0,
        "gpu_definition": "CPU-only Torch and all model parameter devices verified by unchanged runtime; not host GPU inventory.",
        "http_e2e_measured": False,
        "concurrent_core_measured": False,
        "adoption_approved": False,
    }


def validate_result(result):
    """Reject incomplete resource evidence, changed model identity and nonfinite timing or scores."""

    configuration = json.loads(
        (ROOT / "docs/evidence/d27-t02-reranker-comparison.json").read_text()
    )
    query = load_query()
    if (
        result["model_fingerprint"]
        != configuration["actual_worker"]["model_fingerprint"]
        or result["profile_sha256"] != configuration["profile_sha256"]
        or result["query_id"] != query["id"]
    ):
        raise ValueError("request_probe_identity_invalid")
    for key in (
        "worker_start_to_first_request_seconds",
        "model_initialization_seconds",
        "peak_worker_rss_mib",
        "worker_cpu_seconds",
    ):
        if (
            type(result[key]) not in (int, float)
            or not math.isfinite(result[key])
            or result[key] <= 0
        ):
            raise ValueError("request_probe_resource_invalid")
    if (
        result["peak_worker_rss_mib"] > 4096
        or result["worker_cpu_seconds"] > 120
        or type(result["gpu_allocation_bytes"]) is not int
        or result["gpu_allocation_bytes"] != 0
    ):
        raise ValueError("request_probe_budget_failed")
    if (
        any(
            result[key] is not False
            for key in (
                "http_e2e_measured",
                "concurrent_core_measured",
                "adoption_approved",
            )
        )
        or result["boundary_513_rejected"] is not True
        or len(result["warm_requests"]) != 3
    ):
        raise ValueError("request_probe_scope_invalid")
    expected = [row["id"] for row in query["documents"]]
    for request in [result["first_request"], *result["warm_requests"]]:
        if (
            [row["document_id"] for row in request["pairs"]] != expected
            or type(request["seconds"]) not in (int, float)
            or not 0 < request["seconds"] <= 60
        ):
            raise ValueError("request_probe_pairs_invalid")
        for row in request["pairs"]:
            validate_pair(row)
    validate_pair(result["boundary_512"])
    if (
        result["boundary_512"]["tokens"] != 512
        or type(result["boundary_512"]["seconds"]) not in (int, float)
        or not 0 < result["boundary_512"]["seconds"] <= 60
    ):
        raise ValueError("request_probe_boundary_invalid")
    logger.info("request_probe_reply_validated")
    return result


def validate_pair(row):
    """Check complete finite class scores and token limits with an independent softmax consistency check."""
    from scripts.qwen_reranker_runtime import yes_probability

    if (
        type(row["tokens"]) is not int
        or not 1 <= row["tokens"] <= 512
        or type(row["score"]) not in (int, float)
        or not math.isfinite(row["score"])
        or abs(yes_probability(row["logits"]) - row["score"]) > 1e-7
    ):
        raise ValueError("request_probe_pair_invalid")


async def run_probe(*, timeout=180):
    """Launch one pinned offline secret-free probe and join its process group on completion or cancellation."""
    from src.infrastructure.qwen_embedding import join_task

    if type(timeout) not in (int, float) or not 0 < timeout <= 180:
        raise ValueError("request_probe_timeout_invalid")
    verify_freeze()
    executable = shutil.which("uv")
    if executable is None:
        raise ValueError("request_probe_uv_missing")
    env = dict(
        PATH=os.environ.get("PATH", "/usr/bin:/bin"),
        LANG="C.UTF-8",
        PYTHONPATH=str(ROOT),
        OPENBLAS_NUM_THREADS="1",
        OMP_NUM_THREADS="2",
        TOKENIZERS_PARALLELISM="false",
        HF_HUB_OFFLINE="1",
        TRANSFORMERS_OFFLINE="1",
        HF_HUB_DISABLE_IMPLICIT_TOKEN="1",
        CUDA_VISIBLE_DEVICES="",
        UV_CACHE_DIR=str(Path.home() / ".cache/uv"),
        UV_PYTHON_DOWNLOADS="never",
        QWEN_INGESTION_PARENT_PID=str(os.getpid()),
        QWEN_INGESTION_PARENT_START=Path("/proc/self/stat")
        .read_text()
        .rsplit(")", 1)[1]
        .split()[19],
    )
    child, work = None, None
    started = time.perf_counter()
    launch = asyncio.create_task(
        asyncio.create_subprocess_exec(
            executable,
            "run",
            "--offline",
            "--frozen",
            "--script",
            str(WORKER),
            cwd=ROOT,
            env=env,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=True,
        )
    )
    try:
        try:
            child = await asyncio.shield(launch)
        except asyncio.CancelledError:
            child = await join_task(launch)
            raise
        work = asyncio.create_task(child.communicate())
        stdout, _ = await asyncio.wait_for(asyncio.shield(work), timeout)
        if child.returncode or len(stdout) > 65536:
            raise ValueError("request_probe_worker_failed")
        result = validate_result(json.loads(stdout))
        result["parent_total_probe_seconds"] = time.perf_counter() - started
        logger.info("request_probe_completed")
        return result
    finally:
        if child is not None and child.returncode is None:
            try:
                os.killpg(child.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            if work is None:
                work = asyncio.create_task(child.communicate())
        if work is not None:
            await join_task(work)
        logger.info("request_probe_process_joined")


def main():
    """Bound actual CPU/RAM/wall consumption before importing model code and emit sanitized failure output."""
    started = time.perf_counter()
    from scripts.qwen_ingestion_encoder import supervise_parent
    from scripts.qwen_reranker_worker import supervise_rss

    resource.setrlimit(resource.RLIMIT_AS, (8 * 1024**3, 8 * 1024**3))
    resource.setrlimit(resource.RLIMIT_CPU, (120, 121))
    timer = threading.Timer(150, os.kill, args=(os.getpid(), signal.SIGKILL))
    timer.daemon = True
    try:
        supervise_parent()
        supervise_rss(4096 * 1024**2)
        timer.start()
        verify_freeze()
        print(json.dumps(measure(started), allow_nan=False))
        return 0
    except Exception:
        logger.warning("request_probe_worker_failed")
        print('{"error":"request_probe_failed"}')
        return 1
    finally:
        timer.cancel()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    raise SystemExit(main())
