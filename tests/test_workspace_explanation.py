"""Verify bounded explanation contracts and strict independent native-line citation oracles without model inference."""

import json

import pytest

from src.application.services.workspace_explanation import (
    explanation_messages,
    explanation_options,
    resolve_explanation,
)
from src.application.services.workspace_policy import WorkspaceAccessError


@pytest.fixture
def line_units():
    """Provide independently authored Unicode line evidence and a raw-hash placeholder for parser-only tests."""
    return {
        "L7": dict(
            path="src/main.py",
            line_number=12,
            line_text='    return "chào 𝄞"',
            source_sha256="a" * 64,
        )
    }


def test_exact_unicode_quote_resolves_original_line(line_units):
    """Check path/hash/line and Unicode offsets independently of model-supplied metadata."""
    result = resolve_explanation(
        json.dumps(
            dict(
                status="answered",
                answer="A greeting.",
                citations=[dict(source_id="L7", quote="chào 𝄞")],
            )
        ),
        line_units,
    )
    assert result["citations"] == [
        dict(
            path="src/main.py",
            source_sha256="a" * 64,
            line_number=12,
            quote="chào 𝄞",
            column_start=12,
            column_end=18,
            column_unit="unicode_code_points",
        )
    ]


@pytest.mark.parametrize(
    "raw",
    [
        None,
        "not JSON",
        "[]",
        '{"status":"answered","answer":"a","citations":[],"command":"id"}',
        '{"status":"answered","answer":"a","citations":[{"source_id":"L9","quote":"x"}]}',
        '{"status":"answered","answer":"a","citations":[{"source_id":"L7","quote":"absent"}]}',
        '{"status":"answered","answer":"a","citations":[{"source_id":"L7","quote":"chào","path":"/etc/passwd"}]}',
        '{"status":"answered","answer":null,"citations":[]}',
        '{"status":"insufficient_evidence","answer":"guess","citations":[]}',
        '{"status":"insufficient_evidence","answer":null,"citations":[{}]}',
        '{"status":"answered","answer":"a","answer":"b","citations":[]}',
        '{"status":"answered","answer":"a","citations":[{"source_id":[],"quote":"a"}]}',
        '{"status":"answered","answer":"a","citations":[{"source_id":"L7","quote":" "}]}',
        '{"status":"answered","answer":NaN,"citations":[]}',
        "x" * 16385,
    ],
)
def test_invalid_generated_json_fails_closed(line_units, raw):
    """Reject malformed/unbounded output and invented citation authority without trusting generated locators."""
    with pytest.raises(WorkspaceAccessError, match="explanation_answer_invalid"):
        resolve_explanation(raw, line_units)


def test_absent_and_duplicate_or_ambiguous_citations(line_units):
    """Accept explicit abstention and reject duplicate or nonunique exact quotes."""
    result = resolve_explanation(
        '{"status":"insufficient_evidence","answer":null,"citations":[]}', line_units
    )
    assert result["answer"] is None and not result["citations"]
    citation = dict(source_id="L7", quote="chào")
    with pytest.raises(WorkspaceAccessError):
        resolve_explanation(
            json.dumps(
                dict(status="answered", answer="a", citations=[citation, citation])
            ),
            line_units,
        )
    line_units["L7"]["line_text"] = "chào chào"
    with pytest.raises(WorkspaceAccessError):
        resolve_explanation(
            json.dumps(dict(status="answered", answer="a", citations=[citation])),
            line_units,
        )


@pytest.mark.parametrize(
    "question,sources",
    [
        (" ", [dict(path="a")]),
        ("á" * 2049, [dict(path="a")]),
        ("\ud800", [dict(path="a")]),
        ("q", []),
        ("q", [dict(path="a")] * 4),
        ("q", [dict(path="a"), dict(path="a")]),
        ("q", [dict(path="../a")]),
        ("q", [dict(path=".env")]),
        ("q", [dict(path="a", owner="x")]),
        ("q", [dict(path="a", start_line=True)]),
        ("q", [dict(path="a", end_line=201)]),
    ],
)
def test_invalid_source_selection_and_question(question, sources):
    """Reject invalid question bytes and source selection before native access or model work."""
    with pytest.raises(WorkspaceAccessError):
        explanation_options(question, sources)


def test_prompt_preserves_untrusted_source_and_enforces_bytes(line_units):
    """Keep exact source data and server evidence IDs while refusing prompt overflow without truncation."""
    line = line_units["L7"]
    messages, units = explanation_messages("Explain", [line])
    payload = json.loads(messages[1]["content"])
    assert payload["sources"][0]["text"] == line["line_text"]
    assert units["L1"] == line and "untrusted" in messages[0]["content"]
    assert explanation_options("q", [dict(path="src/main.py")])[0]["end_line"] == 200
    with pytest.raises(WorkspaceAccessError, match="explanation_prompt_limit"):
        explanation_messages("q", [dict(line, line_text="á" * 20000)])
