"""Initialize default-disabled read-only retrieval from existing approved ingestion resources."""

import logging
import os

from apps.api.services.retrieval import RetrievalService

logger = logging.getLogger(__name__)


async def initialize_retrieval_service(ingestion):
    """Require enabled ingestion before binding retrieval without creating collections or reading credentials."""
    if os.environ.get("ASSISTANT_RETRIEVAL_ENABLED", "0") != "1":
        logger.info("retrieval_disabled")
        return None
    if ingestion is None or ingestion.closing:
        raise RuntimeError("Retrieval requires enabled ingestion")
    if await ingestion.vectors.owned() is None:
        raise RuntimeError("Retrieval requires the owned ingestion collection")
    logger.info("retrieval_initialized")
    return RetrievalService(ingestion)
