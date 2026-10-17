
"""
Tests for runtime presets and token budget.

These tests require no GPU or running Docker container.
They verify policy configuration, budgeting and payloads.
"""

import pytest

from apps.api.runtime.presets import (
    PresetError,
    build_generation_params,
    calculate_budget,
    classify_completion,
    get_preset,
)


def test_preset_definitions():
    fast = get_preset("fast")
    balanced = get_preset("balanced")
    deep = get_preset("deep")
    unlimited = get_preset("unlimited")

    assert fast.thinking is False
    assert fast.max_output == 4096

    assert balanced.thinking is True
    assert balanced.reasoning_budget == 4096
    assert balanced.max_output == 8192

    assert deep.thinking is True
    assert deep.reasoning_budget == 8192
    assert deep.max_output == 16384

    assert unlimited.thinking is True
    assert unlimited.reasoning_budget == -1
    assert unlimited.max_output is None


def test_invalid_preset():
    with pytest.raises(PresetError):
        get_preset("invalid")


@pytest.mark.parametrize(
    "preset,input_tokens,expected_output",
    [
        ("fast", 1000, 4096),
        ("balanced", 1000, 8192),
        ("deep", 1000, 16384),
        ("unlimited", 1000, 31512),
        ("fast", 30608, 1904),
    ],
)
def test_output_budget(
    preset,
    input_tokens,
    expected_output,
):
    plan = calculate_budget(
        preset=preset,
        input_tokens=input_tokens,
    )

    assert plan.max_tokens == expected_output


def test_balanced_requires_answer_reserve():
    with pytest.raises(PresetError):
        calculate_budget(
            preset="balanced",
            input_tokens=30000,
        )


def test_deep_requires_answer_reserve():
    with pytest.raises(PresetError):
        calculate_budget(
            preset="deep",
            input_tokens=30000,
        )


def test_custom_max_tokens():
    plan = calculate_budget(
        preset="fast",
        input_tokens=1000,
        requested_max_tokens=1024,
    )

    assert plan.max_tokens == 1024


def test_fast_disables_thinking():
    plan = calculate_budget(
        preset="fast",
        input_tokens=100,
    )

    params = build_generation_params(plan)

    assert params["max_tokens"] == 4096
    assert (
        params["chat_template_kwargs"]["enable_thinking"]
        is False
    )
    assert "thinking_budget_tokens" not in params


def test_balanced_reasoning_budget():
    plan = calculate_budget(
        preset="balanced",
        input_tokens=100,
    )

    params = build_generation_params(plan)

    assert params["max_tokens"] == 8192
    assert params["thinking_budget_tokens"] == 4096
    assert (
        params["chat_template_kwargs"]["enable_thinking"]
        is True
    )


def test_deep_reasoning_budget():
    plan = calculate_budget(
        preset="deep",
        input_tokens=100,
    )

    params = build_generation_params(plan)

    assert params["max_tokens"] == 16384
    assert params["thinking_budget_tokens"] == 8192


def test_unlimited_reasoning_budget():
    plan = calculate_budget(
        preset="unlimited",
        input_tokens=100,
    )

    params = build_generation_params(plan)

    assert params["thinking_budget_tokens"] == -1


@pytest.mark.parametrize(
    "finish_reason,content,expected",
    [
        ("stop", "Hello", "PASS"),
        ("length", "", "INCOMPLETE"),
        ("stop", "", "INCOMPLETE"),
        ("tool_calls", "", "UNVERIFIED"),
    ],
)
def test_completion_classification(
    finish_reason,
    content,
    expected,
):
    response = {
        "choices": [
            {
                "finish_reason": finish_reason,
                "message": {
                    "content": content,
                },
            }
        ]
    }

    assert classify_completion(response) == expected
