"""Verify the opt-in working state: extraction, supersession, freshness, carry across windows, limits and CLI."""

import json
import logging
import unicodedata

import pytest
from pydantic import ValidationError

from apps.cli import main as cli
from src.application.services import working_state as module
from src.application.services.context_composer import compose_context
from src.application.services.context_reduction import (
    WORKING_STATE_POLICY,
    HistoryPolicy,
    reduce_history,
)

STATE = {"mode": "token-budget", "working_state": True}


def pairs(texts):
    """Build numbered turns from (user, assistant) tuples."""
    return [
        dict(
            number=index,
            messages=[
                dict(role="user", content=user),
                dict(role="assistant", content=assistant),
            ],
        )
        for index, (user, assistant) in enumerate(texts, start=1)
    ]


def conversation(texts, question="What is current?"):
    """Build a full request from (user, assistant) tuples and one current question."""
    rows = [dict(role="system", content="System policy")]
    for user, assistant in texts:
        rows += [
            dict(role="user", content=user),
            dict(role="assistant", content=assistant),
        ]
    return rows + [dict(role="user", content=question)]


async def count(messages):
    """Count characters as deterministic fake tokens."""
    return sum(len(row["content"]) for row in messages)


async def reduce(rows, policy=STATE, **options):
    """Apply one reduction with the fast preset and a 4096-token output reserve."""
    return await reduce_history(
        rows,
        policy=policy,
        count_tokens=count,
        preset="fast",
        max_tokens=4096,
        **options,
    )


def test_extract_reads_only_marked_user_lines_with_keys_bullets_and_any_form():
    """Markers open a user line (after optional bullet), keys are case-folded, NFD matches, assistant lines never count."""
    turns = pairs(
        [
            (
                "Intro\n- Decision[DB  Region]: Frankfurt\nmore text",
                "Decision: ignored",
            ),
            (unicodedata.normalize("NFD", "QUYẾT ĐỊNH: máy chủ ở Hà Nội"), "ok"),
            ("We made a decision: not a marker", "ok"),
            ("* todo[backup]: verify restore\nDone[old]: closed", "ok"),
            ("Rule: " + "x" * 600, "ok"),
        ]
    )
    items, skipped = module.extract(turns, offset=10)
    assert [(item["kind"], item["key"], item["turn"]) for item in items] == [
        ("decision", "db region", 11),
        ("decision", None, 12),
        ("todo", "backup", 14),
        ("done", "old", 14),
    ]
    assert items[0]["text"] == "- Decision[DB  Region]: Frankfurt"
    assert items[1]["text"] == unicodedata.normalize(
        "NFC", "QUYẾT ĐỊNH: máy chủ ở Hà Nội"
    )
    assert items[0]["sha256"] == module.pair_sha256(turns[0]["messages"])
    assert skipped == [dict(turn=15, reason="line_too_long")]


@pytest.mark.parametrize(
    "line,expected",
    [
        ("Decision [k]: spaced key", ("decision", "k")),
        ("İmportant: dotted capital I", "skip-none"),
        ("DECıSION: dotless i", "skip-none"),
        ("Decision[" + "k" * 49 + "]: long key", "invalid_key"),
        ("Decision[]: empty key", "invalid_key"),
        ("Decision[[k]]: nested", "malformed_marker_line"),
        ("Rule:", "malformed_marker_line"),
        ("Updated: not a marker", "skip-none"),
    ],
)
def test_marked_lines_either_become_items_or_are_reported(line, expected):
    """Unusual capitals never crash; malformed marked lines are reported, never silently dropped."""
    items, skipped = module.extract(pairs([(line, "ok")]), offset=0)
    if isinstance(expected, tuple):
        assert [(i["kind"], i["key"]) for i in items] == [expected] and skipped == []
    elif expected == "skip-none":
        assert items == [] and skipped == []
    else:
        assert items == [] and skipped == [dict(turn=1, reason=expected)]


def test_resolve_supersedes_by_key_closes_todos_and_never_guesses_unkeyed():
    """Keyed later items supersede; done closes the keyed todo; unkeyed items stay active."""
    turns = pairs(
        [
            ("Decision[region]: Frankfurt", "ok"),
            ("Decision: deploy Tuesdays", "ok"),
            ("Todo[backup]: verify restore", "ok"),
            ("Correction[region]: Warsaw instead", "ok"),
            ("Decision: deploy Thursdays", "ok"),
            ("Done[backup]: restore verified", "ok"),
            ("Todo[cert]: renew certificate", "ok"),
            ("Todo[cert]: renew certificate before May", "ok"),
        ]
    )
    state = module.resolve(module.extract(turns, offset=0)[0])
    status = {(item["turn"], item["kind"]): item["status"] for item in state}
    assert status[(1, "decision")] == "superseded" and state[0]["superseded_by"] == 4
    assert status[(4, "correction")] == "active"
    assert status[(2, "decision")] == "active" and status[(5, "decision")] == "active"
    assert status[(3, "todo")] == "closed" and status[(6, "done")] == "record"
    assert status[(7, "todo")] == "superseded" and status[(8, "todo")] == "active"


