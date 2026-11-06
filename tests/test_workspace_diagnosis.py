"""Verify strict bounded diagnosis/manual-plan contracts and source citations without executing proposed reproduction steps."""

import copy
import json

import pytest

from src.application.services.workspace_diagnosis import (
    diagnosis_messages,
    resolve_diagnosis,
)
from src.application.services.workspace_policy import WorkspaceAccessError


def proposed_diagnosis(identifier="L1"):
    """Provide an independently authored synthetic bug plan with a concrete manual input and expected result."""
    return dict(
        status="diagnosed",
        diagnosis="The function increments instead of doubling.",
        citations=[dict(source_id=identifier, quote="return value + 1")],
        plan=[
            dict(
                kind="inspect_source",
                details="Inspect the arithmetic return expression.",
                expected_observation="The operator is addition.",
            )
        ],
        reproduction=dict(
            input="value=3",
            steps=["Manually compare double(3) with the expected doubled value."],
            expected_result="The expected doubled value is 6.",
        ),
    )


@pytest.fixture
def diagnostic_units():
    """Define exact original source provenance independently of the generated plan."""
    return {
        "L1": dict(
            path="calc.py",
            line_number=3,
            source_sha256="a" * 64,
            line_text="    return value + 1",
        )
    }


def test_resolved_plan_has_server_order_and_never_claims_execution(diagnostic_units):
    """Resolve the original arithmetic line and preserve a concrete manual reproducer with no execution authority."""
    result = resolve_diagnosis(json.dumps(proposed_diagnosis()), diagnostic_units)
    assert result["execution_status"] == "not_executed"
    assert result["plan"][0]["step"] == 1
    assert result["citations"][0]["path"] == "calc.py"
    assert result["citations"][0]["line_number"] == 3
    assert result["reproduction"]["input"] == "value=3"
    assert result["diagnosis_trust"] == "generated_untrusted"


@pytest.mark.parametrize(
    "fault",
    [
        "executed",
        "patch",
        "actual_result",
        "shell",
        "unknown_kind",
        "step_id",
        "missing_details",
        "empty_plan",
        "many_steps",
        "long_details",
        "long_expected",
        "bad_reproduction",
        "execution_claim",
        "empty_checks",
        "many_checks",
        "long_check",
        "long_input",
        "long_result",
        "bad_quote",
        "unknown_source",
        "wrong_status",
        "empty_diagnosis",
        "long_diagnosis",
    ],
)
def test_malformed_or_authority_claiming_plans_fail_closed(diagnostic_units, fault):
    """Reject authority overrides, fabricated execution and incomplete/oversized proposed checks."""
    payload = copy.deepcopy(proposed_diagnosis())
    if fault in {"executed", "patch", "actual_result", "shell"}:
        payload[fault] = "untrusted"
    elif fault == "unknown_kind":
        payload["plan"][0]["kind"] = "run_shell"
    elif fault == "step_id":
        payload["plan"][0]["step"] = 999
    elif fault == "missing_details":
        del payload["plan"][0]["details"]
    elif fault in {"empty_plan", "many_steps"}:
        payload["plan"] = [] if fault == "empty_plan" else payload["plan"] * 6
    elif fault in {"long_details", "long_expected"}:
        payload["plan"][0][
            "details" if fault == "long_details" else "expected_observation"
        ] = "á" * 257
    elif fault == "bad_reproduction":
        payload["reproduction"] = None
    elif fault == "execution_claim":
        payload["reproduction"]["executed"] = True
    elif fault in {"empty_checks", "many_checks", "long_check"}:
        payload["reproduction"]["steps"] = {
            "empty_checks": [],
            "many_checks": ["check"] * 6,
            "long_check": ["á" * 257],
        }[fault]
    elif fault in {"long_input", "long_result"}:
        payload["reproduction"][
            "input" if fault == "long_input" else "expected_result"
        ] = "á" * 513
    elif fault == "bad_quote":
        payload["citations"][0]["quote"] = "return value * 2"
    elif fault == "unknown_source":
        payload["citations"][0]["source_id"] = "L99"
    elif fault == "wrong_status":
        payload["status"] = "executed"
    else:
        payload["diagnosis"] = "" if fault == "empty_diagnosis" else "á" * 2049
    with pytest.raises(WorkspaceAccessError, match="diagnosis_answer_invalid"):
        resolve_diagnosis(json.dumps(payload), diagnostic_units)


@pytest.mark.parametrize(
    "raw",
    [
        None,
        "invalid",
        "[]",
        '{"status":NaN}',
        '{"status":"a","status":"b"}',
        "x" * 16385,
    ],
)
def test_malformed_diagnostic_json_is_sanitized(diagnostic_units, raw):
    """Reuse strict bounded Unicode/object parsing and return only a stable diagnostic failure."""
    with pytest.raises(WorkspaceAccessError, match="diagnosis_answer_invalid"):
        resolve_diagnosis(raw, diagnostic_units)


def test_abstention_and_prompt_retain_exact_untrusted_lines(diagnostic_units):
    """Allow explicit missing evidence without fake steps and keep diagnosis prompts source bounded."""
    result = resolve_diagnosis(
        '{"status":"insufficient_evidence","diagnosis":null,"citations":[],"plan":[],"reproduction":null}',
        diagnostic_units,
    )
    assert (
        not result["plan"]
        and result["diagnosis"] is None
        and result["execution_status"] == "not_executed"
    )
    messages, units = diagnosis_messages(
        "double(3) expected6", list(diagnostic_units.values())
    )
    assert units["L1"] == diagnostic_units["L1"]
    assert "NOT executed" in messages[0]["content"]
    assert (
        json.loads(messages[1]["content"])["sources"][0]["text"]
        == diagnostic_units["L1"]["line_text"]
    )
