"""Verify ASR text/edit/micro-aggregation semantics and refusal of fabricated coverage without executing any model."""

import pytest

from scripts.asr_evaluation_metrics import edit_distance, normalize, score


def case(identity="vi-1", reference="xin chào", kind="independent_public_speech"):
    """Build a small independent authored metric input with an explicit common audio duration."""
    return dict(
        id=identity,
        language="vi_vn",
        reference=reference,
        kind=kind,
        sample_count=32000,
    )


def prediction(identity="vi-1", text="xin chào"):
    """Supply an authored successful observation independently of the metric implementation."""
    return dict(id=identity, status="ok", text=text, wall_seconds=1.0)


def test_normalization_preserves_accents_numbers_and_nonpunctuation_symbols():
    """Keep semantic distinctions while applying exactly the declared Unicode normalization."""
    assert normalize("  XIN, CHA\u0300O!  12–34 + A ") == "xin chào 12 34 + a"
    assert normalize("một") != normalize("1")
    assert normalize("ma") != normalize("má")


@pytest.mark.parametrize(
    "ref,hyp,expected",
    [
        ("", "abc", 3),
        ("abc", "", 3),
        ("kitten", "sitting", 3),
        (["a", "b"], ["b", "a"], 2),
        ("đúng", "đúng", 0),
    ],
)
def test_exact_edits_match_known_insertion_deletion_substitution_cases(
    ref, hyp, expected
):
    """Establish edit correctness independently from the normalization/aggregation code."""
    assert edit_distance(ref, hyp) == expected


def test_micro_rates_and_duration_are_not_average_of_case_rates_or_probabilities():
    """Accumulate integer edits/reference counts and preserve rates above one and measured RTF."""
    result = score(
        [case(), case("vi-2", "a")],
        [prediction(text="xin"), prediction("vi-2", "b c d e")],
    )
    aggregate = result["languages"]["vi_vn"]
    assert result["coverage_complete"] and aggregate["word_edits"] == 5
    assert aggregate["reference_words"] == 3 and aggregate["WER"] == 5 / 3
    assert result["cases"][0]["real_time_factor"] == 0.5


def test_controls_report_false_positives_without_zero_denominator_wer():
    """Count normalized nonempty output on known silence separately from speech accuracy."""
    result = score([case("c", "", "authored_no_speech")], [prediction("c", "hello")])
    assert result["no_speech_false_positives"] == 1 and not result["languages"]
    assert "word_edits" not in result["cases"][0]


@pytest.mark.parametrize("observations", [[], [dict(id="vi-1", status="error")]])
def test_failed_or_missing_case_is_not_zero_filled_or_reported_complete(observations):
    """Preserve incomplete coverage without inventing a correct empty transcript or a winner."""
    result = score([case()], observations)
    assert (
        not result["coverage_complete"]
        and not result["languages"]
        and result["selection"] is None
    )


@pytest.mark.parametrize(
    "fault", ["duplicate", "unknown", "nan", "zero", "oversize", "status"]
)
def test_ambiguous_identity_unbounded_text_and_invalid_timing_refuse(fault):
    """Reject corrupt records instead of turning malformed outputs into favorable measured samples."""
    rows = [prediction()]
    if fault == "duplicate":
        rows *= 2
    elif fault == "unknown":
        rows[0]["id"] = "other"
    elif fault == "nan":
        rows[0]["wall_seconds"] = float("nan")
    elif fault == "zero":
        rows[0]["wall_seconds"] = 0
    elif fault == "oversize":
        rows[0]["text"] = "a" * 8193
    elif fault == "status":
        rows[0]["status"] = "skipped"
    with pytest.raises(ValueError):
        score([case()], rows)
