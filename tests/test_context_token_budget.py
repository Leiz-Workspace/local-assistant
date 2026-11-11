"""Verify the opt-in token-budget history policy: soft budget, inspectable importance markers, receipts and overflow."""

import json
import logging
import unicodedata

import pytest

from apps.cli import main as cli
from src.application.ports.inference import InferenceFailure
from src.application.services.context_composer import compose_context
from src.application.services.context_reduction import (
    IMPORTANCE_MARKERS,
    MAX_IMPORTANCE_CANDIDATES,
    ContextError,
    HistoryPolicy,
    importance_marker,
    input_limit,
    reduce_history,
)

POLICY = {"mode": "token-budget"}
SOFT = int(input_limit("fast", 4096) * 0.8)


def dialogue(pairs, size, marked=(), marker="Rule: "):
    """Create numbered complete pairs whose character cost is known; listed pairs open with an importance marker."""
    rows = [dict(role="system", content="System policy")]
    for number in range(1, pairs + 1):
        prefix = marker if number in marked else ""
        rows.extend(
            [
                dict(
                    role="user",
                    content=f"{prefix}Atlas question {number} " + "x" * size,
                ),
                dict(role="assistant", content=f"Atlas answer {number} " + "y" * size),
            ]
        )
    return rows + [dict(role="user", content="Which Atlas generation?")]


def counter():
    """Count characters as deterministic fake tokens and record every call."""
    calls = []

    async def count(messages):
        """Return the summed content length of one candidate."""
        calls.append(len(messages))
        return sum(len(row["content"]) for row in messages)

    return count, calls


def reasons(report):
    """Map each turn number to its recorded selection reason."""
    return {entry["turn"]: entry["reason"] for entry in report["selection"]}


async def reduce(rows, policy=POLICY, **options):
    """Apply one reduction with the fast preset and a 4096-token output reserve."""
    count, calls = counter()
    fitted, report = await reduce_history(
        rows,
        policy=policy,
        count_tokens=count,
        preset="fast",
        max_tokens=4096,
        **options,
    )
    return fitted, report, calls


def test_policy_accepts_token_budget_and_keeps_closed_options():
    """The new mode parses, recall stays compaction-only and the ratio bounds still apply."""
    assert HistoryPolicy.model_validate(POLICY).mode == "token-budget"
    for values in (
        {**POLICY, "recall_ids": ["00000000-0000-4000-8000-000000000000"]},
        {**POLICY, "trigger_ratio": 0.99},
        {**POLICY, "pinned_turns": [0]},
    ):
        with pytest.raises(ValueError):
            HistoryPolicy.model_validate(values)


@pytest.mark.asyncio
async def test_short_turns_keep_more_than_the_eleven_pair_window():
    """Thirty short pairs fit the soft budget, so all stay where the default sliding window keeps eleven."""
    rows = dialogue(30, 10)
    fitted, report, calls = await reduce(rows)
    assert fitted == rows and report["retained_turns"] == list(range(1, 31))
    assert report["window_turns"] is None and report["recent_window_pairs"] == 30
    assert (
        report["mandatory_tokens"] is None and report["recent_share_token_cap"] is None
    )
    assert set(reasons(report).values()) == {"recent"} and len(calls) == 2
    _, sliding, _ = await reduce(rows, policy={"mode": "sliding-window"})
    assert sliding["retained_turns"] == list(range(20, 31))


@pytest.mark.asyncio
async def test_long_turns_keep_a_contiguous_recent_run_within_the_soft_budget():
    """Long pairs are kept newest first while the total stays within the soft budget, not the hard limit."""
    rows = dialogue(10, 3000)
    fitted, report, _ = await reduce(rows)
    assert report["retained_turns"] == [8, 9, 10]
    assert report["soft_input_limit"] == SOFT and report["soft_target_met"]
    assert sum(len(row["content"]) for row in fitted) <= SOFT
    assert {reasons(report)[number] for number in range(1, 8)} == {
        "evicted_token_budget"
    }
    assert fitted[0] == rows[0] and fitted[-1] == rows[-1]
    _, sliding, _ = await reduce(rows, policy={"mode": "sliding-window"})
    assert sliding["retained_turns"] == [7, 8, 9, 10]


