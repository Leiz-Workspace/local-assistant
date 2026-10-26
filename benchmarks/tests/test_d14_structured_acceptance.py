"""Test shared runner/report acceptance against missing, duplicate, failed and merely truthy evidence without model traffic."""

import copy

import pytest

from benchmarks.scripts.d14_structured_acceptance import PROVENANCE_IDS, assess_gate
from benchmarks.scripts.d14_structured_report import assess_replay


@pytest.fixture
def campaign():
    """Build an explicit fully passing synthetic campaign with the exact 42 plus three denominators."""
    cases = [dict(id=f"case-{n}", category="reasoning") for n in range(42)]
    extra = [dict(id=f"stream-{n}", category="performance") for n in range(3)]
    runtime = dict(reaped=True, exit_code=0, guard_failure=None)
    profiles = {}
    for profile in ("core", "unrestricted"):
        profiles[profile] = dict(
            rows=[
                dict(
                    **case, model_requests=1, format_passed=True, functional_passed=True
                )
                for case in cases
            ],
            runtime=copy.deepcopy(runtime),
            cancellation=dict(native_slot_retired=True),
            provenance=[dict(id=key, passed=True) for key in sorted(PROVENANCE_IDS)],
        )
    return (
        dict(
            status="MEASUREMENT_COMPLETE",
            runtime_baseline_restored=True,
            profiles=profiles,
            fresh_stream_compatibility_rows=[
                dict(
                    **case, model_requests=1, format_passed=True, functional_passed=True
                )
                for case in extra
            ],
            fresh_stream_compatibility_runtime=runtime,
        ),
        cases,
        extra,
    )


def replay_inputs(summary):
    """Translate synthetic first observations to the independent report's verified-observation contract."""
    profiles = {}
    for profile, value in summary["profiles"].items():
        profiles[profile] = dict(
            runtime=value["runtime"],
            provenance=value["provenance"],
            observations=[
                dict(
                    id=row["id"],
                    category=row["category"],
                    model_requests=row["model_requests"],
                    corrected_wire_format_passed=row["format_passed"],
                    corrected_wire_functional_passed=row["functional_passed"],
                )
                for row in value["rows"]
            ],
        )
    extra = [
        dict(
            id=row["id"],
            category=row["category"],
            model_requests=row["model_requests"],
            corrected_wire_format_passed=row["format_passed"],
            corrected_wire_functional_passed=row["functional_passed"],
        )
        for row in summary["fresh_stream_compatibility_rows"]
    ]
    return profiles, extra


@pytest.mark.parametrize(
    "fault",
    [
        None,
        "compat_format",
        "compat_fact",
        "compat_missing",
        "compat_duplicate",
        "compat_runtime",
        "provenance",
        "provenance_duplicate",
        "provenance_truthy",
        "main_missing",
        "main_duplicate",
        "main_category",
        "main_retry",
        "main_truthy",
        "main_fact",
        "main_runtime",
        "missing_guard",
        "cancel",
        "baseline",
        "incomplete",
        "profile_missing",
    ],
)
def test_runner_and_report_share_fail_closed_acceptance(campaign, fault):
    """Require both callers to reject every incomplete or failed declared observation, including all-three streaming failures and zero provenance passes."""
    summary, cases, extra = campaign
    value = summary["profiles"]["core"]
    rows = summary["fresh_stream_compatibility_rows"]
    if fault == "compat_format":
        for row in rows:
            row["format_passed"] = False
    elif fault == "compat_fact":
        for row in rows:
            row["functional_passed"] = False
    elif fault == "compat_missing":
        rows.pop()
    elif fault == "compat_duplicate":
        rows[1] = copy.deepcopy(rows[0])
    elif fault == "compat_runtime":
        summary["fresh_stream_compatibility_runtime"]["reaped"] = False
    elif fault == "provenance":
        for row in value["provenance"]:
            row["passed"] = False
    elif fault == "provenance_duplicate":
        value["provenance"][1] = copy.deepcopy(value["provenance"][0])
    elif fault == "provenance_truthy":
        value["provenance"][0]["passed"] = 1
    elif fault == "main_missing":
        value["rows"].pop()
    elif fault == "main_duplicate":
        value["rows"][1] = copy.deepcopy(value["rows"][0])
    elif fault == "main_category":
        value["rows"][0]["category"] = "other"
    elif fault == "main_retry":
        value["rows"][0]["model_requests"] = 2
    elif fault == "main_truthy":
        value["rows"][0]["format_passed"] = 1
    elif fault == "main_fact":
        value["rows"][0]["functional_passed"] = False
    elif fault == "main_runtime":
        value["runtime"]["exit_code"] = False
    elif fault == "missing_guard":
        del value["runtime"]["guard_failure"]
    elif fault == "cancel":
        value["cancellation"]["native_slot_retired"] = False
    elif fault == "baseline":
        summary["runtime_baseline_restored"] = False
    elif fault == "incomplete":
        summary["status"] = "INCOMPLETE"
    elif fault == "profile_missing":
        del summary["profiles"]["unrestricted"]
    live = assess_gate(summary, cases, extra)
    verified_profiles, verified_extra = replay_inputs(summary)
    replay = assess_replay(summary, verified_profiles, verified_extra, cases, extra)
    assert live["quality_gate_passed"] is (fault is None)
    assert replay == live


def test_undeclared_compatibility_cannot_be_silently_accepted(campaign):
    """Reject extra observations absent from the frozen plan and admit an original plan that declares no compatibility cohort."""
    summary, cases, _ = campaign
    assert assess_gate(summary, cases)["quality_gate_passed"] is False
    del summary["fresh_stream_compatibility_rows"]
    del summary["fresh_stream_compatibility_runtime"]
    assert assess_gate(summary, cases)["quality_gate_passed"] is True
