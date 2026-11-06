"""Retire only an idle owner-linked native patch capability without editing source, rewriting approval history or fabricating checkpoint intent."""

import logging

from apps.api.services.files import file_io
from src.application.services.workspace_policy import WorkspaceAccessError

logger = logging.getLogger(__name__)


async def retire_pending_patch(patches, owner, workspace, identifier):
    """Serialize exact owner lookup and pending-capability closure while preserving known commits and independently applying actions."""
    async with patches.operation():
        native = patches.find(owner, workspace, identifier)
        retired = False
        with native.lock:
            if native.state == "applying":
                raise WorkspaceAccessError("workflow_component_busy", 409)
            if native.state == "proposed":
                native.state = "failed"
                native.error_code = "workflow_cancelled"
                retired = True
        uncertain = False
        if retired:
            try:
                await file_io(native.close)
            except OSError:
                uncertain = True
                logger.warning(
                    "workflow_pending_patch_close_uncertain proposal_id=%s", identifier
                )
        value = patches.record_view(native)
        logger.info(
            "workflow_pending_patch_retired proposal_id=%s retired=%s cleanup_uncertain=%s",
            identifier,
            retired,
            uncertain,
        )
        return value, uncertain
