"""Verify fresh multi-source maintenance oracles, native telemetry accounting and first-outcome failure retention."""

import json
import logging
from uuid import uuid4

import pytest

from benchmarks import har008_maintenance as panel
from benchmarks.tests.test_har008_contract import ContractAPI

LOGGER = logging.getLogger(__name__)


class FixtureSampler:
    """Return explicitly synthetic resource counters without touching a native process or GPU."""

    def __init__(self, pid, *, expected_start):
        """Verify the globally pinned native identity is passed to every request measurement."""
        assert pid == 42 and expected_start == 7
        self.thread = object()

    def __enter__(self):
        """Begin a synthetic request measurement with no thread or process side effects."""
        return self

    def __exit__(self, *errors):
        """Finish the synthetic measurement while preserving any operation exception."""

    def report(self):
        """Keep separate sampled RSS and process GPU allocation units for aggregation."""
        return dict(
            status="COMPLETE",
            baseline=dict(rss_kib=100, gpu_process_mib=200),
            sampled_peak_rss_kib=120,
            sampled_peak_gpu_process_mib=210,
            samples=[],
        )


class MultiSourceAPI(ContractAPI):
    """Use the authenticated lifecycle fixture while modelling the requested count of retained snapshots."""

    def request(self, method, path, payload=None):
        """Account for both explicit source files without silently dropping caller/policy evidence."""
        row = super().request(method, path, payload)
        if method == "POST" and path.endswith("/runs") and row["state"] == "succeeded":
            row["context"]["included_evidence"] = [
                {"index": index} for index in range(len(payload["tools"]))
            ]
        return row


def fixture_panel(tmp_path, **options):
    """Build one explicit private fixture workspace and pure software telemetry dependency set."""
    root = tmp_path / "workspace"
    root.mkdir()
    output, workspace = tmp_path / "out", uuid4()
    cases = panel.load_panel(panel.CORPUS.read_bytes())
    api = MultiSourceAPI(cases, workspace, output, **options)
    return api, workspace, root, output


def run_panel(api, workspace, root, output):
    """Invoke the finite panel with deterministic telemetry and no native inference or GPU queries."""
    return panel.evaluate(
        api,
        workspace,
        root,
        output,
        pid=42,
        sampler_factory=FixtureSampler,
        preflight=lambda pid: dict(pid=pid, start_ticks=7),
    )


def test_panel_balances_categories_and_keeps_both_long_source_positions():
    """Check unique fresh cases, complete line oracles and long early/late target coverage before inference."""
    cases = panel.load_panel(panel.CORPUS.read_bytes())
    assert len(cases) == 24
    assert sum(case["value"] is None for case in cases) == 10
    assert sum(len(case["sources"]) == 2 for case in cases) == 10
    long = [case for case in cases if case["category"] == "source-long"]
    positions = [
        case["sources"][0]["text"].splitlines().index(case["quote"]) for case in long
    ]
    assert positions == [4, 70, 4, 70]
    LOGGER.info("test_q2_fresh_maintenance_balance_verified")


@pytest.mark.parametrize(
    "damage",
    ["duplicate", "unsafe_path", "quote", "line", "category", "unbounded", "null"],
)
def test_invalid_panel_is_rejected_before_network(damage):
    """Reject path traversal, category/oracle drift and contract-domain overflow without model calls."""
    raw = json.loads(panel.CORPUS.read_bytes())
    case = raw["cases"][0]
    if damage == "duplicate":
        raw["cases"][1]["id"] = case["id"]
    elif damage == "unsafe_path":
        case["sources"][0]["path"] = "../../secret.md"
    elif damage == "quote":
        case["quote"] = "not present"
    elif damage == "line":
        raw["cases"][12]["value"] = 1
    elif damage == "category":
        case["category"] = "review-safe"
    elif damage == "unbounded":
        case["sources"][0]["text"] = "x" * 20000
    else:
        case["value"] = None
    with pytest.raises(ValueError):
        panel.load_panel(json.dumps(raw))


def test_full_panel_freezes_96_unique_first_outcomes_and_resources(tmp_path):
    """Keep all source snapshots, category totals and telemetry while never promoting a saturated panel."""
    api, workspace, root, output = fixture_panel(tmp_path)
    result = run_panel(api, workspace, root, output)
    assert (
        result["status"] == "MEASUREMENT_COMPLETE"
        and result["completed_attempts"] == 96
    )
    assert (
        result["promotion"] == "NOT_QUALIFIED"
        and result["resources"]["status"] == "COMPLETE"
    )
    assert result["resources"]["sampled_peak_rss_kib"] == 120
    assert all(row["passed"] == 24 for row in result["arms"].values())
    assert len(list(output.glob("*-resources.json"))) == 96
    assert all(
        all(row["passed"] == 4 for row in arms.values())
        for arms in result["categories"].values()
    )
    assert not api.rows and list(api.installs) == ["existing-source-reader"]
    frozen = json.loads((output / "frozen-inputs.json").read_text())
    assert len(frozen["source_sha256"]) == 34


def test_contract_failure_is_scored_without_losing_raw_or_telemetry(tmp_path):
    """Count one malformed first reply as failure instead of replaying it or discarding its measurements."""
    api, workspace, root, output = fixture_panel(tmp_path, invalid_at=3)
    result = run_panel(api, workspace, root, output)
    assert (
        len(api.requests) == 96
        and result["arms"]["constrained_baseline"]["contract_failures"] == 1
    )
    assert (output / "03-response.json").exists() and (
        output / "03-resources.json"
    ).exists()


def test_uncertain_submission_stops_without_retries_and_preserves_first_receipts(
    tmp_path,
):
    """Retain partial scores/resources and remove only owned grants on a transport error."""
    api, workspace, root, output = fixture_panel(tmp_path, fail_at=3)
    with pytest.raises(RuntimeError):
        run_panel(api, workspace, root, output)
    result = json.loads((output / "summary.json").read_text())
    assert result["status"] == "INCOMPLETE" and result["completed_attempts"] == 2
    assert result["unidentified_submission"] and len(api.requests) == 3
    assert list(api.installs) == ["existing-source-reader"]
