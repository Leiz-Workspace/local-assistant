"""Route a fixed owner-bound CORE tool catalog through original workspace and action approval services without accepting model grants."""

import hashlib
import logging
from types import MappingProxyType
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from apps.api.services.workspace_tools import WorkspaceToolRun
from src.application.services.mcp_adapter import canonical
from src.application.services.tool_hooks import GuardedToolRun, HookCall, HookError
from src.application.services.workspace_requests import parse_workspace_json
from src.application.services.workspace_tool_contracts import (
    TOOL_REGISTRY,
    ToolEnvelope,
)

logger = logging.getLogger(__name__)


class ActionTarget(BaseModel):
    """Accept only the canonical existing proposal/job identifier, never a model approval or host scope."""

    model_config = ConfigDict(strict=True, extra="forbid")
    target_id: str = Field(
        pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
    )


CATALOG = MappingProxyType(
    {
        **{name: (model, "read") for name, (_, model) in TOOL_REGISTRY.items()},
        "patch.apply": (ActionTarget, "write"),
        "checks.run": (ActionTarget, "write"),
    }
)


class HarnessToolRun:
    """Own bounded deterministic routes and ephemeral exact action references while original services remain the sole approval authority."""

    def __init__(
        self, owner, workspace, *, profile, workspace_service, patches=None, checks=None
    ):
        """Bind authenticated host identities and already-admitted services without installing tools, approving reviews or starting actions."""
        if (
            type(owner) is not UUID
            or type(workspace) is not UUID
            or type(profile) is not str
            or profile != "core"
        ):
            raise HookError("invalid_scope")
        self.owner, self.workspace = owner, workspace
        self.workspace_service, self.patches, self.checks = (
            workspace_service,
            patches,
            checks,
        )
        self.reader = WorkspaceToolRun(workspace_service, owner, workspace)
        self.references = {}
        self.attempts = 0
        self.guard = GuardedToolRun(
            owner,
            workspace,
            profile=profile,
            effects={name: effect for name, (_, effect) in CATALOG.items()},
            authorize=self.authorize,
        )
        logger.info("harness_router_created run_id=%s", self.guard.identifier)

    async def authorize(self, call):
        """Recheck dependency lifecycle and host scope without treating local references as action approval or reusing consumed grants."""
        if (call.owner_id, call.workspace_id, call.profile) != (
            self.owner,
            self.workspace,
            "core",
        ):
            raise HookError("denied")
        if self.workspace_service.closing:
            raise HookError("denied")
        if call.tool == "patch.apply" and (
            self.patches is None or self.patches.closing
        ):
            raise HookError("denied")
        if call.tool == "checks.run" and (self.checks is None or self.checks.closing):
            raise HookError("denied")
        return None

    def attach_approval_reference(self, owner, workspace, tool, target, approval):
        """Retain an exact host-supplied reference only; the unchanged action service must still verify and consume real approval."""
        if self.guard.closed or self.guard.stopping or self.guard.active is not None:
            raise HookError("closed")
        if (
            type(owner) is not UUID
            or type(workspace) is not UUID
            or owner != self.owner
            or workspace != self.workspace
            or type(tool) is not str
            or tool not in {"patch.apply", "checks.run"}
            or type(target) is not UUID
            or type(approval) is not UUID
        ):
            raise HookError("invalid_scope")
        if len(self.references) >= 8 or (tool, target) in self.references:
            raise HookError("limit")
        self.references[tool, target] = approval
        logger.info(
            "harness_action_reference_attached run_id=%s tool=%s",
            self.guard.identifier,
            tool,
        )

    async def execute(self, raw):
        """Validate the full finite envelope before routing exact canonical arguments through bounded fixed hooks."""
        self.attempts += 1
        if self.attempts > 8:
            raise HookError("limit")
        try:
            envelope = ToolEnvelope.model_validate(parse_workspace_json(raw))
            if envelope.name not in CATALOG:
                raise ValueError()
            model, _ = CATALOG[envelope.name]
            arguments = model.model_validate(envelope.arguments).model_dump(mode="json")
            frozen = canonical(arguments)
        except Exception:
            raise HookError("invalid_scope") from None
        call = HookCall(
            self.owner,
            self.workspace,
            self.guard.identifier,
            uuid4(),
            "core",
            envelope.name,
            hashlib.sha256(frozen).hexdigest(),
        )

        async def operation(scope):
            """Delegate only fixed validated data; approval references never enter arguments, metadata events or checkpoints."""
            if scope.tool in TOOL_REGISTRY:
                return await self.reader.execute(
                    canonical(dict(name=scope.tool, arguments=arguments))
                )
            target = UUID(arguments["target_id"])
            approval = self.references.pop((scope.tool, target), None)
            if approval is None:
                raise HookError("denied")
            if scope.tool == "patch.apply":
                result = await self.patches.apply(
                    self.owner, self.workspace, target, approval
                )
            else:
                result = await self.checks.run(
                    self.owner, self.workspace, target, approval
                )
            return canonical(result)

        return await self.guard.execute(call, operation)

    def request_stop(self, owner, run_id):
        """Forward exact owner/run stop to the owning guard without exposing a model-selected cancellation target."""
        self.guard.request_stop(owner, run_id)

    async def close(self):
        """Drain the active route before retiring read capabilities and local references; service owners close action dependencies separately."""
        await self.guard.close()
        await self.reader.close()
        self.references.clear()
        logger.info("harness_router_closed run_id=%s", self.guard.identifier)
