"""Own bounded asynchronous Qwen encoding subprocesses and validate complete model-bound unit vectors."""

import asyncio
import json
import logging
import os
import shutil
import signal
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from src.application.services.file_storage_policy import StoragePolicyError
from src.application.services.ingestion_contract import validate_token_counts

logger = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parents[2]
WORKER = ROOT / "scripts/qwen_ingestion_encoder.py"


@dataclass(frozen=True)
class EncodedBatch:
    """Retain an immutable complete CPU encoding bound to a single exact model fingerprint."""

    model_fingerprint: str
    counts: tuple[int, ...]
    vectors: tuple[tuple[float, ...], ...]


def validate_encoding(plan, reply):
    """Reject mixed-model, partial, nonfinite, malformed or unnormalized vector replies."""
    try:
        if (
            not isinstance(reply, dict)
            or set(reply) != {"model_fingerprint", "counts", "vectors"}
            or reply["model_fingerprint"] != plan.model_fingerprint
        ):
            raise ValueError("encoding_identity")
        counts = validate_token_counts(plan, reply["counts"])
        if not isinstance(reply["vectors"], list) or any(
            not isinstance(row, list)
            or len(row) != 1024
            or any(
                isinstance(value, bool) or not isinstance(value, (int, float))
                for value in row
            )
            for row in reply["vectors"]
        ):
            raise ValueError("encoding_values")
        vectors = np.asarray(reply["vectors"], dtype=np.float32)
        if len(plan.points) == 0 and reply["vectors"] == []:
            vectors = np.empty((0, 1024), dtype=np.float32)
        if vectors.shape != (len(plan.points), 1024) or not np.isfinite(vectors).all():
            raise ValueError("encoding_shape")
        if len(vectors) and np.max(np.abs(np.linalg.norm(vectors, axis=1) - 1)) > 1e-5:
            raise ValueError("encoding_norm")
    except (ValueError, TypeError, OverflowError):
        logger.warning("ingestion_encoding_rejected job_id=%s", plan.job_id)
        raise StoragePolicyError("ingestion_encoding_invalid", 503) from None
    logger.info(
        "ingestion_encoding_validated job_id=%s points=%d", plan.job_id, len(counts)
    )
    return EncodedBatch(
        plan.model_fingerprint,
        counts,
        tuple(tuple(float(value) for value in row) for row in vectors),
    )


async def join_task(task):
    """Join owned subprocess pipe work despite repeated cancellation before releasing admission."""
    while True:
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            if task.done():
                return task.result()


class QwenEmbedding:
    """Allow one bounded private encoding operation per adapter without importing Torch into the API."""

    def __init__(self):
        """Create process-local nonqueued admission with no model or service startup side effects."""
        self.admission = asyncio.Lock()

    async def encode(self, plan):
        """Run a locked offline worker and kill/join its process group on timeout or cancellation."""
        if self.admission.locked():
            raise StoragePolicyError("ingestion_encoder_busy", 429)
        await self.admission.acquire()
        child, work = None, None
        try:
            command = shutil.which("uv")
            if not command:
                raise ValueError("encoding_runtime")
            body = json.dumps(
                dict(
                    texts=[point.text for point in plan.points],
                    model_fingerprint=plan.model_fingerprint,
                ),
                ensure_ascii=False,
            ).encode()
            if len(body) > 8 * 1024**2:
                raise ValueError("encoding_input_limit")
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
                    command,
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
            stdout, stderr = await asyncio.wait_for(asyncio.shield(work), timeout=600)
            if child.returncode or len(stdout) > 32 * 1024**2:
                raise ValueError("encoding_worker")
            return validate_encoding(plan, json.loads(stdout))
        except asyncio.CancelledError:
            logger.warning("ingestion_encoder_cancelled job_id=%s", plan.job_id)
            raise
        except (ValueError, OSError, asyncio.TimeoutError):
            logger.warning("ingestion_encoder_failed job_id=%s", plan.job_id)
            raise StoragePolicyError("ingestion_encoding_failed", 503) from None
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
                    try:
                        await join_task(work)
                    except Exception:
                        logger.warning("ingestion_encoder_pipe_join_failed")
            finally:
                self.admission.release()
