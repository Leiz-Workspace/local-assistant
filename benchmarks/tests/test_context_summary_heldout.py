"""Check the HAR-009-C summary v2 held-out corpus against the protocol's leakage and validity tests 1-9 without model calls; failures name ids, rules, counts or digests only."""

import asyncio
import functools
import hashlib
import importlib
import json
import re
import unicodedata

import httpx
import pytest

from apps.api.core.model_config import get_model_profile
from apps.harness.inference import ProductInference
from benchmarks import context_budget, context_retention, context_state
from benchmarks import context_summary as v1_runner
from benchmarks import context_summary_heldout as heldout
from benchmarks import context_summary_v2 as runner
from benchmarks.context_retention import score
from benchmarks.har008 import ROOT
from src.application.services import history_summary

KINDS = ("number", "identifier", "swap", "correction", "negation", "condition")
PROBES = dict(
    allow_wording="dropped",
    valueless_correction="unlisted",
    cap_pressure="over_cap",
    leading_condition="admitted",
)
GATES = {
    1: ("en", "approval", "dropped"),
    2: ("vi", "approval", "dropped"),
    3: ("en", "approval", "dropped"),
    4: ("vi", "approval", "dropped"),
    5: ("en", "instruction", "admitted"),
    6: ("vi", "instruction", "admitted"),
}
EARLY = range(1, heldout.LONG_FROM)
TIME = re.compile(r"\d{1,2}:\d{2}")
CLOCK = re.compile(r"\d{1,2}:\d{2}")
DECIMAL = re.compile(r"\d\.\d")
ROW_NUMBER = re.compile(r"(?<![\w-])\d+(?![\w-])")
SPECIAL = re.compile(r"<\|im_(?:start|end)\|>|</?think>")
PIECE = re.compile(r" ?[^\W\d_]+|\d| ?[^\w\s]+\n*|\s+|_")
# Uniform tokenizer scales around the proxy that the design check must survive; the proxy is within about 2% of the native count.
BAND = (0.93, 1.07)
# MAX_SLOTS fixed by S-1 (ADR-192 A1.12); the corpus quotas are built for it, so a contract change must fail here first.
SLOTS = 4
# The allowed dev knobs (MAX_SLOTS, MAX_CLAIMS, CLIPPED_USER): one claim or none, clipped users listed last or withheld.
KNOBS = tuple(
    (SLOTS, claims, clipped) for claims in (1, 0) for clipped in runner.CLIPPED_CHOICES
)
COMMITTED = (
    history_summary.MAX_SLOTS,
    history_summary.MAX_CLAIMS,
    history_summary.CLIPPED_USER,
)
SCORED_TARGETS = 28
# Listed non-targets per listed target across the scored windows: at least 2.4 (12 to 5), so 68 against 28.
RATIO = (12, 5)
GROUP_SEPARATOR = dict(en=",", vi=".")
# The protocol's new shapes with a size band, as (kind, language, shape): medium 400-900 characters; deep 1,900-2,000 with the target at 1,200-1,900.
MEDIUM_SHAPES = {("number", "en", "new"), ("negation", "vi", "new")}
DEEP_SHAPES = {("number", "vi", "new"), ("negation", "en", "new")}
ASKING_WORDS = {"what", "which", "how", "số"}


def digests(values):
    """Return sorted SHA-256 digests so a failing assertion prints no corpus text."""
    return sorted(hashlib.sha256(value.encode()).hexdigest() for value in set(values))


@functools.lru_cache(maxsize=1)
def corpus():
    """Return the held-out corpus once per test session."""
    return heldout.corpus_heldout()


def by_id():
    """Return the corpus keyed by case id."""
    return {item["id"]: item for item in corpus()}


def role(item):
    """Return the case role."""
    return runner.case_role(item)


def scored_cases():
    """Return the 24 scored cases."""
    return [item for item in corpus() if role(item) == "scored"]


def text(item, pair, speaker):
    """Return one original message of a case."""
    return runner.message_text(item, pair, speaker)


def question(item):
    """Return the current question of a case."""
    return item["messages"][-1]["content"]


def options(item):
    """Return every required option, forbidden token and evidence token of a case."""
    return (
        [option for group in item["required"] for option in group]
        + item["forbidden"]
        + item["evidence"]
    )


def answers(item):
    """Return the case-folded answer forms: the gold value and every required option."""
    found = {history_summary.nfc(item["gold"]["value"]).casefold()}
    return found | {
        history_summary.nfc(option).casefold()
        for group in item["required"]
        for option in group
    }


def option_values(option):
    """Return an option's value tokens; in a multi-token rendering (grouped digits, hour words, scaled amounts) bare numbers of up to three digits are parts, not values, and the single-token form in the same group is checked instead."""
    values = history_summary.value_tokens(option)
    if len(history_summary.summary_tokens(option)) > 1:
        values = {value for value in values if not re.fullmatch(r"\d{1,3}", value)}
    return values


def case_values(item):
    """Return runner.case_tokens() values with option values taken by option_values()."""
    found = set()
    for pair in item["target_turns"]:
        found |= history_summary.value_tokens(text(item, pair, "user")) - {"i"}
    for option in options(item):
        found |= option_values(option)
    found.add(history_summary.nfc(item["gold"]["value"]).casefold())
    return found


def sentence_values(content):
    """Return value tokens per span sentence, so a sentence-initial capital is not a value."""
    found = set()
    for match in history_summary.SPAN_SENTENCE.finditer(history_summary.nfc(content)):
        found |= history_summary.value_tokens(match.group()) - {"i"}
    return found


def is_candidate(content):
    """Report whether a user message is a v2 listing candidate on its own."""
    clipped, _ = history_summary.clip(content)
    return history_summary.can_host_quote(clipped) and history_summary.signals(clipped)


def copies(item):
    """Return non-target pairs whose user message repeats a target user message verbatim."""
    targets = {text(item, pair, "user") for pair in item["target_turns"]}
    return {
        pair
        for pair in EARLY
        if pair not in item["target_turns"] and text(item, pair, "user") in targets
    }


def swap_reply_pairs(item):
    """Return the pairs whose assistant reply is the designed swap distractor (new-shape swap only)."""
    if item["kind"] != "swap" or item.get("shape") != "new":
        return set()
    gold = item["gold"]["pair"]
    return {
        pair
        for pair in (gold - 1, gold + 1)
        if pair in EARLY
        and pair not in item["target_turns"]
        and any(
            token.casefold() in text(item, pair, "assistant").casefold()
            for token in item["forbidden"]
        )
    }


def distractor_users(item):
    """Return the non-target pairs 1-7 whose user message is a value-bearing listing candidate."""
    return [
        pair
        for pair in EARLY
        if pair not in item["target_turns"]
        and pair not in copies(item)
        and is_candidate(text(item, pair, "user"))
        and sentence_values(text(item, pair, "user"))
    ]


def value_kind(token):
    """Classify a value token as a number, a clock time, a code or a name."""
    if re.fullmatch(r"\d+(?:\.\d+)*", token):
        return "number"
    if TIME.fullmatch(token):
        return "time"
    if any(char.isdigit() for char in token) or re.search(r"[-_./:]", token):
        return "code"
    return "name"


def render(messages, thinking):
    """Render a ChatML prompt shaped like the native template (system, turns, then the open assistant turn)."""
    parts = [
        f"<|im_start|>{row['role']}\n{row['content'].strip()}<|im_end|>\n"
        for row in messages
    ]
    parts.append("<|im_start|>assistant\n")
    parts.append("<think>\n" if thinking else "<think>\n\n</think>\n\n")
    return "".join(parts)


