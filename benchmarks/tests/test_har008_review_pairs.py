"""Verify fresh L1 review cases, line-pair scoring and immutable first-outcome lifecycle without native model calls."""

import json
import logging
from uuid import uuid4

import pytest

from benchmarks import har008_review_pairs as panel
from benchmarks.tests.test_har008_maintenance import MultiSourceAPI, FixtureSampler

LOGGER = logging.getLogger(__name__)


class PairAPI(MultiSourceAPI):
    """Model only the new request-bound metadata while reusing tested finite API lifecycle behavior."""

    def request(self, method, path, payload=None):
        """Bind each successful fake receipt to the requested generic or review mode and target."""
        row = super().request(method, path, payload)
        if method == "POST" and path.endswith("/runs") and row["state"] == "succeeded":
            row["context"]["output_contract"] = dict(
                name=payload["output_contract"], status="VALID"
            )
            if payload["review_target"]:
                row["context"]["output_contract"]["review_target"] = payload[
                    "review_target"
                ]
        return row


def setup_panel(tmp_path, **options):
    """Create one explicit source root and private receipt directory with synthetic telemetry."""
    root = tmp_path / "workspace"
    root.mkdir()
    output, workspace = tmp_path / "out", uuid4()
    api = PairAPI(
        panel.load_panel(panel.CORPUS.read_bytes()), workspace, output, **options
    )
    return api, workspace, root, output


def evaluate(api, workspace, root, output):
    """Run deterministic software fixtures without reading /proc, GPU state or actual model outputs."""
    return panel.evaluate(
        api,
        workspace,
        root,
        output,
        pid=42,
        sampler_factory=FixtureSampler,
        preflight=lambda pid: dict(pid=pid, start_ticks=7),
    )


def test_new_panel_keeps_absolute_ranges_and_duplicate_quotes():
    """Validate all predeclared unique case identities and original line positions without executing source."""
    cases = panel.load_panel(panel.CORPUS.read_bytes())
    assert len(cases) == 12 and sum(case["read_start"] > 1 for case in cases) == 3
    assert sum(case["value"] is None for case in cases) == 2
    old = json.loads(
        (panel.ROOT / "benchmarks/fixtures/har008-q2-maintenance-v1.json").read_text()
    )["cases"]
    assert not {case["id"] for case in cases} & {case["id"] for case in old}
    duplicate = next(case for case in cases if case["id"] == "review-duplicate-false")
    assert (
        duplicate["sources"][0]["text"].count("return False") == 3
        and duplicate["value"] == 7
    )
    LOGGER.info("test_l1_original_ranges_and_duplicates_verified")


def test_mechanical_pair_validity_is_not_gold_correctness():
    """Accept an actual but nondefective source pair as mechanically valid while keeping its gold score failed."""
    case = panel.load_panel(panel.CORPUS.read_bytes())[0]
    content = json.dumps(
        dict(value=1, quote=case["sources"][0]["text"].splitlines()[0])
    )
    assert (
        panel.pair_valid(case, content)
        and not panel.score_answer(content, case)["passed"]
    )
    assert panel.pair_valid(case, '{"value":null,"quote":null}')
    wrong = json.dumps(dict(value=case["value"] + 1, quote=case["quote"]))
    assert not panel.pair_valid(case, wrong)


@pytest.mark.parametrize("change", ["hidden_gold", "range_type", "quote", "duplicate"])
def test_invalid_gold_or_partial_range_fails_before_inference(change):
    """Reject a hidden target finding, wrong scalar range, invented quote or duplicated ID before transport."""
    data = json.loads(panel.CORPUS.read_bytes())
    if change == "hidden_gold":
        data["cases"][0]["read_start"] = data["cases"][0]["value"] + 1
    elif change == "range_type":
        data["cases"][0]["read_start"] = True
    elif change == "quote":
        data["cases"][0]["quote"] = "not present"
    else:
        data["cases"][1]["id"] = data["cases"][0]["id"]
    with pytest.raises(ValueError):
        panel.load_panel(json.dumps(data))


def test_all_48_first_outcomes_bind_target_ranges_and_keep_existing_grants(tmp_path):
    """Counterbalance four constrained arms and retain exactly one score per source/skill mode."""
    api, workspace, root, output = setup_panel(tmp_path)
    result = evaluate(api, workspace, root, output)
    assert (
        result["status"] == "MEASUREMENT_COMPLETE"
        and result["completed_attempts"] == 48
    )
    assert all(row["passed"] == 12 for row in result["arms"].values())
    assert all(value == 0 for value in result["line_pair_invalid"].values())
    assert (
        result["promotion"] == "NOT_QUALIFIED"
        and result["resources"]["status"] == "COMPLETE"
    )
    assert any(
        request["tools"][0]["arguments"]["start_line"] > 1 for request in api.requests
    )
    assert all(
        (request["output_contract"] == panel.REVIEW_NAME)
        == bool(request["review_target"])
        for request in api.requests
    )
    assert not api.rows and list(api.installs) == ["existing-source-reader"]
    assert len(list(output.glob("*-response.json"))) == 48


def test_invalid_first_completion_remains_failed_without_a_retry(tmp_path):
    """Preserve rejected raw output/resources and finish the remaining finite campaign exactly once."""
    api, workspace, root, output = setup_panel(tmp_path, invalid_at=3)
    result = evaluate(api, workspace, root, output)
    assert len(api.requests) == 48
    assert result["arms"]["bound_baseline"]["passed"] == 11
    assert result["line_pair_invalid"]["bound_baseline"] == 1
    assert json.loads((output / "03-response.json").read_text())["state"] == "failed"


def test_transport_failure_preserves_partial_state_and_does_not_replay(tmp_path):
    """Stop uncertain submissions, keep frozen receipts and clean only campaign-created grants."""
    api, workspace, root, output = setup_panel(tmp_path, fail_at=3)
    with pytest.raises(RuntimeError):
        evaluate(api, workspace, root, output)
    summary = json.loads((output / "summary.json").read_text())
    assert summary["status"] == "INCOMPLETE" and summary["completed_attempts"] == 2
    assert summary["unidentified_submission"] and len(api.requests) == 3
