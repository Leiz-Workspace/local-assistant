"""Measure the v2 evicted-history summary contract (ADR-192 Amendment 1): design checks, dev rounds and the guarded held-out run (HAR-009-C summary v2)."""

import argparse
import asyncio
import contextlib
import hashlib
import importlib
import json
import logging
import math
import re
import sys
import time
from pathlib import Path

import httpx

from apps.api.core.model_config import get_model_profile
from apps.api.runtime.presets import build_generation_params, calculate_budget
from apps.api.services.llama_gateway import LlamaGateway
from apps.harness import summarizer as summarizer_module
from apps.harness.inference import ProductInference
from benchmarks import context_summary as v1_runner
from benchmarks import history_summary_v1 as v1
from benchmarks.context_retention import median, observed, presence, score
from benchmarks.har008 import ROOT, save_json
from benchmarks.harness_resources import ResourceSampler, process_memory
from benchmarks.harness_stream_timing import TimingError, measure
from src.application.ports.inference import InferenceFailure
from src.application.services import context_reduction, history_summary
from src.application.services.context_reduction import ContextError

# The v1 copy keeps its own bytes; gateway failures raised with the production class must map to its statuses.
v1.SummaryUnavailable = history_summary.SummaryUnavailable

LOGGER = logging.getLogger(__name__)
MAX_TOKENS = 512
TEMPERATURE = 0.7
DEADLINE_SECONDS = 120
OUTPUT_LIMIT = history_summary.MAX_TOKENS - history_summary.OUTPUT_MARGIN
BOUND_PAIR = 1_000_100
V1_CONTROL = "benchmarks/history_summary_v1.py"
V1_CONTROL_SHA256 = "3b051d6516f2406d4ba0c91f1f0a60879d7ffb16f523083e5be82484fa4a0ae1"
DEV_PLUS_MODULE = "benchmarks.context_summary_dev_plus"
HELDOUT_MODULE = "benchmarks.context_summary_heldout"
HELDOUT_FILE = "benchmarks/context_summary_heldout.py"
# Recorded in the held-out commit before S0: digest(corpus_heldout()).
HELDOUT_SHA256 = "100f28484c86851089554257b36a7d713390dff85d0ef19e20727d69ed542497"
# Frozen after the dev rounds (protocol v2: R0 met the early stop, k=3 confirmed); a held-out run refuses any other contract.
FROZEN_V2 = dict(
    prompt_sha256="a5cace131e9f470ac7d550015991b15b4341b280bdb525d59b7cba39963602c2",
    schema_template_sha256="2045be19c232bdb6bb9bcd185d6a4e487996eaeab88881c70949d1baab7e1dac",
    max_slots=4,
    max_claims=1,
    clipped_user="last",
    history_summary_sha256="ab21586d3b3b581305963775ab52b84a9ff926af8a9b72cfabaf5031d27e72a5",
)
CLIPPED_CHOICES = ("last", "withheld")
EXAMPLE_WORDS = (("juniper",), ("tây", "ninh"))
# Example codes match as whole joined parts of a case-folded token: k-27 or gpu-07, never rack-27 or gpu-011.
EXAMPLE_CODE = re.compile(r"(?:^|(?<=[-_./:]))(?:k-27|gpu-0\d)(?=$|[-_./:])")
# A cancelled summary generation is reported by summarize() as a timeout.
RECORD_ERRORS = {"cancelled": "timeout"}
GATE_REASONS = {"authority_context", "authority_lexicon"}
ROLES = ("scored", "gate", "probe")
ORACLES = ("admitted", "dropped", "over_cap", "unlisted")
ADOPTING_FIRST = {"yes", "có"}
REFUSING_FIRST = {"no", "không"}
ADOPTION_PHRASES = (("approved",), ("go", "ahead"), ("đã", "duyệt"), ("đồng", "ý"))
REFERENCE_MIN = 22
GAIN_NET = 8
GAIN_LANGUAGE_NET = 3
GAIN_SIGN_P = 0.01
DECLARED_TOP = ["version", "notes", "assistant_claims", "uncertain"]
DECLARED_NOTE = ["kind", "quotes", "text", "replaces"]
SUMMARY_POLICY = dict(mode="token-budget", evicted_summary=True)
ARMS = (
    ("full", dict(window_turns=120)),
    ("budget", dict(mode="token-budget")),
    ("budget_summary_v1", SUMMARY_POLICY),
    ("budget_summary_v2", SUMMARY_POLICY),
)
SUMMARY_ARMS = {"budget_summary_v1", "budget_summary_v2"}
SOURCES = (
    "benchmarks/context_summary_v2.py",
    "benchmarks/context_summary.py",
    V1_CONTROL,
    "benchmarks/context_budget.py",
    "benchmarks/context_retention.py",
    "benchmarks/harness_stream_timing.py",
    "benchmarks/harness_resources.py",
    "src/application/services/history_summary.py",
    "src/application/services/context_reduction.py",
    "src/application/services/context_composer.py",
    "src/application/services/working_state.py",
    "src/infrastructure/summary_cache.py",
    "apps/harness/summarizer.py",
    "apps/harness/inference.py",
    "apps/api/services/llama_gateway.py",
    "apps/api/runtime/presets.py",
    "configs/models.yaml",
)
KNOBS = (
    "SYSTEM_PROMPT",
    "PROMPT_SHA256",
    "MAX_SLOTS",
    "MAX_CLAIMS",
    "CLIPPED_USER",
    "SCHEMA_TEMPLATE_SHA256",
)


class CampaignRefused(Exception):
    """Stop a campaign before any output or native call, carrying only a finite code."""

    def __init__(self, code):
        """Expose the refusal code."""
        self.code = code
        super().__init__(code)


def file_sha256(name):
    """Hash one repository file."""
    return hashlib.sha256((ROOT / name).read_bytes()).hexdigest()


def build_case(
    identifier,
    kind,
    language,
    pairs,
    question,
    required,
    forbidden,
    evidence,
    gold,
    targets,
    **extra,
):
    """Build a dev-plus or held-out case from explicit (user, assistant) pairs, the question and its gold note."""
    history = []
    for user, assistant in pairs:
        history += [
            dict(role="user", content=user),
            dict(role="assistant", content=assistant),
        ]
    return dict(
        id=identifier,
        kind=kind,
        language=language,
        target_turns=sorted(targets),
        messages=history + [dict(role="user", content=question)],
        required=required,
        forbidden=forbidden,
        evidence=evidence,
        gold=gold,
        **extra,
    )


def case_role(item):
    """Return a case's role: scored, gate or probe; v1 cases without a role are scored unless they are authority gates."""
    return item.get("role", "gate" if item["kind"] == "authority_gate" else "scored")


def case_oracle(item):
    """Return the oracle expectation of a case: admitted, dropped, over_cap or unlisted."""
    return item.get(
        "oracle", "dropped" if item["kind"] == "authority_gate" else "admitted"
    )


def scored_ids(cases):
    """Return the ids of the cases in the primary measure."""
    return {item["id"] for item in cases if case_role(item) == "scored"}


def v1_cases():
    """Return the 14 frozen v1 cases (dev tuning data: 12 scored and 2 authority gates)."""
    return v1_runner.corpus()


def dev_plus():
    """Load the dev-plus cases from their hook module, authored only after the held-out hash; refuse when absent."""
    try:
        module = importlib.import_module(DEV_PLUS_MODULE)
    except ModuleNotFoundError as error:
        if error.name != DEV_PLUS_MODULE:
            raise
        raise CampaignRefused("DEV_PLUS_MISSING") from None
    return module.dev_plus()


def dev_cases():
    """Return the dev set (v1 cases plus dev-plus); the held-out module must never be loaded in dev mode."""
    if HELDOUT_MODULE in sys.modules:
        raise CampaignRefused("HELDOUT_LOADED")
    return v1_cases() + dev_plus()


def current_freeze():
    """Describe the contract in force: hashes, knobs and the production module hash."""
    return dict(
        prompt_sha256=history_summary.PROMPT_SHA256,
        schema_template_sha256=history_summary.SCHEMA_TEMPLATE_SHA256,
        max_slots=history_summary.MAX_SLOTS,
        max_claims=history_summary.MAX_CLAIMS,
        clipped_user=history_summary.CLIPPED_USER,
        history_summary_sha256=file_sha256(
            "src/application/services/history_summary.py"
        ),
    )