@functools.lru_cache(maxsize=None)
def part_tokens(part):
    """Count one marker-free prompt part: one token per digit, punctuation run and free whitespace run; one per letter run plus one per 7 further ASCII or 4 further non-ASCII letters."""
    count = 0
    for piece in PIECE.findall(part):
        word = piece.strip()
        if word and word[0].isalpha():
            count += 1 + (len(word) - 1) // (7 if word.isascii() else 4)
        else:
            count += 1
    return count


def proxy_tokens(content):
    """Approximate the native byte-level BPE count of a prompt: one token per template marker plus the parts between markers."""
    return len(SPECIAL.findall(content)) + sum(
        part_tokens(part) for part in SPECIAL.split(content)
    )


def transport(scale=1.0):
    """Serve the model probe, a ChatML template and the proxy tokenizer times a scale; any generation is a test failure."""

    def respond(request):
        """Route probes and counts only."""
        if request.url.path == "/v1/models":
            return httpx.Response(
                200, json={"data": [{"id": get_model_profile("core")["model_id"]}]}
            )
        if request.url.path == "/apply-template":
            body = json.loads(request.content)
            thinking = (body.get("chat_template_kwargs") or {}).get(
                "enable_thinking", True
            )
            return httpx.Response(
                200, json={"prompt": render(body["messages"], thinking)}
            )
        if request.url.path == "/tokenize":
            content = json.loads(request.content)["content"]
            return httpx.Response(
                200, json={"tokens": [0] * int(proxy_tokens(content) * scale)}
            )
        return httpx.Response(599, json=dict(error="unexpected_generation"))

    return httpx.MockTransport(respond)


async def count_text(content):
    """Count raw text with the fake tokenizer of the runner tests (about four characters per token)."""
    return len(content) // 4


def knob_variant(knob):
    """Bind one (MAX_SLOTS, MAX_CLAIMS, CLIPPED_USER) combination through runner.variant()."""
    slots, claims, clipped = knob
    return runner.variant(max_slots=slots, max_claims=claims, clipped_user=clipped)


def design_run(scale=1.0, knob=None):
    """Return the design check at a proxy scale under one knob combination; None means the committed defaults, even inside another variant."""
    return composed(scale, COMMITTED if knob is None else knob)


@functools.lru_cache(maxsize=None)
def composed(scale, knob):
    """Compose every held-out cell over the real composition path with an oracle summarizer and the scaled proxy tokenizer."""
    with knob_variant(knob):
        return asyncio.run(
            runner.design(
                ProductInference(transport=transport(scale)),
                corpus(),
                runner.ARMS,
                count_text=count_text,
            )
        )


def v2_entries(knob=None):
    """Return the budget_summary_v2 design entries keyed by case id."""
    plan, _, _ = design_run(1.0, knob)
    return {
        entry["case_id"]: entry for entry in plan if entry["arm"] == "budget_summary_v2"
    }


def window(item):
    """Return the packet, sent texts and verdicts of the oracle note on the covered window of the design check, under the knobs in force."""
    covered = v2_entries()[item["id"]]["summary"]["covered_pairs"]
    pairs = runner.case_pairs(item, covered)
    source, clipped, withheld, listed, over_cap = history_summary.packet(pairs)
    replies = [row["pair"] for row in source["assistant"]]
    data = history_summary.parse(
        runner.oracle_output_v2(item, listed, replies), listed, replies
    )
    kept, dropped = history_summary.verify(
        history_summary.flatten(data), history_summary.sent_pairs(source, pairs)
    )
    return dict(
        listed=listed,
        over_cap=over_cap,
        withheld=withheld,
        replies=replies,
        clipped=clipped,
        kept=kept,
        dropped=dropped,
    )


def source_texts():
    """Return every text of the blocklist sources: v1, B1, B2 with its fillers and log blocks, C1, the prompt, the module source and the schema template."""
    texts = []
    for item in (
        v1_runner.corpus() + context_retention.corpus() + context_budget.corpus()
    ):
        texts += [row["content"] for row in item["messages"]]
    for pool in (context_retention.FILLER, context_budget.SHORT_FILLER):
        for rows in pool.values():
            for user, assistant in rows:
                texts += [user, assistant]
    for item in context_state.multiwindow_corpus():
        for user, assistant in item["pairs"]:
            texts += [user, assistant]
        texts.append(item["question"])
    identifiers = [item["id"] for item in v1_runner.corpus()] + [
        item["id"] for item in context_budget.corpus()
    ]
    for identifier in identifiers:
        for number in range(1, heldout.PAIRS + 1):
            for language in ("en", "vi"):
                texts += list(context_budget.log_block(identifier, number, language))
    texts.append(history_summary.SYSTEM_PROMPT)
    texts.append(
        (ROOT / "src/application/services/history_summary.py").read_text(
            encoding="utf-8"
        )
    )
    texts.append(history_summary.compact(history_summary.schema_for((1, 2), (1,))))
    return texts + [row["content"] for item in dev_plus() for row in item["messages"]]


def dev_plus():
    """Return the dev-plus cases when their module exists (they are written after the held-out hash), else none."""
    try:
        module = importlib.import_module(runner.DEV_PLUS_MODULE)
    except ModuleNotFoundError as error:
        if error.name != runner.DEV_PLUS_MODULE:
            raise
        return []
    return module.dev_plus()


def source_case_values():
    """Return the case values of the blocklist corpora: answers, stale tokens and target values, plus the prompt-example values."""
    found = set()
    for item in v1_runner.corpus() + dev_plus():
        found |= runner.case_tokens(item)[0]
    for item in context_retention.corpus() + context_budget.corpus():
        for pair in item["target_turns"]:
            for row in item["messages"][2 * (pair - 1) : 2 * pair]:
                found |= history_summary.value_tokens(row["content"]) - {"i"}
        for option in options(item):
            found |= history_summary.value_tokens(option)
    for item in context_state.multiwindow_corpus():
        for pair in item["target_turns"]:
            user, assistant = item["pairs"][pair - 1]
            found |= (
                history_summary.value_tokens(user)
                | history_summary.value_tokens(assistant)
            ) - {"i"}
        for option in options(item):
            found |= history_summary.value_tokens(option)
    for example in (history_summary.EXAMPLE_1_PACKET, history_summary.EXAMPLE_2_PACKET):
        for speaker in ("user", "assistant"):
            for row in example[speaker]:
                found |= history_summary.value_tokens(row["text"]) - {"i"}
    return found | history_summary.value_tokens(history_summary.FILLER_TEXT)


def heldout_case_values():
    """Return the held-out values: per-sentence values of every authored (non-block) message and of each question without its fixed suffix, plus answer, stale and evidence values."""
    found = set()
    for item in corpus():
        for pair in EARLY:
            for speaker in ("user", "assistant"):
                found |= sentence_values(text(item, pair, speaker))
        suffix = (heldout.GATE_SUFFIX if role(item) == "gate" else heldout.SUFFIX)[
            item["language"]
        ]
        found |= sentence_values(question(item).removesuffix(suffix))
        for token in options(item):
            found |= option_values(token)
        found.add(history_summary.nfc(item["gold"]["value"]).casefold())
    return found


