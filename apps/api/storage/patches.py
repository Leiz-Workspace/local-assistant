"""Initialize separately default-off approved patches without adding database, model or host workspace configuration."""

import logging
import os

from apps.api.services.patches import PatchService

logger = logging.getLogger(__name__)


async def initialize_patch_service(workspace, approvals):
    """Require both live scope and explicit approval dependencies before exposing local proposal/edit capability."""
    if os.environ.get("ASSISTANT_PATCH_ENABLED", "0") != "1":
        logger.info("patch_disabled")
        return None
    if workspace is None or workspace.closing or approvals is None or approvals.closing:
        raise RuntimeError(
            "Approved patches require live workspace and approval services"
        )
    logger.info("patch_initialized")
    return PatchService(workspace, approvals)
