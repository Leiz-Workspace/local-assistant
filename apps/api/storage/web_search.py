"""Initialize the operator-enabled fixed owned SearXNG and original CORE search service without network startup."""

import logging
import os

from apps.api.services.web_search import WebSearchService
from src.application.services.search_pipeline import SearchPipeline
from src.infrastructure.inference.llama_adapter import LlamaInferenceAdapter
from src.infrastructure.searxng_search import SearxNGSearchAdapter

logger = logging.getLogger(__name__)


async def initialize_web_search_service():
    """Keep startup inert unless explicitly enabled and never load/download a model or query the provider."""
    if os.environ.get("ASSISTANT_WEB_SEARCH_ENABLED", "0") != "1":
        logger.info("web_search_disabled")
        return None
    pipeline = SearchPipeline(
        provider_id="searxng",
        provider=SearxNGSearchAdapter(instance_reviewed=True),
        inference=LlamaInferenceAdapter(),
    )
    logger.info("web_search_initialized")
    return WebSearchService(pipeline)
