"""Test independent complete contract-gate reporting against wrong facts, failed provenance and stale acceptance evidence."""

import json

import pytest

from benchmarks.scripts import d14_contract_full_report as subject
from benchmarks.scripts.d14_structured_acceptance import PROVENANCE_IDS, assess_gate


@pytest.mark.parametrize(
    "fault", [None, "wrong_fact", "provenance", "stale_acceptance", "request_condition"]
)
def test_complete_report_uses_shared_acceptance_and_verified_selected_requests(
    tmp_path, monkeypatch, fault
):
    """Require full42 accounting and preserve a single failed fact or provenance check instead of promoting a plausible first summary."""
    cases = [dict(id=f"fixture-{n}", category="reasoning") for n in range(42)]
    summary = dict(
        status="MEASUREMENT_COMPLETE", runtime_baseline_restored=True, profiles={}
    )
    for profile in ("core", "unrestricted"):
        summary["profiles"][profile] = dict(
            rows=[
                dict(
                    id=c["id"],
                    category=c["category"],
                    model_requests=1,
                    format_passed=True,
                    functional_passed=True,
                    request_contract_verified=True,
                )
                for c in cases
            ],
            runtime=dict(reaped=True, exit_code=0, guard_failure=None),
            provenance=[dict(id=p, passed=True) for p in PROVENANCE_IDS],
            cancellation=dict(native_slot_retired=True),
        )
    if fault == "wrong_fact":
        summary["profiles"]["core"]["rows"][0]["functional_passed"] = False
    elif fault == "provenance":
        summary["profiles"]["core"]["provenance"][0]["passed"] = False
    elif fault == "request_condition":
        summary["profiles"]["core"]["rows"][0]["request_contract_verified"] = False
    summary.update(assess_gate(summary, cases))
    if fault == "stale_acceptance":
        summary["profiles"]["core"]["rows"][0]["functional_passed"] = False
    monkeypatch.setattr(subject.campaign, "ROOT", tmp_path)
    monkeypatch.setattr(subject.campaign, "OUTPUT", tmp_path)
    (tmp_path / "result.json").write_text(json.dumps(summary))

    def observation(profile, case, row, path, **options):
        """Expose already-verified synthetic first facts while requiring actual selected-mode request reconstruction."""
        assert options["boolean_answer_contract"] is True
        return dict(
            id=row["id"],
            format_passed=row["format_passed"],
            functional_passed=row["functional_passed"],
        )

    monkeypatch.setattr(subject.verifier, "verify_wire", observation)
    if fault in {"stale_acceptance", "request_condition"}:
        with pytest.raises(ValueError):
            subject.verify_result(dict(cases=cases), summary)
    else:
        result = subject.verify_result(dict(cases=cases), summary)
        assert result["status"] == (
            "LOCAL_CONTRACT_REASONING_GATE_PASS"
            if fault is None
            else "LOCAL_CONTRACT_REASONING_GATE_FAIL"
        )
        assert result["profiles"]["core"]["functional_passed"] == (
            41 if fault == "wrong_fact" else 42
        )
        assert result["old_scores_rewritten"] is False