@pytest.mark.asyncio
async def test_marked_user_turn_survives_pressure_in_any_unicode_form():
    """A user message opening with a marker, even NFD with leading space and capitals, is kept as important."""
    marker = unicodedata.normalize("NFD", "  QUY TẮC: ")
    rows = dialogue(10, 3000, marked=(2,), marker=marker)
    fitted, report, _ = await reduce(rows)
    assert report["retained_turns"] == [2, 9, 10]
    assert reasons(report)[2] == "important"
    assert report["importance_turns"] == [dict(turn=2, marker="quy tắc:")]
    assert rows[3] in fitted and rows[4] in fitted
    assert fitted.index(rows[3]) < fitted.index(rows[-4])


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Rule: always G-17", "rule:"),
        ("  decision: ship Friday", "decision:"),
        ("Ghi nhớ: dùng VND", "ghi nhớ:"),
        ("The rule: is here", None),
        ("Rules: plural is not a marker", None),
        ("", None),
    ],
)
def test_marker_must_open_the_user_message(text, expected):
    """Only an exact listed marker at the start of the user message counts."""
    turn = dict(
        number=1,
        messages=[
            dict(role="user", content=text),
            dict(role="assistant", content="ok"),
        ],
    )
    assert importance_marker(turn) == expected


@pytest.mark.asyncio
async def test_assistant_markers_and_mid_text_markers_grant_nothing():
    """An assistant reply that opens with a marker does not promote its pair."""
    rows = dialogue(10, 3000)
    rows[4]["content"] = "Important: " + rows[4]["content"]
    _, report, _ = await reduce(rows)
    assert report["importance_turns"] == [] and 2 not in report["retained_turns"]


def base_tokens(rows):
    """Return the fake token cost of the system, the newest pair and the current question."""
    return sum(len(row["content"]) for row in [rows[0]] + rows[-3:])


@pytest.mark.asyncio
async def test_recent_share_marked_probes_and_receipt_are_bounded():
    """The recent run first takes up to half the headroom, then at most eight marked older pairs are probed."""
    rows = dialogue(12, 3000, marked=range(1, 13))
    _, report, calls = await reduce(rows)
    selection = reasons(report)
    assert report["retained_turns"] == [10, 11, 12]
    assert {selection[number] for number in (10, 11, 12)} == {"recent"}
    assert [selection[n] for n in range(3, 10)] == ["evicted_importance_budget"] * 7
    assert [selection[n] for n in (1, 2)] == ["evicted_importance_limit"] * 2
    assert MAX_IMPORTANCE_CANDIDATES == 8 and report["recent_window_pairs"] == 3
    base = base_tokens(rows)
    assert report["recent_share_token_cap"] == base + (SOFT - base) // 2
    assert len(calls) <= 1 + 1 + 1 + 4 + MAX_IMPORTANCE_CANDIDATES + 4 + 1


@pytest.mark.asyncio
@pytest.mark.parametrize("extra", [(), (11,), (17, 18, 19)])
async def test_marking_recent_pairs_never_costs_an_older_marked_rule(extra):
    """Marked pairs already inside the recent share do not use up the room or probes that keep an older rule."""
    pairs, size = (12, 3000) if extra != (17, 18, 19) else (20, 1500)
    _, report, _ = await reduce(dialogue(pairs, size, marked=(1,) + extra))
    assert 1 in report["retained_turns"] and reasons(report)[1] == "important"
    _, alone, _ = await reduce(dialogue(pairs, size, marked=(1,)))
    assert report["retained_turns"] == alone["retained_turns"]