def test_freshness_lists_newer_pairs_sharing_three_terms():
    """A newer unmarked correction is found; generic overlap below three terms is not."""
    turns = pairs(
        [
            ("Decision: Hydra production deploys go out on Tuesdays.", "Noted."),
            ("Here is the worker log; nothing to act on.", "Received."),
            (
                "Change of plan for Hydra: production deploys move to Thursdays.",
                "Updated.",
            ),
            ("Hydra lunch is on Friday.", "Ok."),
        ]
    )
    built = module.build_state(turns, offset=0, carried=[])
    assert built["mentions"] == {0: [3]}
    raw = module.render(built)
    capsule = json.loads(raw)["untrusted_working_state"]
    assert capsule["items"][0]["newer_mentions"] == [3]
    assert capsule["trust"] == "untrusted-user-marked-history"


def test_limits_drop_notes_first_then_oldest_and_report_them():
    """Over 64 active items or 32 KiB, notes and corrections go first, then the oldest; every drop is reported."""
    assert (
        module.build_state(pairs([("hello", "hi")]), offset=0, carried=[])["raw"]
        is None
    )
    texts = [("Update: step 0 deployed", "ok")] + [
        (f"Rule[r{n}]: rule number {n}", "ok") for n in range(64)
    ]
    built = module.build_state(pairs(texts), offset=0, carried=[])
    assert built["dropped_active"] == [1]
    assert sum(item["status"] == "active" for item in built["items"]) == 64
    long_rules = pairs([(f"Rule[r{n}]: " + "x" * 480, "ok") for n in range(64)])
    built = module.build_state(long_rules, offset=0, carried=[])
    assert built["dropped_active"][:2] == [1, 2] and len(built["raw"].encode()) <= 32768


def test_carried_inactive_statuses_and_keys_are_kept_consistent():
    """An edited client cannot revive a superseded, closed or dropped item; carried keys fold like parsed ones."""
    carried = [
        dict(
            kind="decision",
            key="Region",
            text="Decision[Region]: A",
            turn=1,
            sha256="a" * 64,
            status="superseded",
            superseded_by=2,
        ),
        dict(
            kind="todo",
            key="t",
            text="Todo[t]: x",
            turn=2,
            sha256="b" * 64,
            status="closed",
            superseded_by=3,
        ),
        dict(
            kind="note", text="Remember: y", turn=3, sha256="c" * 64, status="dropped"
        ),
        dict(
            kind="decision",
            key="DB  Region",
            text="Decision[DB Region]: B",
            turn=4,
            sha256="d" * 64,
        ),
    ]
    policy = HistoryPolicy.model_validate(
        {**STATE, "carried_state": carried, "history_offset": 10}
    )
    assert policy.carried_state[3].key == "db region"
    texts = [("Decision[db region]: C", "ok")]
    built = module.build_state(
        pairs(texts),
        offset=10,
        carried=[item.model_dump() for item in policy.carried_state],
    )
    status = {item["turn"]: item["status"] for item in built["items"]}
    assert status == {
        1: "superseded",
        2: "closed",
        3: "dropped",
        4: "superseded",
        11: "active",
    }


def test_prune_drops_oldest_inactive_first():
    """Inactive items beyond 64 are pruned oldest first while every active item stays."""
    turns = pairs(
        [(f"Decision[k]: value {n}", "ok") for n in range(70)] + [("Rule: stay", "ok")]
    )
    built = module.build_state(turns, offset=0, carried=[])
    assert len(built["items"]) == 64
    assert [item["status"] for item in built["items"]].count("active") == 2
    assert built["items"][0]["turn"] == 8


@pytest.mark.parametrize(
    "values",
    [
        {"carried_state": [], "history_offset": 5},
        {"mode": "extractive-compact", "working_state": True},
        {"working_state": "yes"},
        {"working_state": True, "history_offset": -1},
        {
            "working_state": True,
            "carried_state": [
                {
                    "kind": "decision",
                    "text": "x",
                    "turn": 1,
                    "sha256": "0" * 64,
                    "extra": 1,
                }
            ],
        },
        {
            "working_state": True,
            "carried_state": [
                {"kind": "decision", "text": "x", "turn": 1, "sha256": "bad"}
            ],
        },
    ],
)
def test_policy_rejects_incoherent_working_state(values):
    """Offsets need working state, compaction cannot combine with it, and carried items are strictly typed."""
    with pytest.raises(ValidationError):
        HistoryPolicy.model_validate(values)


