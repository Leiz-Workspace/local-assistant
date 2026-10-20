"""Initialize separately default-off approved patches without adding database, model or host workspace configuration."""

import logging
import os

from apps.api.services.checkpoint_patches import CheckpointPatchService
from apps.api.services.files import file_io
from apps.api.services.patches import PatchService
from src.infrastructure.checkpoints import CheckpointStore

logger = logging.getLogger(__name__)


async def initialize_patch_service(workspace, approvals):
    """Require both live scope and explicit approval dependencies before exposing local proposal/edit capability."""
    if os.environ.get("ASSISTANT_PATCH_ENABLED", "0") != "1":
        if os.environ.get("ASSISTANT_CHECKPOINT_ENABLED", "0") == "1":
            raise RuntimeError("Private checkpoints require enabled approved patches")
        logger.info("patch_disabled")
        return None
    if workspace is None or workspace.closing or approvals is None or approvals.closing:
        raise RuntimeError(
            "Approved patches require live workspace and approval services"
        )
    logger.info("patch_initialized")
    if os.environ.get("ASSISTANT_CHECKPOINT_ENABLED", "0") == "1":
        root = os.environ.get("ASSISTANT_CHECKPOINT_ROOT")
        if not root:
            raise RuntimeError(
                "Private checkpoints require an explicit existing private root"
            )
        store = await file_io(
            CheckpointStore, root, workspace.catalog, close_result=True
        )
        try:
            return CheckpointPatchService(workspace, approvals, store)
        except BaseException:
            await file_io(store.close)
            raise
    return PatchService(workspace, approvals)
