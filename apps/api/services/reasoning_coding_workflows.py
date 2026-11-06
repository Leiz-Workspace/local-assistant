"""Compose an explicit bounded reasoning coding workflow while leaving existing fast/feedback services and API defaults unchanged."""

import logging

from apps.api.services.controlled_coding_workflows import (
    ControlledCodingWorkflowService,
)
from src.infrastructure.inference.coding_reasoning import (
    MODE,
    V2_MODE,
    CodingReasoningAdapter,
    CodingReasoningV2Adapter,
)

logger = logging.getLogger(__name__)


class ReasoningCodingWorkflowService(ControlledCodingWorkflowService):
    """Select the named host-only reasoning mode with unchanged source capture, native approvals and cancellation guards."""

    _proposal_preset = MODE

    def __init__(self, workspace, approvals, patches, checks, *, inference=None):
        """Bind the explicit new adapter only for this opt-in service without registering routes or granting actions."""
        super().__init__(
            workspace,
            approvals,
            patches,
            checks,
            inference=inference if inference is not None else CodingReasoningAdapter(),
        )
        logger.info(
            "reasoning_coding_workflow_initialized mode=%s", self._proposal_preset
        )


class ReasoningCodingV2WorkflowService(ReasoningCodingWorkflowService):
    """Select only the distinct second coding mode while preserving all existing source, approval and cancellation guards."""

    _proposal_preset = V2_MODE

    def __init__(self, workspace, approvals, patches, checks, *, inference=None):
        """Bind the separately assessed adapter without replacing the first mode or registering an endpoint/default."""
        super().__init__(
            workspace,
            approvals,
            patches,
            checks,
            inference=inference
            if inference is not None
            else CodingReasoningV2Adapter(),
        )
