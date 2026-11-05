"""Test native source-binding recovery evidence, exact quality and finite attempt budgets without private models."""

import copy
import json

import pytest

from benchmarks.scripts import vi_voice_cuda_recovery as target
from benchmarks.tests.test_vi_voice_cuda_check import metrics


def evidence():
    """Describe40 distinct authored matching predictions with complete bilingual denominator metadata."""
    baseline = metrics()
    baseline["cases"] = [
        dict(id=f"source-{i}", status="ok", prediction=f"text {i}") for i in range(40)
    ]
    return dict(
        candidate=target.CANDIDATE,
        passed=True,
        exact_text_matches=40,
        cpu=baseline,
        gpu=copy.deepcopy(baseline),
    )


def test_retained_exact_quality_is_accepted_without_inference():
    """Allow reuse only of all40 first matching Qwen text outputs with unchanged quality metrics."""
    target.validate_quality(evidence())


@pytest.mark.parametrize(
    "bad",
    [
        "model",
        "failed",
        "boolean_count",
        "count",
        "text",
        "identity",
        "duplicate",
        "row_status",
        "missing",
        "cer",
    ],
)
def test_retained_evidence_cannot_hide_changed_or_missing_quality(bad):
    """Reject fabricated completeness, another model, changed texts and worse metrics before any model load."""
    value = evidence()
    if bad == "model":
        value["candidate"] = "whisper-small-ct2"
    elif bad == "failed":
        value["passed"] = False
    elif bad == "boolean_count":
        value["exact_text_matches"] = True
    elif bad == "count":
        value["exact_text_matches"] = 39
    elif bad == "text":
        value["gpu"]["cases"][0]["prediction"] = "changed"
    elif bad == "identity":
        value["gpu"]["cases"][0]["id"] = "other"
    elif bad == "duplicate":
        for side in ("cpu", "gpu"):
            value[side]["cases"][0]["id"] = value[side]["cases"][1]["id"]
    elif bad == "row_status":
        value["gpu"]["cases"][0]["status"] = "error"
    elif bad == "missing":
        value["gpu"]["cases"].pop()
    else:
        value["gpu"]["languages"]["vi_vn"]["character_edits"] += 1
    with pytest.raises(ValueError, match="cuda_recovery"):
        target.validate_quality(value)


@pytest.mark.parametrize("kind", ["asr", "core", "tts"])
def test_recovery_budgets_attempts_without_retry_refund(tmp_path, kind):
    """Record only four admitted first attempts and reject a duplicate or fifth request."""
    ledger = target.Ledger(tmp_path)
    for i in range(4):
        ledger.admit(kind, f"turn-{i}")
    with pytest.raises(ValueError, match="cuda_recovery_call_budget"):
        ledger.admit(kind, "fifth")
    assert ledger.counts[kind] == 4
    assert len((tmp_path / "calls.jsonl").read_text().splitlines()) == 4


@pytest.mark.asyncio
async def test_source_drift_fails_before_reusing_quality_or_loading_models(
    tmp_path, monkeypatch
):
    """Bind all ten current code/test files to successful software evidence before inspecting private neural assets."""
    (tmp_path / "software-verification.json").write_text(
        json.dumps(dict(status="PASS", source_sha256={}))
    )
    invoked = []
    monkeypatch.setattr(target, "retained_quality", lambda: invoked.append("forbidden"))
    with pytest.raises(ValueError, match="cuda_recovery_software_gate"):
        await target.run(tmp_path)
    assert not invoked
