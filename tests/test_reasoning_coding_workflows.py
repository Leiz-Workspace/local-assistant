"""Exercise the explicit named coding mode through disposable native workflow approvals while keeping defaultfast and response identity fences intact."""

from dataclasses import replace
from uuid import UUID

import pytest
from test_check_jobs import job_store as job_store
from test_coding_workflow_service import propose
from test_coding_workflow_service import workflow_service as workflow_service

from apps.api.services.reasoning_coding_workflows import ReasoningCodingWorkflowService
from src.application.services.workspace_policy import WorkspaceAccessError
from src.infrastructure.inference.coding_reasoning import MODE


@pytest.mark.asyncio
@pytest.mark.parametrize("wrong_mode", [False, True])
async def test_opt_in_mode_keeps_explicit_review_and_rejects_fast_reply(
    workflow_service, wrong_mode
):
    """Capture real selected source and require a matching named result without applying a generated edit or accepting an old preset label."""
    original, source, root, core = workflow_service

    class ExplicitCore:
        """Disclose controlled source while recording the actual named workflow contract."""

        async def complete(self, **options):
            """Return an authored candidate with an intentionally matching or mismatching preset."""
            result = await core.complete(**options)
            return replace(result, preset_selected="fast" if wrong_mode else MODE)

    service = ReasoningCodingWorkflowService(
        original.workspace,
        original.approvals,
        original.patches,
        original.checks,
        inference=ExplicitCore(),
    )
    before = (root / "sample.py").read_bytes()
    try:
        result = await propose((service, source, root, core))
        assert core.calls[0]["preset"] == MODE
        if wrong_mode:
            assert result["state"] == "proposal_failed" and result["patch"] is None
        else:
            assert result["state"] == "awaiting_patch_review"
            with pytest.raises(WorkspaceAccessError):
                await service.apply(
                    source.owner,
                    source.workspace,
                    UUID(result["workflow_id"]),
                    UUID(result["patch"]["approval_id"]),
                )
        assert (root / "sample.py").read_bytes() == before
    finally:
        await service.shutdown()
