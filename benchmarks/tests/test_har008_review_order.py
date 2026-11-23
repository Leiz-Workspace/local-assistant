"""Verify the separate six-arm ordering experiment preserves every first result and never inflates qualification."""

import json
from uuid import uuid4

import pytest

from benchmarks import har008_review_order as panel
from benchmarks.tests.test_har008_review_pairs import PairAPI
from benchmarks.tests.test_har008_maintenance import FixtureSampler


def fixture(tmp_path, **options):
    """Create an isolated panel with fake native/resource dependencies and no model calls."""
    root = tmp_path / "workspace"
    root.mkdir()
    output, workspace = tmp_path / "out", uuid4()
    api = PairAPI(
        panel.load_panel(panel.CORPUS.read_bytes()), workspace, output, **options
    )
    return api, workspace, root, output


def run(api, workspace, root, output):
    """Evaluate six explicit modes with deterministic telemetry instead of hardware readings."""
    return panel.evaluate(
        api,
        workspace,
        root,
        output,
        pid=42,
        sampler_factory=FixtureSampler,
        preflight=lambda pid: dict(pid=pid, start_ticks=7),
    )


def test_second_cohort_has_opaque_ids_and_no_source_reuse():
    """Keep new labels and source text distinct before the ordering variant sees answers."""
    cases = panel.load_panel(panel.CORPUS.read_bytes())
    previous = json.loads(
        (panel.ROOT / "benchmarks/fixtures/har008-l1-review-v1.json").read_text()
    )["cases"]
    assert len(cases) == 12 and all(
        case["id"] == f"review-order-{index:02d}" for index, case in enumerate(cases, 1)
    )
    assert not {source["text"] for case in cases for source in case["sources"]} & {
        source["text"] for case in previous for source in case["sources"]
    }


def test_72_outcomes_cover_all_orders_and_paired_comparisons(tmp_path):
    """Counterbalance each six-arm position twice and keep saturation separate from qualification."""
    api, workspace, root, output = fixture(tmp_path)
    summary = run(api, workspace, root, output)
    assert (
        summary["status"] == "MEASUREMENT_COMPLETE"
        and summary["completed_attempts"] == 72
    )
    assert all(row["passed"] == 12 for row in summary["arms"].values())
    assert len(summary["comparisons"]) == 9 and all(
        row["pairs"] == 12 for row in summary["comparisons"].values()
    )
    assert summary["promotion"] == "NOT_QUALIFIED" and all(
        count == 0 for count in summary["line_pair_invalid"].values()
    )
    for index in range(12):
        expected = panel.ARMS[index % 6 :] + panel.ARMS[: index % 6]
        modes = [
            request["output_contract"]
            for request in api.requests[index * 6 : index * 6 + 6]
        ]
        assert modes == [
            panel.NAME
            if arm.startswith("generic_")
            else panel.REVIEW_NAME
            if arm.startswith("value_")
            else panel.QUOTE_FIRST_NAME
            for arm in expected
        ]
    assert not api.rows and list(api.installs) == ["existing-source-reader"]


def test_first_native_failure_is_preserved_without_replacement(tmp_path):
    """Count a rejected first candidate in its actual arm and finish without a retry."""
    api, workspace, root, output = fixture(tmp_path, invalid_at=3)
    result = run(api, workspace, root, output)
    assert (
        len(api.requests) == 72
        and result["arms"]["value_baseline"]["contract_failures"] == 1
    )
    assert json.loads((output / "03-response.json").read_text())["state"] == "failed"


def test_uncertain_submission_stops_and_keeps_partial_receipts(tmp_path):
    """Retain partial evidence and owned-grant cleanup instead of replaying a failed call."""
    api, workspace, root, output = fixture(tmp_path, fail_at=3)
    with pytest.raises(RuntimeError):
        run(api, workspace, root, output)
    result = json.loads((output / "summary.json").read_text())
    assert result["status"] == "INCOMPLETE" and result["completed_attempts"] == 2
    assert len(api.requests) == 3 and result["unidentified_submission"]
