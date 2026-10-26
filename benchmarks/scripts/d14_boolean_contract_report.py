"""Independently verify balanced boolean-contract first evidence before allowing a separately frozen full validation."""

import copy
import json
import logging
from pathlib import Path

from benchmarks.scripts import d14_boolean_contract as campaign
from benchmarks.scripts.d14_reasoning_gate_report import verify_wire
from scripts.full_regression import source_manifest
from scripts.profile_excerpt_evaluation import publish

logger = logging.getLogger(__name__)


def verify_result(frozen, summary):
    """Recompute qualification and every first request/value while retaining separate true/false correctness and the old full-gate failure."""
    if summary["status"] != "MEASUREMENT_COMPLETE":
        raise ValueError("boolean_contract_report_incomplete")
    recomputed = copy.deepcopy(summary)
    acceptance = campaign.assess(recomputed, frozen["cases"])
    if any(summary.get(key) != value for key, value in acceptance.items()):
        raise ValueError("boolean_contract_report_acceptance_changed")
    cases = {c["id"]: c for c in frozen["cases"]}
    profiles = {}
    for profile, value in summary["profiles"].items():
        observations = [
            verify_wire(
                profile,
                cases[r["id"]],
                r,
                campaign.OUTPUT / profile / r["id"],
                boolean_answer_contract=True,
            )
            for r in value["rows"]
        ]
        for row, observation in zip(value["rows"], observations, strict=True):
            if row["contract_verified"] is not observation["format_passed"]:
                raise ValueError("boolean_contract_report_request_condition_changed")
        profiles[profile] = dict(
            total=12,
            format_passed=sum(o["format_passed"] for o in observations),
            functional_passed=sum(o["functional_passed"] for o in observations),
            true_reference_correct=sum(
                o["functional_passed"]
                for o in observations
                if cases[o["id"]]["expected"]["answer"] is True
            ),
            false_reference_correct=sum(
                o["functional_passed"]
                for o in observations
                if cases[o["id"]]["expected"]["answer"] is False
            ),
            observations=observations,
            runtime=value["runtime"],
            cancellation=value["cancellation"],
            provenance=value["provenance"],
        )
    logger.info(
        "boolean_contract_independently_verified qualified=%s",
        acceptance["boolean_contract_qualification_passed"],
    )
    return dict(
        description="Independent first balanced boolean-contract qualification; no historical score or full42 gate rewrite.",
        status="BOOLEAN_CONTRACT_QUALIFIED"
        if acceptance["boolean_contract_qualification_passed"]
        else "BOOLEAN_CONTRACT_NOT_QUALIFIED",
        acceptance=acceptance,
        profiles=profiles,
        new_model_requests_in_this_verification=0,
        scored_first_requests=24,
        planned_native_cancel_requests=2,
        actual_generation_attempts=26,
        model_or_default_changes=0,
        downloads=0,
        original_scores_rewritten=False,
        release_approved=False,
        first_result=dict(
            path=str((campaign.OUTPUT / "result.json").relative_to(campaign.ROOT)),
            sha256=campaign.shared.BASE["digest"](campaign.OUTPUT / "result.json"),
        ),
    )


def main():
    """Authenticate the frozen corpus/source/application and settled original runtime before publishing a new audit receipt."""
    frozen = json.loads(campaign.FREEZE.read_text())
    for name, expected in frozen["sha256"].items():
        if campaign.shared.BASE["digest"](campaign.ROOT / name) != expected:
            raise ValueError("boolean_contract_report_frozen_input_changed")
    if source_manifest() != frozen["application_sha256"]:
        raise ValueError("boolean_contract_report_application_changed")
    summary = json.loads((campaign.OUTPUT / "result.json").read_text())
    if (
        summary["baseline"] != summary["after"]
        or campaign.shared.BASE["local_state"]() != summary["after"]
        or summary["after"]["native_pids"]
    ):
        raise ValueError("boolean_contract_report_runtime_not_restored")
    result = verify_result(frozen, summary)
    result["verifier_source_sha256"] = campaign.shared.BASE["digest"](Path(__file__))
    publish(
        campaign.ROOT / "docs/evidence/d14-boolean-contract-first-verification.json",
        result,
    )
    print(
        json.dumps(
            dict(
                status=result["status"],
                profiles={
                    p: dict(
                        correct=v["functional_passed"],
                        total=12,
                        true_correct=v["true_reference_correct"],
                        false_correct=v["false_reference_correct"],
                    )
                    for p, v in result["profiles"].items()
                },
            ),
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
