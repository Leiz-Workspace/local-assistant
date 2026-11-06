"""Check fresh coding corpus provenance, paired isolation and unchanged strict plan/source review without invoking CORE."""

import json

import pytest
from coding_mvp_cases import FixtureReviewError, candidate_review
from coding_quality_cases import corpus, variant

from src.application.services.coding_workflow import resolve_candidate
from src.application.services.workspace_policy import WorkspaceAccessError

CASES = corpus()["cases"]


@pytest.mark.parametrize("case", CASES, ids=[row["id"] for row in CASES])
def test_paired_issues_preserve_sources_oracles_and_original_case(case):
    """Change only explicit issue wording and never expose hidden examples or mutate the frozen caller object."""
    original = json.dumps(case, ensure_ascii=False, sort_keys=True)
    baseline, concise = variant(case, "baseline"), variant(case, "concise")
    assert baseline == case and baseline is not case
    assert {key for key in case if baseline[key] != concise[key]} == {"issue"}
    assert all(concise[key] == case[key] for key in case if key != "issue")
    assert json.dumps(case, ensure_ascii=False, sort_keys=True) == original
    concise["sha256"]["buggy_source"] = "changed copy"
    assert case["sha256"]["buggy_source"] != "changed copy"


@pytest.mark.parametrize("arm", ["", "retry", None, "schema"])
def test_unknown_arm_cannot_select_a_feedback_or_grammar_protocol(arm):
    """Reject undeclared comparison factors before any proposal, fixture mutation or model request."""
    with pytest.raises(ValueError, match="ce002_arm_invalid"):
        variant(CASES[0], arm)


def test_six_plan_steps_still_rejected_without_trimming():
    """Preserve the original one-to-five response contract even when a candidate source is otherwise correct."""
    with pytest.raises(WorkspaceAccessError):
        resolve_candidate(
            json.dumps(
                dict(plan=["manual step"] * 6, replacement=CASES[0]["reference_source"])
            )
        )


@pytest.mark.parametrize("case", CASES, ids=[row["id"] for row in CASES])
def test_fresh_reference_cannot_expand_imports_or_native_authority(case):
    """Keep the established pure fixture review mandatory for all new utilities and both paired conditions."""
    with pytest.raises(FixtureReviewError):
        candidate_review(
            case,
            case["reference_source"].replace(
                "import logging", "import logging\nimport os"
            ),
        )
