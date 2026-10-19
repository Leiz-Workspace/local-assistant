"""Rank bounded source-verified pairs in a supervised isolated evaluation worker without runtime adoption."""
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

import hashlib
import json
import logging
import os
import resource
import signal
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
logger = logging.getLogger(__name__)
FREEZE = ROOT / "docs/evidence/d27-t03-http-trial-freeze.json"


def verify_freeze():
    """Verify the complete independent trial and inherited accepted model/runtime identities before inference."""
    from scripts.reranker_request_probe import verify_freeze as prior_freeze

    prior_freeze()
    manifest = json.loads(FREEZE.read_text())
    required = {
        "scripts/qwen_reranker_trial_worker.py",
        "scripts/qwen_reranker_trial_worker.py.lock",
        "scripts/retrieval_reranker_trial.py",
        "tests/test_retrieval_reranker_trial.py",
        "tests/integration/test_reranker_http_trial.py",
        "docs/ADR/041-isolated-http-reranker-trial.md",
    }
    if (
        manifest["scope"] != "ISOLATED_ASGI_HTTP_TRIAL_NO_ADOPTION"
        or set(manifest["sha256"]) != required
    ):
        raise ValueError("trial_freeze_invalid")
    for name, expected in manifest["sha256"].items():
        if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != expected:
            raise ValueError("trial_source_changed")
    logger.info("reranker_trial_freeze_verified")


def validate_request(request):
    """Require exact bounded query/source identities and complete raw source hashes before model loading."""
    profile_sha = hashlib.sha256(
        (ROOT / "configs/reranker-qwen-batch4-evaluation.json").read_bytes()
    ).hexdigest()
    if (
        not isinstance(request, dict)
        or set(request) != {"query", "candidates", "profile_sha256"}
        or request["profile_sha256"] != profile_sha
    ):
        raise ValueError("trial_request_identity_invalid")
    query, rows = request["query"], request["candidates"]
    if (
        not isinstance(query, str)
        or not query.strip()
        or len(query.encode()) > 4096
        or not isinstance(rows, list)
        or not 1 <= len(rows) <= 10
    ):
        raise ValueError("trial_request_invalid")
    for row in rows:
        if (
            not isinstance(row, dict)
            or set(row) != {"id", "text", "text_sha256"}
            or not isinstance(row["id"], str)
            or not 1 <= len(row["id"]) <= 128
            or not isinstance(row["text"], str)
            or not row["text"].strip()
            or len(row["text"].encode()) > 4096
            or row["text_sha256"] != hashlib.sha256(row["text"].encode()).hexdigest()
        ):
            raise ValueError("trial_source_invalid")
    if len({row["id"] for row in rows}) != len(rows):
        raise ValueError("trial_candidate_duplicate")
    logger.info("reranker_trial_request_verified pairs=%d", len(rows))
    return request


def measure(request):
    """Load the accepted candidate once and retain every actual finite pair result with explicit process costs."""
    started = time.perf_counter()
    validate_request(request)
    from scripts.qwen_reranker_runtime import QwenRerankerCpu, profile

    init = time.perf_counter()
    model = QwenRerankerCpu(profile())
    initialization_seconds = time.perf_counter() - init
    rows = []
    for offset in range(0, len(request["candidates"]), 4):
        candidates = request["candidates"][offset : offset + 4]
        scores = model.score_batch(
            request["query"], [row["text"] for row in candidates]
        )
        for row, (score, tokens, logits) in zip(candidates, scores, strict=True):
            rows.append(
                dict(
                    id=row["id"],
                    text_sha256=row["text_sha256"],
                    score=score,
                    tokens=tokens,
                    logits=list(logits),
                )
            )
    usage = resource.getrusage(resource.RUSAGE_SELF)
    logger.info("reranker_trial_scored pairs=%d", len(rows))
    return dict(
        profile_sha256=request["profile_sha256"],
        model_fingerprint=model.fingerprint,
        rows=rows,
        model_initialization_seconds=initialization_seconds,
        worker_wall_seconds=time.perf_counter() - started,
        peak_rss_mib=usage.ru_maxrss / 1024,
        cpu_seconds=usage.ru_utime + usage.ru_stime,
        gpu_allocation_bytes=0,
    )


def main():
    """Supervise exact parent identity, RAM/CPU/wall limits and bounded credential-free input/output."""
    from scripts.qwen_ingestion_encoder import supervise_parent
    from scripts.qwen_reranker_worker import supervise_rss

    resource.setrlimit(resource.RLIMIT_AS, (8 * 1024**3, 8 * 1024**3))
    resource.setrlimit(resource.RLIMIT_CPU, (120, 121))
    timer = threading.Timer(80, os.kill, args=(os.getpid(), signal.SIGKILL))
    timer.daemon = True
    try:
        supervise_parent()
        supervise_rss(4096 * 1024**2)
        timer.start()
        verify_freeze()
        raw = sys.stdin.buffer.read(65537)
        if len(raw) > 65536:
            raise ValueError("trial_input_limit")
        reply = json.dumps(measure(json.loads(raw)), allow_nan=False)
        if len(reply.encode()) > 16384:
            raise ValueError("trial_reply_limit")
        print(reply)
        return 0
    except Exception as exc:
        code = (
            "trial_pair_token_limit"
            if str(exc) == "reranker_pair_token_limit"
            else "trial_worker_failed"
        )
        logger.warning("reranker_trial_worker_failed code=%s", code)
        print(json.dumps(dict(error=code)))
        return 1
    finally:
        timer.cancel()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    raise SystemExit(main())
