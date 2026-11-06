"""Verify actual native fixture/tool/sandbox composition with disclosed controlled code proposals and retained failures."""

import asyncio
import json
from pathlib import Path

import pytest

from scripts.coding_baseline_trial import run_trial
from src.application.ports.inference import CompletionResult

REFERENCES = {
    "floor_division": "def solve(a, b):\n    return a // b",
    "unique_order": "def solve(values):\n    return list(dict.fromkeys(values))",
    "unicode_palindrome": "def solve(text):\n    normalized = ''.join(text.split()).casefold()\n    return normalized == normalized[::-1]",
    "word_counts": "def solve(text):\n    result = {}\n    for word in text.casefold().split():\n        result[word] = result.get(word, 0) + 1\n    return result",
    "window_sums": "def solve(values, width):\n    if width <= 0 or width > len(values):\n        return []\n    return [sum(values[index:index + width]) for index in range(len(values) - width + 1)]",
    "inclusive_clamp": "def solve(value, low, high):\n    return min(high, max(low, value))",
}


def described_reference(source):
    """Add full module/entry descriptions to the independently authored correct repair fixtures."""
    signature, body = source.split("\n", 1)
    return (
        '"""Reference repair for a synthetic evaluation fixture."""\n'
        + signature
        + '\n    """Return the authored reference behavior for the fixture."""\n'
        + body
        + "\n"
    )


class ControlledCodingCore:
    """Return authored reference programs or one deliberately invalid proposal without actual model inference."""

    def __init__(self, *, invalid=False, block=False):
        """Record fixed profile calls and expose completion/cancellation lifecycle for the test harness."""
        self.invalid = invalid
        self.block = block
        self.entered = asyncio.Event()
        self.exited = asyncio.Event()
        self.calls = []
        cases = json.loads(Path("configs/coding-baseline-cases.json").read_text())[
            "tasks"
        ]
        self.references = {
            row["requirements"]: described_reference(REFERENCES[row["id"]])
            for row in cases
        }

    async def complete(self, **options):
        """Supply fixture references while never receiving trusted expected outputs in the generation prompt."""
        self.calls.append(options)
        self.entered.set()
        try:
            if self.block:
                await asyncio.Event().wait()
            content = json.loads(options["messages"][1]["content"])
            assert set(content) == {"requirements", "source_lines"}
            code = self.references[content["requirements"]]
            payload = dict(code=code)
            if self.invalid and len(self.calls) == 1:
                payload["path"] = "/etc/passwd"
            return CompletionResult(
                json.dumps(payload), "controlled-core", "fast", "stop"
            )
        finally:
            self.exited.set()


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid", [False, True])
async def test_actual_fixture_tools_and_oracles_preserve_every_case(tmp_path, invalid):
    """Run all real Git/read/search/non-root sandbox phases and retain an intentional proposal failure without retries."""
    core = ControlledCodingCore(invalid=invalid)
    directory = tmp_path / "run"
    result = await run_trial(directory, inference=core)
    assert result["attempted"] == result["total"] == 6
    assert result["passed"] == (5 if invalid else 6)
    assert len(core.calls) == 6
    assert all(
        (row["profile"], row["preset"], row["temperature"], row["max_tokens"])
        == ("core", "fast", 0, 1024)
        for row in core.calls
    )
    assert all(
        row["before"]["status"] == "completed" and not all(row["before_outcomes"])
        for row in result["tasks"]
    )
    assert all(
        row["tool_attempts"] == 2
        for row in result["tasks"]
        if row["status"] == "measured"
    )
    assert all(
        row["after"]["status"] == "completed"
        and row["diff"].startswith("diff --git a/solve.py b/solve.py")
        for row in result["tasks"]
        if row["status"] == "measured"
    )
    assert json.loads((directory / "result.json").read_text()) == result
    if invalid:
        assert result["tasks"][0]["status"] == "model_or_proposal_failed"
        assert (
            not (directory / "floor_division" / "solve.py").read_text()
            == core.references[
                json.loads(Path("configs/coding-baseline-cases.json").read_text())[
                    "tasks"
                ][0]["requirements"]
            ]
        )


@pytest.mark.asyncio
async def test_cancelled_model_keeps_partial_honest_and_joins(tmp_path):
    """Join owned model/source resources and retain a one-attempt partial instead of fabricating a six-task score."""
    core = ControlledCodingCore(block=True)
    directory = tmp_path / "cancelled"
    task = asyncio.create_task(run_trial(directory, inference=core))
    await asyncio.wait_for(core.entered.wait(), 3)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert core.exited.is_set()
    report = json.loads((directory / "result.json").read_text())
    assert report["attempted"] == 1 and report["total"] == 6
    assert not report["passed"] and not report["specialist_model_adopted"]
