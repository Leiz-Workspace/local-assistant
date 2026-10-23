"""Own finite immutable pre/post/error/stop metadata around trusted tool handlers without granting action approvals or retry authority."""

import asyncio
import logging
import math
import re
from dataclasses import dataclass
from types import MappingProxyType
from uuid import UUID, uuid4

from src.application.services.web_fetch_tasks import finish_owned, spawn_owned

logger = logging.getLogger(__name__)


class HookError(Exception):
    """Expose finite tool-control outcomes without prompt, output, source or approval material."""

    def __init__(self, code):
        """Record only the closed lifecycle/error vocabulary visible to higher-level orchestration."""
        self.code = (
            code
            if code
            in {
                "invalid_scope",
                "invalid_configuration",
                "denied",
                "closed",
                "stopped",
                "busy",
                "limit",
                "timeout",
                "failed",
                "uncertain",
                "invalid_result",
            }
            else "failed"
        )
        super().__init__(self.code)
        logger.warning("tool_hook_rejected code=%s", self.code)


@dataclass(frozen=True, slots=True, repr=False)
class HookCall:
    """Bind a trusted immutable invocation to its exact host actor and argument digest without containing action grants."""

    owner_id: UUID
    workspace_id: UUID
    run_id: UUID
    call_id: UUID
    profile: str
    tool: str
    arguments_sha256: str


@dataclass(frozen=True, slots=True)
class HookEvent:
    """Retain finite ordered lifecycle metadata without raw arguments, outputs, prompts or approval tokens."""

    sequence: int
    run_id: UUID
    call_id: UUID
    tool: str
    arguments_sha256: str
    phase: str
    outcome: str


