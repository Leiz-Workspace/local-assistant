"""Run the versioned D23 corpus with real sandbox readers and explicitly enabled CORE acceptance."""

import json
import os

import pytest

from scripts.document_pipeline_acceptance import (
    evaluate_case,
    load_manifest,
    measure_pipeline,
    save_report,
)

CASES = [case for case in load_manifest()["cases"] if case.get("mode") != "vlm"]


@pytest.mark.asyncio
@pytest.mark.parametrize("case", CASES, ids=[case["id"] for case in CASES])
async def test_real_synthetic_pipeline_case(case):
    """Check each actual verifier/parser/rewrite/chunk path against independent corpus oracles."""
    result = await evaluate_case(case)
    assert result["passed"], result
    assert result["resources"]["wall_ms"] > 0
    assert result["stages"]
    if result["expected_outcome"] == "rejected":
        assert result["outcome"] == "expected_rejection"
    else:
        assert result["metrics"]["coverage_ratio"] == 1
        assert result["checks"]["deterministic_repeat"]
    if case["id"] == "ocr-degraded":
        assert result["outcome"] == "degraded"
        assert result["metrics"]["transcription_passed"] is False
        assert result["metrics"]["character_error_rate"] == 1


@pytest.mark.asyncio
async def test_complete_real_core_pipeline_report(tmp_path):
    """Require all cases, actual CORE table accuracy and an honest retained non-content report."""
    if os.environ.get("LOCAL_ASSISTANT_LIVE_E2E") != "1":
        pytest.skip("LOCAL_ASSISTANT_LIVE_E2E not configured")
    report = await measure_pipeline(include_vlm=True)
    assert report["passed"] and report["complete"], report["failures"]
    assert len(report["cases"]) == 18 and not report["failures"]
    assert report["quality_failures"] == [
        dict(
            case="ocr-degraded",
            code="transcription_inaccurate",
            character_error_rate=1.0,
            word_error_rate=1.0,
        )
    ]
    vision = next(c for c in report["cases"] if c["id"] == "vision-table")
    assert (
        vision["metrics"]["matched_cells"] == vision["metrics"]["expected_cells"] == 6
    )
    path = tmp_path / "pipeline.json"
    save_report(path, report)
    saved = json.loads(path.read_text())
    assert saved == report
    for forbidden in (
        "image_base64",
        "Invoice 2048",
        "Báo cáo D19",
        "uncertain 7381",
        "Tên hàng",
        "Đã sửa",
        "postgresql://",
    ):
        assert forbidden not in path.read_text()
