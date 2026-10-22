"""Compute complete authored OCR text/grid/discrepancy metrics and label absence checks without certifying semantic quality."""

import logging
import re
import unicodedata
from collections import Counter

logger = logging.getLogger(__name__)


def canonical_text(value):
    """Normalize complete NFC/whitespace while preserving all content, punctuation, case and diacritics."""
    if type(value) is not str:
        raise ValueError("invalid_quality_text")
    return " ".join(unicodedata.normalize("NFC", value).split())


def edit_distance(expected, actual):
    """Count exact full sequence Levenshtein edits without truncation or dropping inconvenient tokens."""
    if len(expected) * len(actual) > 4_000_000:
        raise ValueError("metric_work_bound")
    previous = list(range(len(actual) + 1))
    for number, left in enumerate(expected, 1):
        current = [number]
        for index, right in enumerate(actual, 1):
            current.append(
                min(
                    current[-1] + 1,
                    previous[index] + 1,
                    previous[index - 1] + (left != right),
                )
            )
        previous = current
    return previous[-1]


def text_metrics(expected, actual):
    """Expose uncalibrated edit rates and whole-token disagreement, including insertion-heavy blank output."""
    expected, actual = canonical_text(expected), canonical_text(actual)
    wanted, observed = expected.split(), actual.split()
    additions = list((Counter(observed) - Counter(wanted)).elements())
    result = dict(
        character_edits=edit_distance(expected, actual),
        word_edits=edit_distance(wanted, observed),
        reference_characters=len(expected),
        reference_words=len(wanted),
        observed_characters=len(actual),
        observed_words=len(observed),
        unexpected_token_count=len(additions),
        text_exact=expected == actual,
    )
    result.update(
        character_error_rate=result["character_edits"] / max(1, len(expected)),
        word_error_rate=result["word_edits"] / max(1, len(wanted)),
        groundtruth_token_disagreement=bool(additions),
        semantic_hallucination_certified=False,
    )
    logger.info("ocr_quality_text_metrics_computed exact=%s", result["text_exact"])
    return result


def flatten_rows(rows):
    """Keep every complete row/cell in original order without inferring a grid from native OCR text."""
    if type(rows) is not list or any(
        type(row) is not list or any(type(cell) is not str for cell in row)
        for row in rows
    ):
        raise ValueError("invalid_quality_grid")
    return " ".join(canonical_text(cell) for row in rows for cell in row)


def grid_metrics(expected, tables):
    """Compare exact full row/column order and missing/extra cells rather than counting matching values anywhere."""
    flatten_rows(expected)
    if type(tables) is not list or any(
        type(table) is not dict or set(table) != {"rows"} for table in tables
    ):
        raise ValueError("invalid_quality_grid")
    actual = [row for table in tables for row in table["rows"]]
    flatten_rows(actual)
    wanted = [[canonical_text(cell) for cell in row] for row in expected]
    observed = [[canonical_text(cell) for cell in row] for row in actual]
    matched = sum(
        index < len(observed)
        and column < len(observed[index])
        and observed[index][column] == cell
        for index, row in enumerate(wanted)
        for column, cell in enumerate(row)
    )
    count = sum(len(row) for row in wanted)
    result = dict(
        expected_cells=count,
        matched_cells=matched,
        cell_accuracy=matched / max(1, count),
        exact_grid=len(tables) == 1 and observed == wanted,
        actual_tables=len(tables),
        actual_rows=len(observed),
        actual_cells=sum(len(row) for row in observed),
    )
    logger.info("ocr_quality_grid_metrics_computed exact=%s", result["exact_grid"])
    return result


def score_observation(case, observation, mode):
    """Separate prose/table/known-blank/blur criteria and native structure limitations from raw metric delivery."""
    if mode not in {"native", "core"}:
        raise ValueError("invalid_quality_mode")
    expected = (
        flatten_rows(case["expected_rows"])
        if case["kind"] == "table"
        else case["expected_text"]
    )
    actual = observation["text"]
    grid = None
    if mode == "core" and case["kind"] == "table":
        grid = grid_metrics(case["expected_rows"], observation["tables"])
        actual = flatten_rows(
            [row for table in observation["tables"] for row in table["rows"]]
        )
    metrics = text_metrics(expected, actual)
    known_blank = case["criterion"] == "known_blank"
    uncertainties = observation.get(
        "uncertain_regions", observation.get("uncertainties", [])
    )
    review = True if mode == "core" else observation["review_required"]
    metrics.update(
        metric_basis="complete_table_cells" if grid is not None else "complete_text",
        grid=grid,
        native_grid_reconstruction_evaluated=False,
        known_blank_false_positive=known_blank and bool(canonical_text(actual)),
        review_required=review,
        uncertainty_signaled=review
        and (
            bool(uncertainties)
            or mode == "native"
            and (
                observation.get("confidence_score") is None
                or observation["confidence_score"] < 85
            )
        ),
        criterion=case["criterion"],
        uncalibrated_engine_score=observation.get("confidence_score")
        if mode == "native"
        else None,
        confidence_probability=None,
    )
    logger.info(
        "ocr_quality_observation_scored mode=%s criterion=%s", mode, case["criterion"]
    )
    return metrics


def absent_field_match(case, answer):
    """Apply the frozen absence-language/uncertainty check without treating it as independently verified semantic entailment."""
    text = canonical_text(answer.answer).casefold()
    return (
        any(pattern.casefold() in text for pattern in case["absence_patterns"])
        and (not case["requires_uncertainty"] or bool(answer.uncertainties))
        and re.search(r"\d", text) is None
    )
