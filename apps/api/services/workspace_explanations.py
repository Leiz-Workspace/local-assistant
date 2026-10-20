"""Own source-selected existing CORE explanations and private evidence through final response delivery."""

import asyncio
import json
import logging
from contextlib import asynccontextmanager

from apps.api.services.files import file_io, finish_task
from apps.api.services.workspace_evidence import WorkspaceEvidence
from apps.api.services.workspace_tools import WorkspaceToolRun
from src.application.ports.inference import CompletionResult
from src.application.services.workspace_explanation import (
    explanation_messages,
    explanation_options,
    resolve_explanation,
)
from src.application.services.workspace_policy import WorkspaceAccessError
from src.infrastructure.inference.llama_adapter import LlamaInferenceAdapter

logger = logging.getLogger(__name__)
MODEL_SECONDS = 60


class WorkspaceExplanationService:
    """Compose explicitly selected D35 reads with fixed existing CORE and independently pinned source receipts."""

    def __init__(self, workspace, *, inference=None):
        """Bind existing services without model startup, host registration, database access or altered configuration."""
        self.workspace = workspace
        self.inference = inference if inference is not None else LlamaInferenceAdapter()
        self.admission = asyncio.Lock()
        self.operations = set()
        self.closing = False

    async def complete(self, messages):
        """Bound fixed CORE/fast generation and join cancellation before releasing source pins."""
        work = asyncio.create_task(
            self.inference.complete(
                profile="core",
                messages=messages,
                preset="fast",
                temperature=0,
                max_tokens=768,
            )
        )
        try:
            result = await asyncio.wait_for(asyncio.shield(work), MODEL_SECONDS)
            if (
                not isinstance(result, CompletionResult)
                or result.finish_reason != "stop"
                or result.preset_selected != "fast"
            ):
                raise WorkspaceAccessError("explanation_model_incomplete", 503)
            logger.info("workspace_explanation_core_completed")
            return result
        except TimeoutError:
            raise WorkspaceAccessError("explanation_model_timeout", 504) from None
        finally:
            if not work.done():
                work.cancel()
            try:
                await finish_task(work)
            except BaseException:
                logger.info("workspace_explanation_core_joined")

    async def validate(self, evidence):
        """Authorize pinned source identity and current bytes through fresh D34 final fences."""
        await evidence.revalidate()

    @asynccontextmanager
    async def operation(self, owner, identifier, question, sources):
        """Own one bounded explanation and retain source pins through model generation and response completion."""
        selections = explanation_options(question, sources)
        if self.closing or self.workspace.closing:
            raise WorkspaceAccessError("explanation_unavailable", 503)
        if self.admission.locked():
            raise WorkspaceAccessError("explanation_busy", 429)
        evidence = WorkspaceEvidence(self.workspace, owner, identifier, selections)
        run = WorkspaceToolRun(evidence, owner, identifier)
        await self.admission.acquire()
        task = asyncio.current_task()
        self.operations.add(task)
        try:
            lines = []
            try:
                for selection in selections:
                    raw = json.dumps(
                        dict(name="workspace.read", arguments=selection)
                    ).encode()
                    body = json.loads(await run.execute(raw))
                    lines.extend(body["data"]["lines"])
            finally:
                await run.close()
            messages, units = explanation_messages(question, lines)
            if units:
                completion = await self.complete(messages)
                await self.validate(evidence)
                evidence.payload = dict(
                    resolve_explanation(completion.content, units),
                    model_id=completion.model_id,
                )
            else:
                evidence.payload = dict(
                    status="no_sources",
                    answer=None,
                    citations=[],
                    content_trust="untrusted",
                    answer_trust="not_generated",
                )
            logger.info(
                "workspace_explanation_prepared citations=%d",
                len(evidence.payload["citations"]),
            )
            yield evidence
        finally:
            try:
                await file_io(evidence.close)
            finally:
                self.operations.discard(task)
                self.admission.release()
                logger.info("workspace_explanation_operation_closed")

    async def shutdown(self):
        """Reject new explanations and join every owned model/source operation before workspace teardown."""
        self.closing = True
        tasks = [task for task in self.operations if task is not asyncio.current_task()]
        for task in tasks:
            task.cancel()
        for task in tasks:
            try:
                await finish_task(task)
            except BaseException:
                logger.info("workspace_explanation_operation_joined")
        logger.info("workspace_explanation_shutdown_complete")
