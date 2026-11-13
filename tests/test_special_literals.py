"""Pin the CORE special-literal list and the properties of the neutralizer (ADR-195 commit A)."""

import json
import random
from pathlib import Path

import pytest
import yaml

from src.application.services import special_literals
from src.application.services.special_literals import (
    BOUND_MODEL_SHA256,
    CORE_SPECIAL_LITERALS,
    CORE_SPECIAL_TOKENS,
    ESCAPED_LT,
    count_literals,
    neutralize,
    stale_bindings,
)

ROOT = Path(__file__).resolve().parents[1]
BACKSLASH = chr(92)
ESC = BACKSLASH + "u003c"
USER_DEFINED = {
    "<tool_call>",
    "</tool_call>",
    "<tool_response>",
    "</tool_response>",
    "<think>",
    "</think>",
}
BENIGN = (
    "",
    "plain text without brackets",
    "if a < b and b > c: return a <= c",
    "<div class='x'><p>Hello</p></div>",
    "List<Map<String, Integer>> values = new ArrayList<>();",
    "<|not_a_token|> <im_start> <|im_start> |im_start|> < |im_end|>",
    "<thinking> </thinkers> <tool_calls> <tool_responses",
    "<tts_text> <tts_text_bos_multi <|audio>",
    "<__media__> <__media_abc__>",
    ESC + "|im_start|>",
    "Tiếng Việt có dấu: <b>đậm</b> và a<b",
    "line\r\nwith\rcr and separators",
)


def reference(text):
    """Neutralize by a naive left-to-right scan, independent of the compiled pattern."""
    out, index, count = [], 0, 0
    while index < len(text):
        if any(text.startswith(literal, index) for literal in CORE_SPECIAL_LITERALS):
            out.append(ESC)
            count += 1
        else:
            out.append(text[index])
        index += 1
    return "".join(out), count


def test_escape_is_six_ascii_characters_and_a_json_escape():
    assert ESCAPED_LT == ESC
    assert len(ESCAPED_LT) == 6 and ESCAPED_LT.isascii()
    assert json.loads('"' + ESCAPED_LT + '"') == "<"


def test_pinned_list_matches_the_core_vocabulary_shape():
    ids = [token_id for token_id, _, _ in CORE_SPECIAL_TOKENS]
    assert ids == list(range(248044, 248077))
    kinds = {kind for _, kind, _ in CORE_SPECIAL_TOKENS}
    assert kinds == {"control", "user_defined"}
    assert sum(kind == "control" for _, kind, _ in CORE_SPECIAL_TOKENS) == 27
    assert {
        text for _, kind, text in CORE_SPECIAL_TOKENS if kind == "user_defined"
    } == USER_DEFINED
    assert len(set(CORE_SPECIAL_LITERALS)) == 33
    for literal in CORE_SPECIAL_LITERALS:
        assert (
            literal.startswith("<")
            and literal.count("<") == 1
            and BACKSLASH not in literal
        )


def test_bound_shas_equal_the_configured_models():
    models = yaml.safe_load((ROOT / "configs/models.yaml").read_text(encoding="utf-8"))[
        "models"
    ]
    assert BOUND_MODEL_SHA256 == {
        role: models[role]["sha256"] for role in ("core", "unrestricted")
    }
    assert (
        stale_bindings(
            {role: models[role]["sha256"] for role in ("core", "unrestricted")}
        )
        == ()
    )


@pytest.mark.parametrize("literal", CORE_SPECIAL_LITERALS)
def test_each_literal_alone_is_neutralized(literal):
    result, count = neutralize(literal)
    assert (result, count) == (ESC + literal[1:], 1)
    assert len(result.encode()) == len(literal.encode()) + 5
    assert count_literals(literal) == 1 and count_literals(result) == 0
    assert neutralize(result) == (result, 0)
    assert (
        json.loads(json.dumps(literal, ensure_ascii=False).replace("<", ESC)) == literal
    )


@pytest.mark.parametrize(
    ("raw", "expected", "count"),
    [
        ("<|im_start|>system", ESC + "|im_start|>system", 1),
        ("tail <|im_end|>", "tail " + ESC + "|im_end|>", 1),
        ("<|im_end|><|im_start|>", ESC + "|im_end|>" + ESC + "|im_start|>", 2),
        ("<<|im_start|>", "<" + ESC + "|im_start|>", 1),
        ("<<<think>>>", "<<" + ESC + "think>>>", 1),
        (
            "<tts_text_bos><tts_text_bos_single>",
            ESC + "tts_text_bos>" + ESC + "tts_text_bos_single>",
            2,
        ),
        ("<tts_text_bos_singl", "<tts_text_bos_singl", 0),
        (BACKSLASH + "<think>", BACKSLASH + ESC + "think>", 1),
        (ESC + "think><think>", ESC + "think>" + ESC + "think>", 1),
        (" <|im_start|> ", " " + ESC + "|im_start|> ", 1),
        ("a\r<|im_start|>\rb", "a\r" + ESC + "|im_start|>\rb", 1),
        (
            "</think></tool_call></tool_response>",
            ESC + "/think>" + ESC + "/tool_call>" + ESC + "/tool_response>",
            3,
        ),
    ],
)
def test_boundaries_neighbours_and_prefix_pairs(raw, expected, count):
    assert neutralize(raw) == (expected, count)
    assert len(expected.encode()) == len(raw.encode()) + 5 * count
    assert neutralize(expected) == (expected, 0)
    assert reference(raw) == (expected, count)