class GuardedToolRun:
    """Own bounded trusted tool execution, two authorization barriers and joined owner-specific stop/cancel handling."""

    def __init__(self, owner, workspace, *, profile, effects, authorize, timeout=20):
        """Bind fixed host scope/effects/policy before any model-selected argument or handler is processed."""
        if (
            type(owner) is not UUID
            or type(workspace) is not UUID
            or type(profile) is not str
            or profile != "core"
            or type(effects) is not dict
            or not 1 <= len(effects) <= 32
            or any(
                type(name) is not str
                or re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", name) is None
                or type(effect) is not str
                or effect not in {"read", "write"}
                for name, effect in effects.items()
            )
            or not callable(authorize)
            or type(timeout) not in (float, int)
            or not math.isfinite(timeout)
            or not 0 < timeout <= 300
        ):
            raise HookError("invalid_configuration")
        self.owner, self.workspace, self.profile = owner, workspace, profile
        self.identifier = uuid4()
        self.effects, self.authorize = MappingProxyType(dict(effects)), authorize
        self.timeout, self.attempts = timeout, 0
        self.events = ()
        self.active = None
        self.invoked = False
        self.stopping = self.closed = False
        logger.info("guarded_tool_run_initialized run_id=%s", self.identifier)

    def checked(self, call):
        """Reject forged actor metadata, undeclared tools or malformed hashes before recording or authorizing an invocation."""
        if (
            type(call) is not HookCall
            or any(
                type(value) is not UUID
                for value in (
                    call.owner_id,
                    call.workspace_id,
                    call.run_id,
                    call.call_id,
                )
            )
            or (call.owner_id, call.workspace_id, call.run_id, call.profile)
            != (self.owner, self.workspace, self.identifier, self.profile)
            or type(call.profile) is not str
            or type(call.tool) is not str
            or call.tool not in self.effects
            or type(call.arguments_sha256) is not str
            or re.fullmatch(r"[0-9a-f]{64}", call.arguments_sha256) is None
        ):
            raise HookError("invalid_scope")
        if any(event.call_id == call.call_id for event in self.events):
            raise HookError("invalid_scope")

    def record(self, call, phase, outcome):
        """Append a reserved finite event pair without exposing any policy-control return value."""
        if (
            phase not in {"before", "after"}
            or outcome
            not in {
                "pending",
                "completed",
                "denied",
                "stopped",
                "cancelled",
                "failed",
                "timeout",
                "uncertain",
                "invalid_result",
                "closed",
            }
            or len(self.events) >= 16
        ):
            raise HookError("limit")
        event = HookEvent(
            len(self.events) + 1,
            self.identifier,
            call.call_id,
            call.tool,
            call.arguments_sha256,
            phase,
            outcome,
        )
        self.events += (event,)
        logger.info(
            "tool_hook_event run_id=%s call_id=%s phase=%s outcome=%s",
            self.identifier,
            call.call_id,
            phase,
            outcome,
        )

    def live(self, deadline):
        """Refuse closed/stopped/deadline/cancelled work even when a dependency suppresses cancellation."""
        if self.closed:
            raise HookError("closed")
        if self.stopping:
            raise HookError("stopped")
        if deadline.expired():
            raise HookError("timeout")
        if asyncio.current_task().cancelling():
            raise asyncio.CancelledError()

    async def invoke(self, call, operation):
        """Run fixed authorization, handler and publication checks without interpreting any hook as authority."""
        try:
            async with asyncio.timeout(self.timeout) as deadline:
                self.live(deadline)
                if await self.authorize(call) is not None:
                    raise HookError("denied")
                self.live(deadline)
                self.invoked = True
                result = await operation(call)
                self.live(deadline)
                if await self.authorize(call) is not None:
                    raise HookError("denied")
                self.live(deadline)
                if type(result) is not bytes or not 1 <= len(result) <= 65536:
                    raise HookError("invalid_result")
                return result
        except TimeoutError:
            raise HookError("timeout") from None
        except (HookError, asyncio.CancelledError):
            raise
        except Exception:
            raise HookError("failed" if self.invoked else "denied") from None

    async def execute(self, call, operation):
        """Admit one exact call and publish a complete reply only after its owned policy/handler work retires."""
        self.attempts += 1
        if self.attempts > 8:
            raise HookError("limit")
        self.checked(call)
        if self.closed:
            raise HookError("closed")
        if self.stopping:
            raise HookError("stopped")
        if self.active is not None:
            raise HookError("busy")
        if not callable(operation):
            raise HookError("invalid_configuration")
        if len(self.events) + 2 > 16:
            raise HookError("limit")
        self.invoked = False
        self.record(call, "before", "pending")
        outcome = "failed"
        task = None
        try:
            task = spawn_owned(self.invoke(call, operation))
            self.active = task
            try:
                result = await asyncio.shield(task)
            except asyncio.CancelledError:
                if not task.done() and not task.cancelling():
                    task.cancel()
                try:
                    await finish_owned(task)
                except BaseException:
                    logger.info(
                        "tool_hook_cancelled_work_joined run_id=%s", self.identifier
                    )
                outcome = (
                    "uncertain"
                    if self.invoked and self.effects[call.tool] == "write"
                    else ("stopped" if self.stopping else "cancelled")
                )
                if asyncio.current_task().cancelling():
                    raise
                raise HookError("stopped") from None
            if self.closed:
                raise HookError("closed")
            if self.stopping:
                raise HookError("stopped")
            if asyncio.current_task().cancelling():
                raise asyncio.CancelledError()
            outcome = "completed"
            return result
        except HookError as exc:
            if self.invoked and self.effects[call.tool] == "write":
                outcome = "uncertain"
                raise HookError("uncertain") from None
            outcome = exc.code
            raise
        finally:
            if outcome == "uncertain":
                self.stopping = True
            self.record(call, "after", outcome)
            self.active = None
            logger.info("guarded_tool_operation_retired run_id=%s", self.identifier)

    def request_stop(self, owner, run_id):
        """Signal only the exact owner's run and prevent automatic reuse without accepting a model callback."""
        if (
            type(owner) is not UUID
            or type(run_id) is not UUID
            or owner != self.owner
            or run_id != self.identifier
        ):
            raise HookError("invalid_scope")
        self.stopping = True
        if (
            self.active is not None
            and not self.active.done()
            and not self.active.cancelling()
        ):
            self.active.cancel()
        logger.info("guarded_tool_stop_requested run_id=%s", self.identifier)

    async def close(self):
        """Close admission and join the actual owned policy/handler task before the host releases dependencies."""
        self.closed = self.stopping = True
        task = self.active
        if task is not None and task is not asyncio.current_task():
            if not task.done() and not task.cancelling():
                task.cancel()
            try:
                await finish_owned(task)
            except BaseException:
                logger.info("guarded_tool_shutdown_joined run_id=%s", self.identifier)
        logger.info("guarded_tool_run_closed run_id=%s", self.identifier)
        if asyncio.current_task().cancelling():
            raise asyncio.CancelledError()
