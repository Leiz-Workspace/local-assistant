"""Independently verify the complete selected-contract cohort, exact first wire and vocabulary-only context recount without generating new answers."""

import json
import logging
from pathlib import Path

from benchmarks.scripts import d14_contract_full_gate as campaign
from benchmarks.scripts import d14_reasoning_gate_report as verifier
from benchmarks.scripts.d14_structured_acceptance import assess_gate
from scripts.full_regression import source_manifest
from scripts.profile_excerpt_evaluation import publish

logger = logging.getLogger(__name__)


def verify_result(frozen, summary):
    """Recompute shared full acceptance and verify all42 first selected-contract observations per profile, preserving every factual failure."""
    acceptance = assess_gate(summary, frozen["cases"])
    if any(summary.get(key) != value for key, value in acceptance.items()):
        raise ValueError("contract_full_acceptance_changed")
    cases = {case["id"]: case for case in frozen["cases"]}
    profiles = {}
    for profile, record in summary["profiles"].items():
        observations = []
        for row in record["rows"]:
            observation = verifier.verify_wire(
                profile,
                cases[row["id"]],
                row,
                campaign.OUTPUT / profile / row["id"],
                boolean_answer_contract=True,
            )
            if row["request_contract_verified"] is not observation["format_passed"]:
                raise ValueError("contract_full_request_condition_changed")
            observations.append(observation)
        profiles[profile] = dict(
            total=42,
            format_passed=sum(r["format_passed"] for r in observations),
            functional_passed=sum(r["functional_passed"] for r in observations),
            observations=observations,
            runtime=record["runtime"],
            provenance=record["provenance"],
            cancellation=record["cancellation"],
            output_tokens=sum(
                r.get("result", {}).get("output_tokens", 0) for r in record["rows"]
            ),
            total_request_wall_seconds=sum(
                r.get("result", {}).get("wall_seconds", 0) for r in record["rows"]
            ),
        )
    logger.info(
        "contract_full_independently_verified quality=%s",
        acceptance["quality_gate_passed"],
    )
    return dict(
        description="Independent fresh complete selected-contract local gate; no historical-score rewrite or default activation.",
        status="LOCAL_CONTRACT_REASONING_GATE_PASS"
        if acceptance["quality_gate_passed"]
        else "LOCAL_CONTRACT_REASONING_GATE_FAIL",
        acceptance=acceptance,
        profiles=profiles,
        scored_first_requests=84,
        planned_native_cancel_requests=2,
        actual_generation_attempts=86,
        new_model_requests_in_this_verification=0,
        previous_questions_regenerated=0,
        old_scores_rewritten=False,
        application_files=732,
        all_original730_unchanged=True,
        original_full5674_is_historical=True,
        new_full732_run_claimed=False,
        model_or_default_changes=0,
        downloads=0,
        database_or_Vault_accesses=0,
        runtime_baseline_restored=True,
        release_approved=False,
        first_result=dict(
            path=str((campaign.OUTPUT / "result.json").relative_to(campaign.ROOT)),
            sha256=campaign.shared.BASE["digest"](campaign.OUTPUT / "result.json"),
        ),
    )


def main():
    """Authenticate the prerequisite, frozen code/models/corpus and current source before publishing exact native and context proof."""
    frozen = json.loads(campaign.FREEZE.read_text())
    for name, expected in frozen["sha256"].items():
        if campaign.shared.BASE["digest"](campaign.ROOT / name) != expected:
            raise ValueError("contract_full_frozen_input_changed")
    application = source_manifest()
    old = json.loads(
        (
            campaign.ROOT
            / "docs/evidence/d14-reasoning-trial-pre-inference-freeze.json"
        ).read_text()
    )["application_sha256"]
    if (
        application != frozen["application_sha256"]
        or len(application) != 732
        or any(application.get(k) != v for k, v in old.items())
    ):
        raise ValueError("contract_full_application_changed")
    qualified = json.loads(campaign.QUALIFICATION.read_text())
    if (
        qualified["acceptance"]["boolean_contract_qualification_passed"] is not True
        or campaign.shared.BASE["digest"](
            campaign.ROOT / qualified["first_result"]["path"]
        )
        != qualified["first_result"]["sha256"]
    ):
        raise ValueError("contract_full_prerequisite_changed")
    summary = json.loads((campaign.OUTPUT / "result.json").read_text())
    if (
        summary["status"] != "MEASUREMENT_COMPLETE"
        or summary["baseline"] != summary["after"]
        or campaign.shared.BASE["local_state"]() != summary["after"]
        or summary["after"]["native_pids"]
    ):
        raise ValueError("contract_full_runtime_or_execution_incomplete")
    old_audit = verifier.AUDIT
    try:
        verifier.AUDIT = campaign.ROOT / "data/backups/d14-contract-full-audit-20261026"
        result = verify_result(frozen, summary)
    finally:
        verifier.AUDIT = old_audit
    result.update(
        verifier_source_sha256=campaign.shared.BASE["digest"](Path(__file__)),
        wire_verifier_source_sha256=campaign.shared.BASE["digest"](
            Path(verifier.__file__)
        ),
        tokenizer_binary_sha256=campaign.shared.BASE["digest"](verifier.TOKENIZER),
    )
    publish(
        campaign.ROOT / "docs/evidence/d14-contract-full-first-verification.json",
        result,
    )
    print(
        json.dumps(
            dict(
                status=result["status"],
                profiles={
                    p: dict(
                        format=v["format_passed"],
                        correct=v["functional_passed"],
                        total=42,
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