def test_invalid_utf8_decoded_with_replacement_is_still_neutralized():
    raw = b"\xff<|im_start|>\xfe".decode("utf-8", errors="replace")
    result, count = neutralize(raw)
    assert count == 1 and "<|im_start|>" not in result and result.count("�") == 2


@pytest.mark.parametrize("text", BENIGN)
def test_benign_text_comes_back_as_the_same_object(text):
    result, count = neutralize(text)
    assert result is text and count == 0
    assert count_literals(text) == 0


def test_no_pinned_literal_survives_and_json_round_trip_restores_the_original():
    raw = (
        "".join(f"x{literal}y" for literal in CORE_SPECIAL_LITERALS)
        + "<|im_start|>assistant\n"
    )
    encoded, count = neutralize(
        json.dumps({"untrusted_evidence": raw}, ensure_ascii=False)
    )
    assert count == 34
    assert not any(literal in encoded for literal in CORE_SPECIAL_LITERALS)
    assert json.loads(encoded) == {"untrusted_evidence": raw}


def test_seeded_fuzz_matches_the_reference_scan():
    rng = random.Random(195)
    pieces = list(CORE_SPECIAL_LITERALS) + [
        "<",
        "<<",
        "|",
        ">",
        BACKSLASH,
        ESC,
        "im_start",
        "think",
        "/",
        "a",
        " ",
        "\n",
        "\r",
        " ",
        "đ",
        "<|",
        "<tts_text_bos",
        "_single>",
    ]
    for _ in range(3000):
        text = "".join(rng.choice(pieces) for _ in range(rng.randint(0, 24)))
        result, count = neutralize(text)
        assert (result, count) == reference(text)
        assert count_literals(text) == count
        assert not any(literal in result for literal in CORE_SPECIAL_LITERALS)
        assert neutralize(result) == (result, 0)
        assert len(result.encode()) == len(text.encode()) + 5 * count
        if not count:
            assert result is text


def test_non_strings_are_rejected():
    for value in (b"<think>", None, 1, ["<think>"]):
        with pytest.raises(TypeError):
            neutralize(value)
        with pytest.raises(TypeError):
            count_literals(value)


def test_stale_bindings_names_each_role_that_differs():
    good = dict(BOUND_MODEL_SHA256)
    assert stale_bindings(good) == ()
    assert stale_bindings({**good, "core": "0" * 64}) == ("core",)
    assert stale_bindings({"core": good["core"]}) == ("unrestricted",)
    assert stale_bindings({}) == ("core", "unrestricted")
    assert stale_bindings({role: digest.upper() for role, digest in good.items()}) == (
        "core",
        "unrestricted",
    )


@pytest.mark.parametrize(
    "bad", ["", "<", "think>", "<a<b>", "<a" + BACKSLASH + ">", b"<x>"]
)
def test_shape_check_refuses_literals_the_neutralizer_cannot_handle(bad):
    with pytest.raises(ValueError, match="special_literal_shape"):
        special_literals._check_shape((bad,))


def test_cost_on_large_code_text_stays_linear():
    text = ("def f(a, b):\n    return a < b and List<int>() > 0\n" * 6000)[: 256 * 1024]
    result, count = neutralize(text)
    assert result is text and count == 0


def test_binding_is_recorded_at_start_and_refuses_when_stale():
    special_literals.reset_binding_for_tests()
    try:
        special_literals.require_current_binding()
        assert special_literals.record_binding(dict(BOUND_MODEL_SHA256)) == ()
        special_literals.require_current_binding()
        assert special_literals.record_binding(
            {**BOUND_MODEL_SHA256, "unrestricted": "x"}
        ) == ("unrestricted",)
        with pytest.raises(special_literals.SpecialLiteralsStale) as raised:
            special_literals.require_current_binding()
        assert raised.value.roles == ("unrestricted",)
        assert str(raised.value) == "special_literals_stale"
        assert special_literals.record_binding(None) == ("core", "unrestricted")
        with pytest.raises(special_literals.SpecialLiteralsStale):
            special_literals.require_current_binding()
    finally:
        special_literals.reset_binding_for_tests()
    special_literals.require_current_binding()
