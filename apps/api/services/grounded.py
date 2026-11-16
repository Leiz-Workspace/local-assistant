"""Own default-off source-held grounded generation and join model/source resources through response delivery."""

import asyncio
import logging
from contextlib import asynccontextmanager

from apps.api.services.files import finish_task
from src.application.ports.inference import CompletionResult, InferenceFailure
from src.application.services import gpu_admission
from src.application.services import grounded_extract as protocol
from src.application.services.file_storage_policy import StoragePolicyError
from src.application.services.gpu_admission import AdmissionBusy
from src.application.services.grounded_answer import build_messages, parse_answer
from src.application.services.workspace_policy import WorkspaceAccessError
from src.infrastructure.inference.core_request_seal import seal_payload
from src.infrastructure.inference.llama_adapter import LlamaInferenceAdapter
from src.infrastructure.inference.structured_excerpt_adapter import (
    StructuredExcerptAdapter,
    encoded,
)
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

    async def complete_extraction(self, adapter, messages):
        """Bound one per-request structured CORE call and join it despite timeout or repeated cancellation."""
        work = asyncio.create_task(
            adapter.complete(
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
                or result.model_id != protocol.MODEL_ID
                or adapter.provenance is None
            ):
                raise StoragePolicyError("extract_model_unavailable", 503)
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

    async def extract_sources(self, owner, fields, hits, retained, transport):
        """Refuse unsupported sources before any transport call, then run and publish one fenced extraction."""
        try:
            binding = protocol.bind_sources(fields, hits)
        except StoragePolicyError as error:
            if error.code in {"extract_source_mismatch", "extract_source_unsupported"}:
                logger.info("grounded_extract_source_refused code=%s", error.code)
            raise
        try:
            adapter = StructuredExcerptAdapter(
                request=binding.request,
                fields=binding.adapter_fields,
                source_modes=dict(binding.source_modes),
                model_id=protocol.MODEL_ID,
                facts_key=protocol.FACTS_KEY,
                schema_enabled=protocol.SCHEMA_ENABLED,
                literal_strings=protocol.LITERAL_STRINGS,
                transport=transport,
            )
        except ValueError:
            raise StoragePolicyError("extract_contract_invalid", 422) from None
        try:
            # prepare() is pure; the native frame is checked here because the
            # adapter only bounds it after three backend requests. The check
            # runs on the sealed frame, which is the size the adapter sends.
            copied, schema, _ = adapter.prepare(binding.messages)
            frame, _ = seal_payload(
                dict(
                    model=protocol.MODEL_ID,
                    messages=copied,
                    temperature=0,
                    stream=False,
                    max_tokens=512,
                    chat_template_kwargs=dict(enable_thinking=False),
                    response_format=dict(type="json_object", schema=schema),
                ),
                "grounded_precheck",
            )
            encoded(frame)
        except (ValueError, TypeError, WorkspaceAccessError):
            logger.info(
                "grounded_extract_source_refused code=extract_source_unsupported"
            )
            raise StoragePolicyError("extract_source_unsupported", 422) from None
        logger.info("grounded_extract_admitted fields=%d", len(fields))
        await self.validate(owner, retained)
        result = None
        try:
            result = await self.complete_extraction(adapter, binding.messages)
        except InferenceFailure as error:
            if error.code != "structured_insufficient_evidence":
                # The unchanged adapter wraps an inner guarded AdmissionBusy as a
                # backend failure; a quarantined gate is the only mid-call cause.
                gate = gpu_admission._coordinator
                if gate is not None and gate.poisoned:
                    raise AdmissionBusy("gpu_busy") from None
                raise StoragePolicyError("extract_model_unavailable", 503) from None
        await self.validate(owner, retained)
        if result is None:
            logger.info("grounded_extract_insufficient_evidence")
            return protocol.refusal_payload()
        payload = protocol.publish_extraction(
            result.content, binding, adapter.provenance
        )
        logger.info(
            "grounded_extract_published fields=%d citations=%d",
            len(fields),
            len(payload["citations"]),
        )
        return payload

    @asynccontextmanager
    async def extraction(self, owner, query, fields, *, transport=None):
        """Hold sources and the shared grounded admission across one frozen extraction and its delivery."""
        protocol.validate_fields(fields)
        file_ids = [file_id for _, _, file_id in fields]
        search_options(query, len(fields), file_ids)
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
                owner, query, top_k=len(fields), file_ids=file_ids
            ) as (sources, retained):
                hits = sources["hits"]
                if hits:
                    payload = await self.extract_sources(
                        owner, fields, hits, retained, transport
                    )
                else:
                    logger.info("grounded_extract_source_refused code=no_sources")
                    payload = protocol.no_sources_payload()
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
