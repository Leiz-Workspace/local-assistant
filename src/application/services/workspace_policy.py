"""Define explicit owner-bound read-only workspace specifications and clean relative paths."""

import logging
from dataclasses import dataclass
from uuid import UUID

logger = logging.getLogger(__name__)
MAX_WORKSPACES = 8
MAX_PATH_BYTES = 4096
MAX_PATH_PARTS = 64


class WorkspaceAccessError(Exception):
    """Expose stable workspace errors without leaking native paths, contents or OS messages."""

    def __init__(self, code, status_code=404):
        """Record a safe error code for callers and the audit log."""
        super().__init__(code)
        self.code = code
        self.status_code = status_code
        logger.warning("workspace_access_rejected code=%s", code)


def clean_parts(value, *, absolute=False):
    """Validate bounded unexpanded POSIX components before any filesystem operation."""
    if not isinstance(value, str):
        raise WorkspaceAccessError("workspace_path_invalid", 422)
    try:
        length = len(value.encode("utf-8"))
    except UnicodeError:
        raise WorkspaceAccessError("workspace_path_invalid", 422) from None
    if (
        not 1 <= length <= MAX_PATH_BYTES
        or "\\" in value
        or any(ord(char) < 32 or ord(char) == 127 for char in value)
        or value.startswith("/") != absolute
    ):
        raise WorkspaceAccessError("workspace_path_invalid", 422)
    parts = value[1:].split("/") if absolute else value.split("/")
    if (
        len(parts) > MAX_PATH_PARTS
        or any(part in {"", ".", ".."} for part in parts)
        or (not absolute and any(part.startswith(".") for part in parts))
    ):
        raise WorkspaceAccessError("workspace_path_invalid", 422)
    return tuple(parts)


@dataclass(frozen=True, slots=True)
class WorkspaceSpec:
    """Bind one explicitly configured absolute root and display name to exact owner/workspace UUIDs."""

    owner_id: UUID
    workspace_id: UUID
    root: str
    name: str

    def __post_init__(self):
        """Reject malformed identity, ambiguous root paths and unsafe display names without filesystem access."""
        if not isinstance(self.owner_id, UUID) or not isinstance(
            self.workspace_id, UUID
        ):
            raise WorkspaceAccessError("workspace_identity_invalid", 422)
        clean_parts(self.root, absolute=True)
        if (
            not isinstance(self.name, str)
            or not self.name.strip()
            or len(self.name) > 80
            or any(ord(char) < 32 or ord(char) == 127 for char in self.name)
        ):
            raise WorkspaceAccessError("workspace_name_invalid", 422)
        try:
            self.name.encode("utf-8")
        except UnicodeError:
            raise WorkspaceAccessError("workspace_name_invalid", 422) from None
        logger.info("workspace_spec_validated workspace_id=%s", self.workspace_id)
