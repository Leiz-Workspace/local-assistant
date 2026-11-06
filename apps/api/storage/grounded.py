"""Initialize optional stateless grounded generation only after explicit enablement and accepted dense retrieval."""

import logging
import os

from apps.api.services.grounded import GroundedService

logger = logging.getLogger(__name__)


async def initialize_grounded_service(retrieval):
    """Keep default startup inert and require live enabled retrieval before creating generation admission."""
    if os.environ.get("ASSISTANT_GROUNDED_ENABLED", "0") != "1":
        logger.info("grounded_disabled")
        return None
    if retrieval is None or retrieval.closing:
        raise RuntimeError("Grounded generation requires enabled retrieval")
    logger.info("grounded_initialized")
    return GroundedService(retrieval)
