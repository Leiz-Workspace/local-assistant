"""Independently verify and publish D14 first measurements, preserved text scores, runtime retirement and local evidence limits without model calls or data mutation."""

import json
import logging
import runpy
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.profile_excerpt_evaluation import publish

BASE = runpy.run_path("benchmarks/scripts/d14_completion.py")
ROOT = Path(__file__).resolve().parents[2]
FIRST = ROOT / "data/backups/d14-completion-20261026"
SUFFIX = ROOT / "data/backups/d14-completion-20261026-unrestricted-first"
LOGGER = logging.getLogger(__name__)


def verify_profile(profile, value, root, frozen):
    """Recompute every first score and wire hash against frozen oracles, requiring full declared accounting and settled native lifecycle."""
    cases = {
        case["id"]: case
        for category in ["media", "context", "performance"]
        for case in frozen[category]
    }
    rows = value["rows"]
    if len(rows) != 12 or {row["id"] for row in rows} != set(cases):
        raise ValueError("d14_report_case_accounting")
    observations = []
    for row in rows:
        case = cases[row["id"]]
        directory = root / row["id"]
        recorded = json.loads((directory / "measurement.json").read_text())
        raw = (directory / "native-response.bin").read_bytes()
        if (
            recorded != row
            or BASE["digest"](directory / "native-response.bin")
            != row["native_response_sha256"]
            or row["model_requests"] != 1
            or row["category"] != case["category"]
            or type(row["passed"]) is not bool
        ):
            raise ValueError("d14_report_first_observation_changed")
        request = json.loads((directory / "request.json").read_text())
        model = "qwen3.5-9b-" + profile
        response = (
            BASE["decode_stream"](raw, model) if row["stream"] else json.loads(raw)
        )
        if response != row["reply"] or request["model"] != model:
            raise ValueError("d14_report_native_reply_changed")
        choice, usage = response["choices"][0], response["usage"]
        valid = (
            response["model"] == model
            and choice["finish_reason"] == "stop"
            and type(usage["prompt_tokens"]) is int
            and type(usage["completion_tokens"]) is int
            and usage["prompt_tokens"] > 0
            and usage["completion_tokens"] > 0
        )
        if case["category"] == "memory_context":
            valid = valid and 30000 <= usage["prompt_tokens"] <= 32000
        if row["stream"]:
            valid = (
                valid
                and row["first_content_frame_seconds"] is not None
                and row["first_content_frame_seconds"] > 0
            )
        correct = valid and BASE["strict_score"](
            choice["message"]["content"], case["expected"]
        )
        if row["passed"] is not bool(correct) or row[
            "response_contract_passed"
        ] is not bool(valid):
            raise ValueError("d14_report_score_changed")
        reason = None
        if not correct:
            try:
                json.loads(choice["message"]["content"])
                reason = "complete_json_type_or_value_mismatch"
            except ValueError:
                reason = "strict_json_invalid_including_markdown_fences"
        observations.append(
            dict(
                id=row["id"],
                category=row["category"],
                passed=bool(correct),
                response_contract_passed=bool(valid),
                failure_class=reason,
                measurement=dict(
                    path=str((directory / "measurement.json").relative_to(ROOT)),
                    sha256=BASE["digest"](directory / "measurement.json"),
                ),
                wall_seconds=row["wall_seconds"],
                first_content_frame_seconds=row["first_content_frame_seconds"],
                prompt_tokens=usage["prompt_tokens"],
                completion_tokens=usage["completion_tokens"],
            )
        )
    score = BASE["weighted"](
        frozen["retained_text_points"][profile], rows, value["provenance"]
    )
    if score != value["score"] or any(row["wall_seconds"] <= 0 for row in rows):
        raise ValueError("d14_report_weight_or_clock_changed")
    runtime = value["runtime"]
    cancel = json.loads((root / "cancel-receipt.json").read_text())
    if (
        runtime["reaped"] is not True
        or runtime["exit_code"] != 0
        or runtime["guard_failure"] is not None
        or cancel != value["cancellation"]
        or cancel["model_requests"] != 1
        or cancel["native_slot_retired"] is not True
    ):
        raise ValueError("d14_report_lifecycle_not_accepted")
    streams = [row for row in observations if row["category"] == "performance"]
    LOGGER.info("d14_first_profile_verified profile=%s rows=%d", profile, len(rows))
    return dict(
        score=score,
        observations=observations,
        provenance=value["provenance"],
        lifecycle=cancel,
        runtime=runtime,
        performance=dict(
            planned_samples=3,
            wall_seconds=[row["wall_seconds"] for row in streams],
            wall_median_seconds=statistics.median(
                row["wall_seconds"] for row in streams
            ),
            first_content_frame_seconds=[
                row["first_content_frame_seconds"] for row in streams
            ],
            first_content_frame_median_seconds=statistics.median(
                row["first_content_frame_seconds"] for row in streams
            ),
            speed_SLO_established=False,
            note="Three planned samples, client frame-arrival upper bounds; exact response-format failures still score zero.",
        ),
    )


