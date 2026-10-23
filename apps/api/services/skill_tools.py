"""Narrow existing read-only workspace runs to an exact owner-reviewed skill without granting new tools or install authority."""

import logging

from pydantic import ValidationError

from apps.api.services.workspace_tools import MAX_ATTEMPTS, WorkspaceToolRun
from src.application.services.skill_contract import (
    InstalledSkill,
    SkillError,
    SkillManifest,
)
from src.application.services.workspace_policy import WorkspaceAccessError
from src.application.services.workspace_requests import parse_workspace_json
from src.application.services.workspace_tool_contracts import ToolEnvelope

logger = logging.getLogger(__name__)


class SkillToolRun:
    """Delegate only reviewed read-only capabilities to the unchanged source-scoped workspace dispatcher."""

    def __init__(self, registry, installed, workspace, owner_id, workspace_id):
        """Bind exact host-owned installation scope without opening a root, installing a package or running an instruction."""
        self.registry, self.installed = registry, installed
        self.owner, self.workspace = owner_id, workspace_id
        if (
            type(installed) is not InstalledSkill
            or type(installed.manifest) is not SkillManifest
            or not installed.manifest.permissions
        ):
            raise SkillError("invalid_scope")
        registry.authorize(
            owner_id, workspace_id, installed, installed.manifest.permissions[0]
        )
        self.run = WorkspaceToolRun(workspace, owner_id, workspace_id)
        self.attempts = 0
        logger.info("skill_tool_run_initialized install_id=%s", installed.identifier)

    async def execute(self, raw):
        """Validate the finite envelope and installation on every call before delegating the original immutable bytes."""
        self.attempts += 1
        logger.info(
            "skill_tool_attempt install_id=%s attempt=%d",
            self.installed.identifier,
            self.attempts,
        )
        if self.attempts > MAX_ATTEMPTS:
            raise SkillError("attempt_limit")
        try:
            envelope = ToolEnvelope.model_validate(parse_workspace_json(raw))
        except (ValidationError, ValueError, WorkspaceAccessError):
            raise SkillError("permission_denied") from None
        self.registry.authorize(
            self.owner, self.workspace, self.installed, envelope.name
        )
        result = await self.run.execute(raw)
        self.registry.authorize(
            self.owner, self.workspace, self.installed, envelope.name
        )
        logger.info(
            "skill_tool_call_completed install_id=%s", self.installed.identifier
        )
        return result

    async def __aenter__(self):
        """Expose the owned narrowed run to a trusted host context that guarantees joined cleanup."""
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        """Join the existing tool dispatcher on every host context exit without swallowing errors."""
        await self.close()

    async def close(self):
        """Drain only the owned existing tool run without changing the shared installation or workspace service."""
        await self.run.close()
        logger.info("skill_tool_run_closed install_id=%s", self.installed.identifier)
