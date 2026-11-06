"""Validate bounded existing-file patch inputs and render complete review diffs without accepting client authority."""

import difflib
import logging
import re

from src.application.services.workspace_policy import WorkspaceAccessError, clean_parts

logger = logging.getLogger(__name__)
MAX_SOURCE_BYTES = 8192
MAX_PROPOSALS = 16
PROPOSAL_SECONDS = 120
FILE_SECONDS = 5


def patch_input(path, expected_sha256, replacement):
    """Require a literal scoped path, exact base digest and bounded complete UTF-8 replacement without NUL."""
    clean_parts(path)
    try:
        valid = (
            isinstance(expected_sha256, str)
            and re.fullmatch(r"[a-f0-9]{64}", expected_sha256)
            and isinstance(replacement, str)
        )
        if not valid:
            raise ValueError()
        raw = replacement.encode("utf-8")
        if len(raw) > MAX_SOURCE_BYTES or b"\x00" in raw:
            raise ValueError()
    except (ValueError, UnicodeError):
        raise WorkspaceAccessError("patch_request_invalid", 422) from None
    logger.info("patch_request_validated")
    return raw


def unified_patch(path, original, replacement):
    """Render exact bounded unified diff with explicit missing-final-LF markers rather than ambiguous joined lines."""
    lines = difflib.unified_diff(
        original.splitlines(keepends=True),
        replacement.splitlines(keepends=True),
        fromfile="a/" + path,
        tofile="b/" + path,
        lineterm="\n",
    )
    result = "".join(
        line if line.endswith("\n") else line + "\n\\ No newline at end of file\n"
        for line in lines
    )
    logger.info("patch_diff_rendered bytes=%d", len(result.encode("utf-8")))
    return result
