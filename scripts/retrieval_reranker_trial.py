"""Compose source-held retrieval and supervised ranking exclusively for isolated evaluation instances."""

import asyncio
import hashlib
import json
import logging
import math
import os
import shutil
import signal
import time
from collections import deque
from contextlib import asynccontextmanager
from pathlib import Path

from scripts.qwen_reranker_runtime import PROFILE, yes_probability
from scripts.qwen_reranker_trial_worker import ROOT, validate_request, verify_freeze
from src.application.services.file_storage_policy import StoragePolicyError
from src.infrastructure.qdrant_retrieval import search_options
from src.infrastructure.qwen_embedding import join_task

logger = logging.getLogger(__name__)
WORKER = ROOT / "scripts/qwen_reranker_trial_worker.py"


def build_request(query, hits):
    """Bind every candidate to exact rehydrated chunk text without trusting vector-store text or source labels."""
    request = dict(
        query=query,
        profile_sha256=hashlib.sha256(PROFILE.read_bytes()).hexdigest(),
        candidates=[
            dict(
                id=row["point_id"],
                text=row["text"],
                text_sha256=hashlib.sha256(row["text"].encode()).hexdigest(),
            )
            for row in hits
        ],
    )
    return validate_request(request)


def validate_reply(request, reply):
    """Require complete ordered source-bound scores, exact accepted model identity and finite bounded resources."""
    expected_keys = {
        "profile_sha256",
        "model_fingerprint",
        "rows",
        "model_initialization_seconds",
        "worker_wall_seconds",
        "peak_rss_mib",
        "cpu_seconds",
        "gpu_allocation_bytes",
    }
    accepted = json.loads(
        (ROOT / "docs/evidence/d27-t02-reranker-comparison.json").read_text()
    )
    if (
        not isinstance(reply, dict)
        or set(reply) != expected_keys
        or reply["profile_sha256"] != request["profile_sha256"]
        or reply["model_fingerprint"] != accepted["actual_worker"]["model_fingerprint"]
    ):
        raise ValueError("trial_reply_identity_invalid")
    rows = reply["rows"]
    if not isinstance(rows, list) or len(rows) != len(request["candidates"]):
        raise ValueError("trial_reply_incomplete")
    for row, source in zip(rows, request["candidates"], strict=True):
        if (
            not isinstance(row, dict)
            or set(row) != {"id", "text_sha256", "score", "tokens", "logits"}
            or row["id"] != source["id"]
            or row["text_sha256"] != source["text_sha256"]
            or type(row["tokens"]) is not int
            or not 1 <= row["tokens"] <= 512
            or type(row["score"]) not in (int, float)
            or not math.isfinite(row["score"])
            or not 0 <= row["score"] <= 1
            or abs(yes_probability(row["logits"]) - row["score"]) > 1e-7
        ):
            raise ValueError("trial_reply_pair_invalid")
    for key, limit in [
        ("model_initialization_seconds", 80),
        ("worker_wall_seconds", 80),
        ("peak_rss_mib", 4096),
        ("cpu_seconds", 120),
    ]:
        if (
            type(reply[key]) not in (int, float)
            or not math.isfinite(reply[key])
            or not 0 < reply[key] <= limit
        ):
            raise ValueError("trial_reply_resource_invalid")
    if (
        type(reply["gpu_allocation_bytes"]) is not int
        or reply["gpu_allocation_bytes"] != 0
    ):
        raise ValueError("trial_reply_gpu_invalid")
    logger.info("reranker_trial_reply_verified pairs=%d", len(rows))
    return reply