def test_case_contract_and_validation():
    """The corpus validates, is deterministic, and every case carries the contract fields of its role."""
    cases = corpus()
    problems = list(runner.validate_cases(cases))
    if json.dumps(cases, ensure_ascii=False) != json.dumps(
        heldout.corpus_heldout(), ensure_ascii=False
    ):
        problems.append((None, "not_deterministic"))
    for item in cases:
        identifier = item["id"]
        messages = item["messages"]
        if len(messages) != 2 * heldout.PAIRS + 1:
            problems.append((identifier, "not_sixteen_pairs"))
        if item["log_pairs"] != list(range(heldout.LONG_FROM, heldout.PAIRS + 1)):
            problems.append((identifier, "log_pairs"))
        if set(item["gold"]) != {"pair", "quote", "text", "value", "kind", "replaces"}:
            problems.append((identifier, "gold_fields"))
        if item["gold"]["kind"] not in history_summary.NOTE_KINDS:
            problems.append((identifier, "gold_kind"))
        if not all(isinstance(group, list) and group for group in item["required"]):
            problems.append((identifier, "required_groups"))
        if item["oracle"] not in runner.ORACLES or item["role"] not in runner.ROLES:
            problems.append((identifier, "role_or_oracle"))
        # The no-thousands-separator property is a per-case field of the held-out module, never an id list here.
        if (role(item) == "gate") == isinstance(item.get("ungrouped"), bool):
            problems.append((identifier, "ungrouped_field"))
        for content in [row["content"] for row in messages]:
            if content != unicodedata.normalize("NFC", content):
                problems.append((identifier, "not_nfc"))
        # score() matches options without normalizing, so an NFD option would never match an NFC answer.
        for option in options(item):
            if option != unicodedata.normalize("NFC", option):
                problems.append((identifier, "option_not_nfc"))
    assert problems == []


def test_counts_per_role_kind_language_and_shape():
    """24 scored cases (6 kinds x 2 EN + 2 VI, one basic and one new per language), gates G1-G6 and eight probes; 19 EN and 19 VI."""
    cases = corpus()
    counts = {}
    for item in cases:
        key = (role(item), item["kind"], item["language"], item.get("shape"))
        counts[key] = counts.get(key, 0) + 1
    expected = {}
    for kind in KINDS:
        for language in ("en", "vi"):
            for shape in ("basic", "new"):
                expected[("scored", kind, language, shape)] = 1
    for language in ("en", "vi"):
        expected[("gate", "authority_gate", language, None)] = 3
        for kind in PROBES:
            expected[("probe", kind, language, None)] = 1
    assert counts == expected
    assert sum(item["language"] == "en" for item in cases) == 19
    assert sum(item["language"] == "vi" for item in cases) == 19
    problems = []
    for item in cases:
        identifier, kind, language = item["id"], item["kind"], item["language"]
        if role(item) == "scored":
            number = "1" if item["shape"] == "basic" else "2"
            if identifier != f"h-{kind}-{language}-{number}":
                problems.append((identifier, "scored_id"))
            if item["oracle"] != "admitted" or "gate" in item or "probe" in item:
                problems.append((identifier, "scored_fields"))
        elif role(item) == "gate":
            match = re.fullmatch(r"h-gate-([1-6])", identifier)
            spec = GATES.get(int(match.group(1))) if match else None
            if spec != (language, item.get("gate"), item.get("oracle")):
                problems.append((identifier, "gate_definition"))
            if "shape" in item or "probe" in item:
                problems.append((identifier, "gate_fields"))
        else:
            if identifier != f"h-probe-{kind}-{language}" or item.get("probe") != kind:
                problems.append((identifier, "probe_id"))
            if item.get("oracle") != PROBES.get(kind) or "shape" in item:
                problems.append((identifier, "probe_fields"))
    assert problems == []


def test_dialogue_shape_fillers_and_long_blocks():
    """Pairs 1-7 are short or medium (two deep targets), pairs 8-16 are new inventory blocks without clock stamps whose clipped prefix (intro and value-free notes) carries no listing signal; filler pools have 12+ distinct pairs and never repeat in a case."""
    problems = []
    sources = {content.casefold() for content in source_texts()}
    for language, pool in heldout.FILLER.items():
        if len(pool) < 12 or len(set(pool)) != len(pool):
            problems.append((language, "filler_pool"))
        for user, assistant in pool:
            if user.casefold() in sources or assistant.casefold() in sources:
                problems.append((language, "filler_reused"))
            if sentence_values(user) or is_candidate(user):
                problems.append((language, "filler_has_value"))
            if history_summary.hard_value(assistant):
                problems.append((language, "filler_reply_has_value"))
            if history_summary.has_negation(user) or history_summary.has_condition(
                user
            ):
                problems.append((language, "filler_has_negation_or_condition"))
    for item in corpus():
        identifier, language = item["id"], item["language"]
        pool = set(heldout.FILLER[language])
        used = [
            (text(item, pair, "user"), text(item, pair, "assistant"))
            for pair in EARLY
            if (text(item, pair, "user"), text(item, pair, "assistant")) in pool
        ]
        if len(used) != len(set(used)):
            problems.append((identifier, "filler_repeated_in_case"))
        for pair in EARLY:
            for speaker in ("user", "assistant"):
                size = len(text(item, pair, speaker))
                target = (
                    speaker == "user"
                    and pair == item["gold"]["pair"]
                    and (item["kind"], language, item.get("shape")) in DEEP_SHAPES
                )
                if size > (2000 if target else 900):
                    problems.append((identifier, "early_message_too_long", pair))
        for pair in item["log_pairs"]:
            user, assistant = heldout.block(identifier, pair, language)
            if (text(item, pair, "user"), text(item, pair, "assistant")) != (
                user,
                assistant,
            ):
                problems.append((identifier, "block_not_generated", pair))
            if len(user) <= history_summary.CLIP_CHARS:
                problems.append((identifier, "block_not_long", pair))
            if CLOCK.search(user) or DECIMAL.search(user):
                problems.append((identifier, "block_clock_or_decimal", pair))
            if re.search(r"\d,\d", user):
                problems.append((identifier, "block_digit_comma_digit", pair))
            if history_summary.hard_value(assistant):
                problems.append((identifier, "block_reply_has_value", pair))
            lines = user.split("\n")
            if sentence_values(lines[1]) or history_summary.authority_match(lines[1]):
                problems.append((identifier, "block_notes_have_value", pair))
            clipped, cut = history_summary.clip(user)
            if not cut or history_summary.signals(clipped):
                problems.append((identifier, "block_clip_has_signal", pair))
            if lines[2] != heldout.BLOCK_TEXT[language]["header"] or sentence_values(
                lines[2]
            ):
                problems.append((identifier, "block_header", pair))
            for line in lines[3:]:
                for found in ROW_NUMBER.findall(line):
                    if not 400 <= int(found) <= 899:
                        problems.append((identifier, "block_value_range", pair))
        suffix = (
            heldout.GATE_SUFFIX[language]
            if role(item) == "gate"
            else heldout.SUFFIX[language]
        )
        if not question(item).endswith(suffix):
            problems.append((identifier, "question_suffix"))
    case_values = set()
    block_values = set()
    for item in corpus():
        case_values |= runner.case_tokens(item)[0]
        for pair in item["log_pairs"]:
            block_values |= sentence_values(text(item, pair, "user"))
    if block_values & case_values:
        problems.append((None, "block_values_meet_case_values"))
    for language in ("en", "vi"):
        old = set()
        for number in heldout.LOG_PAIRS:
            user, assistant = context_budget.log_block("probe", number, language)
            old |= grams(user.split("\n")[0]) | grams(assistant)
        for number in heldout.LOG_PAIRS:
            user, assistant = heldout.block("probe", number, language)
            if (grams(user.split("\n")[0]) | grams(assistant)) & old:
                problems.append((language, "block_template_reused"))
    assert sorted(set(problems), key=str) == []


def grams(content, width=4):
    """Return the word four-grams of a text, ignoring case and digits."""
    words = [
        word
        for word in history_summary.summary_tokens(content)
        if not any(char.isdigit() for char in word)
    ]
    return {tuple(words[i : i + width]) for i in range(len(words) - width + 1)}


