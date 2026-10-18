"""Run native/OCR/page rendering through the existing credential-free namespace boundary."""

import json
import logging
import subprocess
import tempfile

from src.application.services.file_storage_policy import StoragePolicyError
from src.application.services.ocr_contract import MAX_WORKER_BYTES, validate_page
from src.infrastructure.file_verifier import sandbox_command

logger = logging.getLogger(__name__)
OCR_WALL_SECONDS = 25
ERRORS = {
    "ocr_page_not_found": 422,
    "ocr_processing_timeout": 413,
    "ocr_processing_unavailable": 503,
    "ocr_limits_exceeded": 413,
    "invalid_ocr_request": 422,
    "invalid_ocr_content": 415,
}


def prepare_page(source, suffix, number=1, mode="auto"):
    """Pass trusted format/page/mode parameters only and retain the source FD until workers exit."""
    if (
        suffix not in ("pdf", "png", "jpg", "jpeg", "webp")
        or type(number) is not int
        or not 1 <= number <= 1000
        or mode not in ("auto", "ocr", "vlm")
    ):
        raise StoragePolicyError("invalid_ocr_request", 422)
    source.seek(0)
    try:
        with tempfile.TemporaryFile() as output:
            result = subprocess.run(
                sandbox_command(
                    [
                        "/venv/bin/python",
                        "-m",
                        "src.infrastructure.ocr_worker",
                        suffix,
                        str(number),
                        mode,
                    ]
                ),
                stdin=source,
                stdout=output,
                stderr=subprocess.DEVNULL,
                timeout=OCR_WALL_SECONDS,
                env={},
                close_fds=True,
                start_new_session=True,
                check=False,
            )
            output.seek(0)
            data = output.read(MAX_WORKER_BYTES + 1)
    except subprocess.TimeoutExpired:
        raise StoragePolicyError("ocr_processing_timeout", 413) from None
    except OSError:
        raise StoragePolicyError("ocr_processing_unavailable", 503) from None
    finally:
        source.seek(0)
    if result.returncode or len(data) > MAX_WORKER_BYTES:
        raise StoragePolicyError("ocr_processing_unavailable", 503)
    try:
        payload = json.loads(data)
    except (ValueError, UnicodeError, RecursionError):
        raise StoragePolicyError("ocr_processing_unavailable", 503) from None
    if (
        isinstance(payload, dict)
        and set(payload) == {"error"}
        and isinstance(payload["error"], str)
        and payload["error"] in ERRORS
    ):
        raise StoragePolicyError(payload["error"], ERRORS[payload["error"]])
    page = validate_page(payload)
    if page["page_number"] != number:
        raise StoragePolicyError("ocr_processing_unavailable", 503)
    logger.info("ocr_page_prepared method=%s page=%d", page["method"], number)
    return page