@pytest.mark.asyncio
async def test_oversized_newest_pair_does_not_erase_older_history():
    """A newest pair larger than the soft budget is dropped while the next newest run still fits."""
    rows = dialogue(6, 1000)
    rows[-3]["content"] += "z" * (SOFT + 10)
    _, report, _ = await reduce(rows)
    assert report["retained_turns"] == [1, 2, 3, 4, 5]
    assert reasons(report)[6] == "evicted_token_budget"
    assert report["recent_window_pairs"] == 5


@pytest.mark.asyncio
async def test_pins_are_mandatory_and_irreducible_overflow_is_explicit():
    """Pins stay even above the soft budget; a pin above the hard limit is refused, never clipped."""
    rows = dialogue(4, 3000)
    rows[1]["content"] += "p" * (SOFT - 1000)
    _, report, _ = await reduce(rows, policy={**POLICY, "pinned_turns": [1]})
    assert report["retained_turns"] == [1] and not report["soft_target_met"]
    assert reasons(report)[1] == "pinned" and report["mandatory_tokens"] > SOFT
    rows[1]["content"] += "p" * input_limit("fast", 4096)
    with pytest.raises(InferenceFailure) as error:
        await reduce(rows, policy={**POLICY, "pinned_turns": [1]})
    assert error.value.code == "context_overflow"


@pytest.mark.asyncio
async def test_strict_refuses_any_trim_but_accepts_a_fitting_history():
    """Strict source priority rejects token-budget loss and passes when everything fits."""
    with pytest.raises(ContextError) as error:
        await reduce(dialogue(10, 3000), strict=True)
    assert error.value.code == "strict_context_would_trim"
    _, report, _ = await reduce(dialogue(5, 10), strict=True)
    assert report["evicted_turns"] == []


@pytest.mark.asyncio
async def test_composer_receipt_names_every_turn_without_text(caplog):
    """The composed receipt lists the policy, markers and per-turn reasons but no dialogue text."""
    caplog.set_level(logging.INFO)
    rows = dialogue(10, 3000, marked=(3,))[1:]
    rows[4]["content"] += " PRIVATE_SENTINEL"
    count, _ = counter()
    fitted, report = await compose_context(
        rows,
        history_policy=POLICY,
        preset="fast",
        max_tokens=4096,
        count_tokens=count,
    )
    receipt = report["history_policy"]
    assert receipt["mode"] == "token-budget"
    assert receipt["importance_markers"] == list(IMPORTANCE_MARKERS)
    assert len(receipt["selection"]) == 10 and receipt["archive"] is None
    assert reasons(receipt)[3] == "important" and rows[4] in fitted
    assert "history_policy_applied" in caplog.text
    assert "PRIVATE_SENTINEL" not in json.dumps(report)
    assert "PRIVATE_SENTINEL" not in caplog.text
    assert report["input_tokens"] == await count(fitted)


def test_cli_forwards_token_budget_and_rejects_a_window(monkeypatch, capsys):
    """The CLI sends the mode and budget ratio and refuses a window that this mode would ignore."""
    calls = []

    class Client:
        """Capture one request without a service or credentials."""

        def __init__(self, url, token):
            """Accept the client contract without network use."""

        def request(self, method, path, payload=None):
            """Record a copy of the payload and return a synthetic answer."""
            calls.append(json.loads(json.dumps(payload)))
            return {
                "result": {"choices": [{"message": {"content": "answer"}}]},
                "context": {},
            }

    monkeypatch.setattr(cli, "ApiClient", Client)
    monkeypatch.setattr(cli, "read_token", lambda path: "t" * 48)
    base = ["--json", "chat", "--message", "PRIVATE_INPUT"]
    assert (
        cli.main(
            base + ["--history-policy", "token-budget", "--history-budget-ratio", "0.6"]
        )
        == 0
    )
    policy = calls[0]["history_policy"]
    assert policy["mode"] == "token-budget" and policy["trigger_ratio"] == 0.6
    assert (
        cli.main(base + ["--history-policy", "token-budget", "--history-window", "3"])
        == 2
    )
    assert len(calls) == 1 and "PRIVATE_INPUT" not in capsys.readouterr().err