@pytest.mark.asyncio
async def test_newer_unmarked_correction_is_kept_beside_the_marked_decision():
    """Under token pressure the marked decision and its newer unmarked correction both stay, with reasons."""
    filler = (
        "Here is the ledger log for reference:\n" + "row ok\n" * 900,
        "Received the log.",
    )
    texts = [("Decision: Hydra production deploys go out on Tuesdays.", "Noted.")]
    texts += [filler] * 4
    texts += [
        ("Change of plan for Hydra: production deploys move to Thursdays.", "Updated.")
    ]
    texts += [filler] * 10
    rows = conversation(
        texts, "On which weekday do Hydra production deploys go out now?"
    )
    fitted, report = await reduce(rows)
    reasons = {entry["turn"]: entry["reason"] for entry in report["selection"]}
    assert reasons[1] == "important" and reasons[6] == "newer_related"
    assert 7 not in report["retained_turns"]
    summary = report["working_state_summary"]
    assert summary["newer_mentions"] == [dict(turn=1, mentions=[6])]
    assert "untrusted_working_state" in fitted[-1]["content"]
    _, plain = await reduce(rows, policy={"mode": "token-budget"})
    assert 6 not in plain["retained_turns"] and "working_state" not in plain


@pytest.mark.asyncio
async def test_state_survives_three_successive_client_window_drops():
    """A keyed update, a closed todo and an early rule survive three drops of 32 pairs, with absolute lineage."""
    texts = [(f"Small talk {n}", f"Reply {n}") for n in range(1, 221)]
    texts[1] = ("Rule: invoice numbers use the prefix INV-ACME-", "Understood.")
    texts[2] = ("Decision[db-region]: Frankfurt", "Noted.")
    texts[9] = ("Todo[backup]: verify the nightly restore", "Added.")
    texts[39] = ("Todo[cert]: renew the portal certificate", "Added.")
    texts[69] = ("Decision[db-region]: Warsaw", "Updated.")
    texts[89] = ("Done[backup]: restore verified", "Closed.")
    carried, offset, drops = [], 0, 0
    window_start = 0
    for end in range(1, 221):
        if end - window_start > 127:
            policy = {
                **STATE,
                "carried_state": [i for i in carried if i["turn"] <= offset],
                "history_offset": offset,
            }
            _, report = await reduce(
                conversation(texts[window_start : end - 1]), policy=policy
            )
            carried = report["working_state"]["items"]
            window_start, offset, drops = window_start + 32, offset + 32, drops + 1
    assert drops == 3 and offset == 96
    policy = {
        **STATE,
        "carried_state": [i for i in carried if i["turn"] <= offset],
        "history_offset": offset,
    }
    fitted, report = await reduce(conversation(texts[window_start:]), policy=policy)
    items = {
        (item["turn"], item["kind"]): item for item in report["working_state"]["items"]
    }
    assert (
        items[(3, "decision")]["status"] == "superseded"
        and items[(3, "decision")]["origin"] == "carried"
    )
    assert items[(70, "decision")]["status"] == "active"
    assert (
        items[(10, "todo")]["status"] == "closed"
        and items[(40, "todo")]["status"] == "active"
    )
    assert items[(2, "constraint")]["sha256"] == module.pair_sha256(
        [
            dict(role="user", content=texts[1][0]),
            dict(role="assistant", content=texts[1][1]),
        ]
    )
    capsule = json.loads(fitted[-1]["content"].split("\n")[-1])[
        "untrusted_working_state"
    ]
    rendered = {item["text"] for item in capsule["items"]}
    assert rendered == {
        "Rule: invoice numbers use the prefix INV-ACME-",
        "Todo[cert]: renew the portal certificate",
        "Decision[db-region]: Warsaw",
    }
    assert report["working_state_summary"]["carried"] == 6
    assert not report["working_state_summary"]["carried_hashes_verifiable"]


@pytest.mark.asyncio
async def test_carried_items_inside_the_window_are_recomputed_not_trusted():
    """A carried item whose pair is still present is ignored in favour of the request's own text."""
    texts = [("Decision[k]: real value", "ok"), ("hello", "hi")]
    forged = dict(
        kind="decision", key="k", text="Decision[k]: forged", turn=1, sha256="0" * 64
    )
    _, report = await reduce(
        conversation(texts), policy={**STATE, "carried_state": [forged]}
    )
    assert [item["text"] for item in report["working_state"]["items"]] == [
        "Decision[k]: real value"
    ]
    assert report["working_state_summary"]["carried_recomputed"] == 1


