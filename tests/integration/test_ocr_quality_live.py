"""Require measured real OCR/native/CORE vision golden quality for D21 local acceptance."""

import os

import pytest

from scripts.ocr_acceptance import distance, measure_acceptance, save_metrics


@pytest.mark.parametrize(
    "expected,actual,result",
    [("abc", "abc", 0), ("abc", "axc", 1), (["a", "b"], ["b"], 1)],
)
def test_quality_metric_oracles(expected, actual, result):
    """Check known edit distances so quality gates cannot pass through a broken scoring function."""
    assert distance(expected, actual) == result


@pytest.mark.asyncio
async def test_real_core_vision_and_ocr_quality(tmp_path):
    """Evaluate actual local model/table output and preserve a non-private metric artifact."""
    if os.environ.get("LOCAL_ASSISTANT_LIVE_E2E") != "1":
        pytest.skip("LOCAL_ASSISTANT_LIVE_E2E not configured")
    metrics = await measure_acceptance()
    assert metrics["passed"], metrics
    assert metrics["vision"]["matched_cells"] == 6
    assert (
        metrics["vision"]["review_required"]
        and metrics["vision"]["confidence_score"] is None
    )
    assert metrics["native_pdf_has_no_text_on_scan"]
    degraded = next(
        case for case in metrics["cases"] if case["fixture"] == "unclear.png"
    )
    assert degraded["criterion"] == "uncertainty_detection"
    assert degraded["character_error_rate"] == 1.0 and degraded["review_required"]
    path = tmp_path / "quality.json"
    save_metrics(path, metrics)
    assert (
        "image_base64" not in path.read_text()
        and "Invoice 2048" not in path.read_text()
    )