def test_1_gold_quotes_and_oracle_notes_meet_their_oracle():
    """Gold quotes sit on token boundaries; scored notes are admitted in their slot; gate and allow_wording notes drop on authority; cap targets land over the cap; value-less corrections are unlisted."""
    problems = []
    oracles = {}
    for item in corpus():
        identifier, gold = item["id"], item["gold"]
        source = history_summary.nfc(text(item, gold["pair"], "user"))
        if history_summary.locate(source, history_summary.nfc(gold["quote"])) < 0:
            problems.append((identifier, "gold_quote_not_on_token_boundaries"))
        found = window(item)
        expect = runner.case_oracle(item)
        oracles[expect] = oracles.get(expect, 0) + 1
        if expect == "admitted":
            pairs = [entry[1]["pairs"] for entry in found["kept"]]
            if (
                gold["pair"] not in found["listed"]
                or found["dropped"]
                or pairs != [[gold["pair"]]]
            ):
                problems.append((identifier, "oracle_note_not_admitted_in_slot"))
        elif expect == "dropped":
            reasons = {entry["reason"] for entry in found["dropped"]}
            if (
                gold["pair"] not in found["listed"]
                or found["kept"]
                or not reasons
                or not reasons <= runner.GATE_REASONS
            ):
                problems.append((identifier, "oracle_note_not_dropped_by_authority"))
        elif expect == "over_cap":
            if gold["pair"] not in found["over_cap"] or gold["pair"] in found["listed"]:
                problems.append((identifier, "target_not_over_cap"))
        elif expect == "unlisted":
            if gold["pair"] not in found["withheld"].get("user_no_signal", []):
                problems.append((identifier, "target_not_withheld_as_no_signal"))
        if role(item) == "scored" and expect != "admitted":
            problems.append((identifier, "scored_oracle"))
        if item["kind"] == "allow_wording" and expect != "dropped":
            problems.append((identifier, "allow_wording_oracle"))
    assert problems == []
    assert oracles == dict(admitted=28, dropped=6, over_cap=2, unlisted=2)


@pytest.mark.parametrize("knob", KNOBS, ids=lambda knob: "-".join(map(str, knob)))
def test_oracle_design_check_composes_every_arm_without_violations(knob):
    """Under every allowed knob combination, the tokenizer-only design check over the real composition path has no violations for all four arms, loses no pair to the reserve and makes no generation."""
    plan, violations, checks = design_run(1.0, knob)
    assert [
        (entry["case_id"], entry["arm"], entry["problem"]) for entry in violations
    ] == []
    assert len(plan) == 38 * len(runner.ARMS)
    assert checks["output"]["ok"] and checks["reserve"]["ok"]
    assert checks["output"]["max_slots"] == SLOTS
    v2 = v2_entries(knob)
    assert all(entry["request_matches"] for entry in v2.values())
    assert {tuple(entry["summary"]["covered_pairs"]) for entry in v2.values()} == {
        tuple(range(1, heldout.LONG_FROM + 1))
    }
    lost = [
        (entry["case_id"], entry["arm"])
        for entry in plan
        if entry["summary"] and entry["summary"]["pairs_lost_to_reserve"]
    ]
    assert lost == []
    if knob[1] == 0:
        assert [
            entry["case_id"]
            for entry in v2.values()
            if entry["summary"]["sent_assistant_pairs"]
        ] == []
    statuses = {}
    for item in corpus():
        status = v2[item["id"]]["summary"]["status"]
        key = (runner.case_oracle(item), status)
        statuses[key] = statuses.get(key, 0) + 1
    assert statuses == {
        ("admitted", "applied"): 28,
        ("dropped", "none_verified"): 6,
        ("over_cap", "none_verified"): 2,
        ("unlisted", "none_verified"): 2,
    }
    assert sum(entry["gold_admitted"] for entry in v2.values()) == 28


def test_design_check_holds_over_a_tokenizer_band():
    """Full keeps every pair, budget evicts every target and pair 8, the summary window stays pairs 1-8 and no pair is lost to the reserve at both band edges, so a native count a few percent off the proxy cannot break the reference or the listing."""
    problems = []
    for scale in BAND:
        plan, violations, _ = design_run(scale)
        problems += [
            (scale, entry["case_id"], entry["arm"], entry["problem"])
            for entry in violations
            if entry["case_id"] is not None
        ]
        for entry in plan:
            if entry["arm"] == "budget_summary_v2" and entry["summary"][
                "covered_pairs"
            ] != list(range(1, heldout.LONG_FROM + 1)):
                problems.append((scale, entry["case_id"], "covered_window"))
            if entry["arm"] == "budget" and min(entry["retained_turns"]) <= (
                heldout.LONG_FROM
            ):
                problems.append((scale, entry["case_id"], "budget_keeps_pair_8"))
            if entry["summary"] and entry["summary"]["pairs_lost_to_reserve"]:
                problems.append((scale, entry["case_id"], entry["arm"], "reserve"))
            if entry["arm"] == "full" and not entry["present"]:
                problems.append((scale, entry["case_id"], "full_not_present"))
    assert problems == []


def test_2_answer_tokens_never_leak_into_other_text():
    """Required, forbidden and evidence tokens occur only in target pairs (the swap distractor reply may hold the stale token), never in fillers, blocks, distractors, other cases or questions; all are checked as substrings."""
    problems = []
    cases = corpus()
    for item in cases:
        identifier = item["id"]
        own = []
        for pair in range(1, heldout.PAIRS + 1):
            if pair in item["target_turns"] or pair in copies(item):
                continue
            own.append((pair, "user", text(item, pair, "user")))
            own.append((pair, "assistant", text(item, pair, "assistant")))
        own.append((None, "question", question(item)))
        others = [
            row["content"]
            for other in cases
            if other["id"] != identifier
            for row in other["messages"]
        ]
        for token in options(item):
            folded = history_summary.nfc(token).casefold()
            stale = token in item["forbidden"]
            for pair, speaker, content in own:
                if folded not in history_summary.nfc(content).casefold():
                    continue
                if stale and speaker == "assistant" and pair in swap_reply_pairs(item):
                    continue
                problems.append((identifier, "token_in_own_text", pair, speaker))
            if any(
                folded in history_summary.nfc(content).casefold() for content in others
            ):
                problems.append((identifier, "token_in_other_case"))
    assert sorted(set(problems), key=str) == []


def test_3_disjoint_from_dev_blocklist_and_prompt_both_ways():
    """Held-out values never occur in v1, dev-plus, B1, B2, C1, their fillers and logs, the prompt, the module source or the schema; their case values never occur anywhere in the held-out corpus."""
    sources = set()
    for content in source_texts():
        sources |= set(history_summary.summary_tokens(content))
    assert digests(heldout_case_values() & sources) == []
    found = set()
    for item in corpus():
        for row in item["messages"]:
            found |= sentence_values(row["content"])
        for token in options(item):
            found |= option_values(token)
    assert digests(source_case_values() & found) == []
    assert runner.overlap_digests(corpus(), v1_runner.corpus()) == []
    assert runner.overlap_digests(corpus(), dev_plus()) == []
    messages = {
        history_summary.nfc(row["content"]).casefold()
        for item in corpus()
        for row in item["messages"]
    }
    assert digests(messages & {content.casefold() for content in source_texts()}) == []


def test_prompt_leaks_and_reserved_example_entities():
    """No held-out value or target acknowledgement occurs in the prompt; no dialogue names a reserved prompt-example entity."""
    assert runner.prompt_leaks(corpus()) == []
    assert runner.example_entities_in(corpus()) == []


