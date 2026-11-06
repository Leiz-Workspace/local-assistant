"""Prove the D23 evaluator detects wrong source coverage/content/structure and reports failures honestly."""

import copy
import json
import logging
from uuid import UUID

import pytest

from scripts import document_pipeline_acceptance as module
from scripts.document_pipeline_oracles import (
    chunk_checks,
    native_checks,
    structure_checks,
)
from src.application.services.document_chunks import (
    ChunkSource,
    build_chunks,
    text_unit,
)
from src.application.services.file_storage_policy import StoragePolicyError

logger = logging.getLogger(__name__)
SOURCE = ChunkSource(UUID(int=1), UUID(int=2), UUID(int=3), "a" * 64, "test")


def baseline():
    """Build a correct split Unicode projection plus an independent empty reference field."""
    text = "Việt e\u0301 \U0001f600\n" * 40
    fields = {("source#text", "text"): text, ("source#empty", "text"): ""}
    units = [text_unit(key[0], value) for key, value in fields.items()]
    return build_chunks(SOURCE, units, 256), fields


def test_independent_coverage_accepts_exact_unicode_and_empty():
    """Verify perfect nonoverlapping code-point coverage on known source fields."""
    payload, fields = baseline()
    checks, metrics = chunk_checks(payload, fields, SOURCE, 256)
    assert all(checks.values())
    assert metrics["source_fields"] == metrics["covered_fields"] == 2
    assert metrics["coverage_ratio"] == 1 and metrics["empty_sources"] == 1
    logger.info("pipeline_independent_coverage_oracle_verified")


@pytest.mark.parametrize(
    "mutation,target",
    [
        ("drop", "span_coverage"),
        ("overlap", "span_coverage"),
        ("gap", "span_coverage"),
        ("unknown", "span_valid"),
        ("negative", "span_valid"),
        ("noninteger", "span_valid"),
        ("text", "text_projection"),
        ("misplaced", "text_projection"),
        ("empty_duplicate", "span_coverage"),
        ("false_empty", "span_valid"),
        ("owner", "access_labels"),
        ("digest", "identity_digest"),
        ("hash", "source_binding"),
        ("bytes", "byte_limits"),
    ],
)
def test_oracle_rejects_corrupted_coverage_identity_and_limits(mutation, target):
    """Mutate valid output and require the relevant independent scoring gate to fail."""
    payload, fields = baseline()
    chunk = payload["chunks"][0]
    if mutation == "drop":
        payload["chunks"].pop()
    elif mutation == "overlap":
        payload["chunks"].append(copy.deepcopy(chunk))
    elif mutation == "gap":
        chunk["spans"][0]["start"] = 1
    elif mutation == "unknown":
        chunk["spans"][0]["locator"] = "foreign#text"
    elif mutation == "negative":
        chunk["spans"][0]["start"] = -1
    elif mutation == "noninteger":
        chunk["spans"][0]["start"] = "0"
    elif mutation == "text":
        chunk["text"] = "wrong"
    elif mutation == "misplaced":
        chunk["locator"] = "wrong#page=2"
    elif mutation == "empty_duplicate":
        payload["empty_sources"].append(copy.deepcopy(payload["empty_sources"][0]))
    elif mutation == "false_empty":
        payload["empty_sources"][0]["locator"] = "source#text"
    elif mutation == "owner":
        payload["access"]["principal_id"] = str(UUID(int=99))
    elif mutation == "digest":
        chunk["id"] = "chk_" + "0" * 64
    elif mutation == "hash":
        payload["sha256"] = "0" * 64
    else:
        chunk["text"] = "a" * 257
    checks, _ = chunk_checks(payload, fields, SOURCE, 256)
    assert checks[target] is False


def test_native_oracle_uses_handwritten_expected_text():
    """Reject a parser projection that is internally consistent but disagrees with source ground truth."""
    checks = native_checks(
        "pdf", [dict(page_number=1, text="incorrect")], dict(texts=["known expected"])
    )
    assert checks["exact_text"] is False


def test_row_structure_oracle_detects_changed_formula_and_quality():
    """Refuse stale-cache laundering and mutated row content even when spans still cover the source."""
    view = dict(
        formula_cache_status="preserved_not_recalculated",
        sheets=[
            dict(
                sheet_id=1,
                name="Sheet",
                merged_ranges=[],
                cells=[dict(cell="A1", value=None, formula="1+1", cached_value="2")],
            )
        ],
    )
    chunk = dict(
        kind="rows",
        locator="file:x#sheet=1&row=1",
        structure=dict(
            sheet_id=1,
            sheet_name="Sheet",
            merged_ranges=[],
            rows=[
                dict(
                    row=1,
                    cells=[
                        dict(cell="A1", value=None, formula="1+2", cached_value="2")
                    ],
                )
            ],
        ),
        quality=dict(formula_cache_status="fresh"),
    )
    checks = structure_checks("xlsx", view, dict(chunks=[chunk]), "file:x")
    assert checks == dict(row_structure=False, cache_flag_propagation=False)


def test_ocr_metric_separates_quality_failure_from_uncertainty_gate():
    """Keep incorrect transcription visible even if its required uncertainty flag passes."""
    view = dict(
        text="",
        review_required=True,
        confidence_score=None,
        method="tesseract",
        engine="test",
    )
    checks, metrics = module.ocr_checks(
        view, dict(texts=["uncertain 7381"], outcome="degraded"), "auto"
    )
    assert checks["uncertainty_detection"] and metrics["transcription_passed"] is False
    assert metrics["character_error_rate"] == metrics["word_error_rate"] == 1


