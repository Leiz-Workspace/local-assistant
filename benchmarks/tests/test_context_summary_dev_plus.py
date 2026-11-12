"""Tests for the HAR-009-C summary v2 dev-plus cases: protocol shapes, listing, oracle design and held-out disjointness (digests only)."""

import hashlib
import sys

import pytest

import benchmarks
from apps.harness.inference import ProductInference
from benchmarks import context_summary_dev_plus as dev
from benchmarks import context_summary_v2 as module
from benchmarks.context_budget import SHORT_FILLER
from benchmarks.tests.test_context_summary_v2 import count_text, transport
from src.application.services import history_summary

WINDOW = range(1, 8)
RETAINED = range(9, 17)
KNOBS = [(4, 1, "last"), (4, 1, "withheld"), (4, 0, "last"), (4, 0, "withheld")]


def user(item, pair):
    """Return the user message of one pair."""
    return module.message_text(item, pair, "user")


def assistant(item, pair):
    """Return the assistant message of one pair."""
    return module.message_text(item, pair, "assistant")


def numeric(text):
    """Return the summary tokens of a text that carry a digit, in order."""
    return [
        token
        for token in history_summary.summary_tokens(text)
        if any(char.isdigit() for char in token)
    ]


def value_bearing(text):
    """Report a message that can be listed and carries a digit-bearing value."""
    return (
        history_summary.can_host_quote(text)
        and history_summary.signals(text)
        and bool(numeric(text))
    )


def evicted(item):
    """Return the (pair, [user, assistant]) rows of pairs 1-8, the window the summary covers."""
    messages = item["messages"]
    return [(number, messages[2 * (number - 1) : 2 * number]) for number in range(1, 9)]


def value_replies(item):
    """Return non-target pairs 1-7 whose assistant reply is authored (not a short filler) and carries a digit-bearing value."""
    fillers = {reply for _, reply in SHORT_FILLER[item["language"]]}
    targets = set(item["target_turns"])
    return [
        pair
        for pair in WINDOW
        if pair not in targets
        and assistant(item, pair) not in fillers
        and numeric(assistant(item, pair))
    ]


def by_id(cases):
    """Index cases by id."""
    return {item["id"]: item for item in cases}


def hashed(values):
    """Return the SHA-256 digests of strings, so a failing comparison prints no held-out text."""
    return {hashlib.sha256(value.encode()).hexdigest() for value in values}


def heldout_digest_sets():
    """Return (failure code, digest sets) for the hashed held-out cases; no frame that fails holds held-out data, and the module is unloaded."""
    loaded = module.HELDOUT_MODULE in sys.modules
    name = module.HELDOUT_MODULE.rsplit(".", 1)[1]
    bound = name in vars(benchmarks)
    code, found, cases = None, None, None
    try:
        cases = module.heldout(calibrate=True)
        if history_summary.digest(cases) != module.HELDOUT_SHA256:
            code = "HELDOUT_CHANGED"
        else:
            found = dict(
                ids=hashed(item["id"] for item in cases),
                tokens=hashed(
                    token for item in cases for token in module.case_tokens(item)[0]
                ),
                acks=hashed(
                    ack for item in cases for ack in module.case_tokens(item)[1]
                ),
            )
    except Exception:
        code = "HELDOUT_FIXTURE_FAILED"
    finally:
        cases = None
        if not loaded:
            sys.modules.pop(module.HELDOUT_MODULE, None)
            if not bound:
                vars(benchmarks).pop(name, None)
    return code, found


@pytest.fixture
def heldout_digests():
    """Provide digests of the held-out ids, value tokens and acknowledgements, or fail with a finite code only."""
    code, found = heldout_digest_sets()
    if code is not None:
        pytest.fail(code, pytrace=False)
    return found


def test_dev_plus_has_the_protocol_shapes():
    """Six valid cases, 3 EN and 3 VI: multi-fact in each language, a late target at pair 7 in each, an entity-less EN correction and a medium VI negation."""
    cases = dev.dev_plus()
    assert len(cases) == 6 and module.validate_cases(cases) == []
    assert sorted(item["language"] for item in cases) == ["en"] * 3 + ["vi"] * 3
    assert all(module.case_role(item) == "scored" for item in cases)
    assert all(module.case_oracle(item) == "admitted" for item in cases)
    assert all(len(item["messages"]) == 2 * 16 + 1 for item in cases)
    cases = by_id(cases)
    for name in ("dp-multi-quarrymoor", "dp-multi-trangquyt"):
        item = cases[name]
        message = user(item, item["gold"]["pair"])
        facts = numeric(message)
        value = history_summary.nfc(item["gold"]["value"]).casefold()
        assert len(facts) >= 3 and value in facts[1:], name
        assert history_summary.locate(message, item["gold"]["quote"]) > 0, name
    for name in ("dp-late-tamarack", "dp-late-oqua"):
        item = cases[name]
        assert item["target_turns"] == [7] and item["gold"]["pair"] == 7
        before = [pair for pair in range(1, 7) if value_bearing(user(item, pair))]
        assert len(before) >= 4, name
    item = cases["dp-fix-wexcombe"]
    first, second = item["target_turns"]
    assert item["kind"] == "correction" and item["gold"]["pair"] == second
    assert item["gold"]["replaces"] == first
    entity = {
        token
        for token in history_summary.value_tokens(user(item, first))
        if not any(char.isdigit() for char in token)
    }
    correction = set(history_summary.summary_tokens(user(item, second)))
    assert entity and not entity & correction
    item = cases["dp-neg-ngoive"]
    message = user(item, item["gold"]["pair"])
    start = history_summary.locate(message, item["gold"]["quote"])
    assert item["kind"] == "negation" and 400 <= len(message) <= 900
    assert history_summary.has_negation(item["gold"]["quote"])
    assert 0 < start and start + len(item["gold"]["quote"]) < len(message) - 1


