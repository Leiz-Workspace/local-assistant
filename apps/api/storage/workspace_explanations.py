"""Initialize optional source-selected CORE explanations only after explicitly enabled workspace capability."""

import logging
import os

from apps.api.services.workspace_explanations import WorkspaceExplanationService

logger = logging.getLogger(__name__)


async def initialize_workspace_explanations(workspace):
    """Keep default startup inert and require the existing configured workspace service without loading a model."""
    if os.environ.get("ASSISTANT_WORKSPACE_EXPLAIN_ENABLED", "0") != "1":
        logger.info("workspace_explanation_disabled")
        return None
    if workspace is None or workspace.closing:
        raise RuntimeError("Workspace explanations require enabled workspace reads")
    logger.info("workspace_explanation_initialized")
    return WorkspaceExplanationService(workspace)