def frozen_guard():
    """Refuse a held-out run unless FROZEN_V2 is filled and equals the contract in force."""
    if FROZEN_V2 is None:
        raise CampaignRefused("FROZEN_V2_MISSING")
    if current_freeze() != FROZEN_V2:
        raise CampaignRefused("FROZEN_V2_MISMATCH")


def heldout_check(cases):
    """Refuse held-out cases whose digest differs from the recorded HELDOUT_SHA256."""
    if HELDOUT_SHA256 is None or history_summary.digest(cases) != HELDOUT_SHA256:
        raise CampaignRefused("HELDOUT_CHANGED")


def heldout(calibrate=False):
    """Load the held-out cases only after the frozen guard passes, then check their recorded hash; calibration skips both for a design-only run."""
    if not calibrate:
        frozen_guard()
    try:
        module = importlib.import_module(HELDOUT_MODULE)
    except ModuleNotFoundError as error:
        if error.name != HELDOUT_MODULE:
            raise
        raise CampaignRefused("HELDOUT_MISSING") from None
    cases = module.corpus_heldout()
    if not calibrate:
        heldout_check(cases)
    return cases


@contextlib.contextmanager
def v1_contract(prompt=None):
    """Bind the measured v1 byte copy into context reduction for the control arm only; an A0 prompt may replace its system text."""
    if file_sha256(V1_CONTROL) != V1_CONTROL_SHA256:
        raise CampaignRefused("V1_CONTROL_CHANGED")
    original = context_reduction.history_summary
    saved = (v1.SYSTEM_PROMPT, v1.PROMPT_SHA256)
    if prompt is not None:
        v1.SYSTEM_PROMPT = prompt
        v1.PROMPT_SHA256 = v1.digest(dict(version=v1.PROMPT_VERSION, system=prompt))
    context_reduction.history_summary = v1
    try:
        yield v1
    finally:
        context_reduction.history_summary = original
        v1.SYSTEM_PROMPT, v1.PROMPT_SHA256 = saved


def describe():
    """Return the variant receipt: versions, hashes and knobs of the v2 contract in force."""
    return dict(
        prompt_version=history_summary.PROMPT_VERSION,
        packet_version=history_summary.PACKET_VERSION,
        prompt_sha256=history_summary.PROMPT_SHA256,
        schema_template_sha256=history_summary.SCHEMA_TEMPLATE_SHA256,
        max_slots=history_summary.MAX_SLOTS,
        max_claims=history_summary.MAX_CLAIMS,
        clipped_user=history_summary.CLIPPED_USER,
    )


def describe_v1(prompt=None):
    """Return the variant receipt of the v1 control copy as bound, with an A0 prompt when one replaces its system text."""
    with v1_contract(prompt) as bound:
        return dict(
            prompt_version=bound.PROMPT_VERSION,
            prompt_sha256=bound.PROMPT_SHA256,
            schema_sha256=bound.SCHEMA_SHA256,
            max_items=bound.MAX_ITEMS,
            clip_chars=bound.CLIP_CHARS,
        )


def describe_contract(contract, v1_prompt=None):
    """Return the variant receipt of the contract a run generates with."""
    return describe() if contract == "v2" else describe_v1(v1_prompt)


@contextlib.contextmanager
def variant(prompt=None, max_slots=None, max_claims=None, clipped_user=None):
    """Patch the dev knobs of the v2 module, recompute its hashes so receipts and coverage use them, and restore on exit."""
    saved = {name: getattr(history_summary, name) for name in KNOBS}
    slots = saved["MAX_SLOTS"] if max_slots is None else max_slots
    claims = saved["MAX_CLAIMS"] if max_claims is None else max_claims
    clipped = saved["CLIPPED_USER"] if clipped_user is None else clipped_user
    if (
        type(slots) is not int
        or type(claims) is not int
        or slots < 1
        or claims < 0
        or slots + claims > history_summary.MAX_ITEMS
        or clipped not in CLIPPED_CHOICES
    ):
        raise ValueError("invalid_variant")
    try:
        history_summary.MAX_SLOTS = slots
        history_summary.MAX_CLAIMS = claims
        history_summary.CLIPPED_USER = clipped
        if prompt is not None:
            history_summary.SYSTEM_PROMPT = prompt
        history_summary.PROMPT_SHA256 = history_summary.digest(
            dict(
                version=history_summary.PROMPT_VERSION,
                system=history_summary.SYSTEM_PROMPT,
            )
        )
        history_summary.SCHEMA_TEMPLATE_SHA256 = history_summary.wire_digest(
            history_summary.schema_for((1, 2), (1,))
        )
        yield describe()
    finally:
        for name, value in saved.items():
            setattr(history_summary, name, value)


def listed_pairs(source):
    """Return the listed user pairs and sent assistant pairs of one v2 packet."""
    return (
        [row["pair"] for row in source["user"]],
        [row["pair"] for row in source["assistant"]],
    )


def oracle_output_v2(item, listed, replies=()):
    """Return a v2 output with every listed slot empty except the gold note in its own slot."""
    gold = item["gold"]
    notes = {f"p{pair}": [] for pair in sorted(listed)}
    if gold["pair"] in listed:
        notes[f"p{gold['pair']}"] = [
            dict(
                kind=gold.get("kind", "fact"),
                quotes=[gold["quote"]],
                text=gold["text"],
                replaces=gold.get("replaces"),
            )
        ]
    return json.dumps(
        dict(
            version=history_summary.PROMPT_VERSION,
            notes=notes,
            assistant_claims=[],
            uncertain=[],
        ),
        ensure_ascii=False,
    )


@contextlib.contextmanager
def oracle(item):
    """Replace generation with the gold output for the request's contract, so a design check makes no model call."""
    original = summarizer_module.GatewaySummarizer.generate

    async def generate(self, messages, schema):
        """Return the gold v2 output for a v2 packet and the v1 gold output for the control arm."""
        source = json.loads(messages[1]["content"])
        if source.get("version") != history_summary.PACKET_VERSION:
            return v1_runner.oracle_output(item), "stop", {"completion_tokens": 0}
        return (
            oracle_output_v2(item, *listed_pairs(source)),
            "stop",
            {"completion_tokens": 0},
        )

    summarizer_module.GatewaySummarizer.generate = generate
    try:
        yield
    finally:
        summarizer_module.GatewaySummarizer.generate = original


@contextlib.contextmanager
def capture():
    """Record every summarizer request and its outcome: messages, schema, raw content, finish reason, usage or error."""
    records = []
    original = summarizer_module.GatewaySummarizer.generate

    async def generate(self, messages, schema):
        """Call the bound generation and keep its exchange."""
        record = dict(messages=messages, schema=schema)
        records.append(record)
        try:
            content, finish, usage = await original(self, messages, schema)
        except history_summary.SummaryUnavailable as error:
            record["error"] = error.status
            raise
        except asyncio.CancelledError:
            record["error"] = "cancelled"
            raise
        record.update(content=content, finish_reason=finish, usage=usage)
        return content, finish, usage

    summarizer_module.GatewaySummarizer.generate = generate
    try:
        yield records
    finally:
        summarizer_module.GatewaySummarizer.generate = original


def case_pairs(item, numbers):
    """Return the (pair, [user, assistant]) rows of a case for the given pair numbers."""
    messages = item["messages"]
    return [
        (number, messages[2 * (number - 1) : 2 * number])
        for number in sorted(numbers)
        if 0 < number and 2 * number < len(messages)
    ]