def test_test_module_names_no_heldout_case_or_answer():
    """This test module stays readable beside the never-open corpus, so it names no held-out case id and holds no gold value or answer, stale or evidence token (gate evidence is the protocol's own template wording); per-case rules come from fields of the held-out module."""
    source = history_summary.nfc(open(__file__, encoding="utf-8").read()).casefold()
    problems = []
    for item in corpus():
        identifier = item["id"]
        if re.search(rf"(?<![\w-]){re.escape(identifier)}(?![\w-])", source):
            problems.append((identifier, "case_id_in_test_module"))
        tokens = [item["gold"]["value"]]
        if role(item) != "gate":
            tokens += options(item)
        if any(history_summary.nfc(token).casefold() in source for token in tokens):
            problems.append((identifier, "answer_token_in_test_module"))
    assert problems == []


def test_4_acknowledgements_and_their_mix():
    """No target acknowledgement is shared with the prompt or the dev set; gold-pair acknowledgements split 12 quotable without a hard value (withheld), 4 echoing the value (sent) and 8 short (withheld)."""
    prompt = history_summary.SYSTEM_PROMPT.casefold()
    dev = set()
    for item in (
        v1_runner.corpus()
        + dev_plus()
        + context_retention.corpus()
        + context_budget.corpus()
    ):
        dev |= {
            row["content"].strip().casefold()
            for row in item["messages"]
            if row["role"] == "assistant"
        }
    for item in context_state.multiwindow_corpus():
        dev |= {assistant.strip().casefold() for _, assistant in item["pairs"]}
    problems, mix = [], {}
    for item in corpus():
        for pair in item["target_turns"]:
            ack = text(item, pair, "assistant").strip().casefold()
            if ack in prompt or ack in dev:
                problems.append((item["id"], "acknowledgement_shared", pair))
        if role(item) != "scored":
            continue
        gold = item["gold"]["pair"]
        ack = text(item, gold, "assistant")
        withheld = window(item)["withheld"]
        if not history_summary.can_host_quote(ack):
            group = "short"
            if gold not in withheld.get("assistant_short", []):
                problems.append((item["id"], "short_ack_not_withheld"))
        elif not history_summary.hard_value(ack):
            group = "quotable"
            if gold not in withheld.get("assistant_no_hard_value", []):
                problems.append((item["id"], "quotable_ack_not_withheld"))
        else:
            group = "echo"
            if not answers(item) & set(history_summary.summary_tokens(ack)):
                problems.append((item["id"], "echo_ack_without_the_value"))
            if gold not in window(item)["replies"]:
                problems.append((item["id"], "echo_ack_not_sent"))
        mix[group] = mix.get(group, 0) + 1
    assert problems == []
    assert mix == dict(quotable=12, echo=4, short=8)


def window_candidates(item, listed, over_cap):
    """Return the listing problems of one window: a scored window lists exactly MAX_SLOTS with every target, a cap probe has 7+ candidates with the target over the cap, any other window lists at most MAX_SLOTS."""
    problems = []
    candidates = len(listed) + len(over_cap)
    gold = item["gold"]["pair"]
    if item["kind"] == "cap_pressure":
        if candidates < 7 or gold not in over_cap or gold in listed:
            problems.append((item["id"], "cap_probe_candidates", candidates))
    elif over_cap or candidates > history_summary.MAX_SLOTS:
        problems.append((item["id"], "window_candidates", candidates))
    if role(item) == "scored" and (
        len(listed) != history_summary.MAX_SLOTS
        or not set(item["target_turns"]) <= set(listed)
    ):
        problems.append((item["id"], "scored_window_not_exactly_max_slots", candidates))
    return problems


def test_scored_windows_list_exactly_max_slots():
    """MAX_SLOTS is the S-1 value 4, and every scored window lists exactly MAX_SLOTS candidates, every target among them and none over the cap, so a contract change fails here before any quota."""
    assert history_summary.MAX_SLOTS == SLOTS
    problems = []
    for item in scored_cases():
        summary = v2_entries()[item["id"]]["summary"]
        problems += window_candidates(
            item, summary["listed_pairs"], summary["over_cap_pairs"]
        )
        found = window(item)
        if found["listed"] != summary["listed_pairs"]:
            problems.append((item["id"], "packet_differs_from_design"))
    assert problems == []


def test_5_listing_quotas():
    """Under every allowed knob combination: exactly MAX_SLOTS candidates per scored window, at most MAX_SLOTS in the other non-cap windows, at least 7 in the cap probes with the target over the cap, listed non-targets at least 2.4 times the 28 listed targets, and one listing for all knobs."""
    problems, listings = [], {}
    for knob in KNOBS:
        listed_targets = listed_others = 0
        entries = v2_entries(knob)
        with knob_variant(knob):
            for item in corpus():
                summary = entries[item["id"]]["summary"]
                listed, over_cap = summary["listed_pairs"], summary["over_cap_pairs"]
                problems += [
                    (knob,) + problem
                    for problem in window_candidates(item, listed, over_cap)
                ]
                found = window(item)
                if (found["listed"], found["over_cap"]) != (listed, over_cap):
                    problems.append((knob, item["id"], "packet_differs_from_design"))
                listings.setdefault(item["id"], set()).add(
                    (tuple(listed), tuple(over_cap))
                )
                if role(item) == "scored":
                    targets = set(item["target_turns"])
                    listed_targets += len(targets & set(listed))
                    listed_others += len(set(listed) - targets)
        if (
            listed_targets != SCORED_TARGETS
            or listed_others * RATIO[1] < listed_targets * RATIO[0]
        ):
            problems.append((knob, "ratio", listed_targets, listed_others))
    problems += [
        (identifier, "listing_depends_on_knob")
        for identifier, found in listings.items()
        if len(found) != 1
    ]
    assert problems == []


def test_5_long_blocks_are_never_candidates_under_any_knob():
    """Under every allowed knob combination, long blocks in the covered window are withheld as signal-free, never listed, clipped or over the cap, so the quotas do not depend on the frozen knobs."""
    problems = []
    for knob in KNOBS:
        with knob_variant(knob):
            for item in corpus():
                found = window(item)
                blocks = set(item["log_pairs"]) & set(
                    v2_entries()[item["id"]]["summary"]["covered_pairs"]
                )
                if blocks - set(found["withheld"].get("user_no_signal", [])):
                    problems.append((knob, item["id"], "block_not_withheld"))
                if blocks & set(found["listed"] + found["over_cap"]):
                    problems.append((knob, item["id"], "block_is_candidate"))
                if blocks & set(found["clipped"]):
                    problems.append((knob, item["id"], "block_clipped"))
                if knob[1] == 0 and found["replies"]:
                    problems.append((knob, item["id"], "assistant_rows_sent"))
    assert problems == []


def test_allow_wording_probes_list_nothing_else_admissible():
    """An allow_wording window lists only the target and sends no assistant reply under every allowed knob combination, so any admitted item on the probe can only come from the allow-wording sentence (safety check 3)."""
    problems = []
    for knob in KNOBS:
        with knob_variant(knob):
            for item in corpus():
                if item["kind"] != "allow_wording":
                    continue
                found = window(item)
                if found["listed"] != [item["gold"]["pair"]] or found["over_cap"]:
                    problems.append((knob, item["id"], "other_user_candidates"))
                if found["replies"]:
                    problems.append((knob, item["id"], "assistant_rows_sent"))
    assert problems == []


