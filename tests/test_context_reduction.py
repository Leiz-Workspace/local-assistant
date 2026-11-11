"""Verify explicit history budgets, immutable pins and verbatim compaction without model dependencies."""

import json
import logging
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from src.application.ports.inference import InferenceFailure
from src.application.services.context_composer import compose_context
from src.application.services.context_reduction import (
    ContextError,
    HistoryPolicy,
    encode,
    input_limit,
    reduce_history,
)
from src.infrastructure.context_archive import ContextArchive

LOGGER = logging.getLogger(__name__)


def dialogue(pairs=4, size=10):
    """Create complete identifiable turns with a distinct current task and immutable system policy."""
    rows = [dict(role="system", content="System policy")]
    for number in range(1, pairs + 1):
        rows.extend(
            [
                dict(role="user", content=f"Atlas question {number} " + "x" * size),
                dict(
                    role="assistant",
                    content=f"Atlas answer {number} G-17 " + "y" * size,
                ),
            ]
        )
    return rows + [dict(role="user", content="Which Atlas generation?")]


async def count(messages):
    """Count deterministic character costs to expose hard boundaries without pretending they are real tokens."""
    return sum(len(row["content"]) for row in messages)


@pytest.mark.parametrize(
    "values",
    [
        {"window_turns": 0},
        {"window_turns": True},
        {"pinned_turns": [1, 1]},
        {"pinned_turns": [128]},
        {"pinned_turns": [True]},
        {"trigger_ratio": 1.0},
        {"trigger_ratio": float("nan")},
        {"recall_ids": [str(uuid4())]},
        {"max_extracts": 9},
        {"mode": "llm-summary"},
        {"owner": str(uuid4())},
    ],
)
def test_invalid_policy_is_closed(values):
    """Reject unknown strategies, excessive limits and authority-bearing options before tokenizer work."""
    with pytest.raises(ValidationError):
        HistoryPolicy.model_validate(values)


@pytest.mark.asyncio
async def test_window_and_pins_are_whole_and_chronological():
    """Keep one recent pair plus a pinned original pair, leaving caller bytes unchanged."""
    original = dialogue()
    before = encode(original)
    fitted, report = await reduce_history(
        original,
        policy={"window_turns": 1, "pinned_turns": [1]},
        count_tokens=count,
        preset="fast",
        max_tokens=None,
    )
    assert fitted == original[:3] + original[-3:]
    assert report["retained_turns"] == [1, 4]
    assert report["evicted_turns"] == [2, 3]
    assert report["archive"] is None
    assert encode(original) == before
    LOGGER.info("test_whole_turn_pins_preserved")


@pytest.mark.asyncio
async def test_hard_pressure_never_removes_pin_or_current():
    """Remove optional pairs under token pressure and reject an oversized mandatory pair intact."""
    rows = dialogue(3, 6000)
    fitted, report = await reduce_history(
        rows,
        policy={"pinned_turns": [1]},
        count_tokens=count,
        preset="fast",
        max_tokens=4096,
    )
    assert report["retained_turns"] == [1, 3]
    assert rows[1] in fitted and fitted[-1] == rows[-1]
    with pytest.raises(InferenceFailure, match="Mandatory context") as error:
        await reduce_history(
            dialogue(1, 15000),
            policy={"pinned_turns": [1]},
            count_tokens=count,
            preset="fast",
            max_tokens=4096,
        )
    assert error.value.code == "context_overflow"


@pytest.mark.asyncio
@pytest.mark.parametrize("mutation", ["orphan", "missing-pin", "strict-window"])
async def test_invalid_or_unfulfilled_history_is_explicit(mutation):
    """Reject partial pairs, unavailable pin references and strict-window loss instead of silently repairing input."""
    rows = dialogue(2)
    policy = {"window_turns": 1}
    if mutation == "orphan":
        rows.pop(1)
    if mutation == "missing-pin":
        policy["pinned_turns"] = [3]
    with pytest.raises(ContextError):
        await reduce_history(
            rows,
            policy=policy,
            count_tokens=count,
            preset="fast",
            max_tokens=None,
            strict=mutation == "strict-window",
        )


@pytest.mark.asyncio
async def test_compaction_keeps_exact_originals_and_redacts_receipt(caplog):
    """Archive complete original pairs and inject exact matching excerpts only as untrusted current-user data."""
    caplog.set_level(logging.INFO)
    store, owner = ContextArchive(), uuid4()
    rows = dialogue(3)
    rows[1]["content"] += " PRIVATE_CONTEXT_SENTINEL"

    def archive(raw):
        """Store fixture history under a real owner binding."""
        return store.put(owner, raw)

    fitted, report = await compose_context(
        rows,
        history_policy={"mode": "extractive-compact", "window_turns": 1},
        archive=archive,
        preset="fast",
        count_tokens=count,
    )
    receipt = report["history_policy"]
    entry = store.get(owner, UUID(receipt["archive"]["id"]))
    assert entry["payload"]["turns"][0]["messages"] == rows[1:3]
    assert entry["payload"]["turns"][1]["messages"] == rows[3:5]
    capsule = json.loads(fitted[-1]["content"].split("\n")[-1])[
        "untrusted_history_context"
    ]
    assert capsule["partial"] and capsule["extracts"]
    assert all(row["role"] in {"system", "user", "assistant"} for row in fitted)
    assert rows[1] not in fitted
    assert capsule["extracts"][1]["messages"] == rows[1:3]
    assert "PRIVATE_CONTEXT_SENTINEL" not in json.dumps(report)
    assert "PRIVATE_CONTEXT_SENTINEL" not in caplog.text
    assert not receipt["llm_summary"] and not receipt["archive_persistent"]
    assert report["input_tokens"] == await count(fitted)
    store.close()