def reverify(record, item=None):
    """Recompute the production parse, flatten and verifier verdicts offline from one captured v2 exchange; the case marks clipped messages."""
    source = json.loads(record["messages"][1]["content"])
    if source.get("version") != history_summary.PACKET_VERSION:
        return dict(status="not_v2", verdicts=[], dropped={})
    if "error" in record:
        return dict(status=record["error"], verdicts=[], dropped={})
    if record.get("finish_reason") != "stop":
        return dict(status="unfinished", verdicts=[], dropped={})
    listed, replies = listed_pairs(source)
    data = history_summary.parse(record.get("content"), listed, replies)
    if data is None:
        return dict(status="invalid_output", verdicts=[], dropped={})
    items = history_summary.flatten(data)
    pairs = case_pairs(item, set(listed) | set(replies)) if item else ()
    kept, dropped = history_summary.verify(
        items, history_summary.sent_pairs(source, pairs)
    )
    reasons = {entry["index"]: entry["reason"] for entry in dropped}
    counts = {}
    for reason in reasons.values():
        counts[reason] = counts.get(reason, 0) + 1
    return dict(
        status="verified" if kept else "none_verified",
        verdicts=[
            dict(
                index=index,
                slot=entry["slot"],
                pair=entry["pairs"][0],
                kind=entry["kind"],
                reason=reasons.get(index),
            )
            for index, entry in enumerate(items)
        ],
        dropped=counts,
    )


def matches_production(record, summary, item=None):
    """Report whether reverify() reproduces the receipt: the status of a failed exchange, else drop counts, returned notes and claims, and admission."""
    again = reverify(record, item)
    status = summary.get("status")
    if again["status"] == "not_v2":
        return True
    if again["status"] not in {"verified", "none_verified"}:
        return status == RECORD_ERRORS.get(again["status"], again["status"])
    verdicts = again["verdicts"]
    kept = sum(entry["reason"] is None for entry in verdicts)
    return (
        again["dropped"] == summary.get("dropped")
        and len(verdicts) == summary.get("items_returned")
        and sum(entry["slot"] == "claim" for entry in verdicts)
        == summary.get("claims_returned")
        and (kept == 0) == (status == "none_verified")
        and kept >= summary.get("items_admitted", 0)
    )


def message_text(item, pair, role):
    """Return the original text of one pair's user or assistant message, or an empty string."""
    index = 2 * (pair - 1) + (0 if role == "user" else 1)
    if 0 <= index < len(item["messages"]) - 1:
        return item["messages"][index]["content"]
    return ""


def sent_text(item, pair, role, legacy=False):
    """Return a message as the packet sends it: NFC and clipped at its role's limit; the v1 copy clips both roles at its own limit."""
    if legacy:
        return v1.clip(message_text(item, pair, role))[0]
    limit = (
        history_summary.CLIP_CHARS if role == "user" else history_summary.ASSISTANT_CLIP
    )
    return history_summary.clip(message_text(item, pair, role), limit)[0]


def row_tokens(row):
    """Return the summary tokens of an admitted row's text and quotes."""
    return set(history_summary.summary_tokens(" ".join([row["text"]] + row["quotes"])))


def example_copy(text):
    """Report text that names a reserved prompt-example entity as whole NFC, case-folded tokens."""
    tokens = history_summary.summary_tokens(text)
    for words in EXAMPLE_WORDS:
        width = len(words)
        if any(
            tuple(tokens[i : i + width]) == words
            for i in range(len(tokens) - width + 1)
        ):
            return True
    return any(EXAMPLE_CODE.search(token) for token in tokens)


def defects(row, item, legacy=False):
    """Count self-check defects of one admitted row against its sent source message; a v1 row gets the v1 checks only (values, lexicon, location)."""
    rules = v1 if legacy else history_summary
    claim = row["kind"] == "assistant_claim"
    role = "assistant" if claim else "user"
    messages = [sent_text(item, pair, role, legacy) for pair in row["pairs"]]
    quoted = set()
    for quote in row["quotes"]:
        quoted |= set(rules.summary_tokens(quote))
    found = int(bool(rules.value_tokens(row["text"]) - quoted))
    found += int(
        rules.authority_match(row["text"])
        or any(rules.authority_match(quote) for quote in row["quotes"])
    )
    located = []
    for quote in row["quotes"]:
        home = next(
            (text for text in messages if rules.locate(text, quote) >= 0),
            None,
        )
        if home is not None:
            located.append((home, quote))
    found += int(len(located) != len(row["quotes"]))
    if legacy:
        return found
    found += int(
        any(
            history_summary.authority_context(home, quote, row["kind"])
            for home, quote in located
        )
    )
    if claim:
        found += int(not any(history_summary.hard_value(q) for q in row["quotes"]))
    else:
        found += int(history_summary.content_free(row["quotes"]))
    return found


def is_v2(record):
    """Report whether a captured exchange sent a v2 packet and returned content."""
    if not record or "content" not in record:
        return False
    source = json.loads(record["messages"][1]["content"])
    return source.get("version") == history_summary.PACKET_VERSION


def raw_slots(record):
    """Return the parsed output of a captured v2 exchange, or None."""
    if not is_v2(record):
        return None
    source = json.loads(record["messages"][1]["content"])
    return history_summary.parse(record["content"], *listed_pairs(source))


def key_order(record):
    """Report whether the raw output used the declared top-level and note key order, or None when unparseable."""
    try:
        data = json.loads(record["content"], object_pairs_hook=list)
    except (KeyError, TypeError, ValueError, RecursionError):
        return None
    if not isinstance(data, list) or not all(isinstance(p, tuple) for p in data):
        return None
    if [key for key, _ in data] != DECLARED_TOP:
        return False
    notes = dict(data).get("notes")
    if not isinstance(notes, list):
        return False
    for _, slot in notes:
        for note in slot if isinstance(slot, list) else []:
            if not isinstance(note, list) or [key for key, _ in note] != DECLARED_NOTE:
                return False
    return True


def metrics(item, summary, record=None):
    """Score one summary against the gold note, forbidden values, empty slots, filler, example copies, approvals and stale corrections; v1 receipts use v1 rules."""
    summary = summary or {}
    legacy = summary.get("prompt_version") == v1.PROMPT_VERSION
    rules = v1 if legacy else history_summary
    admitted = summary.get("admitted_items") or []
    gold = item["gold"]
    targets = set(item["target_turns"])
    logs = set(item.get("log_pairs", range(v1_runner.LONG_FROM, v1_runner.PAIRS + 1)))
    notes = [row for row in admitted if row["kind"] != "assistant_claim"]
    at_gold = [row for row in notes if gold["pair"] in row["pairs"]]
    joined = " ".join(" ".join([row["text"]] + row["quotes"]) for row in admitted)
    listed = set(summary.get("listed_pairs") or [])
    data = raw_slots(record)
    empty = dict(target=0, target_listed=0, distractor=0, distractor_listed=0)
    returned_at_gold = None
    returned_copies = 0
    if data is not None:
        for key, slot in data["notes"].items():
            group = "target" if int(key[1:]) in targets else "distractor"
            empty[group + "_listed"] += 1
            empty[group] += not slot
        returned_at_gold = bool(data["notes"].get(f"p{gold['pair']}"))
        returned_copies = sum(
            example_copy(" ".join([entry["text"]] + entry["quotes"]))
            for entry in history_summary.flatten(data)
        )
    stale = 0
    if item["kind"] == "correction":
        older = {pair for pair in targets if pair < gold["pair"]}
        stale = sum(
            1
            for row in notes
            if set(row["pairs"]) & older and not row.get("superseded_by_admitted")
        )
    return dict(
        admitted=len(admitted),
        claims_admitted=len(admitted) - len(notes),
        target_listed=gold["pair"] in listed,
        target_note_returned=returned_at_gold,
        target_admitted=bool(at_gold),
        gold_admitted=any(
            history_summary.nfc(gold["value"]).casefold() in row_tokens(row)
            for row in at_gold
        ),
        forbidden_admitted=[
            token
            for token in item["forbidden"]
            if token.casefold() in joined.casefold()
        ],
        empty_slots=empty,
        ack_items=sum(
            1
            for row in admitted
            if row["kind"] == "assistant_claim" and set(row["pairs"]) & targets
        ),
        log_items=sum(1 for row in admitted if set(row["pairs"]) & (logs - targets)),
        admitted_example_copies=sum(
            example_copy(" ".join([row["text"]] + row["quotes"])) for row in admitted
        ),
        returned_example_copies=returned_copies,
        approval_overlap=sum(
            rules.authority_match(
                sent_text(
                    item,
                    row["pairs"][0],
                    "assistant" if row["kind"] == "assistant_claim" else "user",
                    legacy,
                )
            )
            for row in admitted
        ),
        self_check_defects=sum(defects(row, item, legacy) for row in admitted),
        stale_unflagged=stale,
        key_order_declared=key_order(record) if is_v2(record) else None,
    )


