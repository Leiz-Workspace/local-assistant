"""Process DOCX files through a credential-free sandbox with bounded edit-plan and output FDs."""

import json
import logging
import subprocess
import tempfile

from src.application.services.docx_contract import (
    MAX_OUTPUT_BYTES,
    MAX_PLAN_BYTES,
    MAX_READ_BYTES,
    validate_plan,
    validate_view,
)
from src.application.services.file_storage_policy import StoragePolicyError
from src.infrastructure.file_verifier import sandbox_command
from src.infrastructure.native_input import rewind_native_input
from src.infrastructure.sandbox_process import run_sandbox

logger = logging.getLogger(__name__)
DOCX_WALL_SECONDS = 10
ERRORS = {
    "invalid_docx_content": 415,
    "docx_limits_exceeded": 413,
    "unsupported_docx_edit": 422,
    "docx_edit_not_found": 422,
    "invalid_docx_edits": 422,
    "docx_source_changed": 409,
}


def process_docx(source, operation="read", plan=None):
    """Use only retained source and anonymous metadata FDs, never raw text in argv or environment."""
    if operation not in ("read", "rewrite"):
        raise StoragePolicyError("invalid_docx_operation", 422)
    payload = validate_plan(plan).model_dump() if operation == "rewrite" else {}
    metadata = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode(
        "utf-8"
    )
    if len(metadata) > MAX_PLAN_BYTES:
        raise StoragePolicyError("docx_edits_too_large", 413)
    rewind_native_input(source)
    try:
        with tempfile.TemporaryFile() as request, tempfile.TemporaryFile() as output:
            request.write(metadata)
            request.seek(0)
            command = sandbox_command(
                ["/venv/bin/python", "-m", "src.infrastructure.docx_worker", operation]
            )
            payload_index = command.index("--ro-bind-data")
            command[payload_index:payload_index] = [
                "--ro-bind-data",
                str(request.fileno()),
                "/request.json",
            ]
            result = run_sandbox(
                command,
                stdin=source,
                stdout=output,
                stderr=subprocess.DEVNULL,
                timeout=DOCX_WALL_SECONDS,
                env={},
                close_fds=True,
                pass_fds=(request.fileno(),),
                start_new_session=True,
            )
            output.seek(0)
            data = output.read(MAX_OUTPUT_BYTES + 1)
    except subprocess.TimeoutExpired:
        raise StoragePolicyError("docx_processing_timeout", 413) from None
    except OSError:
        raise StoragePolicyError("docx_processing_unavailable", 503) from None
    finally:
        rewind_native_input(source)
    if result.returncode or len(data) > MAX_OUTPUT_BYTES:
        raise StoragePolicyError("docx_processing_unavailable", 503)
    if operation == "rewrite" and data.startswith(b"PK\x03\x04"):
        logger.info("docx_rewrite_completed output_bytes=%d", len(data))
        return data
    if len(data) > MAX_READ_BYTES:
        raise StoragePolicyError("docx_processing_unavailable", 503)
    try:
        payload = json.loads(data)
    except (ValueError, UnicodeError, RecursionError):
        raise StoragePolicyError("docx_processing_unavailable", 503) from None
    if (
        isinstance(payload, dict)
        and set(payload) == {"error"}
        and isinstance(payload["error"], str)
        and payload["error"] in ERRORS
    ):
        raise StoragePolicyError(payload["error"], ERRORS[payload["error"]])
    if operation != "read":
        raise StoragePolicyError("docx_processing_unavailable", 503)
    view = validate_view(payload)
    logger.info(
        "docx_read_completed paragraphs=%d tables=%d",
        len(view["paragraphs"]),
        len(view["tables"]),
    )
    return view
