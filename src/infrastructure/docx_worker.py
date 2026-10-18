"""Constrain DOCX inspection and run rewrite before importing untrusted-content parsers."""

import hashlib
import json
import logging
import os
import resource
import sys

logger = logging.getLogger(__name__)


def main():
    """Apply kernel budgets and publish only verified DOCX bytes or sanitized structured results."""
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
    from src.application.services.docx_contract import (
        MAX_PLAN_BYTES,
        MAX_READ_BYTES,
        validate_plan,
    )
    from src.application.services.file_storage_policy import (
        DEFAULT_POLICY,
        StoragePolicyError,
    )

    try:
        import zipfile

        from src.infrastructure.docx_content import (
            inspect_document,
            parse_xml,
            rewrite_document,
        )
        from src.infrastructure.file_content_verifier import verify_ooxml

        operation = sys.argv[1]
        if operation not in ("read", "rewrite"):
            raise StoragePolicyError("invalid_docx_content", 415)
        with open("/request.json", "rb") as request:
            raw = request.read(MAX_PLAN_BYTES + 1)
        if len(raw) > MAX_PLAN_BYTES:
            raise StoragePolicyError("docx_limits_exceeded", 413)
        payload = json.loads(raw)
        with os.fdopen(os.dup(0), "rb") as source:
            if (
                not 0
                < os.fstat(source.fileno()).st_size
                <= DEFAULT_POLICY.max_file_bytes
            ):
                raise StoragePolicyError("docx_limits_exceeded", 413)
            if operation == "rewrite":
                plan = validate_plan(payload)
                digest = hashlib.sha256()
                while chunk := source.read(DEFAULT_POLICY.chunk_bytes):
                    digest.update(chunk)
                if digest.hexdigest() != plan.source_sha256:
                    raise StoragePolicyError("docx_source_changed", 409)
                source.seek(0)
            verify_ooxml(source, "docx", DEFAULT_POLICY)
            source.seek(0)
            with zipfile.ZipFile(source) as package:
                root = parse_xml(package.read("word/document.xml"))
                view = inspect_document(package, root)
                if operation == "rewrite":
                    data = rewrite_document(package, root, payload)
                else:
                    data = json.dumps(
                        view, ensure_ascii=False, separators=(",", ":")
                    ).encode("utf-8")
                    if len(data) > MAX_READ_BYTES:
                        raise StoragePolicyError("docx_limits_exceeded", 413)
        with os.fdopen(os.dup(1), "r+b") as output:
            output.seek(0)
            output.write(data)
            output.flush()
            if operation == "rewrite":
                output.seek(0)
                verify_ooxml(output, "docx", DEFAULT_POLICY)
        logger.info("docx_worker_completed operation=%s", operation)
        return 0
    except MemoryError:
        result = {"error": "docx_limits_exceeded"}
    except StoragePolicyError as error:
        allowed = {
            "docx_limits_exceeded",
            "unsupported_docx_edit",
            "docx_edit_not_found",
            "invalid_docx_edits",
            "docx_source_changed",
        }
        result = {
            "error": error.code
            if error.code in allowed
            else "docx_limits_exceeded"
            if error.code.endswith("exceeded")
            else "invalid_docx_content"
        }
    except Exception:
        result = {"error": "invalid_docx_content"}
    with os.fdopen(os.dup(1), "r+b") as output:
        output.seek(0)
        output.truncate()
        output.write(json.dumps(result, separators=(",", ":")).encode("utf-8"))
    logger.info("docx_worker_rejected code=%s", result["error"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