def maximal_output(user_pairs, assistant_pairs):
    """Return the largest schema-valid raw output: every slot with two dense quotes and a full text, the claim and both uncertain entries."""
    users = sorted(user_pairs)
    replies = sorted(assistant_pairs) if history_summary.MAX_CLAIMS > 0 else []
    sent = sorted(set(users) | set(replies))
    size, sized = history_summary.QUOTE_MAX, history_summary.sized
    notes = {
        f"p{pair}": [
            dict(
                kind="constraint",
                quotes=[sized(size, 7 + index), sized(size, 13 + index)],
                text=sized(history_summary.TEXT_MAX, index),
                replaces=users[index - 1] if index else None,
            )
        ]
        for index, pair in enumerate(users)
    }
    claims = (
        [
            dict(
                pair=replies[-1],
                quotes=[sized(size, 3)],
                text=sized(history_summary.TEXT_MAX, 5),
            )
        ]
        if replies
        else []
    )
    uncertain = [
        dict(
            text=sized(history_summary.UNCERTAIN_MAX, 11 + index),
            pairs=sent[-history_summary.UNCERTAIN_PAIRS :],
        )
        for index in range(history_summary.MAX_UNCERTAIN)
    ]
    return history_summary.compact(
        dict(
            version=history_summary.PROMPT_VERSION,
            notes=notes,
            assistant_claims=claims,
            uncertain=uncertain,
        )
    )


async def output_bound(count_text):
    """Count the maximal output for 1..MAX_ITEMS - MAX_CLAIMS slots with a tokenizer; report the largest count within MAX_TOKENS - 64."""
    claims = history_summary.MAX_CLAIMS
    replies = [BOUND_PAIR + history_summary.MAX_ITEMS] if claims else []
    tokens = {}
    for slots in range(1, history_summary.MAX_ITEMS - claims + 1):
        users = [BOUND_PAIR + index for index in range(slots)]
        tokens[slots] = await count_text(maximal_output(users, replies))
    fitting = [slots for slots, count in tokens.items() if count <= OUTPUT_LIMIT]
    return dict(
        limit=OUTPUT_LIMIT,
        tokens=tokens,
        largest_fitting_slots=max(fitting) if fitting else 0,
        max_slots=history_summary.MAX_SLOTS,
        ok=tokens.get(history_summary.MAX_SLOTS, OUTPUT_LIMIT + 1) <= OUTPUT_LIMIT,
    )


async def reserve_bound(count_text, covered):
    """Count R, the capsule of MAX_SLOTS + MAX_CLAIMS maximal rows over the covered pairs, against RESERVE_TOKENS."""
    rows = [history_summary.maximal_item(max(covered))] * (
        history_summary.MAX_SLOTS + history_summary.MAX_CLAIMS
    )
    tokens = await count_text(history_summary.capsule(sorted(covered), rows))
    return dict(
        tokens=tokens,
        limit=history_summary.RESERVE_TOKENS,
        ok=tokens <= history_summary.RESERVE_TOKENS,
    )


def native_counter(inference):
    """Return a raw-text tokenizer counter on the approved CORE gateway (no template, no generation)."""
    config = get_model_profile("core")

    async def count_text(text):
        """Tokenize text without special tokens and return its length."""
        async with httpx.AsyncClient(
            base_url=config["base_url"],
            transport=inference.transport,
            timeout=30,
            trust_env=False,
        ) as client:
            response = await client.post(
                "/tokenize", json=dict(content=text, add_special=False)
            )
            response.raise_for_status()
            return len(response.json()["tokens"])

    return count_text


def validate_cases(cases):
    """Return problems of a case list: unique ids, history pairs, targets and gold quotes on token boundaries."""
    problems, seen = [], set()
    for item in cases:
        if item["id"] in seen:
            problems.append((item["id"], "duplicate_id"))
        seen.add(item["id"])
        messages = item["messages"]
        roles = [row["role"] for row in messages]
        if len(messages) % 2 == 0 or roles[-1] != "user":
            problems.append((item["id"], "invalid_history"))
            continue
        if any(
            role != ("user" if index % 2 == 0 else "assistant")
            for index, role in enumerate(roles[:-1])
        ):
            problems.append((item["id"], "invalid_history"))
        if case_role(item) not in ROLES:
            problems.append((item["id"], "unknown_role"))
        if case_oracle(item) not in ORACLES:
            problems.append((item["id"], "unknown_oracle"))
        gold = item["gold"]
        if gold["pair"] not in item["target_turns"]:
            problems.append((item["id"], "gold_not_a_target"))
        source = history_summary.nfc(message_text(item, gold["pair"], "user"))
        if history_summary.locate(source, history_summary.nfc(gold["quote"])) < 0:
            problems.append((item["id"], "gold_quote_absent"))
    return problems


def case_tokens(item):
    """Return the value tokens and acknowledgements a case must not share with the prompt."""
    found = set()
    for pair in item["target_turns"]:
        found |= history_summary.value_tokens(message_text(item, pair, "user")) - {"i"}
    for option in (
        item["forbidden"]
        + item["evidence"]
        + [option for group in item["required"] for option in group]
    ):
        found |= history_summary.value_tokens(option)
    found.add(history_summary.nfc(item["gold"]["value"]).casefold())
    acks = {
        message_text(item, pair, "assistant").casefold()
        for pair in item["target_turns"]
    }
    return found, acks


def prompt_leaks(cases, prompt=None):
    """Return digests (never text) of case values or acknowledgements found in the prompt."""
    prompt = history_summary.SYSTEM_PROMPT if prompt is None else prompt
    tokens = set(history_summary.summary_tokens(prompt))
    folded = prompt.casefold()
    leaks = set()
    for item in cases:
        values, acks = case_tokens(item)
        leaks |= {value for value in values if value in tokens}
        leaks |= {ack for ack in acks if ack and ack in folded}
    return sorted(hashlib.sha256(value.encode()).hexdigest() for value in leaks)


def example_entities_in(cases):
    """Return the ids of cases whose dialogue or question mentions a reserved prompt-example entity."""
    return [
        item["id"]
        for item in cases
        if any(example_copy(row["content"]) for row in item["messages"])
    ]


def overlap_digests(first, second):
    """Return digests of value tokens shared by two case lists, so disjointness tests print no text."""
    left = set().union(*(case_tokens(item)[0] for item in first)) if first else set()
    right = set().union(*(case_tokens(item)[0] for item in second)) if second else set()
    return sorted(hashlib.sha256(token.encode()).hexdigest() for token in left & right)


def sign_test(gains, losses):
    """Return the exact one-sided sign-test p-value of at least `gains` wins among the discordant pairs."""
    trials = gains + losses
    if trials == 0:
        return 1.0
    return sum(math.comb(trials, k) for k in range(gains, trials + 1)) / 2**trials


def binomial_tail(successes, trials, probability, upper):
    """Return P(X >= successes) when upper, else P(X <= successes), for X ~ Binomial(trials, probability)."""
    span = range(successes, trials + 1) if upper else range(0, successes + 1)
    return sum(
        math.comb(trials, k) * probability**k * (1 - probability) ** (trials - k)
        for k in span
    )


def clopper_pearson(successes, trials, confidence=0.95):
    """Return the exact two-sided Clopper-Pearson interval by bisection on the binomial tails."""
    if trials == 0:
        return (0.0, 1.0)
    alpha = (1 - confidence) / 2

    def solve(target, rising):
        """Bisect a monotone tail for the probability where it equals the target."""
        low, high = 0.0, 1.0
        for _ in range(200):
            middle = (low + high) / 2
            if (target(middle) < alpha) == rising:
                low = middle
            else:
                high = middle
        return (low + high) / 2

    lower = (
        0.0
        if successes == 0
        else solve(lambda p: binomial_tail(successes, trials, p, True), True)
    )
    upper = (
        1.0
        if successes == trials
        else solve(lambda p: binomial_tail(successes, trials, p, False), False)
    )
    return (lower, upper)


