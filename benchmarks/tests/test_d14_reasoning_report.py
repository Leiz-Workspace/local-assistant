"""Verify declared-budget raw-wire replay preserves first validator failures and cannot repair incorrect facts or altered requests."""

import hashlib
import json

import pytest

from benchmarks.scripts import d14_reasoning_report as report


@pytest.mark.parametrize(
    "fault", [None, "wrong_fact", "prompt", "budget", "first_score"]
)
def test_first_512_validator_failure_is_separate_from_declared_1024_wire_replay(
    tmp_path, fault
):
    """Reproduce a complete 540-token thinking answer rejected by the first validator, while preventing a changed prompt or wrong fact from becoming PASS."""
    case = report.trial.make_cases()[0]
    adapter = report.trial.TrialAdapter(
        profile="core",
        schema=case["schema"],
        thinking=True,
        endpoint="http://127.0.0.1:18080",
    )
    request = adapter.payload(case["prompt"], (), False)
    value = dict(case["expected"])
    if fault == "wrong_fact":
        value["answer"] = -999
    if fault == "prompt":
        request["messages"][1]["content"] = (
            "Return the supplied reference: " + json.dumps(case["expected"])
        )
    if fault == "budget":
        request["max_tokens"] = 2048
    native = dict(
        model=adapter.model,
        choices=[
            dict(
                message=dict(
                    role="assistant",
                    content=json.dumps(value),
                    reasoning_content="Authored fixture reasoning.",
                ),
                finish_reason="stop",
            )
        ],
        usage=dict(prompt_tokens=100, completion_tokens=540),
    )
    row = dict(
        id=case["id"],
        category=case["category"],
        thinking=True,
        model_requests=1,
        format_passed=False,
        functional_passed=False,
        reasoning_condition_observed=False,
    )
    if fault == "first_score":
        row["functional_passed"] = True
    for name, payload in [
        ("native-request.json", request),
        ("native-response.bin", native),
        ("measurement.json", row),
    ]:
        (tmp_path / name).write_text(json.dumps(payload))
    if fault in {"prompt", "budget", "first_score"}:
        with pytest.raises(ValueError):
            report.verify_observation("core", case, row, tmp_path)
    else:
        result = report.verify_observation("core", case, row, tmp_path)
        assert result["functional_passed"] is False
        assert result["declared_request_budget_wire_replay"]["format_passed"] is True
        assert result["declared_request_budget_wire_replay"]["functional_passed"] is (
            fault is None
        )
        assert (
            result["declared_request_budget_wire_replay"][
                "reasoning_condition_observed"
            ]
            is True
        )
        assert (
            result["wire_sha256"]
            == hashlib.sha256(
                (tmp_path / "native-response.bin").read_bytes()
            ).hexdigest()
        )
