"""Dispatch only fixed approved native voice roles in an offline bounded worker namespace."""

import contextlib
import hashlib
import json
import logging
import os
import site
import sys
import time
from pathlib import Path

LOGGER = logging.getLogger(__name__)
LIMIT = 24
MODELS = {
    "vad": "silero-vad-v5.0-5cd2ba54",
    "qwen3-asr-0.6b": "qwen3-asr-0.6b",
    "turbo": "vieneu-v3-turbo-truc-ly",
}
POLICIES = {
    "vad": "detector-peak-half-v2",
    "qwen3-asr-0.6b": "original-asr-decoding",
    "turbo": "truc-ly-workflow-reading-1",
}


def validate_scope(scope):
    """Refuse unapproved roles, precision, affinity, model or budgets before importing model libraries."""
    if (
        type(scope) is not dict
        or scope.get("role") not in MODELS
        or scope.get("native_authorized") is not True
        or type(scope.get("max_requests")) is not int
        or scope["max_requests"] != LIMIT
        or scope.get("model") != MODELS[scope["role"]]
        or scope.get("policy") != POLICIES[scope["role"]]
        or type(scope.get("cpu_threads")) is not int
        or scope["cpu_threads"] != (2 if scope["role"] == "vad" else 8)
        or scope.get("mode") != "voice"
        or type(scope.get("scope_sha256")) is not str
        or len(scope["scope_sha256"]) != 64
        or any(c not in "0123456789abcdef" for c in scope["scope_sha256"])
        or scope["role"] == "turbo"
        and scope.get("voice") != "Trúc Ly"
        or scope["role"] == "qwen3-asr-0.6b"
        and scope.get("execution_backend") != "cuda-original-precision"
    ):
        raise ValueError("voice_worker_scope")
    LOGGER.info("voice_worker_scope_verified role=%s", scope["role"])
    return scope


def serve_vad(scope, expected_sha):
    """Serve exact original Silero full-clip observations with one recurrent reset per submitted clip."""
    from src.infrastructure.voice.vad_decode import (
        Runtime,
        load_waveform,
        validate_request,
    )
    from src.infrastructure.voice.waveform import emit

    with contextlib.redirect_stdout(sys.stderr):
        runtime = Runtime(load=True)
    emit(
        "ready",
        candidate="vad",
        manifest_sha256=expected_sha,
        execution=runtime.execution,
    )
    seen = set()
    for _ in range(LIMIT + 1):
        raw = sys.stdin.buffer.readline(16385)
        if not raw or len(raw) > 16384 or not raw.endswith(b"\n"):
            raise ValueError("voice_message_bound")
        message = json.loads(raw)
        if message == {"op": "close"}:
            emit("closed", calls=len(seen))
            return
        if (
            type(message) is not dict
            or set(message)
            != {"op", "id", "filename", "sample_count", "waveform_sha256"}
            or message["op"] != "detect"
            or message["id"] in seen
            or len(seen) >= LIMIT
        ):
            raise ValueError("voice_vad_message")
        case = {k: v for k, v in message.items() if k != "op"}
        validate_request(dict(mode="smoke", cases=[case]))
        seen.add(message["id"])
        started = time.perf_counter()
        with contextlib.redirect_stdout(sys.stderr):
            result = runtime.observe(load_waveform(case))
        emit(
            "result",
            id=message["id"],
            operation="detect",
            worker_wall_seconds=time.perf_counter() - started,
            vad=dict(
                sample_count=case["sample_count"],
                waveform_sha256=case["waveform_sha256"],
                **result,
            ),
        )
    raise ValueError("voice_worker_request_ceiling")


def main():
    """Verify the read-only manifest before importing and loading the sole declared offline stage."""
    logging.basicConfig(level=logging.INFO)
    os.umask(0o077)
    site.addsitedir("/venv/lib/python3.12/site-packages")
    raw = Path("/approved-workflow.json").read_bytes()
    if len(sys.argv) != 2 or hashlib.sha256(raw).hexdigest() != sys.argv[1]:
        raise ValueError("voice_manifest_binding")
    scope = validate_scope(json.loads(raw))
    if sorted(os.sched_getaffinity(0)) != list(range(scope["cpu_threads"])):
        raise ValueError("voice_worker_affinity")
    if scope["role"] == "vad":
        serve_vad(scope, sys.argv[1])
    elif scope["role"] == "turbo":
        from src.infrastructure.voice.tts_runtime import serve

        serve(sys.argv[1])
    else:
        from src.infrastructure.voice.asr_runtime import serve

        serve(scope, sys.argv[1])


if __name__ == "__main__":
    main()
