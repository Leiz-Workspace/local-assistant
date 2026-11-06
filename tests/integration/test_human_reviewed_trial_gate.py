"""Verify the real human-review gate and execute the owned paired diagnostic only when supplied review is complete."""

import json
from pathlib import Path

from test_reranker_http_trial import actual_trial_flag as actual_trial_flag
from test_reranker_http_trial import trial_client as trial_client
from test_retrieval_http import retrieval_client as retrieval_client

from scripts.human_reviewed_retrieval_trial import run


def test_supplied_human_review_gate_and_available_trial(trial_client):
    """Retain pending status honestly or run actual three-round evaluation on the supplied completed review."""
    client, auth, _, _ = trial_client
    result = run(client, auth["headers"][0])
    assert result["status"] in {"PENDING_HUMAN_REVIEW", "PAIRED_EXECUTION_COMPLETE"}
    if result["status"] == "PENDING_HUMAN_REVIEW":
        assert result["inference_executed"] is False
    else:
        assert result["inference_executed"] is True and len(result["runs"]) == 3
        assert result["adoption_approved"] is False
    output = Path("data/backups/d27-t03-reviewed-trial-status.json")
    output.touch(mode=0o600, exist_ok=True)
    output.chmod(0o600)
    output.write_text(json.dumps(result, indent=2) + "\n")