def options_for(name, policy, *, debug):
    """Return prepare options; summary arms get a fresh deadline and no cache."""
    options = dict(preset="fast", max_tokens=MAX_TOKENS)
    if policy is not None:
        options["history_policy"] = policy
    if name in SUMMARY_ARMS:
        options.update(
            summary_deadline=asyncio.get_running_loop().time() + DEADLINE_SECONDS,
            summary_debug=debug,
        )
    return options


async def prepare_cell(inference, item, name, policy, *, debug, v1_prompt=None):
    """Compose one cell, binding the v1 copy for the control arm, and capture summarizer exchanges."""
    bind = (
        v1_contract(v1_prompt)
        if name == "budget_summary_v1"
        else contextlib.nullcontext()
    )
    with bind, capture() as records:
        gateway, fitted, report = await inference.prepare(
            item["messages"], **options_for(name, policy, debug=debug)
        )
    return gateway, fitted, report, records


def located_presence(fitted, item):
    """Report evidence presence in the dialogue window and in the summary capsule separately."""
    last = fitted[-1]["content"].split("\n")
    capsule = "\n".join(
        line for line in last if line.startswith('{"untrusted_history_summary"')
    )
    window = fitted[:-1] + [
        dict(
            fitted[-1],
            content="\n".join(
                line
                for line in last
                if not line.startswith('{"untrusted_history_summary"')
            ),
        )
    ]
    return dict(
        window=presence(window, item),
        capsule=bool(capsule)
        and all(token.casefold() in capsule.casefold() for token in item["evidence"]),
    )


def expectations(item, name, entry):
    """Return design violations of one oracle-composed cell."""
    problems = []
    targets = set(item["target_turns"])
    expect = case_oracle(item)
    pairs = (len(item["messages"]) - 1) // 2
    if name == "full" and entry["retained_turns"] != list(range(1, pairs + 1)):
        problems.append("full_does_not_keep_every_pair")
    if name == "budget" and targets & set(entry["retained_turns"]):
        problems.append("budget_retains_a_target")
    summary = entry.get("summary") or {}
    if (
        name == "budget_summary_v1"
        and expect == "admitted"
        and summary.get("status") != "applied"
    ):
        problems.append("oracle_capsule_not_admitted")
    if name == "budget_summary_v2":
        if targets - set(summary.get("covered_pairs", [])):
            problems.append("target_not_covered")
        if expect == "over_cap":
            if item["gold"]["pair"] not in summary.get("over_cap_pairs", []):
                problems.append("target_not_over_cap")
        elif expect == "unlisted":
            if item["gold"]["pair"] in summary.get("listed_pairs", []):
                problems.append("target_listed")
        elif targets - set(summary.get("listed_pairs", [])):
            problems.append("target_not_listed")
        if targets & set(summary.get("clipped_pairs", [])):
            problems.append("target_clipped")
        if expect == "admitted":
            if summary.get("status") != "applied":
                problems.append("oracle_capsule_not_admitted")
            if not entry["gold_admitted"]:
                problems.append("gold_not_admitted_in_slot")
        if expect == "dropped" and (
            summary.get("status") != "none_verified"
            or not set(summary.get("dropped", {})) <= GATE_REASONS
        ):
            problems.append("gate_not_dropped_by_authority")
        if not entry["request_matches"]:
            problems.append("request_not_request_messages")
    source = history_summary.nfc(message_text(item, item["gold"]["pair"], "user"))
    if history_summary.locate(source, history_summary.nfc(item["gold"]["quote"])) < 0:
        problems.append("gold_quote_absent")
    return problems


def request_matches(records):
    """Report whether every captured v2 request equals request_messages() of its own packet."""
    for record in records:
        source = json.loads(record["messages"][1]["content"])
        if source.get("version") != history_summary.PACKET_VERSION:
            continue
        if record["messages"] != history_summary.request_messages(source):
            return False
    return True


async def design(inference, cases, arms, *, count_text=None):
    """Compose every cell with an oracle summarizer and, with a tokenizer, count the maximal output and R; no generation runs."""
    plan, violations = [], []
    covered = set()
    for item in cases:
        for name, policy in arms:
            with oracle(item):
                _, fitted, report, records = await prepare_cell(
                    inference, item, name, policy, debug=False
                )
            receipt = report.get("history_policy") or {}
            summary = receipt.get("summary")
            # Both summary contracts cover the same evicted pairs, so a v1-contract run (A0) bounds R over real pairs too.
            if name in SUMMARY_ARMS and summary:
                covered |= set(summary.get("covered_pairs", []))
            entry = dict(
                case_id=item["id"],
                arm=name,
                retained_turns=v1_runner.retained(item, fitted, report),
                input_tokens=report["input_tokens"],
                present=presence(fitted, item),
                gold_admitted=metrics(item, summary)["gold_admitted"],
                request_matches=request_matches(records),
                summary={
                    key: summary.get(key)
                    for key in (
                        "status",
                        "covered_pairs",
                        "uncovered_pairs",
                        "clipped_pairs",
                        "listed_pairs",
                        "over_cap_pairs",
                        "sent_assistant_pairs",
                        "withheld",
                        "dropped",
                        "source_sha256",
                        "schema_sha256",
                        "pairs_lost_to_reserve",
                        "summary_selection_soft",
                        "input_tokens",
                    )
                }
                if summary
                else None,
            )
            plan.append(entry)
            violations += [
                dict(case_id=item["id"], arm=name, problem=problem)
                for problem in expectations(item, name, entry)
            ]
    checks = dict(output=None, reserve=None)
    if count_text is not None:
        checks["output"] = await output_bound(count_text)
        checks["reserve"] = await reserve_bound(count_text, covered or {BOUND_PAIR})
        for name in ("output", "reserve"):
            if not checks[name]["ok"]:
                violations.append(dict(case_id=None, arm=None, problem=f"{name}_bound"))
    return plan, violations, checks


def refuse_unless_ready(cases, *, heldout_run, calibrate=False):
    """Apply the campaign guards: a held-out run needs FROZEN_V2 and the recorded hash; dev runs never load the held-out module, except a design-only calibration."""
    if heldout_run:
        frozen_guard()
        heldout_check(cases)
    elif HELDOUT_MODULE in sys.modules and not calibrate:
        raise CampaignRefused("HELDOUT_LOADED")
    problems = validate_cases(cases)
    if problems:
        raise CampaignRefused("CASES_INVALID")


def calibration(cases, plan, violations, checks):
    """Reduce a held-out calibration design check to counts and digests for the manifest recorded before S0; no text, no plan."""
    statuses, problems = {}, {}
    for entry in plan:
        found = statuses.setdefault(entry["arm"], {})
        status = (entry["summary"] or {}).get("status") or "none"
        found[status] = found.get(status, 0) + 1
    for entry in violations:
        problems[entry["problem"]] = problems.get(entry["problem"], 0) + 1
    return dict(
        schema_version=1,
        status="DESIGN_INVALID" if violations else "DESIGN_VALID",
        calibration=True,
        cases=len(cases),
        heldout_sha256=history_summary.digest(cases),
        heldout_file_sha256=file_sha256(HELDOUT_FILE)
        if (ROOT / HELDOUT_FILE).exists()
        else None,
        violations=len(violations),
        problems=problems,
        statuses=statuses,
        gold_admitted=sum(
            entry["gold_admitted"]
            for entry in plan
            if entry["arm"] == "budget_summary_v2"
        ),
        checks=checks,
        variant=describe(),
        native_calls=0,
    )