def test_gold_value_is_specific_to_the_gold_quote():
    """Each gold value occurs once in its gold message, inside the gold quote, so a note from another clause never counts as gold."""
    for item in dev.dev_plus():
        gold = item["gold"]
        value = history_summary.nfc(gold["value"]).casefold()
        tokens = history_summary.summary_tokens(user(item, gold["pair"]))
        assert tokens.count(value) == 1, item["id"]
        assert value in history_summary.summary_tokens(gold["quote"]), item["id"]


def test_scoring_strings_are_absent_from_the_retained_pairs():
    """No required option, forbidden token or evidence string occurs in the retained pairs 9-16, so only the summary can supply them."""
    for item in dev.dev_plus():
        retained = " ".join(
            module.message_text(item, pair, role)
            for pair in RETAINED
            for role in ("user", "assistant")
        ).casefold()
        strings = [option for group in item["required"] for option in group]
        strings += item["forbidden"] + item["evidence"]
        assert [text for text in strings if text.casefold() in retained] == [], item[
            "id"
        ]


def test_each_case_has_value_distractors_and_a_substantive_value_reply():
    """Every case has at least 2 value-bearing distractor user messages and 1 substantive non-target assistant reply with a value."""
    for item in dev.dev_plus():
        targets = set(item["target_turns"])
        distractors = [
            pair
            for pair in WINDOW
            if pair not in targets and value_bearing(user(item, pair))
        ]
        assert len(distractors) >= 2 and value_replies(item), item["id"]


@pytest.mark.parametrize("knob", KNOBS)
def test_every_target_is_listed_unclipped_under_each_knob(knob):
    """Under every allowed knob the evicted window lists exactly MAX_SLOTS rows, every target among them and none clipped; listings match across knobs."""
    max_slots, max_claims, clipped_user = knob
    listings = {}
    for item in dev.dev_plus():
        with module.variant(
            max_slots=max_slots, max_claims=max_claims, clipped_user=clipped_user
        ):
            source, clipped, _, listed, _ = history_summary.packet(evicted(item))
        assert len(listed) == max_slots, item["id"]
        assert set(item["target_turns"]) <= set(listed), item["id"]
        assert not set(item["target_turns"]) & set(clipped), item["id"]
        sent = {row["pair"] for row in source["assistant"]}
        if max_claims > 0:
            assert sent & set(value_replies(item)), item["id"]
        else:
            assert sent == set(), item["id"]
        listings[item["id"]] = listed
    with module.variant(clipped_user="last"):
        for item in dev.dev_plus():
            assert history_summary.packet(evicted(item))[3] == listings[item["id"]]


@pytest.mark.asyncio
@pytest.mark.parametrize("knob", KNOBS)
async def test_oracle_design_check_admits_every_gold_note(knob):
    """The oracle design check over the real composition path has no violation and admits all 6 gold notes in their slots."""
    cases = dev.dev_plus()
    fake, calls = transport(cases)
    max_slots, max_claims, clipped_user = knob
    with module.variant(
        max_slots=max_slots, max_claims=max_claims, clipped_user=clipped_user
    ):
        plan, violations, _ = await module.design(
            ProductInference(transport=fake), cases, module.ARMS, count_text=count_text
        )
    assert violations == [] and len(plan) == 6 * len(module.ARMS)
    assert calls["summaries"] == [] and calls["answers"] == []
    v2 = [entry for entry in plan if entry["arm"] == "budget_summary_v2"]
    assert sum(entry["gold_admitted"] for entry in v2) == 6


def test_dev_cases_join_v1_and_dev_plus(monkeypatch):
    """The dev set is the 14 v1 cases plus dev-plus: 20 cases, 18 scored, with unique ids and no shared value token."""
    monkeypatch.delitem(sys.modules, module.HELDOUT_MODULE, raising=False)
    cases = module.dev_cases()
    assert len(cases) == 20 and len(module.scored_ids(cases)) == 18
    assert module.validate_cases(cases) == []
    assert module.overlap_digests(dev.dev_plus(), module.v1_cases()) == []


def test_dev_plus_is_disjoint_from_the_hashed_heldout_set(heldout_digests):
    """Dev-plus shares no id, value token or acknowledgement with the hashed held-out set; the comparison holds digests only."""
    cases = dev.dev_plus()
    assert heldout_digests["tokens"] and heldout_digests["acks"]
    assert hashed(item["id"] for item in cases) & heldout_digests["ids"] == set()
    tokens = hashed(token for item in cases for token in module.case_tokens(item)[0])
    assert tokens & heldout_digests["tokens"] == set()
    acks = hashed(ack for item in cases for ack in module.case_tokens(item)[1])
    assert acks & heldout_digests["acks"] == set()
