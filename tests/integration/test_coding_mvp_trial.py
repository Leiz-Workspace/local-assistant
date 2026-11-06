"""Validate D46 evaluator protocol success/failure categories using disclosed controlled inference and actual native/TCP/typed-review operations before real model cases."""

import json
from pathlib import Path
from uuid import uuid4

import pytest
from coding_mvp_cases import corpus
from coding_mvp_trial import run_case
from test_check_http import check_client as check_client
from test_checkpoint_http import checkpoint_client as checkpoint_client
from test_coding_workflow_http import workflow_client as workflow_client
from test_patch_http import patch_client as patch_client
from test_workflow_controls_http import controls_client as controls_client
from test_workspace_http import workspace_client as workspace_client


@pytest.mark.parametrize(
    "outcome", ["reference", "wrong_fix", "invalid_response", "review_rejected"]
)
def test_evaluator_distinguishes_model_repair_score_from_completed_measurement(
    controls_client, outcome
):
    """Exercise real two-suite evaluation while retaining wrong/rejected completions without another model attempt, fixture write or granted native action."""
    case = corpus()["cases"][0]
    core = controls_client[-1]
    source = case["reference_source"]
    if outcome == "wrong_fix":
        source = case["buggy_source"] + "\n"
    elif outcome == "review_rejected":
        source = source.replace("import logging", "import logging\nimport os")
    core.raw = (
        "invalid controlled completion"
        if outcome == "invalid_response"
        else json.dumps(
            dict(
                plan=[
                    "Correct only the frozen utility behavior while retaining the API and audit."
                ],
                replacement=source,
            )
        )
    )
    run_id = str(uuid4()) if outcome == "reference" else None
    result, summary = run_case(
        controls_client, case, core, inference_type="controlled", run_id=run_id
    )
    if run_id is not None:
        parent = Path("data/backups") / ("d46-evaluation-" + run_id)
        assert parent.stat().st_mode & 0o777 == 0o700
        assert (
            json.loads((parent / "case-index" / (case["id"] + ".json")).read_text())
            == summary
        )
    assert result["status"] == "COMPLETE_MEASUREMENT" and result["model_attempts"] == 1
    expected = {
        "reference": "FUNCTIONAL_PASS",
        "wrong_fix": "FUNCTIONAL_FAIL",
        "invalid_response": "PROPOSAL_FAILED",
        "review_rejected": "REVIEW_REJECTED",
    }[outcome]
    assert result["repair_outcome"] == expected and result["functional_pass"] is (
        outcome == "reference"
    )
    assert result["fixture_approvals"] == (
        3 if outcome in {"reference", "wrong_fix"} else 0
    )
    assert result["native_runs"] == (2 if outcome in {"reference", "wrong_fix"} else 0)
    assert (
        not result["heldout_source_supplied_to_model"]
        and result["host_canary_unchanged"]
    )


def test_invalid_evaluation_run_id_cannot_write_fixture_files_or_start_a_model(
    controls_client,
):
    """Reject an unsafe run-index scope before any fixture mutation, approval, protocol record or model request."""
    client, _, _, roots, _, _, core = controls_client
    before = (
        (roots[0] / "sample.py").read_bytes()
        if (roots[0] / "sample.py").exists()
        else None
    )
    with pytest.raises(ValueError, match="evaluation_run_id"):
        run_case(
            controls_client,
            corpus()["cases"][0],
            core,
            inference_type="controlled",
            run_id="../outside",
        )
    assert not core.calls and not client.app.state.coding_workflow_service.records
    after = (
        (roots[0] / "sample.py").read_bytes()
        if (roots[0] / "sample.py").exists()
        else None
    )
    assert after == before
