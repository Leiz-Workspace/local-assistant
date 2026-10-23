"""Validate finite typed plans and run explicit owner-bound steps through durable budgets/checkpoints without automatic action retries."""

import asyncio
import hashlib
import logging
import math
import re
import time
from dataclasses import dataclass
from uuid import UUID, uuid4

from src.application.ports.plan_checkpoint import (
    CheckpointError,
    PlanCheckpoint,
    validate_state,
)
from src.application.services.mcp_adapter import canonical, schema_digest
from src.application.services.tool_hooks import GuardedToolRun, HookCall
from src.application.services.web_fetch_tasks import finish_owned, spawn_owned
from src.application.services.workspace_requests import parse_workspace_json

logger = logging.getLogger(__name__)


class PlanError(Exception):
    """Expose finite plan/recovery failures without argument, result, credential or state contents."""

    def __init__(self, code):
        """Keep scheduler audit outcomes inside the closed recovery/budget vocabulary."""
        self.code = (
            code
            if code
            in {
                "invalid_plan",
                "invalid_scope",
                "explicit_action_required",
                "stale",
                "expired",
                "budget",
                "uncertain_write",
                "not_resumable",
                "busy",
                "failed",
                "storage_failed",
                "closed",
            }
            else "failed"
        )
        super().__init__(self.code)
        logger.warning("plan_run_rejected code=%s", self.code)


@dataclass(frozen=True, slots=True, repr=False)
class PlanTool:
    """Bind a host-reviewed tool name, strict model and immutable effect independently of plan text."""

    name: str
    input_model: type
    effect: str
    revision: str


@dataclass(frozen=True, slots=True, repr=False)
class PlanStep:
    """Freeze one validated step's exact typed argument bytes without executable callbacks or scope fields."""

    identifier: str
    tool: str
    arguments: bytes


@dataclass(frozen=True, slots=True, repr=False)
class BoundedPlan:
    """Bind exact raw plan and catalog digests to a finite immutable list of typed host-allowlisted steps."""

    sha256: str
    catalog_sha256: str
    steps: tuple[PlanStep, ...]


def catalog_digest(tools):
    """Bind trusted names, effects and exact argument schemas so recovery cannot silently change an operation contract."""
    if (
        type(tools) is not tuple
        or not 1 <= len(tools) <= 32
        or any(
            type(tool) is not PlanTool
            or type(tool.name) is not str
            or not tool.name
            or len(tool.name) > 128
            or re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", tool.name) is None
            or type(tool.effect) is not str
            or tool.effect not in {"read", "write"}
            or type(tool.revision) is not str
            or len(tool.revision) != 64
            or any(c not in "0123456789abcdef" for c in tool.revision)
            for tool in tools
        )
        or len({tool.name for tool in tools}) != len(tools)
    ):
        raise PlanError("invalid_plan")
    value = {
        tool.name: dict(
            effect=tool.effect,
            revision=tool.revision,
            schema=schema_digest(tool.input_model),
        )
        for tool in tools
    }
    return hashlib.sha256(canonical(value)).hexdigest()


def parse_plan(raw, tools):
    """Reject owner/profile/budget/callback/command fields and validate every complete argument object before execution."""
    try:
        catalog = catalog_digest(tools)
        known = {tool.name: tool for tool in tools}
        value = parse_workspace_json(raw)
        if (
            set(value) != {"version", "steps"}
            or type(value["version"]) is not int
            or value["version"] != 1
            or type(value["steps"]) is not list
            or not 1 <= len(value["steps"]) <= 8
        ):
            raise ValueError()
        steps = []
        seen = set()
        for step in value["steps"]:
            if (
                type(step) is not dict
                or set(step) != {"id", "tool", "arguments"}
                or type(step["id"]) is not str
                or not 1 <= len(step["id"]) <= 64
                or not all(
                    c.isascii() and (c.isalnum() or c in "_-") for c in step["id"]
                )
                or step["id"] in seen
                or type(step["tool"]) is not str
                or step["tool"] not in known
                or type(step["arguments"]) is not dict
            ):
                raise ValueError()
            args = (
                known[step["tool"]]
                .input_model.model_validate(step["arguments"])
                .model_dump(mode="json")
            )
            steps.append(PlanStep(step["id"], step["tool"], canonical(args)))
            seen.add(step["id"])
    except Exception:
        raise PlanError("invalid_plan") from None
    logger.info("bounded_plan_validated steps=%d", len(steps))
    return BoundedPlan(hashlib.sha256(raw).hexdigest(), catalog, tuple(steps))


