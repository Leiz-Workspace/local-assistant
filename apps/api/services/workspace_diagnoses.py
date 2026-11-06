"""Specialize accepted source/model ownership for diagnostics without execution or source modification."""

import logging

from apps.api.services.workspace_explanations import WorkspaceExplanationService
from src.application.services.workspace_diagnosis import (
    diagnosis_messages,
    resolve_diagnosis,
)

logger = logging.getLogger(__name__)


class WorkspaceDiagnosisService(WorkspaceExplanationService):
    """Inherit exact source pins, model profile, final fences and lifecycle while specializing only result contracts."""

    def build_messages(self, question, lines):
        """Build a bounded diagnostic prompt from only the explicitly selected original lines."""
        return diagnosis_messages(question, lines)

    def resolve(self, raw, units):
        """Resolve a finite source-backed plan with an explicit server-owned not-executed status."""
        return resolve_diagnosis(raw, units)

    def empty_result(self):
        """Return a schema-consistent blank-source diagnostic without model generation or fabricated steps."""
        logger.info("workspace_diagnosis_no_sources")
        return dict(
            status="no_sources",
            diagnosis=None,
            citations=[],
            plan=[],
            reproduction=None,
            execution_status="not_executed",
            content_trust="untrusted",
            diagnosis_trust="not_generated",
        )
