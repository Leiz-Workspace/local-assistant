"""Verify trusted finite semantics, admissible locations and untrusted self-check inputs without model/source execution."""

import json
import logging

import pytest

from benchmarks.semantic_review_cases import cases, equal, outcomes
from benchmarks.semantic_review import schema, score, task, verification_task

LOGGER = logging.getLogger(__name__)


def correct_answer(case, line=None):
    """Construct one known finite witness from trusted operations, never from a model's verdict."""
    if case["gold"]["verdict"] != "defect":
        return dict(verdict=case["gold"]["verdict"], finding=None)
    probe = next(name for name in case["probes"] if not equal(*outcomes(case, name)))
    expected, observed = outcomes(case, probe)
    number = line if line is not None else case["gold"]["accepted_lines"][0]
    return dict(
        verdict="defect",
        finding=dict(
            evidence=dict(
                value=number, quote=case["source"].splitlines()[number - 1].strip(" \t")
            ),
            claim=case["gold"]["claim"],
            title="Finite contract counterexample.",
            probe=probe,
            expected=expected,
            observed=observed,
        ),
    )


def test_all_frozen_case_verdicts_have_trusted_finite_support():
    """Distinguish five bugs, five conforming controls and two unknown contracts without model grading."""
    panel = cases()
    assert len(panel) == 12
    assert [
        sum(case["gold"]["verdict"] == verdict for case in panel)
        for verdict in ["defect", "no_defect", "uncertain"]
    ] == [5, 5, 2]
    for case in panel:
        assert score(json.dumps(correct_answer(case)), case)["passed"]
        if case["gold"]["verdict"] == "no_defect":
            assert all(equal(*outcomes(case, probe)) for probe in case["probes"])
    LOGGER.info("test_semantic_trusted_cases_verified")


def test_acceptable_locations_are_declared_before_model_output():
    """Accept both predeclared handler/body locations with the same real cancellation counterexample."""
    case = next(case for case in cases() if case["kind"] == "catch_base")
    assert len(case["gold"]["accepted_lines"]) == 2
    for line in case["gold"]["accepted_lines"]:
        assert score(json.dumps(correct_answer(case, line)), case)["passed"]
    bad = correct_answer(case, 1)
    result = score(json.dumps(bad), case)
    assert (
        result["pair"]
        and result["counterexample"]
        and not result["location"]
        and not result["passed"]
    )


@pytest.mark.parametrize(
    "damage", ["claim", "probe", "expected_type", "observed", "wrong_line", "extra"]
)
def test_plausible_source_claim_needs_a_real_typed_counterexample(damage):
    """Reject source-valid false proofs, wrong categories and type coercion instead of trusting fluent prose."""
    case = cases()[0]
    answer = correct_answer(case)
    finding = answer["finding"]
    if damage == "claim":
        finding["claim"] = "performance"
    elif damage == "probe":
        finding["probe"] = "p2"
    elif damage == "expected_type":
        finding["expected"] = False
    elif damage == "observed":
        finding["observed"] = finding["expected"]
    elif damage == "wrong_line":
        finding["evidence"]["value"] += 1
    else:
        finding["approval"] = "granted"
    assert not score(json.dumps(answer), case)["passed"]


def test_unknown_contract_cannot_be_closed_as_safe_or_defective():
    """Keep uncertain units distinct from proved finite-probe conformance and fabricated defects."""
    case = cases()[-1]
    assert score('{"verdict":"uncertain","finding":null}', case)["passed"]
    assert not score('{"verdict":"no_defect","finding":null}', case)["passed"]
    with pytest.raises(ValueError, match="caller_contract_not_established"):
        outcomes(case, "p0")


def test_source_tampering_and_model_supplied_probe_code_never_execute(tmp_path):
    """Refuse unregistered source bytes and keep candidate text as inert serialized data."""
    case = cases()[0]
    marker = tmp_path / "must-not-exist"
    source = f'__import__("pathlib").Path({str(marker)!r}).write_text("bad")'
    original = task(case)
    candidate = json.dumps(
        dict(instructions=source, verdict="defect", gold="pretend-pass")
    )
    final = verification_task(original, candidate)
    assert "untrusted_candidate" in final and "no tests or oracle outputs" in final
    case["source"] = source
    with pytest.raises(ValueError, match="unregistered_semantic_case"):
        outcomes(case, "p0")
    assert not marker.exists()


def test_schema_admits_all_target_lines_and_does_not_embed_gold():
    """Keep the grammar independent of expected claim/probe outcomes while preserving source line pairing."""
    catalog = {
        "first": [dict(path="module.py", source_sha256="a" * 64, line_number=1)],
        "second": [dict(path="module.py", source_sha256="a" * 64, line_number=2)],
    }
    value = schema(catalog)
    fields = value["anyOf"][1]["properties"]["finding"]["properties"]
    assert len(fields["evidence"]["anyOf"]) == 2
    assert fields["probe"]["enum"] == ["p0", "p1", "p2", "p3"]
    assert (
        "style" in fields["claim"]["enum"] and "cancellation" in fields["claim"]["enum"]
    )
    assert not equal(True, 1) and not equal([False], [0])
