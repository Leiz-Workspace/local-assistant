"""Verify OCR metric work bounds, preserved language/content, grid alignment, blank inventions and uncertainty accounting."""

import logging
from types import SimpleNamespace

import pytest
from vision_quality_cases import (
    absent_field_match,
    canonical_text,
    edit_distance,
    grid_metrics,
    score_observation,
    text_metrics,
)


@pytest.mark.parametrize(
    "expected,actual,count",
    [
        ("abc", "abc", 0),
        ("abc", "axc", 1),
        ("", "abc", 3),
        (["a", "b"], ["b"], 1),
        ("a", "bcd", 3),
    ],
)
def test_exact_sequence_edit_oracles(expected, actual, count):
    """Check independent known edits so an implementation error cannot manufacture perfect quality rates."""
    assert edit_distance(expected, actual) == count


def test_normalization_preserves_case_diacritics_punctuation_and_whole_tail():
    """Permit NFC/whitespace equivalence while retaining content that a scorer must not silently discard."""
    assert canonical_text("  Tên\n hàng ") == "Tên hàng"
    assert text_metrics("Bút", "But")["character_error_rate"] > 0
    assert text_metrics("42 USD", "42 usd")["word_error_rate"] > 0
    assert not text_metrics("same", "same invented tail")["text_exact"]
    assert text_metrics("", "invented")["character_error_rate"] == 8
    assert text_metrics("", "invented")["word_error_rate"] == 1


def test_metric_bound_refuses_instead_of_truncating():
    """Reject unbounded quadratic scoring work without reporting a score from an accepted prefix."""
    with pytest.raises(ValueError, match="metric_work_bound"):
        edit_distance("a" * 2001, "b" * 2000)


@pytest.mark.parametrize(
    "rows,expected",
    [
        ([["A", "1"], ["B", "2"]], True),
        ([["A", "2"], ["B", "1"]], False),
        ([["B", "2"], ["A", "1"]], False),
        ([["A", "1"]], False),
        ([["A", "1"], ["B", "2"], ["extra"]], False),
    ],
)
def test_grid_alignment_and_complete_extra_rows_remain_quality_errors(rows, expected):
    """Do not rescue swapped/missing/extra values by searching for matching cells anywhere in output."""
    assert (
        grid_metrics([["A", "1"], ["B", "2"]], [dict(rows=rows)])["exact_grid"]
        is expected
    )


def test_blank_invention_is_not_perfect_ocr_or_calibrated_confidence():
    """Flag nonempty transcription on authored blank input without certifying all token discrepancies as hallucinations."""
    case = dict(kind="prose", criterion="known_blank", expected_text="")
    value = score_observation(
        case, dict(text="A fabricated invoice", tables=[], uncertain_regions=[]), "core"
    )
    assert (
        value["known_blank_false_positive"] and value["groundtruth_token_disagreement"]
    )
    assert (
        value["confidence_probability"] is None
        and value["semantic_hallucination_certified"] is False
    )
    assert value["review_required"] and not value["uncertainty_signaled"]


def test_blurred_latent_reference_retains_error_and_review_instead_of_scoring_blank_success():
    """Keep the unreadable fixture's lost text visible in metrics while evaluating its uncertainty signal separately."""
    case = dict(
        kind="prose", criterion="uncertainty_detection", expected_text="uncertain 7381"
    )
    value = score_observation(
        case,
        dict(
            text="",
            review_required=True,
            confidence_score=None,
            uncertainties=["unreadable"],
        ),
        "native",
    )
    assert value["character_error_rate"] == value["word_error_rate"] == 1
    assert value["uncertainty_signaled"] and not value["known_blank_false_positive"]


def test_table_metrics_do_not_invent_native_cell_structure_or_drop_extra_model_tables():
    """Treat native flattened text as text only and keep duplicate model table content as a grid failure."""
    case = dict(kind="table", criterion="table_grid", expected_rows=[["A", "1"]])
    native = score_observation(
        case,
        dict(
            text="A 1",
            review_required=True,
            confidence_score=80,
            uncertainties=["no grid"],
        ),
        "native",
    )
    assert native["grid"] is None and native["text_exact"]
    core = score_observation(
        case,
        dict(
            text="ignored prose",
            tables=[dict(rows=[["A", "1"]]), dict(rows=[["A", "1"]])],
            uncertain_regions=[],
        ),
        "core",
    )
    assert (
        not core["grid"]["exact_grid"]
        and not core["text_exact"]
        and core["metric_basis"] == "complete_table_cells"
    )


@pytest.mark.parametrize(
    "answer,uncertainty,expected",
    [
        ("not available", ["field absent"], True),
        ("không có thông tin", ["thiếu giá"], True),
        ("not available", [], False),
        ("The price is 42", ["uncertain"], False),
        ("not available but maybe 42", ["uncertain"], False),
    ],
)
def test_missing_field_check_keeps_uncertainty_and_unsupported_numeric_guess_visible(
    answer, uncertainty, expected
):
    """Keep a narrow disclosed automated absence gate separate from broad semantic truth claims."""
    case = dict(
        absence_patterns=["not available", "không có"], requires_uncertainty=True
    )
    assert (
        absent_field_match(
            case, SimpleNamespace(answer=answer, uncertainties=uncertainty)
        )
        is expected
    )
    logging.getLogger(__name__).info("ocr_quality_metric_controls_verified")
