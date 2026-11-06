"""Initialize default-off ephemeral approval state without database, model, Vault or execution permissions."""

import logging
import os

from src.application.services.approvals import ApprovalStore

logger = logging.getLogger(__name__)


async def initialize_approval_store(workspace):
    """Require explicit local approval enablement and the accepted owner/workspace catalog before storing review requests."""
    if os.environ.get("ASSISTANT_APPROVAL_ENABLED", "0") != "1":
        logger.info("approval_disabled")
        return None
    if workspace is None or workspace.closing:
        raise RuntimeError("Approval review requires enabled workspace reads")
    logger.info("approval_initialized")
    return ApprovalStore(workspace.catalog)