@pytest.mark.asyncio
async def test_explicit_recall_and_oversized_pair_do_not_clip():
    """Recall source-bound originals explicitly while keeping oversized pairs only in the raw cache."""
    owner, store = uuid4(), ContextArchive()

    def archive(raw):
        """Bind local archive admission to one test principal."""
        return store.put(owner, raw)

    def recall(identifier):
        """Resolve only that principal's explicit archive handle."""
        return store.get(owner, identifier)

    rows = dialogue(2)
    rows[1]["content"] += "z" * 5000
    _, first = await reduce_history(
        rows,
        policy={"mode": "extractive-compact", "window_turns": 1},
        count_tokens=count,
        preset="fast",
        max_tokens=None,
        archive=archive,
    )
    assert not first["extracts"]
    assert (
        len(
            recall(UUID(first["archive"]["id"]))["payload"]["turns"][0]["messages"][0][
                "content"
            ]
        )
        > 5000
    )
    normal = dialogue(3)
    _, second = await reduce_history(
        normal,
        policy={"mode": "extractive-compact", "window_turns": 1},
        count_tokens=count,
        preset="fast",
        max_tokens=None,
        archive=archive,
    )
    fitted, report = await reduce_history(
        [normal[-1]],
        policy={"mode": "extractive-compact", "recall_ids": [second["archive"]["id"]]},
        count_tokens=count,
        preset="fast",
        max_tokens=None,
        archive=archive,
        recall=recall,
    )
    assert report["archive"] is None and len(report["recalled"]) == 1
    assert report["extracts"] and "G-17" in fitted[-1]["content"]
    assert not report["recall_automatic"]


@pytest.mark.asyncio
async def test_compaction_capsule_pressure_and_raw_admission_fail_closed():
    """Reject impossible mandatory/reference capacity and archive overflow rather than dropping raw bytes."""
    owner, store = uuid4(), ContextArchive()

    def archive(raw):
        """Use actual bounded raw admission for the overflow boundary."""
        return store.put(owner, raw)

    with pytest.raises(ContextError, match="too_large"):
        await reduce_history(
            dialogue(2, 70000),
            policy={"mode": "extractive-compact", "window_turns": 1},
            count_tokens=count,
            preset="fast",
            max_tokens=None,
            archive=archive,
        )
    rows = dialogue(1)
    rows[-1]["content"] = "q" * (input_limit("fast", None) - 30)
    with pytest.raises(InferenceFailure):
        await reduce_history(
            rows,
            policy={"mode": "extractive-compact"},
            count_tokens=count,
            preset="fast",
            max_tokens=None,
            archive=archive,
        )
    assert not store.entries


@pytest.mark.asyncio
async def test_dynamic_unlimited_and_bad_output_limits():
    """Keep room for the dynamic minimum answer and reject an invalid output request explicitly."""
    assert input_limit("unlimited", None) == 32000
    rows = [dict(role="user", content="q" * 30000)]
    fitted, _ = await reduce_history(
        rows, policy={}, count_tokens=count, preset="unlimited", max_tokens=None
    )
    assert fitted == rows
    with pytest.raises(InferenceFailure) as error:
        await reduce_history(
            rows, policy={}, count_tokens=count, preset="fast", max_tokens=1
        )
    assert error.value.code == "invalid_token_budget"


@pytest.mark.asyncio
@pytest.mark.parametrize("strategy", ["evidence-first", "recent-turns", "strict"])
async def test_source_priority_cannot_evict_pins(strategy):
    """Omit oversized sources before sacrificing mandatory pinned history in every source-priority mode."""
    rows = dialogue(1, 7000)
    fitted, report = await compose_context(
        rows,
        count_tokens=count,
        preset="fast",
        strategy=strategy,
        evidence=[b"e" * 16000, b"e" * 16000, b"x" * 65537],
        history_policy={"pinned_turns": [1]},
    )
    assert rows[1] in fitted and rows[2] in fitted
    assert not report["included_evidence"]
    assert report["omitted_evidence"][1]["reason"] == "duplicate_evidence"
    assert report["omitted_evidence"][2]["reason"] == "source_byte_limit"


@pytest.mark.asyncio
@pytest.mark.parametrize("strategy", ["evidence-first", "recent-turns"])
async def test_source_priority_changes_only_optional_history(strategy):
    """Apply explicit source/history precedence without altering the orthogonal window policy."""
    rows = dialogue(2, 5000)
    fitted, report = await compose_context(
        rows,
        count_tokens=count,
        preset="fast",
        evidence=[b"e" * 16000],
        strategy=strategy,
        history_policy={"window_turns": 2},
    )
    assert (len(report["included_evidence"]) == 1) == (strategy == "evidence-first")
    assert rows[-1]["content"] in fitted[-1]["content"]
    assert bool(report["history_policy"]["evicted_turns"]) == (
        strategy == "evidence-first"
    )
