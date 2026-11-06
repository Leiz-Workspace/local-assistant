"""Select intact conversation turns and fit them to the existing tokenizer budget."""

import logging
from collections.abc import Awaitable, Callable

from apps.api.runtime.presets import PresetError, calculate_budget
from src.application.ports.inference import InferenceFailure

logger = logging.getLogger(__name__)
Message = dict[str, str]


def select_whole_turns(messages: list[Message], max_messages: int) -> list[Message]:
    """Retain system instructions, newest complete pairs and the current user message."""
    if not messages or messages[-1]["role"] != "user":
        raise InferenceFailure(
            "Context must end with the current user message.",
            code="invalid_context",
            status_code=422,
        )
    systems = [message for message in messages if message["role"] == "system"]
    history = [message for message in messages[:-1] if message["role"] != "system"]
    turns = []
    for index in range(len(history) - 1):
        if (
            history[index]["role"] == "user"
            and history[index + 1]["role"] == "assistant"
        ):
            turns.append(history[index : index + 2])
    keep = max(0, (max_messages - 1) // 2)
    selected = turns[-keep:] if keep else []
    result = (
        systems + [message for turn in selected for message in turn] + [messages[-1]]
    )
    logger.info(
        "conversation_context_selected messages=%d dropped=%d",
        len(result),
        len(messages) - len(result),
    )
    return result


async def fit_token_budget(
    messages: list[Message],
    *,
    preset: str,
    max_tokens: int | None,
    count_tokens: Callable[[list[Message]], Awaitable[int]],
) -> list[Message]:
    """Drop oldest complete pairs until template/tokenizer budgeting accepts the context."""
    try:
        calculate_budget(preset=preset, input_tokens=0, requested_max_tokens=max_tokens)
    except PresetError as error:
        raise InferenceFailure(
            "Requested output budget is invalid.",
            code="invalid_token_budget",
            status_code=422,
        ) from error
    systems = [message for message in messages if message["role"] == "system"]
    history = [message for message in messages if message["role"] != "system"]
    while True:
        candidate = systems + history
        tokens = await count_tokens(candidate)
        try:
            calculate_budget(
                preset=preset, input_tokens=tokens, requested_max_tokens=max_tokens
            )
            logger.info(
                "conversation_context_budgeted input_tokens=%d messages=%d",
                tokens,
                len(candidate),
            )
            return candidate
        except PresetError as error:
            if len(history) < 3:
                raise InferenceFailure(
                    "System instructions and current message exceed context capacity.",
                    code="context_overflow",
                    status_code=422,
                ) from error
            history = history[2:]
            logger.info("conversation_context_trimmed removed_messages=2")
