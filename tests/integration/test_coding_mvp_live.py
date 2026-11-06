"""Execute one frozen actual existing CORE attempt for each of ten authored D46 utility repairs while retaining functional failures separately from protocol acceptance."""

import os

import pytest
from coding_mvp_cases import corpus
from coding_mvp_trial import TimedOriginalCore, frozen_oracle, run_case
from test_check_http import check_client as check_client
from test_checkpoint_http import checkpoint_client as checkpoint_client
from test_coding_workflow_http import workflow_client as workflow_client
from test_patch_http import patch_client as patch_client
from test_workflow_controls_http import controls_client as controls_client
from test_workspace_http import workspace_client as workspace_client

CASES = corpus()["cases"]


@pytest.mark.parametrize("case", CASES, ids=[row["id"] for row in CASES])
def test_actual_core_frozen_utility_case_is_measured_once_with_visible_and_heldout_oracles(
    controls_client, case
):
    """Record exactly one original CORE repair attempt, distinct actual reviews/checks and a truthful per-case functional score without automatic retry."""
    assert os.environ.get("LOCAL_ASSISTANT_LIVE_E2E") == "1", (
        "Existing CORE live evaluation must be explicitly enabled"
    )
    oracle = frozen_oracle(case)
    core = TimedOriginalCore()
    result, _ = run_case(
        controls_client,
        case,
        core,
        inference_type="actual_existing_CORE",
        oracle=oracle,
        run_id=os.environ.get("D46_EVALUATION_RUN_ID"),
    )
    assert result["status"] == "COMPLETE_MEASUREMENT" and result["model_attempts"] == 1
    assert result["repair_outcome"] in {
        "FUNCTIONAL_PASS",
        "FUNCTIONAL_FAIL",
        "PROPOSAL_FAILED",
        "REVIEW_REJECTED",
    }
    assert (
        result["selected_tests_unchanged"]
        and result["host_canary_unchanged"]
        and not result["heldout_source_supplied_to_model"]
    )
    assert (
        result["automatic_retries"] == 0 and len(core.calls) == len(core.durations) == 1
    )
