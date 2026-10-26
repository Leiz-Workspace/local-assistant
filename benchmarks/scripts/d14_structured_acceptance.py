"""Apply one fail-closed D14 acceptance policy to live first observations and independently verified wire replays."""

import logging

logger = logging.getLogger(__name__)
PROFILES = {"core", "unrestricted"}
PROVENANCE_IDS = {
    "model_pin",
    "projector_pin",
    "complete_local_source_manifest",
    "runtime_pin",
    "pinned_license_copy",
}


def complete_rows(rows, cases, count):
    """Require exactly the declared unique case identities and categories, each with one first dispatch."""
    expected = {case["id"]: case["category"] for case in cases}
    return (
        len(cases) == len(expected) == count
        and len(rows) == count
        and {row.get("id") for row in rows} == set(expected)
        and all(
            row.get("category") == expected.get(row.get("id"))
            and type(row.get("model_requests")) is int
            and row["model_requests"] == 1
            for row in rows
        )
    )


def retired(runtime):
    """Require explicit successful child retirement with no missing or failed resource-guard observation."""
    return (
        runtime.get("reaped") is True
        and type(runtime.get("exit_code")) is int
        and runtime["exit_code"] == 0
        and "guard_failure" in runtime
        and runtime["guard_failure"] is None
    )


def provenance_passed(rows):
    """Require all five distinct declared provenance checks rather than five duplicate or truthy values."""
    return (
        len(rows) == 5
        and {row.get("id") for row in rows} == PROVENANCE_IDS
        and all(row.get("passed") is True for row in rows)
    )


def assess_gate(summary, cases, compatibility_cases=()):
    """Assess complete first-case, compatibility, provenance and lifecycle evidence without repairing observations or raising a failed gate to PASS."""
    profiles = summary.get("profiles", {})
    extra = summary.get("fresh_stream_compatibility_rows", [])
    checks = {
        "measurement_complete": summary.get("status") == "MEASUREMENT_COMPLETE",
        "profile_accounting": set(profiles) == PROFILES
        and all(
            complete_rows(value.get("rows", []), cases, 42)
            for value in profiles.values()
        ),
        "profile_format": all(
            row.get("format_passed") is True
            for value in profiles.values()
            for row in value.get("rows", [])
        ),
        "profile_functional": all(
            row.get("functional_passed") is True
            for value in profiles.values()
            for row in value.get("rows", [])
        ),
        "profile_lifecycle": all(
            retired(value.get("runtime", {}))
            and value.get("cancellation", {}).get("native_slot_retired") is True
            for value in profiles.values()
        ),
        "profile_provenance": all(
            provenance_passed(value.get("provenance", []))
            for value in profiles.values()
        ),
        "baseline_restored": summary.get("runtime_baseline_restored") is True,
        "compatibility_accounting": complete_rows(extra, compatibility_cases, 3)
        if compatibility_cases
        else not extra and "fresh_stream_compatibility_runtime" not in summary,
        "compatibility_format": all(row.get("format_passed") is True for row in extra),
        "compatibility_functional": all(
            row.get("functional_passed") is True for row in extra
        ),
        "compatibility_lifecycle": retired(
            summary.get("fresh_stream_compatibility_runtime", {})
        )
        if compatibility_cases
        else "fresh_stream_compatibility_runtime" not in summary,
    }
    format_passed = all(
        checks[key]
        for key in (
            "measurement_complete",
            "profile_accounting",
            "profile_format",
            "compatibility_accounting",
            "compatibility_format",
        )
    )
    functional_passed = (
        format_passed
        and checks["profile_functional"]
        and checks["compatibility_functional"]
    )
    quality_passed = all(checks.values())
    logger.info(
        "structured_acceptance_assessed format=%s functional=%s quality=%s failed_checks=%s",
        format_passed,
        functional_passed,
        quality_passed,
        sorted(key for key, value in checks.items() if not value),
    )
    return dict(
        format_gate_passed=format_passed,
        functional_gate_passed=functional_passed,
        quality_gate_passed=quality_passed,
        gate_checks=checks,
    )
