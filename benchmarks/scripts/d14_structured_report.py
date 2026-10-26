"""Verify first structured D14 wire evidence and parser-compatibility observations independently without rewriting any historical score or generating another answer."""

import hashlib
import json
import logging
import runpy
from pathlib import Path

from scripts.full_regression import source_manifest
from scripts.profile_excerpt_evaluation import publish
from src.infrastructure.inference.structured_profile import (
    StructuredProfileAdapter,
    StructuredProfileError,
    strict_json,
)

ROOT = Path.cwd()
FIRST = ROOT / "data/backups/d14-structured-gate-20261026"
SUFFIX = ROOT / "data/backups/d14-structured-suffix-20261026"
BASE = runpy.run_path("benchmarks/scripts/d14_completion.py")
logger = logging.getLogger(__name__)


def verify_wire(profile, case, row, directory):
    """Revalidate exact native bytes with the corrected parser while preserving separate immutable first-result and current-replay outcomes."""
    recorded = json.loads((directory / "measurement.json").read_text())
    if recorded != row or row["model_requests"] != 1:
        raise ValueError("structured_first_observation_changed")
    request_raw, wire = (
        (directory / "native-request.json").read_bytes(),
        (directory / "native-response.bin").read_bytes(),
    )
    request = strict_json(request_raw)
    adapter = StructuredProfileAdapter(
        profile=profile,
        schema=case["schema"],
        endpoint="http://127.0.0.1:18080",
        max_tokens=256,
    )
    if (
        request["model"] != adapter.model
        or request["response_format"]
        != dict(type="json_object", schema=json.loads(adapter.schema_bytes))
        or "tools" in request
    ):
        raise ValueError("structured_request_schema_or_model_changed")
    if any(
        key in json.dumps(request["response_format"])
        for key in ['"enum"', '"const"', '"default"', '"description"']
    ):
        raise ValueError("structured_answer_in_schema")
    value, content, usage = None, None, None
    try:
        if case.get("stream", False):
            events = [
                strict_json(line[6:])
                for line in wire.splitlines()
                if line.startswith(b"data: ") and line != b"data: [DONE]"
            ]
            reply = adapter.stream_reply(
                events, wire.decode().rstrip().endswith("data: [DONE]"), b"", True
            )
        else:
            reply = strict_json(wire)
        content, usage = adapter.validate_reply(reply)
        value = strict_json(content)
        from src.infrastructure.inference.structured_profile import matches_schema

        valid = matches_schema(value, json.loads(adapter.schema_bytes))
    except (ValueError, KeyError, StructuredProfileError):
        valid = False
    functional = bool(
        valid
        and BASE["strict_score"](content, case["expected"])
        and (
            case["category"] != "memory_context"
            or 30000 <= usage["prompt_tokens"] <= 32000
        )
    )
    if row.get("result"):
        saved = row["result"]
        if (
            saved["request_sha256"] != hashlib.sha256(request_raw).hexdigest()
            or saved["wire_sha256"] != hashlib.sha256(wire).hexdigest()
            or saved["schema_sha256"]
            != hashlib.sha256(adapter.schema_bytes).hexdigest()
            or saved["content"] != content
            or saved["value"] != value
        ):
            raise ValueError("structured_first_result_hash_or_content_changed")
        if (
            row["format_passed"] is not valid
            or row["functional_passed"] is not functional
        ):
            raise ValueError("structured_first_score_changed")
    logger.info(
        "structured_wire_revalidated id=%s format=%s functional=%s",
        case["id"],
        valid,
        functional,
    )
    return dict(
        id=case["id"],
        category=case["category"],
        first_format_passed=row["format_passed"],
        first_functional_passed=row["functional_passed"],
        corrected_wire_format_passed=bool(valid),
        corrected_wire_functional_passed=functional,
        expected_answer_sent_in_schema=False,
        measurement=dict(
            path=str((directory / "measurement.json").relative_to(ROOT)),
            sha256=BASE["digest"](directory / "measurement.json"),
        ),
        wire_sha256=hashlib.sha256(wire).hexdigest(),
        first_content_frame_seconds=row.get("result", {}).get(
            "first_content_frame_seconds"
        ),
        wall_seconds=row.get("result", {}).get("wall_seconds"),
    )