def test_6_size_bounds():
    """Target sentences fit 110 characters and target messages 2,048; the medium (400-900) and deep (1,900-2,000) bands hold, with the gold quote of both deep shapes (VI number, EN negation) inside characters 1,200-1,900."""
    problems = []
    deep = 0
    for item in corpus():
        identifier, gold = item["id"], item["gold"]
        values = [history_summary.nfc(token).casefold() for token in options(item)]
        for pair in item["target_turns"]:
            content = history_summary.nfc(text(item, pair, "user"))
            if len(content) > history_summary.CLIP_CHARS:
                problems.append((identifier, "target_message_over_2048", pair))
            start = history_summary.locate(content, history_summary.nfc(gold["quote"]))
            end = start + len(gold["quote"])
            for match in history_summary.SPAN_SENTENCE.finditer(content):
                sentence = match.group().strip()
                holds_gold = (
                    pair == gold["pair"] and match.start() < end and match.end() > start
                )
                holds_value = any(value in sentence.casefold() for value in values)
                if (holds_gold or holds_value) and len(sentence) > 110:
                    problems.append((identifier, "target_sentence_over_110", pair))
        content = history_summary.nfc(text(item, gold["pair"], "user"))
        shape = (item["kind"], item["language"], item.get("shape"))
        if shape in MEDIUM_SHAPES:
            if not 400 <= len(content) <= 900:
                problems.append((identifier, "medium_band"))
        if shape in DEEP_SHAPES:
            if not 1900 <= len(content) <= 2000:
                problems.append((identifier, "deep_band"))
            quote = history_summary.nfc(gold["quote"])
            start = history_summary.locate(content, quote)
            if start < 1200 or start + len(quote) > 1900:
                problems.append((identifier, "deep_position"))
            deep += 1
    assert problems == []
    assert deep == len(DEEP_SHAPES)


def test_7_values_distinct_and_stale_tokens_separate():
    """Case value sets are pairwise disjoint; no forbidden token sits in a gold quote or a required option; distractor and sibling values never equal or contain the answer (equality is checked on non-target text before answer forms are set aside, the gold value included for gates)."""
    problems = []
    cases = corpus()
    values = {item["id"]: case_values(item) for item in cases}
    for index, item in enumerate(cases):
        for other in cases[index + 1 :]:
            if values[item["id"]] & values[other["id"]]:
                problems.append((item["id"], "shared_case_values", other["id"]))
    for item in cases:
        identifier = item["id"]
        quote = history_summary.nfc(item["gold"]["quote"]).casefold()
        required = [
            history_summary.nfc(option).casefold()
            for group in item["required"]
            for option in group
        ]
        for token in item["forbidden"]:
            folded = history_summary.nfc(token).casefold()
            if folded in quote or any(folded in option for option in required):
                problems.append((identifier, "forbidden_in_gold_or_required"))
        found = set()
        for pair in EARLY:
            if pair in item["target_turns"] or pair in copies(item):
                continue
            for speaker in ("user", "assistant"):
                found |= sentence_values(text(item, pair, speaker))
        if found & answers(item):
            problems.append((identifier, "distractor_equals_answer"))
        for pair in item["target_turns"]:
            found |= sentence_values(text(item, pair, "user"))
            found |= sentence_values(text(item, pair, "assistant"))
        found -= answers(item)
        for token in found:
            if any(answer in token for answer in answers(item)):
                problems.append((identifier, "distractor_or_sibling_contains_answer"))
    assert sorted(set(problems), key=str) == []


def test_8_no_answer_derivable_from_the_question():
    """No required option, gold value, forbidden or evidence token, and no value token of an answer, occurs in the question."""
    problems = []
    for item in corpus():
        asked = history_summary.nfc(question(item)).casefold()
        tokens = set(history_summary.summary_tokens(asked))
        for token in options(item) + [item["gold"]["value"]]:
            if history_summary.nfc(token).casefold() in asked:
                problems.append((item["id"], "answer_in_question"))
        for answer in answers(item):
            if history_summary.value_tokens(answer) & tokens or answer in tokens:
                problems.append((item["id"], "answer_value_in_question"))
    assert sorted(set(problems), key=str) == []


def test_scored_case_rules():
    """Target positions, two-target corrections, verbatim repeats, value-bearing distractors and replies, and the new-shape requirement of every kind."""
    problems = []
    late = repeats = valued = 0
    longest = 0
    for item in scored_cases():
        identifier, gold = item["id"], item["gold"]
        language, shape, kind = item["language"], item["shape"], item["kind"]
        targets = item["target_turns"]
        content = history_summary.nfc(text(item, gold["pair"], "user"))
        late += sum(pair in (6, 7) for pair in targets)
        if not set(targets) <= set(EARLY):
            problems.append((identifier, "target_outside_pairs_1_7"))
        for pair in copies(item):
            withheld = window(item)["withheld"].get("user_duplicate", [])
            if pair < gold["pair"] and pair in withheld:
                repeats += 1
            else:
                problems.append((identifier, "repeat_not_an_older_withheld_copy"))
        distractors = distractor_users(item)
        if len(distractors) < 2:
            problems.append((identifier, "fewer_than_two_value_distractors"))
        wanted = value_kind(history_summary.nfc(gold["value"]).casefold())
        if not any(
            value_kind(token) == wanted
            for pair in distractors
            for token in sentence_values(text(item, pair, "user"))
        ):
            problems.append((identifier, "no_distractor_with_the_value_type"))
        replies = [
            pair
            for pair in EARLY
            if pair not in targets
            and history_summary.hard_value(text(item, pair, "assistant"))
            and history_summary.can_host_quote(text(item, pair, "assistant"))
        ]
        valued += bool(replies)
        longest = max(
            [longest] + [len(text(item, pair, "assistant")) for pair in replies]
        )
        if kind == "correction":
            older = [pair for pair in targets if pair != gold["pair"]]
            if len(targets) != 2 or gold["replaces"] != (older[0] if older else None):
                problems.append((identifier, "correction_targets"))
            if shape == "basic" and not content.startswith(
                "Correction:" if language == "en" else "Sửa lại:"
            ):
                problems.append((identifier, "correction_wording"))
            if shape == "new":
                names = sentence_values(content) - {gold["value"]}
                older_names = {
                    token
                    for token in sentence_values(text(item, older[0], "user"))
                    if value_kind(token) == "name"
                }
                if names & older_names or (
                    language == "en"
                    and not re.fullmatch(r"Make that .+ instead\.", content)
                ):
                    problems.append((identifier, "correction_not_entity_less"))
        elif len(targets) != 1 or gold["replaces"] is not None:
            problems.append((identifier, "single_target"))
        quote = history_summary.nfc(gold["quote"])
        if kind == "identifier" and shape == "new":
            codes = [
                token
                for token in history_summary.summary_tokens(content)
                if value_kind(token) == "code"
            ]
            value = history_summary.nfc(gold["value"]).casefold()
            near = [
                token
                for token in item["forbidden"]
                if sorted(token.casefold()) == sorted(value)
            ]
            if not 2 <= len(codes) <= 3 or value not in codes[1:] or not near:
                problems.append((identifier, "identifier_multi_fact"))
            if language == "en" and (len(codes) != 3 or codes[2] != value):
                problems.append((identifier, "identifier_not_third_of_three"))
        if kind == "identifier" and shape == "basic":
            if (
                len([t for t in sentence_values(content) if value_kind(t) == "code"])
                != 1
            ):
                problems.append((identifier, "identifier_not_single"))
        if kind == "swap":
            if not any(
                token.casefold() in content.casefold() for token in item["forbidden"]
            ):
                problems.append((identifier, "swap_without_two_entities"))
            if shape == "new":
                pairs = swap_reply_pairs(item)
                if (
                    not pairs
                    or min(len(text(item, pair, "assistant")) for pair in pairs) < 80
                ):
                    problems.append((identifier, "swap_distractor_reply"))
        if kind == "negation":
            word = "never" if language == "en" else "không được"
            if shape == "basic" and word not in quote.casefold():
                problems.append((identifier, "negation_wording"))
            if not history_summary.has_negation(quote):
                problems.append((identifier, "negation_not_in_quote"))
            if shape == "new" and language == "en":
                sentence = next(
                    match.group()
                    for match in history_summary.SPAN_SENTENCE.finditer(content)
                    if quote in match.group()
                )
                if not DECIMAL.search(sentence):
                    problems.append((identifier, "negated_sentence_without_decimal"))
        if kind == "condition":
            word = "unless" if language == "en" else "trừ khi"
            if shape == "basic" and word not in quote.casefold():
                problems.append((identifier, "condition_wording"))
            if not history_summary.has_condition(quote):
                problems.append((identifier, "condition_not_in_quote"))
            if shape == "new":
                sentences = history_summary.token_sentences(content)
                conditioned = [
                    match
                    for match in sentences
                    if history_summary.has_condition(match.group())
                ]
                bearing = [
                    match
                    for match in sentences
                    if history_summary.hard_value(match.group())
                ]
                if (
                    len(sentences) != 2
                    or len(conditioned) != 1
                    or len(bearing) != 1
                    or conditioned[0] is bearing[0]
                ):
                    problems.append(
                        (identifier, "condition_and_value_not_in_two_sentences")
                    )
                elif history_summary.nfc(gold["value"]).casefold() not in (
                    history_summary.summary_tokens(bearing[0].group())
                ):
                    problems.append((identifier, "answer_not_in_value_sentence"))
                start = history_summary.locate(content, quote)
                if not all(
                    match.start() < start + len(quote) and match.end() > start
                    for match in sentences
                ):
                    problems.append((identifier, "gold_quote_not_over_both_sentences"))
    assert problems == []
    assert late >= 6 and repeats == 2
    assert valued >= 6 and longest > 512


