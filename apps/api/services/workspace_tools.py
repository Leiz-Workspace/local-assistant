"""Dispatch finite read-only workspace tools with fixed authenticated scope and joined per-run budgets."""

import asyncio
import json
import logging
from dataclasses import dataclass
from time import monotonic
from uuid import UUID, uuid4

from pydantic import ValidationError

from apps.api.services.files import finish_task
from src.application.services.workspace_policy import WorkspaceAccessError
from src.application.services.workspace_requests import (
    parse_workspace_json,
    validate_workspace_request,
)
from src.application.services.workspace_tool_contracts import (
    TOOL_REGISTRY,
    ToolEnvelope,
)

logger = logging.getLogger(__name__)
MAX_ATTEMPTS = 8
MAX_RUN_SECONDS = 60
MAX_TOOL_SECONDS = 20
MAX_CALL_SECONDS = 5
MAX_CALL_BYTES = 64 * 1024
MAX_RUN_BYTES = 256 * 1024


@dataclass(frozen=True, slots=True)
class ToolScope:
    """Bind trusted application identities and a server-generated run identity immutably."""

    owner_id: UUID
    workspace_id: UUID
    run_id: UUID


class WorkspaceToolRun:
    """Own one ephemeral application-scoped tool run without a public API or persisted session store."""

    def __init__(self, workspace, owner_id, workspace_id):
        """Bind typed trusted identities and fixed server budgets without opening a workspace root."""
        if type(owner_id) is not UUID or type(workspace_id) is not UUID:
            raise WorkspaceAccessError("tool_scope_invalid", 422)
        self.scope = ToolScope(owner_id, workspace_id, uuid4())
        self.workspace = workspace
        self.deadline = monotonic() + MAX_RUN_SECONDS
        self.attempts = 0
        self.output_bytes = 0
        self.tool_seconds = 0.0
        self.admission = asyncio.Lock()
        self.active = None
        self.closed = False
        logger.info("workspace_tool_run_created run_id=%s", self.scope.run_id)

    def remaining(self, started):
        """Reject exhausted fixed deadlines and return the smallest remaining cooperative call budget."""
        now = monotonic()
        remaining = min(
            self.deadline - now,
            MAX_TOOL_SECONDS - self.tool_seconds - (now - started),
            MAX_CALL_SECONDS - (now - started),
        )
        if remaining <= 0:
            raise WorkspaceAccessError("tool_time_limit", 504)
        return remaining

    async def execute(self, raw):
        """Count every attempt and expose immutable result bytes only after source validation and joined cleanup."""
        started = monotonic()
        self.attempts += 1
        call_id = uuid4()
        name = None
        outcome = "rejected"
        owned = False
        work = None
        try:
            if self.closed:
                raise WorkspaceAccessError("tool_run_closed", 503)
            if self.attempts > MAX_ATTEMPTS:
                raise WorkspaceAccessError("tool_attempt_limit", 429)
            if self.admission.locked():
                raise WorkspaceAccessError("tool_run_busy", 429)
            await self.admission.acquire()
            owned = True
            self.active = asyncio.current_task()
            self.remaining(started)
            if self.output_bytes >= MAX_RUN_BYTES:
                raise WorkspaceAccessError("tool_output_limit", 413)
            try:
                envelope = ToolEnvelope.model_validate(parse_workspace_json(raw))
                contract = TOOL_REGISTRY.get(envelope.name)
                if contract is None:
                    raise WorkspaceAccessError("tool_unknown", 422)
                name = envelope.name
                operation, model = contract
                parameters = validate_workspace_request(
                    operation, model.model_validate(envelope.arguments).model_dump()
                )
            except ValidationError:
                raise WorkspaceAccessError("tool_arguments_invalid", 422) from None

            async def invoke():
                """Keep the native snapshot through serialization and final validation before releasing its resources."""
                async with self.workspace.operation(
                    self.scope.owner_id,
                    self.scope.workspace_id,
                    operation,
                    parameters,
                ) as snapshot:
                    body = json.dumps(
                        dict(
                            run_id=str(self.scope.run_id),
                            call_id=str(call_id),
                            name=name,
                            data=snapshot.payload,
                        ),
                        ensure_ascii=False,
                        allow_nan=False,
                        separators=(",", ":"),
                    ).encode("utf-8")
                    self.output_bytes += len(body)
                    if len(body) > MAX_CALL_BYTES or self.output_bytes > MAX_RUN_BYTES:
                        raise WorkspaceAccessError("tool_output_limit", 413)
                    await self.workspace.validate(snapshot)
                    self.remaining(started)
                    return body

            work = asyncio.create_task(invoke())
            try:
                body = await asyncio.wait_for(
                    asyncio.shield(work), self.remaining(started)
                )
            except TimeoutError:
                raise WorkspaceAccessError("tool_time_limit", 504) from None
            finally:
                if not work.done():
                    work.cancel()
                try:
                    await finish_task(work)
                except BaseException:
                    logger.info("workspace_tool_work_joined call_id=%s", call_id)
            self.remaining(started)
            if self.closed:
                raise WorkspaceAccessError("tool_run_closed", 503)
            outcome = "completed"
            return body
        except asyncio.CancelledError:
            outcome = "cancelled"
            raise
        except WorkspaceAccessError:
            raise
        except (OSError, ValueError, TypeError, KeyError, RuntimeError):
            raise WorkspaceAccessError("tool_unavailable", 503) from None
        finally:
            elapsed = max(0.0, monotonic() - started)
            self.tool_seconds += elapsed
            if owned:
                self.active = None
                self.admission.release()
            logger.info(
                "workspace_tool_call_finished run_id=%s call_id=%s name=%s outcome=%s attempts=%d bytes=%d elapsed_ms=%.3f",
                self.scope.run_id,
                call_id,
                name or "unregistered",
                outcome,
                self.attempts,
                self.output_bytes,
                elapsed * 1000,
            )

    async def close(self):
        """Reject subsequent calls and cancel/join any active call before the trusted request releases its run."""
        self.closed = True
        task = self.active
        if task is not None and task is not asyncio.current_task():
            task.cancel()
            try:
                await finish_task(task)
            except BaseException:
                logger.info("workspace_tool_run_joined run_id=%s", self.scope.run_id)
        logger.info("workspace_tool_run_closed run_id=%s", self.scope.run_id)
