"""Load explicitly enabled private workspace specifications without implicit roots, credential lookup or repository execution."""

import json
import logging
import os
import stat
from uuid import UUID

from apps.api.services.files import file_io
from apps.api.services.workspaces import WorkspaceService
from src.application.services.workspace_policy import WorkspaceSpec, clean_parts
from src.infrastructure.readonly_workspace import (
    READ_FLAGS,
    ROOT_FLAGS,
    ROOT_RESOLVE,
    WorkspaceCatalog,
    open_beneath,
)

logger = logging.getLogger(__name__)


def unique_object(pairs):
    """Reject duplicate JSON keys in trusted control-plane configuration rather than silently replacing identity."""
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("workspace_config_duplicate")
        result[key] = value
    return result


def load_workspace_catalog(path):
    """Read one bounded owner0600 single-link configuration without following symlink ancestors."""
    clean_parts(path, absolute=True)
    anchor = os.open("/", ROOT_FLAGS)
    try:
        descriptor = open_beneath(
            anchor, path[1:], flags=READ_FLAGS, resolve=ROOT_RESOLVE
        )
    finally:
        os.close(anchor)
    with os.fdopen(descriptor, "rb") as source:
        info = os.fstat(source.fileno())
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.geteuid()
            or stat.S_IMODE(info.st_mode) != 0o600
            or info.st_nlink != 1
            or info.st_size > 32768
        ):
            raise ValueError("workspace_config_unsafe")
        raw = source.read(32769)
        if len(raw) > 32768:
            raise ValueError("workspace_config_limit")
        after = os.fstat(source.fileno())
        if (
            info.st_dev,
            info.st_ino,
            info.st_size,
            info.st_mtime_ns,
            info.st_ctime_ns,
        ) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        ):
            raise ValueError("workspace_config_changed")
    payload = json.loads(raw, object_pairs_hook=unique_object)
    if (
        not isinstance(payload, dict)
        or set(payload) != {"description", "workspaces"}
        or not isinstance(payload["description"], str)
        or not 1 <= len(payload["description"].strip()) <= 512
        or not isinstance(payload["workspaces"], list)
        or len(payload["workspaces"]) > 8
    ):
        raise ValueError("workspace_config_invalid")
    specifications = []
    for item in payload["workspaces"]:
        if not isinstance(item, dict) or set(item) != {
            "owner_id",
            "workspace_id",
            "root",
            "name",
        }:
            raise ValueError("workspace_config_invalid")
        if not isinstance(item["owner_id"], str) or not isinstance(
            item["workspace_id"], str
        ):
            raise ValueError("workspace_config_invalid")
        specifications.append(
            WorkspaceSpec(
                UUID(item["owner_id"]),
                UUID(item["workspace_id"]),
                item["root"],
                item["name"],
            )
        )
    catalog = WorkspaceCatalog(specifications)
    for spec in specifications:
        with catalog.open(spec.owner_id, spec.workspace_id) as workspace:
            workspace.discover()
    logger.info("workspace_configuration_loaded count=%d", len(specifications))
    return catalog


async def initialize_workspace_service():
    """Keep default startup inert and fail closed on enabled but unavailable private configuration."""
    if os.environ.get("ASSISTANT_WORKSPACE_ENABLED", "0") != "1":
        logger.info("workspace_disabled")
        return None
    try:
        path = os.environ.get("ASSISTANT_WORKSPACE_CONFIG_FILE")
        catalog = await file_io(load_workspace_catalog, path)
    except Exception:
        logger.error("workspace_configuration_unavailable")
        raise RuntimeError(
            "Workspace initialization failed; verify runtime configuration."
        ) from None
    logger.info("workspace_initialized")
    return WorkspaceService(catalog)
