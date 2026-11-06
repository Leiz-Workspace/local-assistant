"""Constrain XLSX inspection and literal cell rewrite before importing untrusted-content parsers."""

import hashlib
import json
import logging
import os
import resource
import sys

logger = logging.getLogger(__name__)


def main():
    """Apply kernel budgets and publish only verified XLSX bytes or sanitized structured results."""
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
    resource.setrlimit(resource.RLIMIT_FSIZE, (25 * 1024 * 1024, 25 * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_NOFILE, (32, 32))
    os.umask(0o077)
    from src.application.services.file_storage_policy import (
        DEFAULT_POLICY,
        StoragePolicyError,
    )
    from src.application.services.xlsx_contract import (
        MAX_PLAN_BYTES,
        MAX_READ_BYTES,
        validate_plan,
    )

    try:
        import zipfile

        from src.infrastructure.file_content_verifier import verify_ooxml
        from src.infrastructure.xlsx_content import (
            inspect_workbook,
            rewrite_workbook,
            workbook_parts,
        )

        operation = sys.argv[1]
        if operation not in ("read", "rewrite"):
            raise StoragePolicyError("invalid_xlsx_content", 415)
        with open("/request.json", "rb") as request:
            raw = request.read(MAX_PLAN_BYTES + 1)
        if len(raw) > MAX_PLAN_BYTES:
            raise StoragePolicyError("xlsx_limits_exceeded", 413)
        payload = json.loads(raw)
        with os.fdopen(os.dup(0), "rb") as source:
            if (
                not 0
                < os.fstat(source.fileno()).st_size
                <= DEFAULT_POLICY.max_file_bytes
            ):
                raise StoragePolicyError("xlsx_limits_exceeded", 413)
            if operation == "rewrite":
                plan = validate_plan(payload)
                digest = hashlib.sha256()
                while chunk := source.read(DEFAULT_POLICY.chunk_bytes):
                    digest.update(chunk)
                if digest.hexdigest() != plan.source_sha256:
                    raise StoragePolicyError("xlsx_source_changed", 409)
                source.seek(0)
            verify_ooxml(source, "xlsx", DEFAULT_POLICY)
            source.seek(0)
            with zipfile.ZipFile(source) as package:
                parts = workbook_parts(package)
                view = inspect_workbook(package, parts)
                if operation == "rewrite":
                    data = rewrite_workbook(package, parts, view, payload)
                else:
                    data = json.dumps(
                        view, ensure_ascii=False, separators=(",", ":")
                    ).encode("utf-8")
                    if len(data) > MAX_READ_BYTES:
                        raise StoragePolicyError("xlsx_limits_exceeded", 413)
        with os.fdopen(os.dup(1), "r+b") as output:
            output.seek(0)
            output.write(data)
            output.flush()
            if operation == "rewrite":
                output.seek(0)
                verify_ooxml(output, "xlsx", DEFAULT_POLICY)
        logger.info("xlsx_worker_completed operation=%s", operation)
        return 0
    except MemoryError:
        result = {"error": "xlsx_limits_exceeded"}
    except StoragePolicyError as error:
        allowed = {
            "xlsx_limits_exceeded",
            "unsupported_xlsx_edit",
            "xlsx_edit_not_found",
            "invalid_xlsx_edits",
            "xlsx_source_changed",
        }
        result = {
            "error": error.code
            if error.code in allowed
            else "xlsx_limits_exceeded"
            if error.code.endswith("exceeded")
            else "invalid_xlsx_content"
        }
    except Exception:
        result = {"error": "invalid_xlsx_content"}
    with os.fdopen(os.dup(1), "r+b") as output:
        output.seek(0)
        output.truncate()
        output.write(json.dumps(result, separators=(",", ":")).encode("utf-8"))
    logger.info("xlsx_worker_rejected code=%s", result["error"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