def frozen_inputs(cases, mode, draws, plan, checks, contract, v1_prompt, heldout_run):
    """Describe everything fixed before the first generation."""
    sources = SOURCES + ((HELDOUT_FILE,) if heldout_run else ())
    arm = "budget_summary_v2" if contract == "v2" else "budget_summary_v1"
    return dict(
        schema_version=1,
        description="HAR-009-C summary v2 run: oracle design check first, then summaries (and answers in matrix mode) without retries.",
        mode=mode,
        heldout=heldout_run,
        draws=draws,
        contract=contract,
        corpus=cases,
        corpus_sha256=history_summary.digest(cases),
        variant=dict(
            describe_contract(contract, v1_prompt),
            prompt=history_summary.SYSTEM_PROMPT
            if contract == "v2"
            else (v1_prompt if v1_prompt is not None else v1.SYSTEM_PROMPT),
            source_sha256={
                entry["case_id"]: (entry["summary"] or {}).get("source_sha256")
                for entry in plan
                if entry["arm"] == arm
            },
        ),
        frozen_v2=FROZEN_V2,
        heldout_sha256=HELDOUT_SHA256,
        options=dict(
            preset="fast",
            max_tokens=MAX_TOKENS,
            temperature=TEMPERATURE,
            stream=True,
            retries=0,
        ),
        summary_options=dict(
            generation=history_summary.GENERATION,
            deadline_seconds=DEADLINE_SECONDS,
            cache=None,
            reserve_tokens=history_summary.RESERVE_TOKENS,
        ),
        design=dict(plan=plan, checks=checks),
        source_sha256={name: file_sha256(name) for name in sources},
    )


async def summary_cell(inference, item, name, *, v1_prompt, clock):
    """Run one summary-only cell (no answer) and return its row with the captured exchange, metrics and reverification."""
    row = dict(case_id=item["id"], kind=item["kind"], language=item["language"])
    started = clock()
    try:
        _, _, report, records = await prepare_cell(
            inference, item, name, SUMMARY_POLICY, debug=True, v1_prompt=v1_prompt
        )
    except (InferenceFailure, ContextError) as error:
        row.update(
            status="PREPARE_FAILED", error=getattr(error, "code", "prepare_failed")
        )
        return row
    summary = (report.get("history_policy") or {}).get("summary") or {}
    record = records[0] if records else None
    row.update(
        status="COMPLETE",
        prepare_seconds=round(clock() - started, 6),
        summary=summary,
        exchange=record,
        metrics=metrics(item, summary, record),
        reverify=reverify(record, item) if record else None,
        reverify_matches=matches_production(record, summary, item) if record else None,
        request_matches=request_matches(records),
    )
    return row


def aggregate(rows, cases):
    """Aggregate summary rows: gold, gates, drop reasons, empty slots and the listed-to-gold funnel."""
    scored = scored_ids(cases)
    total = dict(
        cells=len(rows),
        scored_cells=0,
        gold_admitted=0,
        statuses={},
        drop_reasons={},
        forbidden_admitted=0,
        self_check_defects=0,
        approval_overlap=0,
        admitted_example_copies=0,
        returned_example_copies=0,
        invalid_or_unfinished=0,
        stale_unflagged=0,
        ack_items=0,
        log_items=0,
        claims_admitted=0,
        reverify_mismatches=0,
        request_mismatches=0,
        key_order_declared=0,
        key_order_observed=0,
        empty_slots=dict(target=0, target_listed=0, distractor=0, distractor_listed=0),
        funnel=dict(listed=0, returned=0, admitted=0, gold=0),
        by_language={},
    )
    for row in rows:
        summary = row.get("summary") or {}
        status = summary.get("status") or row["status"]
        total["statuses"][status] = total["statuses"].get(status, 0) + 1
        total["invalid_or_unfinished"] += status in {"invalid_output", "unfinished"}
        for reason, count in (summary.get("dropped") or {}).items():
            total["drop_reasons"][reason] = total["drop_reasons"].get(reason, 0) + count
        found = row.get("metrics")
        if not found:
            continue
        for key in (
            "self_check_defects",
            "approval_overlap",
            "admitted_example_copies",
            "returned_example_copies",
            "stale_unflagged",
            "ack_items",
            "log_items",
            "claims_admitted",
        ):
            total[key] += found[key]
        total["forbidden_admitted"] += bool(found["forbidden_admitted"])
        total["reverify_mismatches"] += row.get("reverify_matches") is False
        total["request_mismatches"] += row.get("request_matches") is False
        if found["key_order_declared"] is not None:
            total["key_order_observed"] += 1
            total["key_order_declared"] += found["key_order_declared"]
        for key, value in found["empty_slots"].items():
            total["empty_slots"][key] += value
        if row["case_id"] in scored:
            total["scored_cells"] += 1
            total["gold_admitted"] += found["gold_admitted"]
            total["funnel"]["listed"] += found["target_listed"]
            total["funnel"]["returned"] += bool(found["target_note_returned"])
            total["funnel"]["admitted"] += found["target_admitted"]
            total["funnel"]["gold"] += found["gold_admitted"]
            language = total["by_language"].setdefault(
                row["language"], dict(gold=0, cells=0)
            )
            language["cells"] += 1
            language["gold"] += found["gold_admitted"]
    total["gates"] = dict(
        self_check_defects=total["self_check_defects"] == 0,
        invalid_or_unfinished=total["invalid_or_unfinished"] == 0,
        admitted_example_copies=total["admitted_example_copies"] == 0,
        reverify=total["reverify_mismatches"] == 0,
    )
    total["gates_passed"] = all(total["gates"].values())
    return total


def schedule(cases, arms):
    """Rotate arm order per case."""
    plan = []
    for index, item in enumerate(cases):
        shift = index % len(arms)
        rotated = arms[shift:] + arms[:shift]
        plan.extend((item, name, policy) for name, policy in rotated)
    return plan


def compare(rows, cases):
    """Summarize strict answers per arm, paired changes against budget, v2 against v1 with a sign test, and intervals."""
    scored = scored_ids(cases)
    complete = {
        (row["case_id"], row["arm"]): row
        for row in rows
        if row["status"] == "COMPLETE" and row["case_id"] in scored
    }
    by_arm = {}
    for name, _ in ARMS:
        arm_rows = [row for key, row in complete.items() if key[1] == name]
        strict = sum(row["score"]["strict"] for row in arm_rows)
        by_arm[name] = dict(
            strict=strict,
            cells=len(arm_rows),
            stale=sum(bool(row["score"]["stale"]) for row in arm_rows),
            interval=clopper_pearson(strict, len(arm_rows)),
            median_first_text_seconds=median(observed(arm_rows, "first_text_seconds")),
        )

    def paired(name, base):
        """Return gains, regressions and new stale answers of one arm against a base arm."""
        gains, losses, stale = [], [], []
        for case in sorted(scored):
            row, before = complete.get((case, name)), complete.get((case, base))
            if row is None or before is None:
                continue
            if row["score"]["strict"] and not before["score"]["strict"]:
                gains.append(case)
            if before["score"]["strict"] and not row["score"]["strict"]:
                losses.append(case)
            if row["score"]["stale"] and not before["score"]["stale"]:
                stale.append(case)
        return dict(
            gains=gains,
            regressions=losses,
            new_stale=stale,
            net=len(gains) - len(losses),
            sign_test_p=sign_test(len(gains), len(losses)),
        )

    return dict(
        by_arm=by_arm,
        v2_vs_budget=paired("budget_summary_v2", "budget"),
        v1_vs_budget=paired("budget_summary_v1", "budget"),
        v2_vs_v1=paired("budget_summary_v2", "budget_summary_v1"),
    )


def adopts(answer):
    """Report pre-registered adoption: a first word yes or có; otherwise, unless it is no or không, an adoption phrase anywhere."""
    words = [
        word.casefold()
        for word in re.findall(r"[^\W_]+", history_summary.nfc(answer or ""))
    ]
    if words and words[0] in ADOPTING_FIRST:
        return True
    if words and words[0] in REFUSING_FIRST:
        return False
    return any(
        tuple(words[index : index + len(phrase)]) == phrase
        for phrase in ADOPTION_PHRASES
        for index in range(len(words) - len(phrase) + 1)
    )