def test_gate_and_probe_definitions():
    """G1-G4 carry approval wording at the target, G5-G6 are lexicon-free instructions; probes match their protocol definitions."""
    problems = []
    for item in corpus():
        identifier, gold = item["id"], item["gold"]
        content = history_summary.nfc(text(item, gold["pair"], "user"))
        if role(item) == "gate":
            number = int(identifier.rsplit("-", 1)[1])
            sentences = [
                m.group() for m in history_summary.SPAN_SENTENCE.finditer(content)
            ]
            if item["required"] or item["forbidden"]:
                problems.append((identifier, "gate_scored_tokens"))
            if number == 1 and not any(
                history_summary.authority_match(s)
                and history_summary.value_tokens(s)
                and history_summary.nfc(gold["quote"]) in s
                for s in sentences
            ):
                problems.append((identifier, "g1_value_not_with_approval"))
            if number == 2 and not any(
                "chấp thuận" in s and history_summary.nfc(gold["quote"]) in s
                for s in sentences
            ):
                problems.append((identifier, "g2_value_not_with_approval"))
            if number == 3 and not re.fullmatch(
                r"Approved\. Ship \S+ to \S+ tonight\.", content
            ):
                problems.append((identifier, "g3_wording"))
            if number == 4 and not re.fullmatch(
                r"Chạy migration \S+ tối nay\. Tôi đồng ý\.", content
            ):
                problems.append((identifier, "g4_wording"))
            if number in (5, 6) and history_summary.authority_match(content):
                problems.append((identifier, "instruction_has_lexicon_word"))
        if item["kind"] == "allow_wording":
            word = "is not allowed" if item["language"] == "en" else "không được phép"
            if word not in history_summary.nfc(gold["quote"]).casefold():
                problems.append((identifier, "allow_wording"))
        if item["kind"] == "valueless_correction":
            older = [pair for pair in item["target_turns"] if pair != gold["pair"]]
            first = text(item, older[0], "user") if older else ""
            if (
                len(older) != 1
                or is_candidate(content)
                or sentence_values(content)
                or not all(
                    token in first
                    for token in item["required"][0][:1] + item["forbidden"]
                )
            ):
                problems.append((identifier, "valueless_correction"))
        if item["kind"] == "cap_pressure":
            summary = v2_entries()[identifier]["summary"]
            older = [
                pair
                for pair in summary["listed_pairs"] + summary["over_cap_pairs"]
                if pair < gold["pair"]
            ]
            if len(older) > 1:
                problems.append((identifier, "cap_target_not_among_oldest"))
        if item["kind"] == "leading_condition":
            head, _, tail = content.partition(";")
            if (
                not history_summary.has_condition(head)
                or history_summary.nfc(gold["quote"]) not in tail
                or history_summary.has_condition(tail)
            ):
                problems.append((identifier, "leading_condition"))
    assert problems == []


def name_words(content, language):
    """Return the case-folded proper-name words of a text (capitalized letter-only tokens after the first token), plus in VI the word right before a name (its head noun)."""
    tokens = history_summary.TOKEN.findall(history_summary.expand(content))
    found = set()
    for index, token in enumerate(tokens):
        if index and token.isalpha() and token[0].isupper():
            found.add(token.casefold())
            before = tokens[index - 1]
            if language == "vi" and not (before.isalpha() and before[0].isupper()):
                found.add(before.casefold())
    return found


def test_approval_gate_distractors_stay_off_the_gated_decision():
    """In G1-G4, every authored non-target pair (user and reply) shares no content word with the gate question or gold quote beyond the gate entity's name, and at least one value-bearing non-target is a listing candidate, so an admissible distractor note cannot bear on the yes or no decision (safety check 2)."""
    problems = []
    gates = 0
    for item in corpus():
        if role(item) != "gate" or item.get("gate") != "approval":
            continue
        gates += 1
        identifier, language = item["id"], item["language"]
        asked = question(item).removesuffix(heldout.GATE_SUFFIX[language])
        quote = item["gold"]["quote"]
        decision = (
            set(history_summary.summary_tokens(asked))
            | set(history_summary.summary_tokens(quote))
        ) - (
            history_summary.SUMMARY_STOPWORDS
            | name_words(asked, language)
            | name_words(quote, language)
        )
        pool = set(heldout.FILLER[language])
        authored = [
            pair
            for pair in EARLY
            if pair not in item["target_turns"]
            and (text(item, pair, "user"), text(item, pair, "assistant")) not in pool
        ]
        for pair in authored:
            for speaker in ("user", "assistant"):
                words = set(history_summary.summary_tokens(text(item, pair, speaker)))
                if words & decision:
                    problems.append(
                        (identifier, "distractor_on_gated_decision", pair, speaker)
                    )
        if not any(
            is_candidate(text(item, pair, "user"))
            and sentence_values(text(item, pair, "user"))
            for pair in authored
        ):
            problems.append((identifier, "no_value_bearing_distractor"))
    assert problems == []
    assert gates == 4


def grouped(number, language):
    """Return a bare digit string with the case language's thousands separator."""
    return f"{int(number):,}".replace(",", GROUP_SEPARATOR[language])


def day_periods(hour, language):
    """Return the day-period markers that may follow the 12-hour form of a 24-hour hour over 12: EN pm, plain or dotted (the open 'p.m' also matches 'p.m.'); VI chiều up to 18, tối from 18 and đêm from 22, the first two also after buổi."""
    if language != "vi":
        return ("pm", "p.m")
    words = [
        word
        for word, first, last in (("chiều", 13, 18), ("tối", 18, 23), ("đêm", 22, 23))
        if first <= hour <= last
    ]
    return tuple(words + [f"buổi {word}" for word in words if word != "đêm"])


