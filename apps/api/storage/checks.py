"""Initialize separately default-off approved snapshot checks only with durable checkpoint composition and explicit private runtime configuration."""

import logging
import os
import threading

from apps.api.services.checkpoint_patches import CheckpointPatchService
from apps.api.services.checks import CheckService
from apps.api.services.files import file_io
from apps.api.services.workspaces import joined_work
from src.infrastructure.check_jobs import CheckJobStore
from src.infrastructure.check_runtime import RuntimeSpec

logger = logging.getLogger(__name__)
RUNTIME_SETTINGS = (
    "ASSISTANT_CHECKS_ROOT",
    "ASSISTANT_CHECKS_PYTHON_PATH",
    "ASSISTANT_CHECKS_PYTHON_SHA256",
    "ASSISTANT_CHECKS_STDLIB_ROOT",
    "ASSISTANT_CHECKS_RUFF_PATH",
    "ASSISTANT_CHECKS_RUFF_SHA256",
)


async def initialize_check_service(workspace, approvals, patches):
    """Require explicit trusted roots/tool hashes and live scope/approval/checkpoint dependencies before admitting isolated checks."""
    if os.environ.get("ASSISTANT_CHECKS_ENABLED", "0") != "1":
        logger.info("checks_disabled")
        return None
    if (
        workspace is None
        or workspace.closing
        or approvals is None
        or approvals.closing
        or not isinstance(patches, CheckpointPatchService)
        or patches.closing
        or patches.checkpoint_store.storage.closing
    ):
        raise RuntimeError(
            "Approved checks require live workspace, approval and durable checkpoint services"
        )
    settings = [os.environ.get(name) for name in RUNTIME_SETTINGS]
    if not all(settings):
        raise RuntimeError(
            "Approved checks require an explicit existing private root and trusted runtime paths/hashes"
        )
    root, python, python_sha, stdlib, ruff, ruff_sha = settings
    spec = RuntimeSpec(python, python_sha, stdlib, ruff, ruff_sha)
    stop = threading.Event()
    store = await joined_work(
        stop,
        CheckJobStore,
        root,
        workspace.catalog,
        spec,
        patches.checkpoint_store.storage.fd,
        stop,
        close_result=True,
    )
    try:
        service = CheckService(workspace, approvals, store)
    except BaseException:
        await file_io(store.close)
        raise
    logger.info("checks_initialized")
    return service
