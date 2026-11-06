"""Extract bounded native PDF pages through the isolated D17 parser boundary."""

import json
import logging
import subprocess
import tempfile
from importlib.metadata import version
from typing import BinaryIO

from src.application.services.file_storage_policy import StoragePolicyError
from src.infrastructure.file_verifier import sandbox_command

logger = logging.getLogger(__name__)
MAX_PAGE_TEXT_BYTES = 128 * 1024
MAX_DOCUMENT_TEXT_BYTES = 1024 * 1024
MAX_EXTRACTION_OUTPUT_BYTES = 8 * 1024 * 1024
MAX_EXTRACTION_PAGES = 1000
EXTRACTION_WALL_SECONDS = 10
EXTRACTOR_VERSION = "native-pdf-v1:pypdf-" + version("pypdf")


def validate_pages(payload: object) -> list[dict]:
    """Validate the worker protocol and reject partial, oversized or ambiguous page results."""
    if not isinstance(payload, dict) or set(payload) != {"extractor", "pages"}:
        raise StoragePolicyError("extraction_unavailable", 503)
    pages = payload["pages"]
    if (
        payload["extractor"] != EXTRACTOR_VERSION
        or not isinstance(pages, list)
        or not 1 <= len(pages) <= MAX_EXTRACTION_PAGES
    ):
        raise StoragePolicyError("extraction_unavailable", 503)
    total = 0
    for number, page in enumerate(pages, 1):
        if (
            not isinstance(page, dict)
            or set(page) != {"page_number", "text"}
            or type(page["page_number"]) is not int
            or page["page_number"] != number
            or not isinstance(page["text"], str)
        ):
            raise StoragePolicyError("extraction_unavailable", 503)
        try:
            size = len(page["text"].encode("utf-8"))
        except UnicodeError:
            raise StoragePolicyError("extraction_unavailable", 503) from None
        total += size
        if size > MAX_PAGE_TEXT_BYTES or total > MAX_DOCUMENT_TEXT_BYTES:
            raise StoragePolicyError("extraction_limits_exceeded", 413)
    return pages


def extract_pdf(source: BinaryIO) -> list[dict]:
    """Run a credential-free bounded worker using only a borrowed read-only source descriptor."""
    command = sandbox_command(
        ["/venv/bin/python", "-m", "src.infrastructure.pdf_extractor_worker"]
    )
    source.seek(0)
    try:
        with tempfile.TemporaryFile() as output:
            result = subprocess.run(
                command,
                stdin=source,
                stdout=output,
                stderr=subprocess.DEVNULL,
                timeout=EXTRACTION_WALL_SECONDS,
                env={},
                close_fds=True,
                start_new_session=True,
                check=False,
            )
            output.seek(0)
            data = output.read(MAX_EXTRACTION_OUTPUT_BYTES + 1)
    except subprocess.TimeoutExpired:
        raise StoragePolicyError("extraction_timeout", 413) from None
    except OSError:
        raise StoragePolicyError("extraction_unavailable", 503) from None
    finally:
        source.seek(0)
    if result.returncode or len(data) > MAX_EXTRACTION_OUTPUT_BYTES:
        raise StoragePolicyError("extraction_unavailable", 503)
    try:
        payload = json.loads(data)
    except (ValueError, UnicodeError, RecursionError):
        raise StoragePolicyError("extraction_unavailable", 503) from None
    if (
        isinstance(payload, dict)
        and set(payload) == {"error"}
        and payload["error"] in ("invalid_pdf_content", "extraction_limits_exceeded")
    ):
        code = payload["error"]
        raise StoragePolicyError(code, 413 if code.endswith("exceeded") else 415)
    pages = validate_pages(payload)
    logger.info(
        "pdf_extraction_completed pages=%d extractor=%s", len(pages), EXTRACTOR_VERSION
    )
    return pages