class TrialReranker:
    """Hold the actual ingestion encoder slot until the isolated scoring child is completely joined."""

    def __init__(self, admission, *, timeout=90):
        """Bind existing nonqueued model admission and a bounded evaluation-only deadline."""
        if type(timeout) not in (int, float) or not 0 < timeout <= 90:
            raise ValueError("trial_timeout_invalid")
        self.admission, self.timeout = admission, timeout

    async def rank(self, query, hits):
        """Run the immutable offline candidate contract and fail closed without silent ordering fallback."""
        verify_freeze()
        request = build_request(query, hits)
        if self.admission.locked():
            raise StoragePolicyError("trial_model_busy", 429)
        await self.admission.acquire()
        child, work = None, None
        try:
            executable = shutil.which("uv")
            if executable is None:
                raise ValueError("trial_runtime_missing")
            body = json.dumps(request, ensure_ascii=False).encode()
            if len(body) > 65536:
                raise ValueError("trial_input_limit")
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
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    start_new_session=True,
                )
            )
            try:
                child = await asyncio.shield(launch)
            except asyncio.CancelledError:
                child = await join_task(launch)
                raise
            work = asyncio.create_task(child.communicate(body))
            stdout, _ = await asyncio.wait_for(asyncio.shield(work), self.timeout)
            if len(stdout) > 16384:
                raise ValueError("trial_reply_limit")
            reply = json.loads(stdout)
            if child.returncode:
                if reply == {"error": "trial_pair_token_limit"}:
                    raise StoragePolicyError("trial_pair_token_limit", 422)
                raise ValueError("trial_worker_failed")
            return validate_reply(request, reply)
        except (ValueError, OSError, TimeoutError, KeyError, TypeError):
            logger.warning("reranker_trial_failed_safely")
            raise StoragePolicyError("trial_ranking_unavailable", 503) from None
        finally:
            try:
                if child is not None and child.returncode is None:
                    try:
                        os.killpg(child.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    if work is None:
                        work = asyncio.create_task(child.communicate())
                if work is not None:
                    await join_task(work)
            finally:
                self.admission.release()
                logger.info("reranker_trial_child_joined")


class TrialRetrievalService:
    """Wrap only an explicitly injected evaluation instance while retaining all D26 source/delivery fences."""

    def __init__(self, dense, *, reranker=None):
        """Reuse the live dense service and existing encoder slot with bounded numeric-only observations."""
        self.dense = dense
        self.reranker = reranker or TrialReranker(dense.ingestion.encoder.admission)
        self.observations = deque(maxlen=128)

    @property
    def closing(self):
        """Expose the existing service lifecycle state without separate shutdown or application wiring."""
        return self.dense.closing

    async def validate(self, owner, retained):
        """Delegate final delivery authorization to unchanged SQL/source identity and byte verification."""
        await self.dense.validate(owner, retained)

    @asynccontextmanager
    async def operation(self, owner, query, *, top_k=5, file_ids=None):
        """Retain every dense source through actual ranking, post-model fences and response delivery."""
        search_options(query, top_k, file_ids)
        started = time.perf_counter()
        async with self.dense.operation(owner, query, top_k=10, file_ids=file_ids) as (
            data,
            retained,
        ):
            hits = data["hits"]
            if hits:
                await self.validate(owner, retained)
                ranking = await self.reranker.rank(query, hits)
                validate_reply(build_request(query, hits), ranking)
                await self.validate(owner, retained)
                indexed = {row["id"]: row["score"] for row in ranking["rows"]}
                hits = [
                    dict(row, reranker_score=indexed[row["point_id"]]) for row in hits
                ]
                hits.sort(key=lambda row: (-row["reranker_score"], row["point_id"]))
                self.observations.append(
                    dict(
                        candidate_count=len(hits),
                        model_fingerprint=ranking["model_fingerprint"],
                        profile_sha256=ranking["profile_sha256"],
                        pair_results=ranking["rows"],
                        seconds_to_post_rank_fence=time.perf_counter() - started,
                        model_initialization_seconds=ranking[
                            "model_initialization_seconds"
                        ],
                        worker_wall_seconds=ranking["worker_wall_seconds"],
                        peak_rss_mib=ranking["peak_rss_mib"],
                        cpu_seconds=ranking["cpu_seconds"],
                        gpu_allocation_bytes=ranking["gpu_allocation_bytes"],
                    )
                )
            logger.info(
                "reranker_trial_sources_prepared candidates=%d returned=%d",
                len(hits),
                min(top_k, len(hits)),
            )
            yield (
                dict(
                    data,
                    hits=hits[:top_k],
                    top_k=top_k,
                    ranking="evaluation_only_qwen_batch4",
                ),
                retained,
            )

    async def shutdown(self):
        """Drain the existing owner-tracked source operations and model child through unchanged shutdown."""
        await self.dense.shutdown()
        logger.info("reranker_trial_shutdown_complete")
