"""Verify frozen integrated attack inputs, honest functional scoring and complete provenance/cancel cleanup using explicitly authored model/native fixtures."""

import json

import pytest
from test_claim_validation import Core
from test_claim_validation_policy import completion
from test_report_export import AuthoredExporter
from web_phase_cases import evaluate_case, load_corpus

from src.application.services.report_export_policy import ReportExportError


def controlled_core():
    """Return fixed known claim labels and independent E1/E2 references without reading the evaluation case's expected labels."""
    core = Core()
    core.result = completion(
        dict(
            claims=[
                dict(
                    claim_id="C1",
                    status="supported",
                    evidence_ids=["E1"],
                    reason="First quote states G-17.",
                ),
                dict(
                    claim_id="C2",
                    status="contradicted",
                    evidence_ids=["E2"],
                    reason="Second quote states 128 MiB, not 256 MiB.",
                ),
                dict(
                    claim_id="C3",
                    status="insufficient",
                    evidence_ids=[],
                    reason="No source states a launch year.",
                ),
            ]
        )
    )
    return core


@pytest.mark.parametrize("case", load_corpus()["cases"], ids=lambda row: row["id"])
@pytest.mark.asyncio
async def test_original_components_keep_all_authored_attack_data_untrusted_and_proofs_owner_bound(
    case,
):
    """Exercise the entire original proof/report/export protocol and finite denial paths without claiming fixture outputs are real inference/native structure."""
    core, native = controlled_core(), AuthoredExporter()
    row = await evaluate_case(case, core, native, "fixture-core")
    assert row["functional_pass"] and row["finite_authority_boundary_pass"]
    assert row["model_port_attempts"] == case["expected_model_calls"]
    assert (
        row["native_batches"] == case["expected_native_batches"]
        and row["cleanup_complete"]
    )
    if native.calls:
        payload = json.loads(native.calls[0])
        text = "\n".join(block["text"] for block in payload["blocks"])
        assert all(quote in text for quote in case["quotes"])
        assert all(claim in text for claim in case["claims"])
        if case["date"]:
            assert case["date"] in text


@pytest.mark.parametrize(
    "mutation", ["unsupported_label", "wrong_citation", "format_rejection"]
)
@pytest.mark.asyncio
async def test_valid_schema_or_safe_rejection_does_not_fabricate_functional_success(
    mutation,
):
    """Score unsupported model labels/wrong source binding/rejected shape as functional failures even when action authority stays bounded."""
    case = load_corpus()["cases"][0]
    core = controlled_core()
    value = json.loads(core.result.content)
    if mutation == "unsupported_label":
        value["claims"][2].update(status="supported", evidence_ids=["E1"])
    elif mutation == "wrong_citation":
        value["claims"][0]["evidence_ids"] = ["E2"]
    else:
        value = value["claims"]
    core.result = completion(json.dumps(value))
    row = await evaluate_case(case, core, AuthoredExporter(), "fixture-core")
    assert not row["functional_pass"] and row["finite_authority_boundary_pass"]
    assert row["model_port_attempts"] == 1 and row["cleanup_complete"]


@pytest.mark.asyncio
async def test_native_failure_is_retained_without_retry_or_fake_artifacts():
    """Keep an actual native-port failure in the functional denominator instead of replacing it with authored success."""

    class FailedNative:
        """Expose a finite authored native failure with no process, filesystem or network activity."""

        async def render(self, payload):
            """Fail the sole native request without returning placeholder output bytes."""
            raise ReportExportError("export_native_failed")

    row = await evaluate_case(
        load_corpus()["cases"][0], controlled_core(), FailedNative(), "fixture-core"
    )
    assert not row["functional_pass"] and row["finite_authority_boundary_pass"]
    assert row["native_batches"] == 1 and not row["artifact_hashes"]


def test_original_d52_failed_role_delimiters_are_preserved_in_new_integration_inputs():
    """Carry the historical first failure's exact source bytes forward rather than simplifying the attack after repair."""
    from pathlib import Path

    old = json.loads(Path("tests/fixtures/web_redteam/d52-cases.json").read_text())
    original = next(
        row["snippet"] for row in old["cases"] if row["id"] == "role-delimiters"
    )
    current = next(
        row
        for row in load_corpus()["cases"]
        if row["id"] == "original-d52-role-delimiters"
    )
    assert current["quotes"][0] == original
