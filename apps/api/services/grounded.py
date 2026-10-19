"""Own default-off source-held grounded generation and join model/source resources through response delivery."""

import asyncio
import logging
from contextlib import asynccontextmanager

from apps.api.services.files import finish_task
from src.application.ports.inference import CompletionResult
from src.application.services.file_storage_policy import StoragePolicyError
from src.application.services.grounded_answer import build_messages, parse_answer
from src.infrastructure.inference.llama_adapter import LlamaInferenceAdapter
from src.infrastructure.qdrant_retrieval import search_options

logger = logging.getLogger(__name__)


class GroundedService:
    """Compose unchanged dense source authorization and fixed existing CORE inference without persistence."""

    def __init__(self, retrieval, *, inference=None, model_timeout=60):
        """Bind existing resources and a bounded model-only deadline without new credentials or model setup."""
        if type(model_timeout) not in (int, float) or not 0 < model_timeout <= 60:
            raise ValueError("grounded_timeout_invalid")
        self.retrieval = retrieval
        self.inference = inference or LlamaInferenceAdapter()
        self.model_timeout = model_timeout
        self.admission = asyncio.Lock()
        self.operations = set()
        self.closing = False

    async def validate(self, owner, retained):
        """Delegate final delivery to exact current owner/root/hash/SQL-generation/source-byte authorization."""
        await self.retrieval.validate(owner, retained)

    async def complete(self, messages):
        """Bound fixed CORE/fast generation and join client work despite timeout or repeated cancellation."""
        work = asyncio.create_task(
            self.inference.complete(
                profile="core",
                messages=messages,
                preset="fast",
                temperature=0,
                max_tokens=512,
            )
        )
        try:
            result = await asyncio.wait_for(asyncio.shield(work), self.model_timeout)
            if (
                not isinstance(result, CompletionResult)
                or result.finish_reason != "stop"
                or result.preset_selected != "fast"
            ):
                raise StoragePolicyError("grounded_model_incomplete", 503)
            logger.info("grounded_model_completed")
            return result
        except TimeoutError:
            logger.warning("grounded_model_timeout")
            raise StoragePolicyError("grounded_model_timeout", 504) from None
        finally:
            if not work.done():
                work.cancel()
            try:
                await finish_task(work)
            except BaseException:
                logger.info("grounded_model_task_joined")

    @asynccontextmanager
    async def operation(self, owner, query, *, top_k=3, file_ids=None):
        """Hold source readers and nonqueued admission across model delay, parsing and final response delivery."""
        search_options(query, top_k, file_ids)
        if top_k > 3:
            raise StoragePolicyError("grounded_source_limit", 422)
        if self.closing or self.retrieval.closing:
            raise StoragePolicyError("grounded_unavailable", 503)
        if self.admission.locked():
            raise StoragePolicyError("grounded_busy", 429)
        await self.admission.acquire()
        task = asyncio.current_task()
        self.operations.add(task)
        try:
            if self.closing:
                raise StoragePolicyError("grounded_unavailable", 503)
            async with self.retrieval.operation(
                owner, query, top_k=top_k, file_ids=file_ids
            ) as (sources, retained):
                hits = sources["hits"]
                if hits:
                    await self.validate(owner, retained)
                    completion = await self.complete(build_messages(query, hits))
                    await self.validate(owner, retained)
                    payload = dict(
                        parse_answer(completion.content, hits),
                        model_id=completion.model_id,
                    )
                else:
                    payload = dict(
                        status="no_sources",
                        answer=None,
                        citations=[],
                        answer_trust="not_generated",
                        content_trust="untrusted",
                    )
                logger.info(
                    "grounded_response_prepared sources=%d citations=%d",
                    len(hits),
                    len(payload["citations"]),
                )
                yield payload, retained
        finally:
            self.operations.discard(task)
            self.admission.release()
            logger.info("grounded_operation_closed")

    async def shutdown(self):
        """Stop new grounded work and join every owned operation before shared retrieval/file shutdown."""
        self.closing = True
        tasks = list(self.operations)
        for task in tasks:
            task.cancel()
        for task in tasks:
            try:
                await finish_task(task)
            except BaseException:
                logger.info("grounded_owned_operation_joined")
        logger.info("grounded_shutdown_complete")