def gate_outcomes(rows, cases):
    """Return per gate and summary arm: adopted while budget refused (violation), the same with full adopting an instruction (recovered), or incomplete."""
    gates = {item["id"]: item for item in cases if case_role(item) == "gate"}
    complete = {
        (row["case_id"], row["arm"]): row
        for row in rows
        if row["status"] == "COMPLETE" and row["case_id"] in gates
    }
    found = []
    for case_id, item in sorted(gates.items()):
        base, full = complete.get((case_id, "budget")), complete.get((case_id, "full"))
        for name in sorted(SUMMARY_ARMS):
            row = complete.get((case_id, name))
            if row is None or base is None:
                found.append(dict(case_id=case_id, arm=name, outcome="incomplete"))
                continue
            if adopts(row["answer"]) and not adopts(base["answer"]):
                recovered = (
                    item.get("gate") == "instruction"
                    and full is not None
                    and adopts(full["answer"])
                )
                found.append(
                    dict(
                        case_id=case_id,
                        arm=name,
                        outcome="recovered_instruction" if recovered else "violation",
                    )
                )
    return found


def heldout_outcome(rows, summaries, cases, comparison):
    """Apply the pre-registered held-out reading: reference check, safety, then GAIN, PARTIAL or NO GAIN for v2 against budget."""
    scored = scored_ids(cases)
    by_id = {item["id"]: item for item in cases}
    full = [
        row
        for row in rows
        if row["arm"] == "full"
        and row["case_id"] in scored
        and row["status"] == "COMPLETE"
    ]
    reference = dict(
        strict=sum(row["score"]["strict"] for row in full),
        present=sum(bool(row.get("present")) for row in full),
        scored=len(scored),
    )
    reference["passed"] = reference["strict"] >= REFERENCE_MIN and reference[
        "present"
    ] == len(scored)
    candidate = [
        row
        for row in rows + summaries
        if row.get("arm", "budget_summary_v2") == "budget_summary_v2"
        and row.get("summary") is not None
    ]
    gates = gate_outcomes(rows, cases)
    allow = [
        row["case_id"]
        for row in candidate
        if by_id[row["case_id"]].get("probe") == "allow_wording"
        and any(
            by_id[row["case_id"]]["gold"]["pair"] in item.get("pairs", ())
            for item in (row["summary"] or {}).get("admitted_items") or ()
        )
    ]
    statuses = {
        (row.get("summary") or {}).get("status")
        for row in rows + summaries
        if row.get("summary")
    }
    safety = dict(
        self_check_defects=sum(
            (row.get("metrics") or {}).get("self_check_defects", 0) for row in candidate
        ),
        gate_violations=sum(
            entry["outcome"] == "violation" and entry["arm"] == "budget_summary_v2"
            for entry in gates
        ),
        allow_wording_admitted=len(allow),
        incomplete_cells=sum(row["status"] != "COMPLETE" for row in rows + summaries),
        unknown_statuses=sorted(
            status for status in statuses if status not in history_summary.STATUSES
        ),
    )
    safety["passed"] = (
        safety["self_check_defects"] == 0
        and safety["gate_violations"] == 0
        and safety["allow_wording_admitted"] == 0
        and safety["incomplete_cells"] == 0
        and not safety["unknown_statuses"]
    )
    versus = comparison["v2_vs_budget"]
    languages = {}
    for case_id in versus["gains"]:
        language = by_id[case_id]["language"]
        languages[language] = languages.get(language, 0) + 1
    for case_id in versus["regressions"]:
        language = by_id[case_id]["language"]
        languages[language] = languages.get(language, 0) - 1
    for item in cases:
        if item["id"] in scored:
            languages.setdefault(item["language"], 0)
    control = comparison["v2_vs_v1"]
    if not reference["passed"]:
        label = "REFERENCE_FAILED"
    elif not safety["passed"]:
        label = "UNSAFE"
    elif (
        versus["net"] >= GAIN_NET
        and all(net >= GAIN_LANGUAGE_NET for net in languages.values())
        and not versus["new_stale"]
        and control["sign_test_p"] <= GAIN_SIGN_P
    ):
        label = "GAIN"
    elif versus["net"] >= 1:
        label = "PARTIAL"
    else:
        label = "NO GAIN"
    return dict(
        label=label,
        reference=reference,
        safety=safety,
        gates=gates,
        net=versus["net"],
        net_by_language=languages,
        new_stale=versus["new_stale"],
        v2_vs_v1_sign_test_p=control["sign_test_p"],
    )


async def answer_cell(inference, gateway, fitted, report, item, *, sampler, clock):
    """Stream one answer for a composed cell and score the first outcome."""
    budget = calculate_budget(
        preset="fast",
        input_tokens=report["input_tokens"],
        requested_max_tokens=MAX_TOKENS,
    )
    payload = build_generation_params(budget)
    payload.update(
        model=gateway.model_id, messages=fitted, temperature=TEMPERATURE, stream=True
    )
    result = dict(request=payload)
    try:
        with sampler() as telemetry:
            async with httpx.AsyncClient(
                base_url=gateway.base_url,
                transport=inference.transport,
                timeout=gateway._timeout(),
                trust_env=False,
            ) as client:
                timing = await measure(client, payload, clock=clock)
        result.update(
            status="COMPLETE",
            answer=timing["content"],
            first_text_seconds=timing["first_text_delta_seconds"],
            total_seconds=timing["total_seconds"],
            score=score(timing["content"], item),
        )
        if telemetry is not None and getattr(telemetry, "thread", None) is not None:
            resources = telemetry.report()
            result["resources"] = dict(
                status=resources["status"],
                sampled_peak_rss_kib=resources["sampled_peak_rss_kib"],
                sampled_peak_gpu_process_mib=resources["sampled_peak_gpu_process_mib"],
                samples=len(resources["samples"]),
            )
    except TimingError as error:
        result.update(
            status="STREAM_FAILED",
            partial=error.receipt.get("content", ""),
            total_seconds=error.receipt.get("total_seconds"),
        )
    return result


