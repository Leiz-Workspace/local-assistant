"""Delegate bounded browser-session requests to unchanged qualified resident inference implementations."""

import hashlib
import json
import logging
import os
import site
import sys
from pathlib import Path

LOGGER = logging.getLogger(__name__)
LIMIT = 24


def validate_scope(scope):
    """Allow only the fixed research lane and finite browser request budget before importing model libraries."""
    from benchmarks.scripts.vi_voice_resident_worker import ROLE_MODELS, ROLE_POLICIES

    role = scope.get("role")
    if (
        role not in {"vad", "qwen3-asr-0.6b", "turbo"}
        or scope.get("native_authorized") is not True
        or type(scope.get("max_requests")) is not int
        or scope["max_requests"] != LIMIT
        or scope.get("model") != ROLE_MODELS[role]
        or scope.get("policy") != ROLE_POLICIES[role]
        or scope.get("cpu_threads") != (2 if role == "vad" else 8)
        or type(scope.get("cpu_threads")) is not int
        or scope.get("mode") != "voice"
        or type(scope.get("scope_sha256")) is not str
        or len(scope["scope_sha256"]) != 64
        or any(c not in "0123456789abcdef" for c in scope["scope_sha256"])
        or role == "turbo"
        and scope.get("voice") != "Trúc Ly"
        or role == "qwen3-asr-0.6b"
        and scope.get("execution_backend") != "cuda-original-precision"
    ):
        raise ValueError("trial_worker_scope")
    LOGGER.info("trial_worker_scope_verified role=%s limit=%d", role, LIMIT)
    return scope


def main():
    """Verify the explicit manifest then reuse exact existing VAD, CUDA ASR or accepted reading serving logic."""
    logging.basicConfig(level=logging.INFO)
    os.umask(0o077)
    site.addsitedir("/venv/lib/python3.12/site-packages")
    raw = Path("/approved-workflow.json").read_bytes()
    if len(sys.argv) != 2 or hashlib.sha256(raw).hexdigest() != sys.argv[1]:
        raise ValueError("trial_manifest_binding")
    scope = validate_scope(json.loads(raw))
    threads = scope["cpu_threads"]
    if sorted(os.sched_getaffinity(0)) != list(range(threads)):
        raise ValueError("trial_worker_affinity")
    if scope["role"] == "qwen3-asr-0.6b":
        from benchmarks.scripts.vi_voice_cuda_worker import serve
    else:
        from benchmarks.scripts.vi_voice_resident_worker import serve
    serve(scope, sys.argv[1])


if __name__ == "__main__":
    main()