@pytest.mark.asyncio
async def test_vision_is_explicit_and_unrun_case_is_not_pass(monkeypatch):
    """Do not call any model or mark the required vision case complete without explicit opt-in."""
    case = next(c for c in module.load_manifest()["cases"] if c["id"] == "vision-table")

    async def forbidden(image):
        """Fail if default evaluation discloses any image to a model."""
        pytest.fail("implicit model call")

    monkeypatch.setattr(module, "transcribe_image", forbidden)
    result = await module.evaluate_case(case)
    assert result["outcome"] == "not_run" and result["passed"] is False
    assert result["stages"] == []
    assert result["error"]["code"] == "explicit_vlm_not_requested"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure", ["unexpected_exception", "wrong_stage", "wrong_status"]
)
async def test_failure_report_is_sanitized_and_rejection_matches_exact_contract(
    monkeypatch, failure
):
    """Never hide unexpected failures as expected rejections or retain private exception messages."""
    case = next(c for c in module.load_manifest()["cases"] if c["id"] == "nested-table")

    def broken(*args, **kwargs):
        """Inject a controlled failure at verification to test stage/status provenance."""
        if failure == "unexpected_exception":
            raise ValueError("sensitive source and credential marker")
        raise StoragePolicyError(
            "unsupported_chunk_structure", 503 if failure == "wrong_status" else 422
        )

    monkeypatch.setattr(module, "run_source", broken)
    result = await module.evaluate_case(case)
    assert not result["passed"] and result["error"]["stage"] == "verify"
    assert "sensitive source" not in json.dumps(result)
    assert result["stages"][0]["stage"] == "verify"


def test_parser_source_descriptor_is_read_only():
    """Ensure the evaluation harness lends the same read-only FD access mode as production readers."""
    import os

    def inspect(source):
        """Attempt a forbidden write while checking exact input remains readable."""
        assert source.read() == b"synthetic"
        with pytest.raises(OSError):
            os.write(source.fileno(), b"x")
        return True

    assert module.run_source(b"synthetic", inspect)


def test_manifest_refuses_fixture_escape(monkeypatch, tmp_path):
    """Keep the evaluation CLI scoped to the trusted repository fixture corpus."""
    path = tmp_path / "manifest.json"
    path.write_text(
        json.dumps(
            dict(
                version="mixed-documents-v1",
                cases=[dict(id="escape", kind="text", fixture="../../pyproject.toml")],
            )
        )
    )
    monkeypatch.setattr(module, "MANIFEST", path)
    with pytest.raises(ValueError, match="Invalid synthetic case"):
        module.load_manifest()


@pytest.mark.parametrize(
    "passed,complete,expected_exit",
    [(True, True, 0), (True, False, 1), (False, True, 1)],
)
def test_cli_exit_requires_complete_and_passed(
    monkeypatch, tmp_path, passed, complete, expected_exit
):
    """Refuse success for incomplete evaluations and preserve explicit vision opt-in in CLI dispatch."""
    import sys

    async def measured(*, include_vlm):
        """Supply controlled gate results while requiring the parsed explicit model flag."""
        assert include_vlm
        return dict(passed=passed, complete=complete, cases=[])

    monkeypatch.setattr(module, "measure_pipeline", measured)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "document_pipeline_acceptance",
            "--include-vlm",
            "--output",
            str(tmp_path / "cli.json"),
        ],
    )
    assert module.main() == expected_exit
    assert json.loads((tmp_path / "cli.json").read_text())["complete"] is complete


@pytest.mark.asyncio
async def test_corpus_continues_after_one_unexpected_stage_failure(monkeypatch):
    """Keep subsequent case evidence and place the failed stage in the aggregate error report."""
    original = module.run_source

    def fail_one(data, function, *args, **kwargs):
        """Break only plain Markdown verification while preserving actual remaining parser execution."""
        if data.startswith(b"# Purpose:"):
            raise RuntimeError("private exception marker")
        return original(data, function, *args, **kwargs)

    monkeypatch.setattr(module, "run_source", fail_one)
    report = await module.measure_pipeline()
    assert not report["passed"] and not report["complete"]
    assert len(report["cases"]) == 18
    assert {failure["case"] for failure in report["failures"]} == {
        "notes",
        "vision-table",
    }
    assert report["cases"][-1]["passed"]
    assert "private exception marker" not in json.dumps(report)


def test_identity_oracle_detects_omitted_namespace_in_production(monkeypatch):
    """Catch a production identity assembly defect using independently assembled private fields."""

    def incomplete(source):
        """Simulate a source identity bug that could allow cross-namespace ID reuse."""
        return dict(owner=str(source.owner_id), file=str(source.file_id))

    monkeypatch.setattr(ChunkSource, "identity", incomplete)
    payload, fields = baseline()
    checks, _ = chunk_checks(payload, fields, SOURCE, 256)
    assert checks["identity_digest"] is False and checks["access_labels"] is False


def test_pdf_oracle_detects_shifted_page_numbers():
    """Reject correct text attached to the wrong actual page number."""
    checks = native_checks(
        "pdf", [dict(page_number=7, text="known")], dict(texts=["known"])
    )
    assert checks["exact_text"] and checks["page_mapping"] is False
