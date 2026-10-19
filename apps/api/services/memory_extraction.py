"""Own explicit message-memory source/model/capture/delivery lifetimes without automatic learning or model changes."""

import asyncio
import logging
from contextlib import asynccontextmanager

from apps.api.services.files import finish_task
from apps.api.services.memory_work import joined_memory_work
from src.application.ports.inference import CompletionResult
from src.application.services.memory_contract import MemoryPolicyError
from src.application.services.memory_selection import (
    parse_selection,
    selection_messages,
)
from src.infrastructure.inference.llama_adapter import LlamaInferenceAdapter

logger = logging.getLogger(__name__)


class MemoryExtractor:
    """Select at most one literal user-message quote under current consent and tracked response-lifetime ownership."""

    def __init__(self, journal, *, inference=None, model_timeout=60):
        """Bind the existing journal/CORE adapter with one nonqueued selection and a bounded model deadline."""
        if type(model_timeout) not in (int, float) or not 0 < model_timeout <= 60:
            raise ValueError("memory_model_timeout_invalid")
        self.journal = journal
        self.inference = inference or LlamaInferenceAdapter()
        self.model_timeout = model_timeout
        self.admission = asyncio.Lock()
        self.operations = {}
        self.closing = False

    async def complete(self, kind, source):
        """Use only fixed CORE/fast selection and join model-client cleanup on deadline or cancellation."""
        try:
            result = await joined_memory_work(
                self.inference.complete(
                    profile="core",
                    messages=selection_messages(kind, source),
                    preset="fast",
                    temperature=0,
                    max_tokens=512,
                ),
                timeout=self.model_timeout,
            )
        except TimeoutError:
            raise MemoryPolicyError("memory_model_timeout") from None
        if (
            not isinstance(result, CompletionResult)
            or result.finish_reason != "stop"
            or result.preset_selected != "fast"
            or not isinstance(result.model_id, str)
            or not result.model_id.strip()
        ):
            raise MemoryPolicyError("memory_model_invalid")
        logger.info("memory_selection_model_completed")
        return result

    @asynccontextmanager
    async def operation(self, owner, consent_id, conversation_id, message_id):
        """Hold tracked selection ownership through SQL/source/model work and eventual response delivery."""
        if self.closing:
            raise MemoryPolicyError("memory_unavailable")
        if self.admission.locked():
            raise MemoryPolicyError("memory_busy")
        await self.admission.acquire()
        task = asyncio.current_task()
        self.operations[task] = (owner, consent_id)
        try:
            if self.closing:
                raise MemoryPolicyError("memory_unavailable")
            consent, source = await joined_memory_work(
                self.journal.preflight_selection(
                    owner, consent_id, conversation_id, message_id
                )
            )
            result = await self.complete(consent.kind, source)
            quote = parse_selection(result.content, source)
            record = None
            if quote is not None:
                record = await joined_memory_work(
                    self.journal.capture_selection(
                        owner, consent_id, source, quote, result.model_id
                    )
                )
            payload = dict(
                status="captured" if record is not None else "insufficient_evidence",
                record=record,
                content_trust="untrusted",
            )
            logger.info("memory_selection_prepared captured=%s", record is not None)
            yield payload, (source, record)
        finally:
            self.operations.pop(task, None)
            self.admission.release()
            logger.info("memory_selection_operation_closed")

    async def validate(self, owner, consent_id, retained):
        """Require fresh source/consent and exact stored record version before any generated response headers."""
        source, record = retained
        await joined_memory_work(
            self.journal.validate_selection(owner, consent_id, source, record)
        )

    async def cancel_owner(self, owner, consent_id=None):
        """Cancel/join matching in-flight selections only after an owner control transaction committed."""
        tasks = [
            task
            for task, (principal, receipt) in list(self.operations.items())
            if principal == owner and (consent_id is None or consent_id == receipt)
        ]
        for task in tasks:
            task.cancel()
        for task in tasks:
            try:
                await finish_task(task)
            except BaseException:
                logger.info("memory_owner_selection_joined")

    async def shutdown(self):
        """Stop new selections and join every owned model/source/SQL operation before resource shutdown."""
        self.closing = True
        tasks = list(self.operations)
        for task in tasks:
            task.cancel()
        for task in tasks:
            try:
                await finish_task(task)
            except BaseException:
                logger.info("memory_selection_task_joined")
        logger.info("memory_selection_shutdown_complete")
