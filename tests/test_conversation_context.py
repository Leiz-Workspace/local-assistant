"""Test intact turn selection and exact token-budget context fitting."""

import logging

import pytest

from src.application.ports.inference import InferenceFailure
from src.application.services.conversation_context import (
    fit_token_budget,
    select_whole_turns,
)

logger = logging.getLogger(__name__)


def message(role, content):
    """Build one text-only context message for deterministic assertions."""
    return {"role": role, "content": content}


def test_selection_preserves_system_and_complete_turns():
    """Discard failed user turns and dangling assistants while preserving newest pairs."""
    system = message("system", "Keep this instruction")
    current = message("user", "Current")
    history = [
        system,
        message("assistant", "dangling"),
        message("user", "failed"),
        message("user", "old"),
        message("assistant", "old reply"),
        message("user", "new"),
        message("assistant", "new reply"),
        current,
    ]
    assert select_whole_turns(history, 4) == [system, *history[-3:]]
    assert select_whole_turns(history, 1) == [system, current]
    logger.info("whole_turn_selection_verified")


@pytest.mark.parametrize("messages", [[], [message("assistant", "invalid")]])
def test_context_requires_current_user(messages):
    """Reject malformed contexts instead of guessing which message is current."""
    with pytest.raises(InferenceFailure) as error:
        select_whole_turns(messages, 24)
    assert error.value.code == "invalid_context"


@pytest.mark.asyncio
async def test_budget_drops_whole_pairs_and_keeps_system():
    """Use the supplied tokenizer count rather than text length to decide trimming."""
    system = message("system", "system")
    current = message("user", "current")
    context = [system, message("user", "old"), message("assistant", "reply"), current]
    calls = []

    async def count_tokens(candidate):
        """Simulate template token counts crossing the exact 32K boundary."""
        calls.append(candidate.copy())
        return 32700 if len(candidate) == 4 else 32000

    assert await fit_token_budget(
        context, preset="fast", max_tokens=512, count_tokens=count_tokens
    ) == [system, current]
    assert calls == [context, [system, current]]
    assert context[1]["content"] == "old"


@pytest.mark.asyncio
async def test_current_message_overflow_is_controlled():
    """Keep system and current input intact even when they cannot fit."""

    async def count_tokens(candidate):
        """Return an overflowing count for irreducible input."""
        return 32768

    with pytest.raises(InferenceFailure) as error:
        await fit_token_budget(
            [message("system", "system"), message("user", "huge")],
            preset="fast",
            max_tokens=512,
            count_tokens=count_tokens,
        )
    assert error.value.status_code == 422
    assert error.value.code == "context_overflow"


@pytest.mark.asyncio
async def test_invalid_output_budget_does_not_trim_history():
    """Reject intrinsic preset/output conflicts before counting or dropping turns."""

    async def count_tokens(candidate):
        """Fail if an invalid request reaches tokenization."""
        pytest.fail("Invalid output budget must be rejected before tokenization")

    with pytest.raises(InferenceFailure) as error:
        await fit_token_budget(
            [message("user", "current")],
            preset="balanced",
            max_tokens=512,
            count_tokens=count_tokens,
        )
    assert error.value.code == "invalid_token_budget"
