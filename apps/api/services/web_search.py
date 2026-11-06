"""Own bounded authenticated search requests and joined pipeline tasks through response completion."""

import asyncio
import logging
from contextlib import asynccontextmanager
from uuid import UUID

from apps.api.services.files import finish_task
from src.application.services.search_pipeline import SearchPipelineError
from src.application.services.web_search_policy import (
    WebSearchError,
    WebSearchQuota,
    normalize_query,
)

logger = logging.getLogger(__name__)
create_task = asyncio.create_task


class WebSearchService:
    """Retain one nonqueued request until its provider/model work and final HTTP delivery have finished."""

    def __init__(self, pipeline, *, clock=None):
        """Bind the accepted pipeline and finite quota without endpoint, credential or model startup."""
        self.pipeline = pipeline
        self.quota = WebSearchQuota(**({"clock": clock} if clock is not None else {}))
        self.admission = asyncio.Lock()
        self.operations = set()
        self.closing = False
        logger.info("web_search_service_initialized")

    @asynccontextmanager
    async def operation(self, owner, query):
        """Charge one admitted explicit query and retain its slot until the response closes its context."""
        if not isinstance(owner, UUID):
            raise WebSearchError("web_search_owner_invalid")
        normalized = normalize_query(query)
        if self.closing:
            raise WebSearchError("web_search_unavailable")
        if self.admission.locked():
            raise WebSearchError("web_search_busy", retry_after=1)
        await self.admission.acquire()
        caller, work = asyncio.current_task(), None
        try:
            self.quota.charge(owner)
            self.operations.add(caller)
            pending = self.pipeline.run(normalized)
            try:
                work = create_task(pending)
            except BaseException:
                pending.close()
                raise
            try:
                payload = await asyncio.shield(work)
            except asyncio.CancelledError:
                work.cancel()
                try:
                    await finish_task(work)
                except BaseException:
                    logger.info("web_search_cancelled_child_joined")
                raise
            except SearchPipelineError as error:
                if error.code in {"search_provider_timeout", "search_model_timeout"}:
                    raise WebSearchError("web_search_timeout") from None
                if error.code in {
                    "search_provider_failed",
                    "search_provider_unconfigured",
                }:
                    raise WebSearchError("web_search_provider_unavailable") from None
                if error.code == "search_model_failed":
                    raise WebSearchError("web_search_model_unavailable") from None
                raise WebSearchError("web_search_pipeline_invalid") from None
            result = dict(
                payload, query=normalized, normalization_applied=normalized != query
            )
            logger.info("web_search_response_prepared")
            yield result
        finally:
            if work is not None and not work.done():
                work.cancel()
                try:
                    await finish_task(work)
                except BaseException:
                    logger.info("web_search_owned_child_joined")
            self.operations.discard(caller)
            self.admission.release()
            logger.info("web_search_operation_closed")

    async def shutdown(self):
        """Reject new requests and cancel/join only owned callers before application resource teardown."""
        self.closing = True
        tasks = [task for task in self.operations if task is not asyncio.current_task()]
        for task in tasks:
            task.cancel()
        for task in tasks:
            try:
                await finish_task(task)
            except BaseException:
                logger.info("web_search_shutdown_request_joined")
        logger.info("web_search_shutdown_complete")