def main():
    """Verify joined current and historical bindings, disclose intentional registry changes and publish a limited local measurement receipt."""
    combined = json.loads((SUFFIX / "result.json").read_text())
    frozen = json.loads(
        (
            ROOT / "docs/evidence/d14-completion-unmeasured-suffix-freeze.json"
        ).read_text()
    )
    first = json.loads((FIRST / "result.json").read_text())
    BASE["validate_continuation"](first)
    if (
        combined["status"] != "MEASUREMENT_COMPLETE_QUALITY_FINDINGS_RETAINED"
        or combined["profiles"]["core"] != first["profiles"]["core"]
        or combined["runtime_baseline_restored"] is not True
    ):
        raise ValueError("d14_combined_first_result_invalid")
    for path, expected in frozen["sha256"].items():
        if BASE["digest"](ROOT / path) != expected:
            raise ValueError("d14_posttrial_frozen_input_drift")
    BASE["verify_manifest"](frozen["application_sha256"])
    full = json.loads(
        (ROOT / "data/backups/ce003-current-full/source-freeze.json").read_text()
    )["sha256"]
    if full != frozen["application_sha256"]:
        raise ValueError("d14_application_snapshot_changed")
    now = BASE["local_state"]()
    if now != combined["baseline"] or now != combined["after"] or now["native_pids"]:
        raise ValueError("d14_runtime_baseline_not_restored")
    original = json.loads(
        (ROOT / "docs/evidence/d70-specialist-approved-freeze.json").read_text()
    )
    protected_delta = {
        path: dict(before=expected, after=BASE["digest"](ROOT / path))
        for path, expected in original["protected_sha256"].items()
        if BASE["digest"](ROOT / path) != expected
    }
    if set(protected_delta) - {"docs/MODEL_REGISTRY.md"}:
        raise ValueError("d14_unexpected_protected_input_drift")
    if any(
        BASE["digest"](ROOT / path) != expected
        for path, expected in original["original_inputs_sha256"].items()
    ):
        raise ValueError("d14_original_media_or_control_input_drift")
    pending = json.loads(
        (ROOT / "data/backups/d70-tts-listening-review/review.pending.json").read_text()
    )
    if any(
        row["has_actually_listened"] is not False
        or row["naturalness_judgement"] is not None
        for row in pending["items"]
    ):
        raise ValueError("d14_deferred_listening_changed")
    profiles = {
        profile: verify_profile(
            profile,
            combined["profiles"][profile],
            FIRST / "core" if profile == "core" else SUFFIX / "unrestricted",
            frozen,
        )
        for profile in ["core", "unrestricted"]
    }
    result = dict(
        description="Independently verified actual D14 missing-domain measurements; mixed-date local composite, not universal capability, model replacement, legal clearance or product release.",
        status="D14_MEASUREMENT_COMPLETE_QUALITY_FINDINGS_RETAINED",
        reviewed_first_commit="f33289e",
        reviewed_suffix_commit="72cb1ae",
        profiles=profiles,
        retained_text_requests=60,
        new_scored_requests=24,
        planned_cancel_requests=2,
        actual_new_model_requests=26,
        automatic_retries=0,
        previously_scored_questions_regenerated=0,
        total_model_questions_per_profile=42,
        additional_local_provenance_checks_per_profile=5,
        original_day13_weights_unchanged=True,
        current_application_files_unchanged=len(full),
        current_full_suite_historical_passed=5674,
        full_suite_rerun=False,
        runtime_and_container_baseline_restored=True,
        initial_and_final_native_processes=0,
        boot_id=now["boot_id"],
        protected_reference_files=len(original["protected_sha256"]),
        byte_identical_protected_files=len(original["protected_sha256"])
        - len(protected_delta),
        intentional_prior_registry_documentation_delta=protected_delta,
        original_inputs_unchanged=len(original["original_inputs_sha256"]),
        actual_listening_labels=0,
        database_and_Vault_accesses=0,
        model_replacements=0,
        downloads=0,
        production_defaults_changed=False,
        independent_human_review=False,
        upstream_attestation_or_legal_clearance=False,
        d14_quality_pass_inferred=False,
        release_approved=False,
        first_result=dict(
            path=str((FIRST / "result.json").relative_to(ROOT)),
            sha256=BASE["digest"](FIRST / "result.json"),
        ),
        combined_result=dict(
            path=str((SUFFIX / "result.json").relative_to(ROOT)),
            sha256=BASE["digest"](SUFFIX / "result.json"),
        ),
    )
    publish(ROOT / "docs/evidence/d14-completion-first-result.json", result)
    LOGGER.info(
        "d14_independent_measurement_receipt_published requests=26 protected_exact=%d",
        result["byte_identical_protected_files"],
    )
    print(
        json.dumps(
            dict(
                status=result["status"],
                scores={
                    p: r["score"]["local_composite_points"] for p, r in profiles.items()
                },
                protected_exact=result["byte_identical_protected_files"],
            ),
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
