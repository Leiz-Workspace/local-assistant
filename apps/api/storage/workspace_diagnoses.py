"""Initialize optional source-backed manual diagnosis without model loading or execution capability."""

import logging
import os

from apps.api.services.workspace_diagnoses import WorkspaceDiagnosisService

logger = logging.getLogger(__name__)


async def initialize_workspace_diagnoses(workspace):
    """Require explicit enablement and a live authorized workspace before creating the inert diagnosis service."""
    if os.environ.get("ASSISTANT_WORKSPACE_DIAGNOSE_ENABLED", "0") != "1":
        logger.info("workspace_diagnosis_disabled")
        return None
    if workspace is None or workspace.closing:
        raise RuntimeError("Workspace diagnosis requires enabled workspace reads")
    logger.info("workspace_diagnosis_initialized")
    return WorkspaceDiagnosisService(workspace)
