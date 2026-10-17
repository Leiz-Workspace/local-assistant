
"""
Local Assistant - Runtime Presets & Context Budget Manager.

Five user-facing presets:
    auto       : route to fast / balanced / deep
    fast       : thinking OFF, max output 4096
    balanced   : thinking ON, budget 4096, max output 8192
    deep       : thinking ON, budget 8192, max output 16384
    unlimited  : thinking ON, budget -1, output = remaining context

Auto is a routing policy, not a separate inference mode.
It cannot select Unlimited.

This module contains no HTTP or Docker operations.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any
import re


CONTEXT_SIZE = 32768
CONTEXT_RESERVE = 256
ANSWER_RESERVE = 512


class PresetError(ValueError):
    """Invalid preset or insufficient context budget."""


class RuntimePreset(str, Enum):
    AUTO = "auto"
    FAST = "fast"
    BALANCED = "balanced"
    DEEP = "deep"
    UNLIMITED = "unlimited"


@dataclass(frozen=True)
class PresetConfig:
    name: RuntimePreset
    thinking: bool
    reasoning_budget: int | None
    max_output: int | None


PRESETS = {
    RuntimePreset.FAST: PresetConfig(
        RuntimePreset.FAST, False, None, 4096
    ),
    RuntimePreset.BALANCED: PresetConfig(
        RuntimePreset.BALANCED, True, 4096, 8192
    ),
    RuntimePreset.DEEP: PresetConfig(
        RuntimePreset.DEEP, True, 8192, 16384
    ),
    RuntimePreset.UNLIMITED: PresetConfig(
        RuntimePreset.UNLIMITED, True, -1, None
    ),
}


@dataclass(frozen=True)
class TokenPlan:
    preset: RuntimePreset
    input_tokens: int
    max_tokens: int
    thinking: bool
    reasoning_budget: int | None
    context_size: int


@dataclass(frozen=True)
class AutoDecision:
    preset: RuntimePreset
    source: str


def get_preset(
    name: RuntimePreset | str,
) -> PresetConfig:
    """Resolve a concrete preset, never Auto."""

    try:
        selected = RuntimePreset(name)
    except ValueError as exc:
        raise PresetError(
            f"Unknown runtime preset: {name}"
        ) from exc

    if selected == RuntimePreset.AUTO:
        raise PresetError(
            "Auto must be resolved before token budgeting"
        )

    return PRESETS[selected]


def classify_simple_request(
    messages: list[dict[str, Any]],
) -> AutoDecision | None:
    """
    Fast-path only for standalone, unambiguous greetings.

    Do not use substring keywords such as:
        'code', 'math', 'explain', 'analyze'.

    Only one user message and no prior context qualifies.
    """

    if len(messages) != 1:
        return None

    message = messages[0]

    if message.get("role") != "user":
        return None

    content = message.get("content")

    if not isinstance(content, str):
        return None

    normalized = re.sub(
        r"[!.?。！？\s]+$",
        "",
        content.strip().lower(),
    )

    greetings = {
        "hi",
        "hello",
        "hey",
        "xin chào",
        "chào",
        "chào bạn",
    }

    if normalized in greetings:
        return AutoDecision(
            preset=RuntimePreset.FAST,
            source="simple_greeting_rule",
        )

    return None


def parse_classifier_output(
    content: str,
) -> RuntimePreset | None:
    """
    Accept only one exact label.

    No substring matching: 'deep explanation' is invalid.
    Malformed or ambiguous responses trigger fallback.
    """

    label = content.strip().lower()

    mapping = {
        "fast": RuntimePreset.FAST,
        "balanced": RuntimePreset.BALANCED,
        "deep": RuntimePreset.DEEP,
    }

    return mapping.get(label)


def calculate_budget(
    *,
    preset: RuntimePreset | str,
    input_tokens: int,
    requested_max_tokens: int | None = None,
    context_size: int = CONTEXT_SIZE,
    reserve: int = CONTEXT_RESERVE,
    answer_reserve: int = ANSWER_RESERVE,
) -> TokenPlan:
    """
    Calculate safe output capacity.

    input_tokens must be counted with llama.cpp tokenizer.

    For finite reasoning budgets, require room for:
        hard reasoning budget + minimum answer reserve.

    This reserves capacity mathematically; it does not
    guarantee reasoning correctness or answer length.
    """

    config = get_preset(preset)

    if input_tokens < 0:
        raise PresetError("input_tokens cannot be negative")

    if context_size <= 0 or reserve < 0:
        raise PresetError("Invalid context configuration")

    if answer_reserve <= 0:
        raise PresetError("Invalid answer reserve")

    if (
        requested_max_tokens is not None
        and requested_max_tokens <= 0
    ):
        raise PresetError(
            "max_tokens must be greater than zero"
        )

    available = (
        context_size - input_tokens - reserve
    )

    if available < answer_reserve:
        raise PresetError(
            "Insufficient context for a final answer. "
            f"Available output tokens: {max(0, available)}"
        )

    ceiling = (
        config.max_output
        if config.max_output is not None
        else available
    )

    max_tokens = min(available, ceiling)

    if requested_max_tokens is not None:
        max_tokens = min(
            max_tokens,
            requested_max_tokens,
        )

    if max_tokens < answer_reserve:
        raise PresetError(
            "Requested output limit is smaller than "
            "the minimum answer reserve"
        )

    if (
        config.thinking
        and config.reasoning_budget is not None
        and config.reasoning_budget >= 0
    ):
        minimum_required = (
            config.reasoning_budget + answer_reserve
        )

        if max_tokens < minimum_required:
            raise PresetError(
                f"Preset {config.name.value} needs at least "
                f"{minimum_required} output tokens; "
                f"only {max_tokens} available. "
                "Shorten history or select a lower preset."
            )

    return TokenPlan(
        preset=config.name,
        input_tokens=input_tokens,
        max_tokens=max_tokens,
        thinking=config.thinking,
        reasoning_budget=config.reasoning_budget,
        context_size=context_size,
    )


def build_generation_params(
    plan: TokenPlan,
) -> dict[str, Any]:
    """
    Build request-level llama.cpp parameters.

    thinking_budget_tokens is backend-specific.
    Verify that the installed build honors it.
    """

    params: dict[str, Any] = {
        "max_tokens": plan.max_tokens,
        "chat_template_kwargs": {
            "enable_thinking": plan.thinking,
        },
    }

    if plan.thinking:
        params["thinking_budget_tokens"] = (
            plan.reasoning_budget
        )

    return params


def classify_completion(
    response: dict[str, Any],
) -> str:
    """Classify non-streaming, text-only completions."""

    choices = response.get("choices")

    if not isinstance(choices, list) or not choices:
        return "ERROR"

    choice = choices[0]

    if not isinstance(choice, dict):
        return "ERROR"

    finish_reason = choice.get("finish_reason")

    if finish_reason == "length":
        return "INCOMPLETE"

    if finish_reason != "stop":
        return "UNVERIFIED"

    message = choice.get("message")

    if not isinstance(message, dict):
        return "ERROR"

    content = message.get("content")

    if isinstance(content, str) and content.strip():
        return "PASS"

    return "INCOMPLETE"
