"""Verify frozen four-arm ordering, immutable first scores and failure-safe cleanup without model calls."""

import json
import logging
from uuid import uuid4

import pytest

from benchmarks import har008_contract as runner
from benchmarks.tests.test_har008 import FixtureAPI

LOGGER = logging.getLogger(__name__)


class ContractAPI(FixtureAPI):
    """Extend the legacy lifecycle fixture with explicit native contract outcomes."""

    def __init__(self, *args, invalid_at=None, software_failure=False, **kwargs):
        """Choose one first-attempt contract or software failure without introducing retries."""
        super().__init__(*args, **kwargs)
        self.invalid_at, self.software_failure = invalid_at, software_failure

    def request(self, method, path, payload=None):
        """Add contract receipts or a retained malformed native response to the controlled lifecycle."""
        row = super().request(method, path, payload)
        if method == "POST" and path.endswith("/runs"):
            if payload["output_contract"] == runner.NAME:
                row["context"]["output_contract"] = {"status": "VALID"}
            if len(self.requests) == self.invalid_at:
                raw = row.pop("result")
                raw["choices"][0]["message"]["content"] = "```json\n{}\n```"
                row.update(
                    state="failed",
                    diagnostic={
                        "code": "source_contract_unavailable"
                        if self.software_failure
                        else "source_contract_invalid",
                        "raw_result": raw,
                    },
                )
                row.pop("context")
        return row


def setup_panel(tmp_path, **options):
    """Create isolated explicit source and receipt locations for the controlled four-arm runner."""
    output, workspace = tmp_path / "out", uuid4()
    source = tmp_path / "workspace"
    source.mkdir()
    cases = runner.load_cases(runner.CORPUS.read_bytes())
    return ContractAPI(cases, workspace, output, **options), workspace, source, output


def test_new_corpus_is_distinct_and_scored_without_output_repair():
    """Verify new source cases and null controls without invoking any synthetic Python source."""
    from benchmarks.har008 import CORPUS

    old = runner.load_cases(CORPUS.read_bytes())
    new = runner.load_cases(runner.CORPUS.read_bytes())
    assert not {case["id"] for case in old} & {case["id"] for case in new}
    assert len(new) == 12 and sum(case["value"] is None for case in new) == 4
    assert sum(case["skill"] == "repo-review" for case in new) == 6
    replacement = runner.load_cases(
        (runner.ROOT / "benchmarks/fixtures/har008-source-review-r2.json").read_bytes()
    )
    assert not {case["source"] for case in replacement} & {
        case["source"] for case in new + old
    }
    assert sum(case["value"] is None for case in replacement) == 4
    final = runner.load_cases(
        (runner.ROOT / "benchmarks/fixtures/har008-source-review-r3.json").read_bytes()
    )
    for key in ("id", "source", "question"):
        assert not {case[key] for case in final} & {
            case[key] for case in old + new + replacement
        }
    assert sum(case["value"] is None for case in final) == 4
    LOGGER.info("test_har008_r1_distinct_cohort_verified")


def test_four_arm_freeze_order_and_grants(tmp_path):
    """Run 48 unique first outcomes, rotate all four positions and retain existing grants."""
    api, workspace, source, output = setup_panel(tmp_path)
    result = runner.evaluate(api, workspace, source, output)
    assert (
        result["status"] == "MEASUREMENT_COMPLETE" and result["complete_blocks"] == 12
    )
    assert result["completed_attempts"] == 48
    assert all(row["passed"] == 12 for row in result["arms"].values())
    assert result["promotion"] == "NOT_QUALIFIED"
    assert [row["output_contract"] for row in api.requests[:8]] == [
        "text",
        "text",
        runner.NAME,
        runner.NAME,
        "text",
        runner.NAME,
        runner.NAME,
        "text",
    ]
    assert len(list(output.glob("*-response.json"))) == 48 and not api.rows
    assert list(api.installs) == ["existing-source-reader"]
    with pytest.raises(FileExistsError):
        runner.evaluate(api, workspace, source, output)


def test_contract_failure_is_retained_as_first_quality_outcome(tmp_path):
    """Keep a rejected native JSON response, count its failure and continue without resubmission."""
    api, workspace, source, output = setup_panel(tmp_path, invalid_at=3)
    result = runner.evaluate(api, workspace, source, output)
    arm = result["arms"]["constrained_baseline"]
    assert result["completed_attempts"] == 48 and len(api.requests) == 48
    assert arm["contract_failures"] == 1 and arm["passed"] == arm["format"] == 11
    assert json.loads((output / "03-response.json").read_text())["state"] == "failed"


@pytest.mark.parametrize("failure", ["transport", "software"])
def test_campaign_stops_without_retries_on_nonquality_failure(tmp_path, failure):
    """Preserve partial evidence and clean only owned grants on uncertain transport or software errors."""
    options = (
        {"fail_at": 3}
        if failure == "transport"
        else {"invalid_at": 3, "software_failure": True}
    )
    api, workspace, source, output = setup_panel(tmp_path, **options)
    with pytest.raises((RuntimeError, ValueError)):
        runner.evaluate(api, workspace, source, output)
    result = json.loads((output / "summary.json").read_text())
    assert result["status"] == "INCOMPLETE" and result["completed_attempts"] == 2
    assert len(api.requests) == 3 and list(api.installs) == ["existing-source-reader"]
    assert result["unidentified_submission"] == (failure == "transport")


def test_duplicate_outcomes_cannot_inflate_four_arm_totals():
    """Reject duplicate or unknown arms before a complete evaluation can be claimed."""
    cases = [{"id": "one"}]
    row = dict(
        case_id="one",
        arm=runner.ARMS[0],
        score=dict.fromkeys(("format", "value", "quote", "passed"), True),
        contract_failed=False,
    )
    with pytest.raises(ValueError):
        runner.aggregate([row, row], cases)
