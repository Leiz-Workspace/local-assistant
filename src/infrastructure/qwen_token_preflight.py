"""Run bounded credential-free tokenizer admission for immutable Qwen ingestion plans."""

import json
import logging
import os
import shutil
import signal
import subprocess
from pathlib import Path
from threading import BoundedSemaphore

from src.application.services.document_chunks import MAX_REPLY_BYTES
from src.application.services.file_storage_policy import StoragePolicyError
from src.application.services.ingestion_contract import validate_token_counts

logger = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parents[2]
WORKER = ROOT / "scripts/qwen_ingestion_preflight.py"
ADMISSION = BoundedSemaphore(1)


def preflight_plan(plan):
    """Own one process-local admission until the offline tokenizer group exits or is killed and joined."""
    if not ADMISSION.acquire(blocking=False):
        logger.warning("ingestion_token_worker_busy job_id=%s", plan.job_id)
        raise StoragePolicyError("ingestion_token_busy", 429)
    try:
        return _preflight_plan(plan)
    finally:
        ADMISSION.release()


def run_worker(command, *, cwd, env, input, timeout):
    """Run one owned worker in cwd with piped text I/O; kill and join its group on timeout or interruption."""
    with subprocess.Popen(
        command,
        cwd=cwd,
        env=env,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    ) as child:
        try:
            stdout, stderr = child.communicate(input=input, timeout=timeout)
        except BaseException:
            try:
                os.killpg(child.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            child.communicate()
            logger.warning("ingestion_token_process_group_joined")
            raise
        return subprocess.CompletedProcess(command, child.returncode, stdout, stderr)


def _preflight_plan(plan):
    """Validate bounded count replies against the admitted plan and pinned Qwen identity."""
    command = shutil.which("uv")
    if not command:
        raise StoragePolicyError("ingestion_token_runtime_unavailable", 503)
    data = json.dumps(
        dict(texts=[point.text for point in plan.points]), ensure_ascii=False
    )
    if len(data.encode()) > MAX_REPLY_BYTES:
        raise StoragePolicyError("ingestion_limits_exceeded", 413)
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
    )
    try:
        result = run_worker(
            [command, "run", "--offline", "--frozen", "--script", str(WORKER)],
            cwd=ROOT,
            env=env,
            input=data,
            timeout=90,
        )
        if len(result.stdout.encode()) > 16384:
            raise ValueError("preflight_failed")
        reply = json.loads(result.stdout)
        if result.returncode == 2 and reply == dict(error="ingestion_token_limit"):
            raise StoragePolicyError("ingestion_token_limit", 422)
        if result.returncode:
            raise ValueError("preflight_failed")
        if (
            not isinstance(reply, dict)
            or set(reply) != {"model_fingerprint", "max_tokens", "counts"}
            or reply["model_fingerprint"] != plan.model_fingerprint
            or type(reply["max_tokens"]) is not int
            or reply["max_tokens"] != 512
        ):
            raise ValueError("preflight_identity")
        counts = validate_token_counts(plan, reply["counts"])
    except (ValueError, KeyError, TypeError, OSError, subprocess.TimeoutExpired):
        logger.warning("ingestion_token_worker_failed job_id=%s", plan.job_id)
        raise StoragePolicyError("ingestion_token_preflight_failed", 503) from None
    logger.info(
        "ingestion_token_worker_accepted job_id=%s points=%d", plan.job_id, len(counts)
    )
    return counts
