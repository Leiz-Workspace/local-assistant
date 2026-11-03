"""Verify exact speech-only reading conventions and preservation of code, identifiers and unsupported formats."""

import hashlib
from dataclasses import FrozenInstanceError

import pytest

from benchmarks.scripts.vi_speech_text import number, render_speech


@pytest.mark.parametrize(
    "value,expected",
    [
        (0, "không"),
        (5, "năm"),
        (15, "mười lăm"),
        (21, "hai mươi mốt"),
        (24, "hai mươi bốn"),
        (105, "một trăm lẻ năm"),
        (2000, "hai nghìn"),
        (2005, "hai nghìn không trăm lẻ năm"),
        (2026, "hai nghìn không trăm hai mươi sáu"),
        (9999, "chín nghìn chín trăm chín mươi chín"),
    ],
)
def test_explicit_number_conventions(value, expected):
    """Freeze authored research reading conventions without claiming independent phonetic correctness."""
    assert number(value) == expected


@pytest.mark.parametrize("value", [-1, 10000, True, 1.0, "15"])
def test_invalid_number(value):
    """Reject out-of-range and implicitly coerced number values."""
    with pytest.raises(ValueError):
        number(value)


@pytest.mark.parametrize(
    "source,expected",
    [
        (
            "Hẹn lúc 09:15 ngày 14/11.",
            "Hẹn lúc chín giờ mười lăm phút ngày mười bốn tháng mười một.",
        ),
        (
            "Nhắc lúc 00:05 ngày 29/02/2028.",
            "Nhắc lúc không giờ năm phút ngày hai mươi chín tháng hai năm hai nghìn không trăm hai mươi tám.",
        ),
        ("Từ 09:00 đến 21:30.", "Từ chín giờ đến hai mươi mốt giờ ba mươi phút."),
        (
            "Ngày 31/12/2026.",
            "Ngày ba mươi mốt tháng mười hai năm hai nghìn không trăm hai mươi sáu.",
        ),
        ("Học Python và dùng API.", "Học pai thờn và dùng ây pi ai."),
    ],
)
def test_speech_reading_is_separate_and_traced(source, expected):
    """Preserve the displayed answer and bind each edit to its original character range."""
    result = render_speech(source)
    assert result.source_text == source and result.speech_text == expected
    assert result.source_sha256 == hashlib.sha256(source.encode()).hexdigest()
    assert result.speech_sha256 == hashlib.sha256(expected.encode()).hexdigest()
    assert result.render_seconds >= 0
    for edit in result.edits:
        assert source[edit.start : edit.end] == edit.original
    with pytest.raises(FrozenInstanceError):
        result.speech_text = "changed"


@pytest.mark.parametrize(
    "source",
    [
        "Mã 09:15 và 14/11 chưa có ngữ cảnh.",
        "Hẹn lúc 25:15 ngày 31/02/2026.",
        "Hẹn lúc 09:60 ngày 29/02/2027.",
        "Hẹn lúc 09:15:30 ngày 14/11/20265.",
        "Lúc 09:15h, ngày 00/12 hoặc ngày 14/00.",
        "Pythonic Python3 APIv2 APIs API_KEY API-key foo.API",
        "`Python API lúc 09:15 ngày 14/11`",
        "```python\nPython API lúc 09:15 ngày 14/11\n```",
        "```Python API ngày 14/11",
        "https://example.org/API/Python?day=14/11;time=09:15",
        "[API](https://example.org/Python)",
        "/home/API/Python.py ./Python/API ../Python/API C:\\Python\\API",
        "API@example.org Python.json v2.14.11",
        '{"API":"Python", "ngày 14/11":"lúc 09:15"}',
        "Bạn đồng ý chứ?",
    ],
)
def test_unsupported_or_protected_spans_are_unchanged(source):
    """Avoid guessing ambiguous dates or rewriting code, links, paths, partial tokens and questions."""
    assert render_speech(source).speech_text == source


def test_context_outside_protected_span_still_changes():
    """Protect only the literal region while rendering a distinct natural-language occurrence."""
    source = "Dùng API, giữ `API` và https://example.org/API."
    result = render_speech(source)
    assert result.speech_text == "Dùng ây pi ai, giữ `API` và https://example.org/API."


def test_clause_variant_is_explicit_and_preserves_protected_punctuation():
    """Keep clause-boundary experimentation separate from the reading-only baseline."""
    source = "Python đã sẵn sàng; hãy kiểm tra API. Giữ `API;`."
    assert "; hãy" in render_speech(source, "reading").speech_text
    result = render_speech(source, "clauses")
    assert ". hãy" in result.speech_text and "`API;`" in result.speech_text
    assert result.source_text == source
    assert render_speech(source, "raw").speech_text == source
    assert not render_speech(source, "raw").edits


@pytest.mark.parametrize(
    "source,policy",
    [
        ("", "reading"),
        ("x" * 2049, "reading"),
        ("hello\x00", "reading"),
        (None, "reading"),
        ("Hello", "unknown"),
    ],
)
def test_text_policy_bounds(source, policy):
    """Reject invalid text and unreviewed policies before producing speech text."""
    with pytest.raises(ValueError):
        render_speech(source, policy)


def test_reading_is_idempotent_and_multiword_text_is_unmodified():
    """Prevent repeated normalization from expanding the same terms or altering unaffected words."""
    first = render_speech("Hẹn lúc 09:15 ngày 14/11; học Python và dùng API.")
    assert render_speech(first.speech_text).speech_text == first.speech_text
    assert (
        render_speech("Chị sẽ nhắc bạn vào sáng mai.").speech_text
        == "Chị sẽ nhắc bạn vào sáng mai."
    )
