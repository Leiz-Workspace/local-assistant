"""Execute actual three-round owner-delegated AI diagnostic on owned source/HTTP/model resources."""

import json
from pathlib import Path

from test_reranker_http_trial import actual_trial_flag as actual_trial_flag
from test_reranker_http_trial import trial_client as trial_client
from test_retrieval_http import retrieval_client as retrieval_client

from scripts.agent_reviewed_retrieval_trial import run


def test_actual_owner_delegated_ai_reviewed_paired_trial(trial_client):
    """Retain every actual round and failing diagnostic gate without asserting adoption or human quality."""
    client, auth, _, _ = trial_client
    report = run(client, auth["headers"][0])
    path = Path("data/backups/d27-t03-latest-agent-paired-trial.json")
    path.touch(mode=0o600, exist_ok=True)
    path.chmod(0o600)
    path.write_text(json.dumps(report, indent=2) + "\n")
    assert report["status"] == "PAIRED_EXECUTION_COMPLETE" and len(report["runs"]) == 3
    assert all(
        len(row["observations"]["baseline"]) == 8
        and len(row["observations"]["candidate"]) == 8
        for row in report["raw_runs"]
    )
    assert report["reviewer_type"] == "assistant" and report["human_reviewed"] is False
    assert not report["adoption_approved"] and not report["production_routing_changed"]
