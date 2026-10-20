"""Evaluate bounded candidate functions inside an already isolated non-root namespace without host test oracles."""

import json
import logging
import os
import resource
import sys

logger = logging.getLogger(__name__)


def main():
    """Apply hard limits before compiling untrusted source and return values only, never a self-reported PASS."""
    logging.basicConfig(level=logging.INFO)
    resource.setrlimit(resource.RLIMIT_AS, (512 * 1024**2, 512 * 1024**2))
    resource.setrlimit(resource.RLIMIT_CPU, (2, 3))
    resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_NOFILE, (32, 32))
    resource.setrlimit(resource.RLIMIT_NPROC, (16, 16))
    os.umask(0o077)
    logger.info("coding_sandbox_worker_started uid=%d", os.getuid())
    try:
        raw = sys.stdin.buffer.read(32769)
        if len(raw) > 32768:
            raise ValueError()
        payload = json.loads(raw)
        if not isinstance(payload, dict) or set(payload) != {"code", "inputs"}:
            raise ValueError()
        if not isinstance(payload["code"], str) or len(payload["code"].encode()) > 8192:
            raise ValueError()
        if (
            not isinstance(payload["inputs"], list)
            or not 1 <= len(payload["inputs"]) <= 16
        ):
            raise ValueError()
        namespace = {"__name__": "candidate"}
        exec(compile(payload["code"], "<candidate>", "exec"), namespace)
        function = namespace.get("solve")
        if not callable(function):
            raise ValueError()
        results = []
        for arguments in payload["inputs"]:
            if not isinstance(arguments, list):
                raise ValueError()
            try:
                results.append(dict(value=function(*arguments)))
            except BaseException:
                results.append(dict(error="candidate_exception"))
        encoded = json.dumps(dict(results=results), ensure_ascii=False, allow_nan=False)
    except BaseException:
        encoded = json.dumps(dict(error="candidate_invalid"))
    logger.info("coding_sandbox_worker_finished")
    sys.stdout.write(encoded)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