def main():
    """Verify fresh case accounting, frozen inputs, old-source retention and all owned-runtime cleanup, then publish the truthful local gate state."""
    frozen = json.loads(
        (
            ROOT / "docs/evidence/d14-structured-unmeasured-suffix-freeze.json"
        ).read_text()
    )
    first = json.loads((FIRST / "result.json").read_text())
    combined = json.loads((SUFFIX / "result.json").read_text())
    if (
        set(combined["profiles"]) != {"core", "unrestricted"}
        or combined["status"] != "MEASUREMENT_COMPLETE"
        or combined["profiles"]["core"]["rows"] != first["profiles"]["core"]["rows"]
        or combined["runtime_baseline_restored"] is not True
    ):
        raise ValueError("structured_combined_accounting_invalid")
    for path, expected in frozen["sha256"].items():
        if BASE["digest"](ROOT / path) != expected:
            raise ValueError("structured_frozen_artifact_changed")
    if source_manifest() != frozen["application_sha256"]:
        raise ValueError("structured_current_application_changed")
    old = json.loads(
        (ROOT / "data/backups/ce003-current-full/source-freeze.json").read_text()
    )["sha256"]
    if len(old) != 728 or any(
        BASE["digest"](ROOT / path) != expected for path, expected in old.items()
    ):
        raise ValueError("structured_previous_passed_component_changed")
    now = BASE["local_state"]()
    if now != combined["baseline"] or now != combined["after"] or now["native_pids"]:
        raise ValueError("structured_runtime_not_restored")
    protected = json.loads(
        (ROOT / "docs/evidence/d70-specialist-approved-freeze.json").read_text()
    )
    changed_protected = {
        path
        for path, expected in protected["protected_sha256"].items()
        if BASE["digest"](ROOT / path) != expected
    }
    if changed_protected - {"docs/MODEL_REGISTRY.md"} or any(
        BASE["digest"](ROOT / path) != expected
        for path, expected in protected["original_inputs_sha256"].items()
    ):
        raise ValueError("structured_original_protected_input_changed")
    cases = {case["id"]: case for case in frozen["cases"]}
    profiles = {}
    for profile, value in combined["profiles"].items():
        rows = value["rows"]
        if len(rows) != 42 or {r["id"] for r in rows} != set(cases):
            raise ValueError("structured_case_denominator_changed")
        root = FIRST / "core" if profile == "core" else SUFFIX / "unrestricted"
        observations = [
            verify_wire(profile, cases[r["id"]], r, root / r["id"]) for r in rows
        ]
        runtime = value["runtime"]
        if (
            runtime["reaped"] is not True
            or runtime["exit_code"] != 0
            or runtime["guard_failure"] is not None
            or value["cancellation"]["native_slot_retired"] is not True
        ):
            raise ValueError("structured_lifecycle_failed")
        profiles[profile] = dict(
            first_format_passed=sum(r["first_format_passed"] for r in observations),
            first_functional_passed=sum(
                r["first_functional_passed"] for r in observations
            ),
            corrected_wire_format_passed=sum(
                r["corrected_wire_format_passed"] for r in observations
            ),
            corrected_wire_functional_passed=sum(
                r["corrected_wire_functional_passed"] for r in observations
            ),
            total=42,
            observations=observations,
            runtime=runtime,
            provenance=value["provenance"],
        )
    extra_cases = {c["id"]: c for c in frozen["fresh_stream_compatibility_cases"]}
    extra = combined["fresh_stream_compatibility_rows"]
    if len(extra) != 3 or {r["id"] for r in extra} != set(extra_cases):
        raise ValueError("structured_compatibility_case_accounting")
    observations = [
        verify_wire(
            "core",
            extra_cases[r["id"]],
            r,
            SUFFIX / "core-stream-compatibility" / r["id"],
        )
        for r in extra
    ]
    runtime = combined["fresh_stream_compatibility_runtime"]
    if (
        runtime["reaped"] is not True
        or runtime["exit_code"] != 0
        or runtime["guard_failure"] is not None
    ):
        raise ValueError("structured_extra_runtime_uncertain")
    format_fixed = all(
        v["corrected_wire_format_passed"] == 42 for v in profiles.values()
    ) and all(
        r["corrected_wire_format_passed"] and r["corrected_wire_functional_passed"]
        for r in observations
    )
    functional = all(
        v["corrected_wire_functional_passed"] == 42 for v in profiles.values()
    )
    result = dict(
        description="Corrected structural decoding and native-stream compatibility, with immutable first scores and independent functional quality blocking.",
        status="FORMAT_FIX_VERIFIED_QUALITY_GATE_PASS"
        if format_fixed and functional
        else "FORMAT_FIX_VERIFIED_QUALITY_GATE_FAIL"
        if format_fixed
        else "FORMAT_FIX_NOT_QUALIFIED",
        profiles=profiles,
        format_fix_verified=format_fixed,
        local_functional_quality_gate_passed=format_fixed and functional,
        original_first_scores_rewritten=False,
        prior_D14_local_composites_unchanged=dict(core=66.5, unrestricted=52.0),
        fresh_stream_compatibility=observations,
        scored_first_requests=84,
        new_compatibility_requests=3,
        planned_cancel_requests=2,
        actual_generation_attempts=89,
        automatic_retries=0,
        previous_questions_regenerated=0,
        app_files=len(frozen["application_sha256"]),
        prior728_passed_application_files_unchanged=True,
        original_protected_reference_files=len(protected["protected_sha256"]),
        byte_identical_protected_files=len(protected["protected_sha256"])
        - len(changed_protected),
        disclosed_prior_registry_documentation_delta=sorted(changed_protected),
        original_inputs_unchanged=len(protected["original_inputs_sha256"]),
        earlier_full5674_is_historical=True,
        new_full_application_run_claimed=False,
        runtime_baseline_restored=True,
        database_or_Vault_accesses=0,
        model_or_default_changes=0,
        downloads=0,
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
    publish(
        ROOT / "docs/evidence/d14-structured-quality-gate-first-result.json", result
    )
    print(
        json.dumps(
            dict(
                status=result["status"],
                format_fix=format_fixed,
                quality_gate=result["local_functional_quality_gate_passed"],
                profiles={
                    p: {
                        k: v[k]
                        for k in [
                            "first_format_passed",
                            "first_functional_passed",
                            "corrected_wire_format_passed",
                            "corrected_wire_functional_passed",
                        ]
                    }
                    for p, v in profiles.items()
                },
            ),
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
