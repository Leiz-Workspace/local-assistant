"""Execute bounded credential-free CPU reranker repetitions with actual RAM and per-query wall supervision."""
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


def supervise_rss(limit_bytes):
    """Kill only this candidate process if actual resident pages exceed the frozen RAM budget."""

    def watch():
        """Poll current candidate RSS without confusing virtual address space with RAM usage."""
        while True:
            pages = int(Path("/proc/self/statm").read_text().split()[1])
            if pages * os.sysconf("SC_PAGE_SIZE") > limit_bytes:
                logger.warning("reranker_rss_limit_exceeded")
                os.kill(os.getpid(), signal.SIGKILL)
            time.sleep(0.05)

    threading.Thread(target=watch, daemon=True).start()


def measure(request):
    """Verify request identity, load once and retain complete pair scores/counts/timings across fixed rounds."""
    from scripts.qwen_reranker_runtime import PROFILE, QwenRerankerCpu, profile

    configuration = profile()
    if (
        not isinstance(request, dict)
        or set(request) != {"profile_sha256", "queries"}
        or request["profile_sha256"] != hashlib.sha256(PROFILE.read_bytes()).hexdigest()
    ):
        raise ValueError("reranker_request_identity_invalid")
    queries = request["queries"]
    if (
        not isinstance(queries, list)
        or len(queries) != 36
        or len({row["id"] for row in queries}) != 36
    ):
        raise ValueError("reranker_request_invalid")
    for query in queries:
        if (
            set(query) != {"id", "text", "documents"}
            or len(query["documents"]) != 10
            or len({row["id"] for row in query["documents"]}) != 10
            or any(set(row) != {"id", "text"} for row in query["documents"])
        ):
            raise ValueError("reranker_request_invalid")
    started = time.perf_counter()
    model = QwenRerankerCpu(configuration)
    load = time.perf_counter() - started
    parity = model.reference_parity(
        queries[0]["text"], queries[0]["documents"][0]["text"]
    )
    rounds = []
    for repeat in range(configuration["repetitions"]):
        rows = []
        for query in queries:
            timer = threading.Timer(
                configuration["max_query_seconds"],
                os.kill,
                args=(os.getpid(), signal.SIGKILL),
            )
            timer.daemon = True
            timer.start()
            started = time.perf_counter()
            try:
                documents = []
                for offset in range(
                    0, len(query["documents"]), configuration["batch_size"]
                ):
                    batch = query["documents"][
                        offset : offset + configuration["batch_size"]
                    ]
                    outputs = model.score_batch(
                        query["text"], [doc["text"] for doc in batch]
                    )
                    for document, (score, count, logits) in zip(
                        batch, outputs, strict=True
                    ):
                        documents.append(
                            dict(
                                document_id=document["id"],
                                score=score,
                                tokens=count,
                                logits=logits,
                            )
                        )
                rows.append(
                    dict(
                        query_id=query["id"],
                        documents=documents,
                        wall_seconds=time.perf_counter() - started,
                    )
                )
            finally:
                timer.cancel()
        rounds.append(rows)
        logger.info("reranker_evaluation_round_completed round=%d", repeat + 1)
    return dict(
        profile_sha256=request["profile_sha256"],
        model_fingerprint=model.fingerprint,
        contract=model.contract,
        cold_load_seconds=load,
        last_logits_reference_parity=parity,
        peak_candidate_rss_mib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        / 1024,
        candidate_gpu_allocation_bytes=0,
        gpu_measurement="Verified CPU-only Torch and all model parameters on CPU; not host GPU inventory.",
        rounds=rounds,
    )


def main():
    """Enforce bounded input/output, exact parent death supervision and safe fixed worker failure diagnostics."""
    from scripts.qwen_ingestion_encoder import supervise_parent

    resource.setrlimit(resource.RLIMIT_AS, (8 * 1024**3, 8 * 1024**3))
    resource.setrlimit(resource.RLIMIT_CPU, (480, 481))
    try:
        supervise_parent()
        supervise_rss(4096 * 1024**2)
        raw = sys.stdin.buffer.read(1024**2 + 1)
        if len(raw) > 1024**2:
            raise ValueError("reranker_input_limit")
        result = json.dumps(measure(json.loads(raw)), allow_nan=False)
        if len(result.encode()) > 2 * 1024**2:
            raise ValueError("reranker_reply_limit")
        print(result)
        return 0
    except Exception:
        logger.warning("reranker_evaluation_worker_failed")
        print(json.dumps(dict(error="reranker_evaluation_failed")))
        return 1


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    raise SystemExit(main())
