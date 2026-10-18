"""Constrain native PDF parsing and return all page text or a sanitized failure."""

import json
import logging
import os
import resource
import sys

logger = logging.getLogger(__name__)


def main() -> int:
    """Set hard limits before parser imports and never serialize parser exception details."""
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
    resource.setrlimit(resource.RLIMIT_FSIZE, (8 * 1024 * 1024, 8 * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_NOFILE, (32, 32))
    os.umask(0o077)
    from src.application.services.file_storage_policy import (
        DEFAULT_POLICY,
        StoragePolicyError,
    )
    from src.infrastructure.pdf_extractor import (
        EXTRACTOR_VERSION,
        MAX_DOCUMENT_TEXT_BYTES,
        MAX_PAGE_TEXT_BYTES,
    )

    try:
        from pypdf import PdfReader

        from src.infrastructure.file_content_verifier import verify_pdf

        with os.fdopen(os.dup(0), "rb") as source:
            if os.fstat(source.fileno()).st_size > DEFAULT_POLICY.max_file_bytes:
                raise StoragePolicyError("extraction_limits_exceeded", 413)
            verify_pdf(source, DEFAULT_POLICY)
            source.seek(0)
            reader = PdfReader(source, strict=True)
            pages = []
            total = 0
            for number, page in enumerate(reader.pages, 1):
                text = page.extract_text(extraction_mode="plain") or ""
                size = len(text.encode("utf-8"))
                total += size
                if size > MAX_PAGE_TEXT_BYTES or total > MAX_DOCUMENT_TEXT_BYTES:
                    raise StoragePolicyError("extraction_limits_exceeded", 413)
                pages.append({"page_number": number, "text": text})
        result = {"extractor": EXTRACTOR_VERSION, "pages": pages}
    except MemoryError:
        result = {"error": "extraction_limits_exceeded"}
    except StoragePolicyError as error:
        result = {
            "error": "extraction_limits_exceeded"
            if error.code.endswith("exceeded")
            else "invalid_pdf_content"
        }
    except Exception:
        result = {"error": "invalid_pdf_content"}
    logger.info("pdf_extraction_worker_finished accepted=%s", "pages" in result)
    sys.stdout.write(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
