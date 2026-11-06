"""Independently verify first paired reasoning requests, wire answers, condition evidence and lifecycle without another model generation."""

import copy
import hashlib
import json
import logging
from pathlib import Path

from benchmarks.scripts import d14_reasoning_trial as trial
from scripts.full_regression import source_manifest
from scripts.profile_excerpt_evaluation import publish
from src.infrastructure.inference.structured_profile import matches_schema, strict_json

logger = logging.getLogger(__name__)


def verify_observation(profile, case, row, directory):
    """Bind a first row to its frozen exact request and independently parsed native answer, retaining genuine quality and condition failures."""
    recorded = strict_json((directory / "measurement.json").read_bytes())
    if (
        recorded != row
        or row["id"] != case["id"]
        or row["category"] != case["category"]
        or type(row["thinking"]) is not bool
    ):
        raise ValueError("reasoning_report_first_row_changed")
    request_raw = (directory / "native-request.json").read_bytes()
    wire = (directory / "native-response.bin").read_bytes()
    request = strict_json(request_raw)
    adapter = trial.TrialAdapter(
        profile=profile,
        schema=case["schema"],
        thinking=row["thinking"],
        endpoint="http://127.0.0.1:18080",
    )
    expected = adapter.payload(case["prompt"], (), False)
    if json.dumps(request, sort_keys=True, ensure_ascii=False) != json.dumps(
        expected, sort_keys=True, ensure_ascii=False
    ):
        raise ValueError("reasoning_report_request_changed")
    adapter.max_tokens = 512
    valid, functional, condition = False, False, False
    content, value = None, None
    try:
        native = strict_json(wire)
        content, usage = adapter.validate_reply(native)
        value = strict_json(content)
        valid = matches_schema(value, case["schema"])
        functional = bool(
            valid and trial.BASE["strict_score"](content, case["expected"])
        )
        reasoning = native["choices"][0]["message"].get("reasoning_content", "")
        if reasoning is None:
            reasoning = ""
        condition = bool(
            valid
            and type(reasoning) is str
            and bool(reasoning.strip()) is row["thinking"]
        )
    except (ValueError, KeyError, trial.StructuredProfileError):
        pass
    if (
        row["format_passed"] is not valid
        or row["functional_passed"] is not functional
        or row["reasoning_condition_observed"] is not condition
    ):
        raise ValueError("reasoning_report_first_score_changed")
    if row.get("result"):
        saved = row["result"]
        if (
            saved["content"] != content
            or saved["value"] != value
            or saved["model_id"] != adapter.model
            or saved["request_sha256"] != hashlib.sha256(request_raw).hexdigest()
            or saved["wire_sha256"] != hashlib.sha256(wire).hexdigest()
            or saved["schema_sha256"]
            != hashlib.sha256(adapter.schema_bytes).hexdigest()
            or row["native_usage"] != usage
        ):
            raise ValueError("reasoning_report_native_binding_changed")
    replay = dict(
        format_passed=False,
        functional_passed=False,
        reasoning_condition_observed=False,
        output_tokens=0,
    )
    try:
        declared_adapter = copy.copy(adapter)
        declared_adapter.max_tokens = request["max_tokens"]
        native = strict_json(wire)
        replay_content, replay_usage = declared_adapter.validate_reply(native)
        replay_value = strict_json(replay_content)
        replay_valid = matches_schema(replay_value, case["schema"])
        reasoning = native["choices"][0]["message"].get("reasoning_content") or ""
        replay.update(
            format_passed=replay_valid,
            functional_passed=bool(
                replay_valid
                and trial.BASE["strict_score"](replay_content, case["expected"])
            ),
            reasoning_condition_observed=bool(
                replay_valid
                and type(reasoning) is str
                and bool(reasoning.strip()) is row["thinking"]
            ),
            output_tokens=replay_usage["completion_tokens"],
        )
    except (ValueError, KeyError, trial.StructuredProfileError):
        pass
    logger.info(
        "reasoning_report_first_verified profile=%s id=%s thinking=%s functional=%s",
        profile,
        case["id"],
        row["thinking"],
        functional,
    )
    return dict(
        id=case["id"],
        category=case["category"],
        thinking=row["thinking"],
        format_passed=valid,
        functional_passed=functional,
        native_reasoning_condition_observed=condition,
        declared_request_budget_wire_replay=replay,
        request_sha256=hashlib.sha256(request_raw).hexdigest(),
        wire_sha256=hashlib.sha256(wire).hexdigest(),
        measurement_sha256=trial.BASE["digest"](directory / "measurement.json"),
    )


