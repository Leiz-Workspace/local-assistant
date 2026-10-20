"""Initialize separately default-off finite coding workflows only with matching live checkpoint/check/approval/workspace dependencies."""

import logging
import os

from apps.api.services.checkpoint_patches import CheckpointPatchService
from apps.api.services.checks import CheckService
from apps.api.services.coding_workflows import CodingWorkflowService

logger = logging.getLogger(__name__)


async def initialize_coding_workflow_service(workspace, approvals, patches, checks):
    """Bind the established CORE adapter and existing native services without opening roots, loading a model or creating approvals."""
    if os.environ.get("ASSISTANT_CODING_WORKFLOW_ENABLED", "0") != "1":
        logger.info("coding_workflow_disabled")
        return None
    if (
        workspace is None
        or approvals is None
        or not isinstance(patches, CheckpointPatchService)
        or not isinstance(checks, CheckService)
    ):
        raise RuntimeError(
            "Coding workflows require live durable patch/check/approval/workspace services"
        )
    if (
        any(value.closing for value in (workspace, approvals, patches, checks))
        or patches.workspace is not workspace
        or checks.workspace is not workspace
        or patches.approvals is not approvals
        or checks.approvals is not approvals
        or patches.checkpoint_store.storage.closing
        or checks.store.closing
    ):
        raise RuntimeError("Coding workflows require matching live composition")
    service = CodingWorkflowService(workspace, approvals, patches, checks)
    logger.info("coding_workflow_initialized")
    return service