class BoundedPlanRunner:
    """Own one explicit fixed plan with durable attempts/output/time budgets and safe read-only recovery."""

    def __init__(
        self,
        owner,
        workspace,
        *,
        profile,
        store,
        tools,
        authorize,
        invoke,
        clock=time.time,
    ):
        """Bind trusted host scope/contracts/state and cancellation-aware handlers without executing a plan or recovering approvals."""
        if (
            type(owner) is not UUID
            or type(workspace) is not UUID
            or type(profile) is not str
            or profile != "core"
            or not callable(authorize)
            or not callable(invoke)
        ):
            raise PlanError("invalid_scope")
        self.catalog = catalog_digest(tools)
        self.tools = {tool.name: tool for tool in tools}
        self.owner, self.workspace, self.store = owner, workspace, store
        self.profile = profile
        self.authorize, self.invoke, self.clock = authorize, invoke, clock
        self.guard = None
        self.active = False
        self.closed = False
        self.pending = None
        self.pausing = False
        self.run_id = None
        self.last_time = None

    async def admit(self, operation):
        """Own the entire lock/checkpoint/guard operation so cancellation and close join durable terminal publication too."""
        if self.closed or self.pending is not None:
            operation.close()
            raise PlanError("closed" if self.closed else "busy")
        task = spawn_owned(operation)
        self.pending = task
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            if not task.done() and not task.cancelling():
                task.cancel()
            try:
                await finish_owned(task)
            except BaseException:
                logger.info("plan_cancelled_checkpoint_work_joined")
            raise
        except CheckpointError as exc:
            raise PlanError(
                "busy" if exc.code == "busy" else "storage_failed"
            ) from None
        finally:
            self.pending = None

    def now(self):
        """Refuse invalid or rolled-back wall clocks instead of extending a durable run lifetime."""
        value = self.clock()
        if type(value) not in (float, int) or not math.isfinite(value) or value < 0:
            raise PlanError("expired")
        if self.last_time is not None and value < self.last_time:
            raise PlanError("expired")
        self.last_time = value
        return value

    def scope(self, plan, state=None):
        """Check exact trusted plan/catalog/owner scope and fixed durable budgets before any action or resume."""
        if self.closed:
            raise PlanError("closed")
        if type(plan) is not BoundedPlan or plan.catalog_sha256 != self.catalog:
            raise PlanError("invalid_plan")
        if state is not None:
            validate_state(state)
            if (
                state["owner_id"] != str(self.owner)
                or state["workspace_id"] != str(self.workspace)
                or state["profile"] != "core"
                or state["plan_sha256"] != plan.sha256
                or state["catalog_sha256"] != self.catalog
            ):
                raise PlanError("invalid_scope")
            now = self.now()
            if (
                now < state["observed_at"]
                or now >= state["expires_at"]
                or state["expires_at"] != state["created_at"] + 120
            ):
                raise PlanError("expired")
            if not 0 <= state["attempts"] < 12 or state["output_bytes"] >= 262144:
                raise PlanError("budget")

    async def start(self, raw, *, explicit_start):
        """Create one signed ready state only for an explicit owner start, without accepting model-selected limits or grants."""
        if explicit_start is not True:
            raise PlanError("explicit_action_required")
        if self.active:
            raise PlanError("busy")
        plan = parse_plan(raw, tuple(self.tools.values()))
        self.scope(plan)
        return await self.admit(self.start_locked(plan))

    async def start_locked(self, plan):
        """Create the first durable record under the run lock before executing any admitted step."""
        run_id = uuid4()
        self.run_id = run_id
        self.pausing = False
        now = self.now()
        state = dict(
            owner_id=str(self.owner),
            workspace_id=str(self.workspace),
            profile="core",
            plan_sha256=plan.sha256,
            catalog_sha256=self.catalog,
            created_at=now,
            observed_at=now,
            expires_at=now + 120,
            next_step=0,
            attempts=0,
            step_attempts=[0] * len(plan.steps),
            output_bytes=0,
            outputs=[],
            status="ready",
        )
        with self.store.lock(run_id):
            ref = self.store.append(run_id, state, None)
            return await self.execute(plan, state, ref)

    async def resume(self, raw, reference, *, explicit_resume):
        """Require the latest exact signed checkpoint and fresh authorization; never replay an uncertain/in-flight write."""
        if explicit_resume is not True:
            raise PlanError("explicit_action_required")
        if self.active:
            raise PlanError("busy")
        if type(reference) is not PlanCheckpoint:
            raise PlanError("stale")
        plan = parse_plan(raw, tuple(self.tools.values()))
        return await self.admit(self.resume_locked(plan, reference))

    async def resume_locked(self, plan, reference):
        """Verify the latest chain and read-only retry policy while holding the recovery lock through completion."""
        with self.store.lock(reference.run_id):
            state, latest = self.store.latest(reference.run_id)
            if latest != reference:
                raise PlanError("stale")
            self.scope(plan, state)
            if state["status"] == "uncertain_write":
                raise PlanError("uncertain_write")
            if state["status"] not in {
                "ready",
                "failed",
                "inflight",
                "cancelled",
            } or not 0 <= state["next_step"] < len(plan.steps):
                raise PlanError("not_resumable")
            step = plan.steps[state["next_step"]]
            if self.tools[step.tool].effect == "write" and state["status"] != "ready":
                raise PlanError("uncertain_write")
            if state["step_attempts"][state["next_step"]] >= 2:
                raise PlanError("budget")
            self.run_id = reference.run_id
            self.pausing = False
            return await self.execute(plan, state, latest)

    async def execute(self, plan, state, reference):
        """Charge/fsync every attempt before invocation and retain only complete output hashes or explicit terminal ambiguity."""
        if self.active:
            raise PlanError("busy")
        self.active = True
        emitted = []
        self.guard = GuardedToolRun(
            self.owner,
            self.workspace,
            profile="core",
            effects={name: tool.effect for name, tool in self.tools.items()},
            authorize=self.authorize,
        )
        try:
            while state["next_step"] < len(plan.steps):
                self.scope(plan, state)
                if self.pausing:
                    return dict(
                        status="paused",
                        checkpoint=reference,
                        completed_steps=state["next_step"],
                        attempts=state["attempts"],
                        outputs=tuple(emitted),
                    )
                index = state["next_step"]
                step = plan.steps[index]
                self.guard.timeout = min(20, state["expires_at"] - self.now())
                if state["step_attempts"][index] >= 2:
                    raise PlanError("budget")
                state.update(
                    status="inflight",
                    attempts=state["attempts"] + 1,
                    observed_at=self.now(),
                )
                state["step_attempts"][index] += 1
                reference = self.store.append(reference.run_id, state, reference)
                call = HookCall(
                    self.owner,
                    self.workspace,
                    self.guard.identifier,
                    uuid4(),
                    "core",
                    step.tool,
                    hashlib.sha256(step.arguments).hexdigest(),
                )

                async def operation(scope):
                    """Delegate only the already frozen step to the host's trusted cancellation-aware dispatcher."""
                    return await self.invoke(step, scope)

                try:
                    result = await self.guard.execute(call, operation)
                    if self.now() >= state["expires_at"]:
                        raise PlanError("expired")
                    state["output_bytes"] += len(result)
                    if state["output_bytes"] > 262144:
                        raise PlanError("budget")
                except BaseException as exc:
                    uncertain = self.tools[step.tool].effect == "write"
                    state.update(
                        status="uncertain_write"
                        if uncertain
                        else (
                            "cancelled"
                            if isinstance(exc, asyncio.CancelledError)
                            else "failed"
                        ),
                        observed_at=self.now(),
                    )
                    reference = self.store.append(reference.run_id, state, reference)
                    if isinstance(exc, asyncio.CancelledError):
                        raise
                    return dict(
                        status=state["status"],
                        checkpoint=reference,
                        completed_steps=index,
                        attempts=state["attempts"],
                        outputs=tuple(emitted),
                    )
                emitted.append((step.identifier, result))
                state["outputs"].append(
                    dict(
                        step_id=step.identifier,
                        sha256=hashlib.sha256(result).hexdigest(),
                    )
                )
                state.update(
                    next_step=index + 1,
                    status="complete" if index + 1 == len(plan.steps) else "ready",
                    observed_at=self.now(),
                )
                reference = self.store.append(reference.run_id, state, reference)
            logger.info(
                "bounded_plan_complete run_id=%s steps=%d attempts=%d",
                reference.run_id,
                len(plan.steps),
                state["attempts"],
            )
            return dict(
                status="complete",
                checkpoint=reference,
                completed_steps=state["next_step"],
                attempts=state["attempts"],
                output_sha256=tuple(row["sha256"] for row in state["outputs"]),
                outputs=tuple(emitted),
            )
        except CheckpointError:
            raise PlanError("storage_failed") from None
        finally:
            try:
                await self.guard.close()
            finally:
                self.active = False

    async def close(self):
        """Close admission and join the current guard without deleting signed state or recovering action grants."""
        self.closed = True
        if self.guard is not None and self.guard.active is asyncio.current_task():
            await self.guard.close()
            logger.info("plan_close_from_handler_publication_blocked")
            return
        task = self.pending
        if task is not None and task is not asyncio.current_task():
            if not task.done() and not task.cancelling():
                task.cancel()
            try:
                await finish_owned(task)
            except BaseException:
                logger.info("plan_close_checkpoint_work_joined")
        logger.info("bounded_plan_runner_closed")

    def request_pause(self, owner, run_id):
        """Pause the exact owner's active run between fully checkpointed steps without cancelling an admitted action."""
        if self.closed:
            raise PlanError("closed")
        if (
            type(owner) is not UUID
            or type(run_id) is not UUID
            or owner != self.owner
            or run_id != self.run_id
        ):
            raise PlanError("invalid_scope")
        if self.pending is None:
            raise PlanError("not_resumable")
        self.pausing = True
        logger.info("bounded_plan_pause_requested run_id=%s", run_id)