def renderings(token, language, code=False):
    """Return the other accepted renderings of one answer or stale token in the case language: the grouped form of a 4+ digit quantity (comma EN, dot VI), the hour without its leading zero, the VI hour-letter and hour-word forms, every 12-hour form of an hour over 12 with each day-period marker (VI after the hour letter, the hour word with or without the minute unit, or a colon; EN after the colon, spaced or not), and the VI decimal comma."""
    found = set()
    if re.fullmatch(r"\d{4,}", token) and not code:
        found.add(grouped(token, language))
    clock = re.fullmatch(r"(\d{2}):(\d{2})", token)
    if clock:
        hour, minute = int(clock.group(1)), clock.group(2)
        if hour < 10:
            found.add(f"{hour}:{minute}")
        if language == "vi":
            found |= {f"{hour}h{minute}", f"{hour} giờ {minute}"}
        if hour > 12:
            twelve = hour - 12
            for period in day_periods(hour, language):
                if language == "vi":
                    found |= {
                        f"{twelve}h{minute} {period}",
                        f"{twelve} giờ {minute} {period}",
                        f"{twelve} giờ {minute} phút {period}",
                        f"{twelve}:{minute} {period}",
                    }
                else:
                    found |= {
                        f"{twelve}:{minute} {period}",
                        f"{twelve}:{minute}{period}",
                    }
    if language == "vi" and re.match(r"\d+\.\d{1,2}(?!\d)", token):
        found.add(token.replace(".", ",", 1))
    return found


# Day-period markers of natural clock answers per language: (first hour, last hour, markers), with the EN capital and dotted spellings.
SPOKEN_MARKERS = dict(
    en=(
        (0, 11, ("am", "AM", "a.m.", "A.M.")),
        (12, 23, ("pm", "PM", "p.m.", "P.M.")),
    ),
    vi=(
        (0, 11, ("sáng", "buổi sáng")),
        (11, 12, ("trưa", "buổi trưa")),
        (13, 18, ("chiều", "buổi chiều")),
        (18, 23, ("tối", "buổi tối")),
        (22, 23, ("đêm",)),
    ),
)


def spoken_clock(token, language):
    """Return natural answer phrasings of an HH:MM token for score() checks, wider than the listed options: 24-hour forms with or without the leading zero and the minute unit, and 12-hour forms with each day-period marker after an hour letter, an hour word with or without the minute unit, or a colon (EN: spaced or not, dotted and capital markers)."""
    clock = re.fullmatch(r"(\d{2}):(\d{2})", token)
    if not clock:
        return set()
    hour, minute = int(clock.group(1)), clock.group(2)
    twelve = hour - 12 if hour > 12 else hour
    found = {token, f"{hour}:{minute}"}
    if language == "vi":
        found |= {
            f"{hour}h{minute}",
            f"{hour:02d}h{minute}",
            f"{hour} giờ {minute}",
            f"{hour} giờ {minute} phút",
        }
    for first, last, markers in SPOKEN_MARKERS[language]:
        if not first <= hour <= last:
            continue
        for marker in markers:
            if language == "vi":
                found |= {
                    f"{twelve}h{minute} {marker}",
                    f"{twelve} giờ {minute} {marker}",
                    f"{twelve} giờ {minute} phút {marker}",
                    f"{twelve}:{minute} {marker}",
                }
            else:
                found |= {f"{twelve}:{minute} {marker}", f"{twelve}:{minute}{marker}"}
    return found


def spoken_answer(form, language):
    """Wrap one clock phrasing in a one-line answer sentence of the case language."""
    head = "It is at" if language == "en" else "Vào lúc"
    return f"{head} {form}" + ("" if form.endswith(".") else ".")


def test_answer_renderings_in_the_case_language():
    """Every required option's accepted renderings sit in its group (grouped 4+ digit quantities unless the case's ungrouped field marks them as codes, clock forms, VI decimal comma), and every stale token that occurs in the dialogue is mirrored in the forbidden list by each of its accepted renderings, so a stale answer in any accepted form is caught."""
    problems = []
    for item in corpus():
        identifier, language = item["id"], item["language"]
        code = item.get("ungrouped", False)
        numbers = [
            token
            for token in [option for group in item["required"] for option in group]
            + item["forbidden"]
            if re.fullmatch(r"\d{4,}", token)
        ]
        # An ungrouped case has a 4+ digit answer or stale number and lists no grouped form of any of them.
        if code and (
            not numbers
            or any(grouped(token, language) in options(item) for token in numbers)
        ):
            problems.append((identifier, "ungrouped_case_inconsistent"))
        dialogue = " ".join(row["content"] for row in item["messages"][:-1])
        for group in item["required"]:
            for option in group:
                if not renderings(option, language, code) <= set(group):
                    problems.append((identifier, "answer_rendering_missing"))
        for token in item["forbidden"]:
            if token in dialogue and not renderings(token, language, code) <= set(
                item["forbidden"]
            ):
                problems.append((identifier, "stale_rendering_not_mirrored"))
    assert problems == []


def test_clock_answers_score_in_every_natural_form():
    """score() is strict for a clock answer in every natural phrasing (minute unit, day-period word after a colon or an hour word, dotted or capital EN markers), and flags as stale every such phrasing of a clock stale token that occurs in the dialogue."""
    problems = []
    checked = 0
    for item in corpus():
        identifier, language = item["id"], item["language"]
        dialogue = " ".join(row["content"] for row in item["messages"][:-1])
        reference = " ".join(group[0] for group in item["required"])
        for group in item["required"]:
            rest = [other[0] for other in item["required"] if other is not group]
            for option in group:
                for form in spoken_clock(option, language):
                    checked += 1
                    answer = " ".join([spoken_answer(form, language)] + rest)
                    if not score(answer, item)["strict"]:
                        problems.append((identifier, "clock_answer_not_strict"))
        for token in item["forbidden"]:
            if token not in dialogue:
                continue
            for form in spoken_clock(token, language):
                checked += 1
                answer = f"{reference} {spoken_answer(form, language)}"
                if not score(answer, item)["stale"]:
                    problems.append((identifier, "clock_stale_not_flagged"))
    assert sorted(set(problems), key=str) == []
    assert checked > 0


def test_questions_name_only_what_the_target_pairs_name():
    """No content word of a question occurs only in authored non-target user messages, so the question is answerable from its target pair alone (interrogatives aside)."""
    problems = []
    for item in corpus():
        pool = set(heldout.FILLER[item["language"]])
        suffix = (heldout.GATE_SUFFIX if role(item) == "gate" else heldout.SUFFIX)[
            item["language"]
        ]
        asked = (
            set(history_summary.summary_tokens(question(item).removesuffix(suffix)))
            - history_summary.SUMMARY_STOPWORDS
            - ASKING_WORDS
        )
        targets, others = set(), set()
        for pair in EARLY:
            if (text(item, pair, "user"), text(item, pair, "assistant")) in pool:
                continue
            words = set(history_summary.summary_tokens(text(item, pair, "user")))
            (targets if pair in item["target_turns"] else others).update(words)
        if asked & (others - targets):
            problems.append((item["id"], "question_word_only_in_distractors"))
    assert problems == []


def test_reference_answers_score_strict_and_stale_answers_do_not():
    """An answer built from the first option of each required group is strict; adding any forbidden token makes it not strict."""
    problems = []
    for item in corpus():
        reference = " ".join(group[0] for group in item["required"])
        if not score(reference, item)["strict"]:
            problems.append((item["id"], "reference_not_strict"))
        for group in item["required"]:
            for option in group:
                answer = " ".join(
                    [option]
                    + [other[0] for other in item["required"] if other is not group]
                )
                if not score(answer, item)["strict"]:
                    problems.append((item["id"], "option_not_strict"))
        for token in item["forbidden"]:
            if score(f"{reference} {token}", item)["strict"]:
                problems.append((item["id"], "stale_answer_strict"))
        if role(item) != "gate" and not item["forbidden"]:
            problems.append((item["id"], "no_forbidden_token"))
    assert problems == []


def test_9_hash_constant_equals_computed_hash():
    """The recorded HELDOUT_SHA256 equals digest(corpus_heldout()); it fails until the held-out hash is recorded before S0."""
    computed = history_summary.digest(heldout.corpus_heldout())
    recorded = runner.HELDOUT_SHA256
    assert recorded == computed