@pytest.mark.asyncio
async def test_state_is_mandatory_content_in_both_modes_and_in_evidence_estimates():
    """The capsule is counted in sliding-window and token-budget and in the evidence-first mandatory estimate."""
    from src.application.services.context_reduction import mandatory_context

    texts = [("Goal: keep the capsule mandatory", "ok"), ("hello", "hi")]
    rows = conversation(texts)
    for mode in ("sliding-window", "token-budget"):
        fitted, report = await reduce(
            rows, policy={"mode": mode, "working_state": True}
        )
        assert "untrusted_working_state" in fitted[-1]["content"]
    policy = HistoryPolicy.model_validate(STATE)
    assert "untrusted_working_state" in mandatory_context(rows, policy)[-1]["content"]
    assert (
        "untrusted_working_state"
        not in mandatory_context(rows, HistoryPolicy())[-1]["content"]
    )


@pytest.mark.asyncio
async def test_composer_adds_policy_and_logs_no_text(caplog):
    """The host policy names the state's limits; logs carry counts only."""
    caplog.set_level(logging.INFO)
    rows = conversation([("Goal: PRIVATE_GOAL_SENTINEL migrate reports", "ok")])[1:]
    fitted, report = await compose_context(
        rows, history_policy=STATE, preset="fast", max_tokens=4096, count_tokens=count
    )
    assert WORKING_STATE_POLICY in fitted[0]["content"]
    assert "working_state_applied active=1" in caplog.text
    assert "PRIVATE_GOAL_SENTINEL" not in caplog.text
    assert "PRIVATE_GOAL_SENTINEL" not in json.dumps(
        report["history_policy"]["working_state_summary"]
    )
    assert report["history_policy"]["working_state"]["items"][0]["kind"] == "goal"


def test_cli_without_working_state_sends_no_new_fields(monkeypatch):
    """Older servers keep working: the new policy fields are only sent when working state is requested."""
    calls = []

    class Client:
        """Capture one request."""

        def __init__(self, url, token):
            """Accept the client contract."""

        def request(self, method, path, payload=None):
            """Record the policy keys."""
            calls.append(set(payload["history_policy"]))
            return {
                "result": {"choices": [{"message": {"content": "a"}}]},
                "context": {},
            }

    monkeypatch.setattr(cli, "ApiClient", Client)
    monkeypatch.setattr(cli, "read_token", lambda path: "t" * 48)
    cli.main(["--json", "chat", "--message", "q", "--history-policy", "token-budget"])
    assert not calls[0] & {"working_state", "carried_state", "history_offset"}


class Recorder:
    """Capture CLI requests and return receipts with a growing synthetic working state."""

    calls = []

    def __init__(self, url, token):
        """Accept the client contract without network use."""

    def request(self, method, path, payload=None):
        """Record the request size and policy, and return one carried item per pair."""
        policy = payload["history_policy"]
        Recorder.calls.append(
            (
                len(payload["messages"]),
                policy["history_offset"],
                len(policy["carried_state"]),
            )
        )
        pairs_seen = policy["history_offset"] + (len(payload["messages"]) - 1) // 2
        items = [
            dict(
                kind="note",
                text=f"Remember: {n}",
                turn=n,
                sha256="a" * 64,
                status="active",
                origin="window",
            )
            for n in range(1, min(pairs_seen, 64) + 1)
        ]
        return {
            "result": {"choices": [{"message": {"content": "answer"}}]},
            "context": {"history_policy": {"working_state": {"items": items}}},
        }


def test_cli_working_state_carries_and_drops_instead_of_stopping(monkeypatch):
    """With working state and no pins the CLI drops 32 old pairs at the bound and sends the offset and carried items."""
    Recorder.calls = []
    inputs = iter(["question"] * 140 + ["/exit"])
    monkeypatch.setattr(cli, "ApiClient", Recorder)
    monkeypatch.setattr(cli, "read_token", lambda path: "t" * 48)
    monkeypatch.setattr("builtins.input", lambda prompt: next(inputs))
    assert (
        cli.main(["chat", "--history-policy", "token-budget", "--working-state"]) == 0
    )
    assert len(Recorder.calls) == 140
    assert Recorder.calls[127] == (255, 0, 0)
    assert Recorder.calls[128] == (193, 32, 32)
    assert all(size <= 256 for size, _, _ in Recorder.calls)


@pytest.mark.parametrize(
    "flags,code",
    [
        (["--working-state"], "history_policy_required"),
        (
            ["--history-policy", "extractive-compact", "--working-state"],
            "invalid_history_policy",
        ),
    ],
)
def test_cli_working_state_flag_errors(flags, code, monkeypatch, capsys):
    """The flag needs a compatible explicit policy and fails locally without sending text."""
    monkeypatch.setattr(cli, "read_token", lambda path: "t" * 48)
    assert cli.main(["chat", "--message", "PRIVATE_INPUT"] + flags) == 2
    error = capsys.readouterr().err
    assert code in error and "PRIVATE_INPUT" not in error
