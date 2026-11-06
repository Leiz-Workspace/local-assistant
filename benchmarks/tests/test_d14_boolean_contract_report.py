"""Verify balanced qualification reporting retains wrong facts and checks request-contract evidence rather than promoting a stale flag."""

import json

import pytest

from benchmarks.scripts import d14_boolean_contract_report as subject
from benchmarks.scripts.d14_structured_acceptance import PROVENANCE_IDS


@pytest.mark.parametrize(
    "fault", [None, "wrong_fact", "false_contract", "stale_acceptance"]
)
def test_independent_report_cannot_promote_incorrect_or_unobserved_first_results(
    tmp_path, monkeypatch, fault
):
    """Keep sixTrue/sixFalse accounting and reject a forged PASS or missing contract condition without model/artifact dependencies."""
    cases = subject.campaign.make_cases()
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
                    native_reasoning_verified=True,
                    contract_verified=True,
                )
                for c in cases
            ],
            runtime=dict(reaped=True, exit_code=0, guard_failure=None),
            cancellation=dict(native_slot_retired=True),
            provenance=[dict(id=p, passed=True) for p in PROVENANCE_IDS],
        )
    if fault == "wrong_fact":
        summary["profiles"]["core"]["rows"][0]["functional_passed"] = False
    if fault == "false_contract":
        summary["profiles"]["core"]["rows"][0]["contract_verified"] = False
    summary.update(subject.campaign.assess(summary, cases))
    if fault == "stale_acceptance":
        summary["profiles"]["core"]["rows"][0]["functional_passed"] = False
    monkeypatch.setattr(subject.campaign, "OUTPUT", tmp_path)
    monkeypatch.setattr(subject.campaign, "ROOT", tmp_path)
    (tmp_path / "result.json").write_text(json.dumps(summary))

    def observation(profile, case, row, path, **options):
        """Expose finite authored already-verified observations while asserting that the selected request contract is mandatory."""
        assert options["boolean_answer_contract"] is True
        return dict(
            id=row["id"],
            category=row["category"],
            format_passed=row["format_passed"],
            functional_passed=row["functional_passed"],
        )

    monkeypatch.setattr(subject, "verify_wire", observation)
    if fault in {"false_contract", "stale_acceptance"}:
        with pytest.raises(ValueError):
            subject.verify_result(dict(cases=cases), summary)
    else:
        result = subject.verify_result(dict(cases=cases), summary)
        assert result["status"] == (
            "BOOLEAN_CONTRACT_QUALIFIED"
            if fault is None
            else "BOOLEAN_CONTRACT_NOT_QUALIFIED"
        )
        assert result["profiles"]["core"]["false_reference_correct"] == (
            6 if fault is None else 5
        )
        assert result["original_scores_rewritten"] is False