def verify_result(frozen, summary):
    """Recompute paired acceptance and improvement counts from complete first evidence while preserving the original D14 gate state."""
    if summary["status"] != "MEASUREMENT_COMPLETE":
        raise ValueError("reasoning_report_incomplete_campaign")
    cases = {case["id"]: case for case in frozen["cases"]}
    recomputed = copy.deepcopy(summary)
    acceptance = trial.assess(recomputed, frozen["cases"])
    if any(summary.get(key) != value for key, value in acceptance.items()):
        raise ValueError("reasoning_report_acceptance_changed")
    profiles = {}
    for profile, record in summary["profiles"].items():
        if record["conditions"] != recomputed["profiles"][profile]["conditions"]:
            raise ValueError("reasoning_report_condition_summary_changed")
        observations = [
            verify_observation(
                profile,
                cases[row["id"]],
                row,
                trial.OUTPUT
                / profile
                / row["id"]
                / ("thinking" if row["thinking"] else "direct"),
            )
            for row in record["rows"]
        ]
        pairs = {
            case_id: {
                r["thinking"]: r["functional_passed"]
                for r in observations
                if r["id"] == case_id
            }
            for case_id in cases
        }
        profiles[profile] = dict(
            conditions=record["conditions"],
            observations=observations,
            runtime=record["runtime"],
            provenance=record["provenance"],
            pair_counts=dict(
                both_correct=sum(p[False] and p[True] for p in pairs.values()),
                thinking_only=sum(not p[False] and p[True] for p in pairs.values()),
                direct_only=sum(p[False] and not p[True] for p in pairs.values()),
                both_wrong=sum(not p[False] and not p[True] for p in pairs.values()),
            ),
        )
        profiles[profile]["declared_request_budget_wire_replay"] = {
            name: dict(
                total=12,
                format_passed=sum(
                    r["declared_request_budget_wire_replay"]["format_passed"]
                    for r in observations
                    if r["thinking"] is flag
                ),
                functional_passed=sum(
                    r["declared_request_budget_wire_replay"]["functional_passed"]
                    for r in observations
                    if r["thinking"] is flag
                ),
                condition_observed=sum(
                    r["declared_request_budget_wire_replay"][
                        "reasoning_condition_observed"
                    ]
                    for r in observations
                    if r["thinking"] is flag
                ),
                output_tokens=sum(
                    r["declared_request_budget_wire_replay"]["output_tokens"]
                    for r in observations
                    if r["thinking"] is flag
                ),
            )
            for name, flag in [("direct", False), ("thinking", True)]
        }
    return dict(
        description="Independent paired fresh reasoning diagnostic verification; no new model calls or historical-score updates.",
        acceptance=acceptance,
        profiles=profiles,
        new_model_requests_in_this_verification=0,
        historical_D14_quality_gate_passed=False,
        model_or_default_changes=0,
        downloads=0,
        original_scores_rewritten=False,
        runtime_baseline_restored=summary["runtime_baseline_restored"],
        first_result=dict(
            path=str((trial.OUTPUT / "result.json").relative_to(trial.ROOT)),
            sha256=trial.BASE["digest"](trial.OUTPUT / "result.json"),
        ),
    )


def main():
    """Verify all frozen inputs, the unchanged application and restored native baseline before publishing a separate first-comparison audit."""
    frozen = strict_json(trial.FREEZE.read_bytes())
    for name, expected in frozen["sha256"].items():
        if trial.BASE["digest"](trial.ROOT / name) != expected:
            snapshots = {
                "benchmarks/scripts/d14_reasoning_trial.py": "data/backups/d14-reasoning-first-executed-trial.py",
                "benchmarks/tests/test_d14_reasoning_trial.py": "data/backups/test_d14_reasoning_first_executed_trial.py",
            }
            if (
                name not in snapshots
                or trial.BASE["digest"](trial.ROOT / snapshots[name]) != expected
            ):
                raise ValueError("reasoning_report_frozen_input_changed")
    application = source_manifest()
    if any(
        application.get(name) != expected
        for name, expected in frozen["application_sha256"].items()
    ) or set(application) - set(frozen["application_sha256"]) not in (
        set(),
        {
            "src/infrastructure/inference/reasoning_profile.py",
            "tests/test_reasoning_profile.py",
        },
    ):
        raise ValueError("reasoning_report_application_changed")
    summary = strict_json((trial.OUTPUT / "result.json").read_bytes())
    now = trial.BASE["local_state"]()
    if now != summary["baseline"] or now != summary["after"] or now["native_pids"]:
        raise ValueError("reasoning_report_runtime_not_restored")
    result = verify_result(frozen, summary)
    result["verifier_source_sha256"] = trial.BASE["digest"](Path(__file__))
    publish(
        trial.ROOT
        / "docs/evidence/d14-reasoning-trial-budget-correction-verification.json",
        result,
    )
    print(
        json.dumps(
            dict(
                acceptance=result["acceptance"],
                profiles={
                    p: dict(conditions=v["conditions"], pair_counts=v["pair_counts"])
                    for p, v in result["profiles"].items()
                },
            ),
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