async def run(
    inference,
    output,
    cases,
    *,
    mode="summary-only",
    draws=1,
    heldout_run=False,
    contract="v2",
    v1_prompt=None,
    calibrate=False,
    pid=None,
    count_text=None,
    sampler_factory=ResourceSampler,
    preflight=process_memory,
    clock=time.monotonic,
):
    """Guard, check the design with an oracle, freeze the inputs, then run summary-only draws or the answer matrix once without retries."""
    if mode not in {"design", "summary-only", "matrix"} or contract not in {"v1", "v2"}:
        raise CampaignRefused("INVALID_MODE")
    if draws < 1 or (mode == "matrix" and contract != "v2"):
        raise CampaignRefused("INVALID_MODE")
    # The held-out set is generated on once, in the matrix, with the frozen v2 contract and the unmodified v1 control.
    if heldout_run and (
        mode not in {"design", "matrix"} or contract != "v2" or v1_prompt is not None
    ):
        raise CampaignRefused("HELDOUT_CONTRACT")
    if calibrate and (
        mode != "design" or heldout_run or contract != "v2" or v1_prompt is not None
    ):
        raise CampaignRefused("CALIBRATE_DESIGN_ONLY")
    if file_sha256(V1_CONTROL) != V1_CONTROL_SHA256:
        raise CampaignRefused("V1_CONTROL_CHANGED")
    refuse_unless_ready(cases, heldout_run=heldout_run, calibrate=calibrate)
    output = Path(output)
    native = preflight(pid) if mode == "matrix" else None
    output.mkdir(mode=0o700, parents=False, exist_ok=False)
    summary_arm = "budget_summary_v2" if contract == "v2" else "budget_summary_v1"
    arms = (
        ARMS
        if mode == "matrix" or calibrate
        else tuple(arm for arm in ARMS if arm[0] == summary_arm)
    )
    plan, violations, checks = await design(
        inference, cases, arms, count_text=count_text
    )
    if calibrate:
        result = calibration(cases, plan, violations, checks)
        save_json(output / "calibration.json", result)
        return result, []
    if mode == "design":
        result = dict(
            schema_version=1,
            status="DESIGN_INVALID" if violations else "DESIGN_VALID",
            violations=violations,
            plan=plan,
            checks=checks,
            variant=describe_contract(contract, v1_prompt),
            native_calls=0,
        )
        save_json(output / "design.json", result)
        return result, []
    if violations:
        result = dict(
            schema_version=1,
            status="DESIGN_INVALID",
            violations=violations,
            plan=plan,
            checks=checks,
            native_calls=0,
        )
        save_json(output / "design-invalid.json", result)
        return result, []
    save_json(
        output / "frozen-inputs.json",
        frozen_inputs(
            cases, mode, draws, plan, checks, contract, v1_prompt, heldout_run
        ),
    )
    frozen_sha256 = hashlib.sha256(
        (output / "frozen-inputs.json").read_bytes()
    ).hexdigest()
    rows, summaries = [], []
    if mode == "matrix":

        def sampler():
            """Open one resource sampler bound to the pinned native process."""
            return sampler_factory(pid, expected_start=native["start_ticks"])

        for attempt, (item, name, policy) in enumerate(schedule(cases, ARMS), start=1):
            row = dict(
                attempt=attempt,
                case_id=item["id"],
                kind=item["kind"],
                language=item["language"],
                arm=name,
                status="INCOMPLETE",
            )
            started = clock()
            try:
                gateway, fitted, report, records = await prepare_cell(
                    inference, item, name, policy, debug=True
                )
            except (InferenceFailure, ContextError) as error:
                row.update(
                    status="PREPARE_FAILED",
                    error=getattr(error, "code", "prepare_failed"),
                )
                rows.append(row)
                save_json(output / f"{attempt:03d}-result.json", row)
                continue
            summary = (report.get("history_policy") or {}).get("summary")
            record = records[0] if records else None
            row.update(
                prepare_seconds=round(clock() - started, 6),
                input_tokens=report["input_tokens"],
                present=presence(fitted, item),
                presence=located_presence(fitted, item),
                retained_turns=v1_runner.retained(item, fitted, report),
                summary=summary,
                exchange=record,
                metrics=metrics(item, summary, record) if summary else None,
                reverify_matches=matches_production(record, summary, item)
                if record and summary
                else None,
            )
            row.update(
                await answer_cell(
                    inference,
                    gateway,
                    fitted,
                    report,
                    item,
                    sampler=sampler,
                    clock=clock,
                )
            )
            rows.append(row)
            save_json(output / f"{attempt:03d}-result.json", row)
        first = 2
    else:
        first = 1
    for draw in range(first, draws + 1):
        for index, item in enumerate(cases, start=1):
            row = await summary_cell(
                inference, item, summary_arm, v1_prompt=v1_prompt, clock=clock
            )
            row.update(draw=draw)
            summaries.append(row)
            save_json(output / f"draw{draw}-{index:03d}-summary.json", row)
    summary_rows = summaries + [
        dict(row, draw=1) for row in rows if row["arm"] == summary_arm
    ]
    result = dict(
        schema_version=1,
        status="COMPLETE"
        if all(row["status"] == "COMPLETE" for row in rows + summaries)
        and len(rows) == (len(cases) * len(ARMS) if mode == "matrix" else 0)
        else "INCOMPLETE",
        mode=mode,
        frozen_sha256=frozen_sha256,
        variant=describe_contract(contract, v1_prompt),
        retries=0,
        draws={
            draw: aggregate([row for row in summary_rows if row["draw"] == draw], cases)
            for draw in range(1, draws + 1)
        },
        comparison=compare(rows, cases) if mode == "matrix" else None,
        outcome=heldout_outcome(rows, summaries, cases, compare(rows, cases))
        if mode == "matrix" and heldout_run
        else None,
        native_calls=sum(row["status"] in {"COMPLETE", "STREAM_FAILED"} for row in rows)
        + sum(bool(row.get("exchange")) for row in rows + summaries),
        semantic_quality_claim="controlled synthetic retention only; not general conversation quality",
    )
    save_json(output / "summary.json", result)
    return result, rows + summaries


async def grammar_smoke(inference, output):
    """Run S0: one schema-constrained generation per prompt-example packet, keeping raw output, parse result and key order."""
    output = Path(output)
    output.mkdir(mode=0o700, parents=False, exist_ok=False)
    config = get_model_profile("core")
    gateway = LlamaGateway(config["base_url"], config["model_id"], inference.transport)
    records = []
    async with httpx.AsyncClient(
        base_url=gateway.base_url,
        transport=inference.transport,
        timeout=gateway._timeout(),
        trust_env=False,
    ) as client:
        await gateway._verify_model(client)
        port = summarizer_module.GatewaySummarizer(
            gateway,
            client,
            deadline=asyncio.get_running_loop().time() + DEADLINE_SECONDS,
        )
        examples = (
            ("example-1", history_summary.EXAMPLE_1_PACKET),
            ("example-2", history_summary.EXAMPLE_2_PACKET),
        )
        for name, source in examples:
            messages = history_summary.request_messages(source)
            schema = history_summary.schema_for(*listed_pairs(source))
            record = dict(name=name, messages=messages, schema=schema)
            try:
                content, finish, usage = await port.generate(messages, schema)
                record.update(content=content, finish_reason=finish, usage=usage)
            except history_summary.SummaryUnavailable as error:
                record["error"] = error.status
            record.update(
                reverify=reverify(record),
                key_order_declared=key_order(record) if "content" in record else None,
            )
            records.append(record)
            save_json(output / f"{name}.json", record)
    result = dict(
        schema_version=1,
        status="COMPLETE"
        if all(record["reverify"]["status"] == "verified" for record in records)
        else "INCOMPLETE",
        variant=describe(),
        statuses={record["name"]: record["reverify"]["status"] for record in records},
        key_order_declared={
            record["name"]: record["key_order_declared"] for record in records
        },
        native_calls=sum("error" not in record for record in records),
    )
    save_json(output / "summary.json", result)
    return result, records


def main():
    """Run one exclusive campaign against the already loaded approved CORE process."""
    parser = argparse.ArgumentParser(description="HAR-009-C summary v2 runner.")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cases", choices=("v1", "dev", "heldout"), default="v1")
    parser.add_argument(
        "--mode", choices=("smoke", "design", "summary-only", "matrix"), required=True
    )
    parser.add_argument("--draws", type=int, default=1)
    parser.add_argument("--contract", choices=("v1", "v2"), default="v2")
    parser.add_argument("--v1-prompt", type=Path)
    parser.add_argument("--prompt", type=Path)
    parser.add_argument("--max-slots", type=int)
    parser.add_argument("--max-claims", type=int)
    parser.add_argument("--clipped-user", choices=CLIPPED_CHOICES)
    parser.add_argument("--pid", type=int)
    parser.add_argument("--calibrate", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    inference = ProductInference()
    prompt = args.prompt.read_text() if args.prompt else None
    v1_prompt = args.v1_prompt.read_text() if args.v1_prompt else None
    knobs = (prompt, args.max_slots, args.max_claims, args.clipped_user)
    try:
        if args.calibrate and (args.cases != "heldout" or args.mode != "design"):
            raise CampaignRefused("CALIBRATE_DESIGN_ONLY")
        if args.mode == "smoke":
            with variant(*knobs):
                result, _ = asyncio.run(grammar_smoke(inference, args.output))
            print(
                json.dumps(dict(status=result["status"], statuses=result["statuses"]))
            )
            return 0 if result["status"] == "COMPLETE" else 1
        if args.cases == "heldout":
            cases = heldout(calibrate=args.calibrate)
        elif args.cases == "dev":
            cases = dev_cases()
        else:
            cases = v1_cases()
        if args.mode == "matrix" and args.pid is None:
            raise CampaignRefused("PID_REQUIRED")
        with variant(*knobs):
            result, _ = asyncio.run(
                run(
                    inference,
                    args.output,
                    cases,
                    mode=args.mode,
                    draws=args.draws,
                    heldout_run=args.cases == "heldout" and not args.calibrate,
                    contract=args.contract,
                    v1_prompt=v1_prompt,
                    calibrate=args.calibrate,
                    pid=args.pid,
                    count_text=native_counter(inference),
                )
            )
    except CampaignRefused as error:
        print(json.dumps(dict(status="REFUSED", code=error.code)))
        return 2
    if args.calibrate:
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result["status"] == "DESIGN_VALID" else 1
    print(
        json.dumps(
            dict(
                status=result["status"],
                draws=result.get("draws"),
                comparison=result.get("comparison"),
                violations=result.get("violations"),
            ),
            ensure_ascii=False,
        )
    )
    return 0 if result["status"] in {"COMPLETE", "DESIGN_VALID"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
