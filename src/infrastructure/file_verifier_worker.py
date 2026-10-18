"""Constrain an isolated verifier process and return only a tiny safe JSON verdict."""

import json
import logging
import os
import resource
import sys

logger = logging.getLogger(__name__)


def main() -> int:
    """Apply hard resource limits before loading parsers and never expose parser exception text."""
    from src.infrastructure.file_verifier import (
        VERIFIER_CPU_SECONDS,
        VERIFIER_MEMORY_BYTES,
    )

    resource.setrlimit(
        resource.RLIMIT_AS, (VERIFIER_MEMORY_BYTES, VERIFIER_MEMORY_BYTES)
    )
    resource.setrlimit(
        resource.RLIMIT_CPU, (VERIFIER_CPU_SECONDS, VERIFIER_CPU_SECONDS + 1)
    )
    resource.setrlimit(resource.RLIMIT_FSIZE, (4096, 4096))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_NOFILE, (32, 32))
    os.umask(0o077)
    try:
        from src.application.services.file_storage_policy import (
            StoragePolicy,
            StoragePolicyError,
        )
        from src.infrastructure.file_content_verifier import detect_content

        policy = StoragePolicy(**json.loads(sys.argv[2]))
        with os.fdopen(os.dup(0), "rb") as source:
            media = detect_content(source, sys.argv[1], policy)
        result = {"media_type": media}
    except MemoryError:
        result = {"error": "verification_limits_exceeded"}
    except StoragePolicyError as error:
        result = {
            "error": error.code
            if error.code == "archive_limits_exceeded"
            else "invalid_file_content"
        }
    except Exception:
        result = {"error": "invalid_file_content"}
    logger.info("file_verifier_finished accepted=%s", "media_type" in result)
    sys.stdout.write(json.dumps(result, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
