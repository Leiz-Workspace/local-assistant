"""Verify the opt-in evicted-history summary (ADR-192, Amendment 1 v2 contract) with fake ports: flags, listing, schema, verifier, statuses, reserve, cache and routes."""

import asyncio
import json
import logging
import random

import httpx
import pytest
from pydantic import ValidationError

from apps.cli import main as cli
from apps.harness.summarizer import GatewaySummarizer
from src.application.services import history_summary as module
from src.application.services.context_composer import compose_context
from src.application.services.context_reduction import (
    SUMMARY_POLICY,
    ContextError,
    HistoryPolicy,
    input_limit,
    reduce_history,
)
from src.infrastructure.summary_cache import BoundSummaryCache, SummaryCache
from tests import test_product_harness as harness_tests

product_client = harness_tests.product_client
PREFIX = harness_tests.PREFIX
SOFT = int(input_limit("fast", 4096) * 0.8)
FILLER = "Here is the ledger log for reference:\n" + "row ok\n" * 900
EXAMPLE_1_DIALOGUE = (
    (
        "Can the Juniper build use runner gpu-09 tonight?",
        "I can't check runner bookings.",
    ),
    ("Never run the Juniper build on runner gpu-02.", "OK."),
    ("The Juniper build runs on runner gpu-04.", "Sure."),
    (
        "Correction: the Juniper build now runs on runner gpu-07.",
        "Switching to gpu-07 then.",
    ),
)
EXAMPLE_2_DIALOGUE = (
    (
        "Kho Tây Ninh mở cửa lúc 06:30; chưa được nhận hàng sau 18:00.",
        "Vâng, em ghi lại rồi.",
    ),
    ("Cảm ơn em nhé.", "Không có gì ạ."),
    (
        "Nếu trời mưa thì chuyển ca giao hàng sang cổng K-27.",
        "Em sẽ báo đội giao hàng.",
    ),
)


def conversation(texts, question="Which port does the Lynx agent use?"):
    """Build a request from (user, assistant) tuples and a current question."""
    rows = [dict(role="system", content="System policy")]
    for user, assistant in texts:
        rows += [
            dict(role="user", content=user),
            dict(role="assistant", content=assistant),
        ]
    return rows + [dict(role="user", content=question)]


def pressured(
    early=(
        "The Lynx agent listens on port 9464 for metrics.",
        "Noted: Lynx metrics agent uses port 9464.",
    ),
):
    """Return a history whose early target pair is evicted by token-budget under the fake character tokenizer."""
    return conversation([early] + [(FILLER, "Received.")] * 9)


def pair_rows(texts, start=1):
    """Number (user, assistant) tuples as packet input pairs from a start pair."""
    return [
        (
            start + index,
            [
                dict(role="user", content=user),
                dict(role="assistant", content=assistant),
            ],
        )
        for index, (user, assistant) in enumerate(texts)
    ]


async def count(messages):
    """Count characters as deterministic fake tokens."""
    return sum(len(row["content"]) for row in messages)


def listed_and_replies(source):
    """Return the listed user pairs and sent assistant pairs of one packet."""
    return (
        [row["pair"] for row in source["user"]],
        [row["pair"] for row in source["assistant"]],
    )


class Port:
    """Fake summarizer port with scripted output, a counted tokenizer and an injectable clock."""

    model_id = "fixture-model"

    def __init__(
        self,
        output=None,
        *,
        finish="stop",
        deadline=1000.0,
        delay=0.0,
        error=None,
        cache=None,
    ):
        """Script one generation outcome."""
        self.output, self.finish, self.deadline = output, finish, deadline
        self.delay, self.error, self.cache = delay, error, cache
        self.generations, self.counts = 0, 0
        self.requests, self.keys = [], []
        self.now = 0.0
        self.chars_per_token = 4

    def clock(self):
        """Return a fixed fake time."""
        return self.now

    async def count(self, messages):
        """Count about four characters per token, like a real tokenizer on this text."""
        self.counts += 1
        return sum(len(row["content"]) for row in messages) // self.chars_per_token

    async def generate(self, messages, schema):
        """Return the scripted output after an optional real delay; the schema must be the per-request v2 schema."""
        self.generations += 1
        source = json.loads(messages[1]["content"])
        assert messages[0]["content"] == module.SYSTEM_PROMPT
        assert schema == module.schema_for(*listed_and_replies(source))
        self.requests.append((messages, schema))
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.error:
            raise module.SummaryUnavailable(self.error)
        output = (
            self.output
            if isinstance(self.output, str)
            else json.dumps(self.output, ensure_ascii=False)
        )
        return output, self.finish, {"completion_tokens": 42}

    def cache_get(self, key):
        """Record the key and read the optional cache."""
        self.keys.append(key)
        return None if self.cache is None else self.cache.get(key)

    def cache_put(self, key, value):
        """Write the optional cache."""
        if self.cache is not None:
            self.cache.put(key, value)


def lynx_output(
    text="Lynx agent listens on port 9464",
    quote="Lynx agent listens on port 9464",
    pair=1,
    kind="fact",
    slots=(1,),
    claims=(),
):
    """Return a v2 output with empty slots and one note in the given slot."""
    notes = {f"p{number}": [] for number in slots}
    notes[f"p{pair}"] = [dict(kind=kind, quotes=[quote], text=text, replaces=None)]
    return dict(version=2, notes=notes, assistant_claims=list(claims), uncertain=[])


async def reduce(rows, policy=None, port=None, **options):
    """Reduce with token-budget plus the summary flag by default."""
    policy = policy or {"mode": "token-budget", "evicted_summary": True}
    return await reduce_history(
        rows,
        policy=policy,
        count_tokens=count,
        preset="fast",
        max_tokens=4096,
        summarizer=port,
        **options,
    )


def sent(user, assistant="ok", pair=1):
    """Build the verifier's sent-text map for one pair."""
    return {pair: dict(user=user, assistant=assistant)}


def item(text, quotes, kind="fact", pair=1, replaces=None):
    """Build one flattened item as flatten() would."""
    return dict(
        kind=kind,
        text=text,
        pairs=[pair],
        quotes=list(quotes),
        replaces=replaces,
        slot="claim" if kind == "assistant_claim" else "note",
    )


class FakeGateway:
    """Expose the gateway surface GatewaySummarizer uses, counting four characters per token."""

    model_id = "fixture-model"

    async def _count_input_tokens(self, client, messages, *, thinking):
        """Count characters without a model."""
        assert thinking is False
        return sum(len(row["content"]) for row in messages) // 4


@pytest.mark.parametrize(
    "values",
    [
        {"mode": "extractive-compact", "evicted_summary": True},
        {"evicted_summary": "yes"},
        {
            "carried_state": [
                dict(kind="note", text="Remember: x", turn=1, sha256="0" * 64)
            ],
            "evicted_summary": True,
            "history_offset": 4,
        },
    ],
)
def test_policy_rules(values):
    """The flag is strict, refused with compaction, and carried state still needs working state."""
    with pytest.raises(ValidationError):
        HistoryPolicy.model_validate(values)
    assert (
        HistoryPolicy.model_validate(
            {"evicted_summary": True, "history_offset": 32}
        ).history_offset
        == 32
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("strategy", ["recent-turns", "strict"])
async def test_composer_refuses_the_flag_outside_evidence_first(strategy):
    """Only evidence-first may use the summary, because the other strategies reduce before evidence."""
    with pytest.raises(ContextError) as error:
        await compose_context(
            pressured()[1:],
            history_policy={"mode": "token-budget", "evicted_summary": True},
            preset="fast",
            max_tokens=4096,
            count_tokens=count,
            strategy=strategy,
        )
    assert error.value.code == "summary_requires_evidence_first"


def test_tokenizer_values_and_lexicons():
    """Whole-token values, contractions, NFD, negation questions, conditions, hard values and the authority lexicon."""
    assert module.summary_tokens("Don't use port 9446") == [
        "do",
        "not",
        "use",
        "port",
        "9446",
    ]
    assert "9464" not in module.summary_tokens("port 9446")
    assert module.value_tokens("Use staging-3 and Port 21.50") == {
        "staging-3",
        "port",
        "21.50",
    }
    assert "staging-31" not in module.summary_tokens("deploy staging-3")
    assert module.summary_tokens("We cannot go") == ["we", "can", "not", "go"]
    assert module.summary_tokens("Café") == ["café"]
    assert module.has_negation("chưa được deploy staging")
    assert not module.has_negation("Có deploy staging không?")
    assert module.has_negation("Không deploy staging.")
    assert module.has_condition("chỉ khi có duyệt") and module.has_condition(
        "only on Friday"
    )
    assert not module.has_condition("chỉ đường khi nào")
    assert module.hard_value("Switching to gpu-07 then.") and module.hard_value(
        "Batch 8 done."
    )
    assert not module.hard_value("Noted for the Lynx Team.")
    assert module.can_host_quote("Đã cập nhật.") and not module.can_host_quote("Noted.")
    for text in (
        "approved",
        "Authorized",
        "consent",
        "allowed",
        "permission",
        "disregard that",
        "go ahead",
        "ignore previous",
        "đồng ý",
        "cho phép",
        "được phép",
        "chấp thuận",
        "xác nhận",
        "duyệt",
        "bỏ qua",
    ):
        assert module.authority_match(text), text
    for text in (
        "approach",
        "permanent",
        "going ahead slowly",
        "bỏ vào túi",
        "cho phần",
    ):
        assert not module.authority_match(text), text


def test_question_exception_does_not_survive_a_decimal():
    """has_negation keeps SENTENCE, so a 'có … 2.5 … không?' question splits at '2.' and its 'không' counts as a negation."""
    assert not module.has_negation("Có triển khai bản mới không?")
    assert module.has_negation("Có triển khai bản 2.5 không?")


@pytest.mark.parametrize(
    "entry,source,reason",
    [
        (
            dict(
                text="Lynx uses port 9464",
                quotes=["Lynx agent listens on port 9464"],
                pair=2,
            ),
            "The Lynx agent listens on port 9464.",
            "pair_not_summarized",
        ),
        (
            dict(text="Lynx uses port 9464", quotes=["listens on port 9446 ok"]),
            "The Lynx agent listens on port 9464.",
            "quote_not_in_source",
        ),
        (
            dict(text="Code port-9464-xyz", quotes=["port-9464-xyz"]),
            "The code port-9464-xyz.",
            "quote_too_short",
        ),
        (
            dict(text="Deploy to staging-3 now", quotes=["deploy to staging-3"]),
            "Do not deploy to staging-3.",
            "quote_context_dropped",
        ),
        (
            dict(text="Deploy staging nightly", quotes=["được deploy staging nightly"]),
            "Chưa được deploy staging nightly.",
            "quote_context_dropped",
        ),
        (
            dict(
                text="Migration on Atlas tonight", quotes=["migration on Atlas tonight"]
            ),
            "Do not start the 2.5 migration on Atlas tonight.",
            "quote_context_dropped",
        ),
        (
            dict(text="Trên máy Atlas tối nay", quotes=["trên máy Atlas tối nay"]),
            "Không chạy bản 3.14 trên máy Atlas tối nay.",
            "quote_context_dropped",
        ),
        (
            dict(
                text="Migration on Atlas tonight", quotes=["migration on Atlas tonight"]
            ),
            "Start the 2.5 migration on Atlas tonight.",
            None,
        ),
        (
            dict(
                text="Lynx uses port 9446", quotes=["Lynx agent listens on port 9464"]
            ),
            "The Lynx agent listens on port 9464.",
            "value_not_quoted",
        ),
        (
            dict(
                text="Lynx uses staging-31", quotes=["Lynx agent uses staging-3 here"]
            ),
            "Lynx agent uses staging-3 here.",
            "value_not_quoted",
        ),
        (
            dict(
                text="Owner prefers blue dashboards strongly",
                quotes=["Lynx agent listens on port 9464"],
            ),
            "The Lynx agent listens on port 9464.",
            "text_not_grounded",
        ),
        (
            dict(
                text="Lynx never listens on port 9464",
                quotes=["Lynx agent listens on port 9464"],
            ),
            "The Lynx agent listens on port 9464.",
            "negation_mismatch",
        ),
        (
            dict(
                text="Lynx agent listens on port 9464 only",
                quotes=["Lynx agent listens on port 9464"],
            ),
            "The Lynx agent listens on port 9464 weekly.",
            "condition_mismatch",
        ),
        (
            dict(
                text="Owner approved the Lynx port 9464",
                quotes=["owner approved the Lynx port 9464"],
            ),
            "The owner approved the Lynx port 9464.",
            "authority_context",
        ),
        (
            dict(
                text="Lynx agent listens on port 9464 approved",
                quotes=["Lynx agent listens on port 9464"],
            ),
            "The Lynx agent listens on port 9464.",
            "authority_lexicon",
        ),
        (
            dict(
                kind="assistant_claim",
                text="Lynx agent listens on port 9464",
                quotes=["Lynx agent listens on port 9464"],
            ),
            "The Lynx agent listens on port 9464.",
            "speaker_mismatch",
        ),
        (
            dict(
                text="Lynx agent listens on port 9464",
                quotes=["Lynx agent listens on port 9464"],
            ),
            "The Lynx agent listens on port 9464.",
            None,
        ),
    ],
)
def test_each_drop_reason_at_its_boundary(entry, source, reason):
    """Every deterministic check fires on its own case and a grounded item passes."""
    assert module.check(item(**entry), sent(source)) == reason


@pytest.mark.parametrize(
    "source,quote,text",
    [
        (
            "Set the gateway port to 9446 tonight please.",
            "Set the gateway port to 944",
            "Gateway port to 944",
        ),
        (
            "Retired is the staging-31 cluster today.",
            "Retired is the staging-3",
            "Retired is the staging-3",
        ),
        (
            "I don't want staging deployed now.",
            "t want staging deployed now",
            "want staging deployed now",
        ),
    ],
)
def test_quotes_must_start_and_end_on_token_boundaries(source, quote, text):
    """A quote cut inside a token (944 of 9446, staging-3 of staging-31, the t of don't) is not in the source."""
    assert module.check(item(text, [quote]), sent(source)) == "quote_not_in_source"


def test_value_tokens_share_the_contraction_normalization():
    """A capitalized contraction is normalized on both sides, so an identical quote is grounded."""
    source = "We Cannot ship the beta build tonight."
    entry = item(
        "We Cannot ship the beta build tonight",
        ["We Cannot ship the beta build tonight"],
        kind="constraint",
    )
    assert module.check(entry, sent(source)) is None


def test_withheld_text_is_never_a_quote_source():
    """A quote copied from a withheld reply cannot be admitted as a claim, and a note cannot quote a reply."""
    pairs = {1: dict(user="The Lynx agent listens on port 9464.", assistant=None)}
    claim = item(
        "Lynx agent listens on port 9464",
        ["Lynx agent listens on port 9464"],
        kind="assistant_claim",
    )
    assert module.check(claim, pairs) == "speaker_mismatch"
    pairs = {1: dict(user=None, assistant="The Lynx agent listens on port 9464.")}
    note = item("Lynx agent listens on port 9464", ["Lynx agent listens on port 9464"])
    assert module.check(note, pairs) == "speaker_mismatch"


def test_prompt_numbers_match_the_constants_and_text_is_nfc():
    """Every limit the prompt states equals the enforced constant, and the prompt is NFC."""
    prompt = module.SYSTEM_PROMPT
    assert prompt == module.nfc(prompt)
    for phrase in (
        f"at least {module.QUOTE_MIN_TOKENS} words and {module.QUOTE_MIN} characters and at most {module.QUOTE_MAX} characters",
        f'"text": at most {module.TEXT_MAX} characters',
        f'"assistant_claims": at most {module.MAX_CLAIMS} claim',
        f'"uncertain": at most {module.MAX_UNCERTAIN} entries',
        f'"text" of at most {module.UNCERTAIN_MAX} characters',
    ):
        assert phrase in prompt, phrase
    assert module.PROMPT_SHA256 == module.digest(
        dict(version=module.PROMPT_VERSION, system=prompt)
    )
    assert prompt.endswith("\n\nReturn only JSON that matches the schema.")


@pytest.mark.parametrize(
    "dialogue,start,example,output",
    [
        (
            EXAMPLE_1_DIALOGUE,
            1,
            module.EXAMPLE_1_PACKET,
            module.EXAMPLE_1_OUTPUT,
        ),
        (
            EXAMPLE_2_DIALOGUE,
            4,
            module.EXAMPLE_2_PACKET,
            module.EXAMPLE_2_OUTPUT,
        ),
    ],
)
def test_prompt_examples_are_packets_and_pass_the_verifier(
    dialogue, start, example, output
):
    """Each example input is packet() of its fixture dialogue, embedded exactly; its output parses and verifies with 0 drops."""
    source, clipped, withheld, listed, over_cap = module.packet(
        pair_rows(dialogue, start)
    )
    assert module.compact(source) == module.compact(example)
    assert clipped == [] and over_cap == []
    assert (
        f"Input:\n{module.compact(example)}\nOutput:\n{module.compact(output)}\n"
        in module.SYSTEM_PROMPT
    )
    data = module.parse(module.compact(output), *listed_and_replies(source))
    assert data is not None
    items = module.flatten(data)
    kept, dropped = module.verify(items, module.sent_pairs(source))
    assert dropped == [] and len(kept) == len(items)
    if start == 1:
        assert withheld == {"assistant_no_hard_value": [1], "assistant_short": [2, 3]}
        rows = module.admitted_rows(kept, [])
        assert rows[1]["superseded_by_pairs"] == [4]
    else:
        assert withheld["user_no_signal"] == [5]
        assert withheld["assistant_no_hard_value"] == [4, 5, 6]


@pytest.mark.parametrize(
    "text,reason",
    [
        ("Can the Orca job use runner b-12 tonight?", None),
        ("Máy pha cà phê tầng hai đã sửa chưa?", "user_no_signal"),
        ("Remind me to water the office plants.", "user_no_signal"),
        ("Yesterday I watered the office plants.", "user_no_signal"),
        ("We water the plants daily. Sometimes we skip a day.", "user_no_signal"),
        ("Nhóm họp ở Phú Quốc vào sáng thứ sáu.", None),
        ("Do not water the office plants.", None),
        ("Only water the plants when the soil is dry.", None),
        ("Should we never water the plants?", "user_no_signal"),
        ("Hi there!", "user_short"),
        ("ok ok", "user_short"),
    ],
)
def test_listing_rules(text, reason):
    """Questions with a value are listed; sentence-initial capitals, I and value-free questions are not; short text is not."""
    source, _, withheld, listed, _ = module.packet(pair_rows([(text, "ok")]))
    if reason is None:
        assert listed == [1] and source["user"] == [dict(pair=1, text=text)]
    else:
        assert listed == [] and withheld[reason] == [1]


def test_listing_keeps_the_newest_duplicate_ranks_clipped_last_and_caps():
    """Of duplicates the newest is kept; clipped rows rank after unclipped ones; the cap fills over_cap_pairs."""
    same = "Lynx metrics live on port 9464."
    _, _, withheld, listed, _ = module.packet(
        pair_rows([(same, "ok"), ("Kite runs build k-2.", "ok"), (same, "ok")])
    )
    assert listed == [2, 3] and withheld["user_duplicate"] == [1]
    long = "Batch 7 ledger log follows:\n" + "row ok\n" * 600
    rows = [(f"Runner r-{number} is free.", "ok") for number in range(1, 7)]
    source, clipped, _, listed, over_cap = module.packet(
        pair_rows(rows + [(long, "ok")])
    )
    assert listed == [2, 3, 4, 5, 6] and over_cap == [1, 7] and clipped == []
    source, clipped, _, listed, over_cap = module.packet(
        pair_rows(rows[:3] + [(long, "ok")])
    )
    assert listed == [1, 2, 3, 4] and clipped == [4] and over_cap == []
    assert source["user"][-1]["text"] == long[: module.CLIP_CHARS].rsplit("\n", 1)[0]


def test_clipped_user_messages_can_be_withheld(monkeypatch):
    """The dev knob withholds clipped user messages instead of listing them last."""
    monkeypatch.setattr(module, "CLIPPED_USER", "withheld")
    long = "Batch 7 ledger log follows:\n" + "row ok\n" * 600
    _, clipped, withheld, listed, _ = module.packet(
        pair_rows([("Runner r-1 is free.", "ok"), (long, "ok")])
    )
    assert listed == [1] and withheld["user_clipped"] == [2] and clipped == []


def test_assistant_filter_withholds_acknowledgements_duplicates_and_clips():
    """Short and value-free replies and older duplicates are withheld; a hard-value reply is sent, clipped back from 512 to whole tokens."""
    reply = "Port 9464 is open on the Lynx host."
    long = "Build log: " + "step-1 ok " * 80
    rows = [
        ("Please check the office plants.", "Noted."),
        ("Please check the office plants again.", "Đã cập nhật."),
        ("Please check the lamps.", reply),
        ("Please check the lamps again.", reply),
        ("Please check the doors.", long),
    ]
    source, clipped, withheld, listed, _ = module.packet(pair_rows(rows))
    assert listed == []
    assert source["assistant"] == [
        dict(pair=4, text=reply),
        dict(pair=5, text=long[: module.ASSISTANT_CLIP].rsplit(" ", 1)[0]),
    ]
    assert withheld["assistant_short"] == [1]
    assert withheld["assistant_no_hard_value"] == [2]
    assert withheld["assistant_duplicate"] == [3]
    assert clipped == [5]


def test_assistant_rows_are_off_without_claims(monkeypatch):
    """With MAX_CLAIMS 0 no reply is sent and the schema allows no claim."""
    monkeypatch.setattr(module, "MAX_CLAIMS", 0)
    source, _, withheld, listed, _ = module.packet(
        pair_rows([("Runner r-1 is free.", "Port 9464 is open on the Lynx host.")])
    )
    assert source["assistant"] == [] and withheld["assistant_disabled"] == [1]
    schema = module.schema_for(listed, [1])
    assert schema["properties"]["assistant_claims"] == {"type": "array", "maxItems": 0}


@pytest.mark.asyncio
async def test_packet_version_is_independent_of_the_prompt(monkeypatch):
    """A prompt-only change keeps source_sha256 and the packet version; it changes the prompt hash."""
    _, first = await reduce(pressured(), port=Port(lynx_output()))
    monkeypatch.setattr(module, "SYSTEM_PROMPT", module.SYSTEM_PROMPT + " ")
    monkeypatch.setattr(
        module,
        "PROMPT_SHA256",
        module.digest(dict(version=module.PROMPT_VERSION, system=module.SYSTEM_PROMPT)),
    )
    port = Port(lynx_output())
    _, second = await reduce(pressured(), port=port)
    one, two = first["summary"], second["summary"]
    assert one["source_sha256"] == two["source_sha256"]
    assert one["prompt_sha256"] != two["prompt_sha256"]
    assert two["packet_version"] == module.PACKET_VERSION == 2
    assert json.loads(port.requests[0][0][1]["content"])["version"] == 2


def test_schema_for_slots_enums_and_template():
    """Slots are p<N> keys with backward replaces enums; claims and uncertain pairs are enumerated; the template hash is the wire digest."""
    schema = module.schema_for([2, 5, 9], [5])
    notes = schema["properties"]["notes"]
    assert list(notes["properties"]) == notes["required"] == ["p2", "p5", "p9"]
    enums = [
        slot["items"]["properties"]["replaces"]["enum"]
        for slot in notes["properties"].values()
    ]
    assert enums == [[None], [2, None], [2, 5, None]]
    note = notes["properties"]["p2"]["items"]
    assert note["required"] == ["kind", "quotes", "text", "replaces"]
    assert note["properties"]["quotes"]["items"]["minLength"] == 1
    assert note["properties"]["kind"]["enum"] == list(module.NOTE_KINDS)
    claims = schema["properties"]["assistant_claims"]
    assert claims["maxItems"] == module.MAX_CLAIMS
    assert claims["items"]["properties"]["pair"]["enum"] == [5]
    uncertain = schema["properties"]["uncertain"]
    assert uncertain["maxItems"] == module.MAX_UNCERTAIN
    assert uncertain["items"]["properties"]["pairs"]["items"]["enum"] == [2, 5, 9]
    assert module.schema_for([2], [])["properties"]["assistant_claims"] == {
        "type": "array",
        "maxItems": 0,
    }
    assert module.SCHEMA_TEMPLATE_SHA256 == module.wire_digest(
        module.schema_for((1, 2), (1,))
    )
    assert module.wire_digest(schema) != module.digest(schema)


def ordered(value):
    """Return the keys of an object parsed with object_pairs_hook=list."""
    return [key for key, _ in value]


def field(value, key):
    """Return one field of an object parsed with object_pairs_hook=list."""
    return dict(value)[key]


@pytest.mark.asyncio
async def test_wire_order_is_the_declared_order():
    """The schema body captured from a fake transport keeps the declared property order."""
    bodies = []

    def respond(request):
        """Capture the summarizer request and answer with a valid output."""
        bodies.append(request.content)
        content = json.dumps(lynx_output())
        return httpx.Response(
            200,
            json=dict(
                choices=[dict(message=dict(content=content), finish_reason="stop")],
                usage=dict(completion_tokens=9),
            ),
        )

    async with httpx.AsyncClient(
        base_url="http://fixture", transport=httpx.MockTransport(respond)
    ) as client:
        port = GatewaySummarizer(
            FakeGateway(), client, deadline=1000.0, clock=lambda: 0.0
        )
        _, report = await reduce(pressured(), port=port)
    assert report["summary"]["status"] == "applied" and len(bodies) == 1
    payload = json.loads(bodies[0], object_pairs_hook=list)
    schema = field(field(field(payload, "response_format"), "json_schema"), "schema")
    assert ordered(schema) == ["type", "additionalProperties", "required", "properties"]
    properties = field(schema, "properties")
    assert ordered(properties) == ["version", "notes", "assistant_claims", "uncertain"]
    assert field(schema, "required") == ordered(properties)
    slot = field(field(field(properties, "notes"), "properties"), "p1")
    note = field(slot, "items")
    assert ordered(field(note, "properties")) == ["kind", "quotes", "text", "replaces"]
    assert field(note, "required") == ["kind", "quotes", "text", "replaces"]


def parse_base():
    """Return a valid output for listed users 1 and 2 and the sent reply 2."""
    return dict(
        version=2,
        notes=dict(
            p1=[],
            p2=[
                dict(
                    kind="fact",
                    quotes=["Runner r-2 is free"],
                    text="Runner r-2 is free",
                    replaces=None,
                )
            ],
        ),
        assistant_claims=[dict(pair=2, quotes=["Port 9464 is open"], text="9464")],
        uncertain=[dict(text="which runner", pairs=[1, 2])],
    )


def mutate_missing_slot(data):
    """Remove a listed slot."""
    del data["notes"]["p1"]


def mutate_extra_slot(data):
    """Add an unlisted slot."""
    data["notes"]["p3"] = []


def mutate_two_notes(data):
    """Put two notes in one slot."""
    data["notes"]["p2"] = data["notes"]["p2"] * 2


def mutate_bool_replaces(data):
    """Use a boolean for replaces."""
    data["notes"]["p2"][0]["replaces"] = True


def mutate_later_replaces(data):
    """Point replaces at a later pair."""
    data["notes"]["p1"] = [dict(data["notes"]["p2"][0], replaces=2)]


def mutate_self_replaces(data):
    """Point replaces at its own pair."""
    data["notes"]["p2"][0]["replaces"] = 2


def mutate_claim_pair(data):
    """Cite a reply that was not sent."""
    data["assistant_claims"][0]["pair"] = 1


def mutate_long_quote(data):
    """Use a quote over QUOTE_MAX characters."""
    data["notes"]["p2"][0]["quotes"] = ["x" * (module.QUOTE_MAX + 1)]


def mutate_empty_quote(data):
    """Use an empty quote."""
    data["notes"]["p2"][0]["quotes"] = [""]


def mutate_three_uncertain(data):
    """Return one uncertain entry too many."""
    data["uncertain"] = [dict(text="a", pairs=[])] * (module.MAX_UNCERTAIN + 1)


def mutate_uncertain_pair(data):
    """Cite an unsent pair in uncertain."""
    data["uncertain"][0]["pairs"] = [7]


def mutate_claim_kind(data):
    """Use the claim kind on a note."""
    data["notes"]["p2"][0]["kind"] = "assistant_claim"


def mutate_version(data):
    """Use the v1 version."""
    data["version"] = 1


def mutate_two_claim_quotes(data):
    """Give a claim two quotes."""
    data["assistant_claims"][0]["quotes"] *= 2


@pytest.mark.parametrize(
    "mutation",
    [
        mutate_missing_slot,
        mutate_extra_slot,
        mutate_two_notes,
        mutate_bool_replaces,
        mutate_later_replaces,
        mutate_self_replaces,
        mutate_claim_pair,
        mutate_long_quote,
        mutate_empty_quote,
        mutate_three_uncertain,
        mutate_uncertain_pair,
        mutate_claim_kind,
        mutate_version,
        mutate_two_claim_quotes,
    ],
)
def test_parse_rejects_every_shape_deviation(mutation):
    """Any deviation from the per-request shape is invalid output."""
    assert module.parse(json.dumps(parse_base()), [1, 2], [2]) is not None
    data = parse_base()
    mutation(data)
    assert module.parse(json.dumps(data), [1, 2], [2]) is None


@pytest.mark.parametrize(
    "raw",
    [
        "not json",
        "{}",
        '{"version":2,"notes":{"p1":[],"p1":[]},"assistant_claims":[],"uncertain":[]}',
        json.dumps(dict(version=1, items=[], uncertain=[])),
    ],
)
def test_invalid_output_is_rejected_by_shape(raw):
    """Non-JSON, v1 shapes and duplicate slot keys are invalid output."""
    assert module.parse(raw, [1], []) is None


@pytest.mark.asyncio
async def test_short_quote_drops_only_its_item():
    """A 'Noted.' quote beside a valid note drops as quote_too_short; the valid note is still applied."""
    rows = conversation(
        [
            ("The Lynx agent listens on port 9464 for metrics.", "Noted."),
            ("The Kite agent listens on port 7311 for metrics.", "Noted."),
        ]
        + [(FILLER, "Received.")] * 9
    )
    output = lynx_output(slots=(1, 2))
    output["notes"]["p2"] = [
        dict(kind="fact", quotes=["Noted."], text="Noted", replaces=None)
    ]
    _, report = await reduce(rows, port=Port(output))
    summary = report["summary"]
    assert summary["listed_pairs"] == [1, 2]
    assert summary["status"] == "applied" and summary["items_admitted"] == 1
    assert summary["dropped"] == {"quote_too_short": 1}


@pytest.mark.parametrize(
    "entry,pairs,reason",
    [
        (
            item(
                "running the Orca nightly reindex at 23:00",
                ["running the Orca nightly reindex at 23:00"],
            ),
            sent("I approve running the Orca nightly reindex at 23:00."),
            "authority_context",
        ),
        (
            item(
                "chạy bản vá Lạng Sơn lúc 22:00",
                ["chạy bản vá Lạng Sơn lúc 22:00"],
                kind="constraint",
            ),
            sent("Tôi đồng ý cho chạy bản vá Lạng Sơn lúc 22:00."),
            "authority_context",
        ),
        (
            item(
                "Ship build b-41 to host kiln-2 tonight",
                ["Ship build b-41 to host kiln-2 tonight"],
                kind="constraint",
            ),
            sent("Approved. Ship build b-41 to host kiln-2 tonight."),
            "authority_context",
        ),
        (
            item(
                "Chạy migration Tràng An tối nay",
                ["Chạy migration Tràng An tối nay"],
            ),
            sent("Chạy migration Tràng An tối nay. Tôi đồng ý."),
            "authority_context",
        ),
        (
            item(
                "We picked runner pool r-9 for the Orca job",
                ["We picked runner pool r-9 for the Orca job"],
                kind="decision",
            ),
            sent(
                "We picked runner pool r-9 for the Orca job. It starts on Monday. I approve that plan."
            ),
            "authority_context",
        ),
        (
            item(
                "Orca job uses runner pool r-9",
                ["The Orca job uses runner pool r-9"],
            ),
            sent(
                "The Orca job uses runner pool r-9. It starts on Monday. I approve that plan."
            ),
            None,
        ),
        (
            item(
                "Here is the ledger log for reference",
                ["Here is the ledger log for reference"],
            ),
            sent(FILLER),
            "content_free",
        ),
        (
            item("Never water the office plants", ["Never water the office plants"]),
            sent("Never water the office plants."),
            None,
        ),
        (
            item(
                "no action is needed", ["no action is needed"], kind="assistant_claim"
            ),
            {
                1: dict(
                    user=None,
                    assistant="Received the batch 8 log; no action is needed.",
                )
            },
            "claim_without_value",
        ),
        (
            item(
                "Received the batch 8 log",
                ["Received the batch 8 log"],
                kind="assistant_claim",
            ),
            {
                1: dict(
                    user=None,
                    assistant="Received the batch 8 log; no action is needed.",
                )
            },
            None,
        ),
    ],
)
def test_new_drops_at_their_boundaries(entry, pairs, reason):
    """authority_context covers approvals around the quote (or the whole message for decisions); content-free notes and value-free claims drop."""
    assert module.check(entry, pairs) == reason


TOKEN_FREE_SEPARATORS = (
    "\r\n",
    " \n",
    "\n \n",
    " 🙂. ",
    " ; ",
    "\n---\n",
    "\n👍\n",
    "\n)\n",
)


def on_role(kind, text):
    """Place a message on the role a kind is quoted from."""
    if kind == "assistant_claim":
        return {1: dict(user=None, assistant=text)}
    return sent(text)


@pytest.mark.parametrize("separator", TOKEN_FREE_SEPARATORS)
@pytest.mark.parametrize("kind", ["fact", "constraint", "assistant_claim"])
def test_authority_context_skips_token_free_pieces(kind, separator):
    """CRLF, trailing spaces, blank, punctuation-only or emoji pieces between an approval and the quote do not hide it, before or after."""
    before = "Ship build b-41 to host kiln-2 tonight"
    entry = item(before, [before], kind=kind)
    message = "Approved." + separator + before + "."
    assert module.check(entry, on_role(kind, message)) == "authority_context"
    after = "Chạy migration M-12 tối nay"
    entry = item(after, [after], kind=kind)
    message = after + "." + separator + "Tôi đồng ý."
    assert module.check(entry, on_role(kind, message)) == "authority_context"


@pytest.mark.parametrize("separator", (" ", "\r\n", " \n", "\n---\n"))
def test_authority_two_sentences_away_is_still_admitted(separator):
    """A fact two real sentences from an approval stays admitted whatever pieces separate them."""
    quote = "The Orca job uses runner pool r-9"
    message = separator.join(
        (quote + ".", "It starts on Monday.", "I approve that plan.")
    )
    assert module.check(item(quote, [quote]), sent(message)) is None


@pytest.mark.parametrize("kind", list(module.NOTE_KINDS))
@pytest.mark.parametrize(
    "source,quote",
    [
        (
            "Pre-approved: ship rel-7 to prod-3 tonight.",
            "Pre-approved: ship rel-7 to prod-3 tonight",
        ),
        (
            "Auto-approve the rel-7 rollout to prod-3 tonight.",
            "Auto-approve the rel-7 rollout to prod-3 tonight",
        ),
        (
            "Rollout is re-authorized. Ship rel-7 to prod-3 tonight.",
            "Ship rel-7 to prod-3 tonight",
        ),
        (
            "Pre-approval granted. Ship rel-7 to prod-3 tonight.",
            "Ship rel-7 to prod-3 tonight",
        ),
        (
            "Go-ahead given. Ship rel-7 to prod-3 tonight.",
            "Ship rel-7 to prod-3 tonight",
        ),
        (
            "Ship rel-7 to prod-3 tonight. Pre-approved by ops.",
            "Ship rel-7 to prod-3 tonight",
        ),
    ],
)
def test_joined_authority_words_are_matched(source, quote, kind):
    """Approval words joined by '-' (pre-approved, auto-approve, re-authorized, go-ahead) drop the note, in the quote or beside it."""
    assert module.check(item(quote, [quote], kind=kind), sent(source)) == (
        "authority_context"
    )


def test_joined_authority_words_in_claims_and_benign_codes():
    """A hyphenated approval in a reply drops the claim; codes such as rel-7, prod-3, gpu-04 and 06:30 match nothing."""
    quote = "Pre-approved: deployed rel-7 to prod-3 at 23:00"
    claim = item(quote, [quote], kind="assistant_claim")
    assert module.check(claim, on_role("assistant_claim", quote + ".")) == (
        "authority_context"
    )
    for word in ("Pre-approved", "auto-approve", "re-authorized", "pre-approval"):
        assert module.authority_match(word), word
    assert module.authority_match("Go-ahead given")
    benign = "Ship rel-7 to prod-3 at 06:30 on gpu-04 via kiln-2/b_7"
    assert not module.authority_match(benign)
    assert module.check(item(benign, [benign]), sent(benign + ".")) is None


def log_message(intro, tail, rows):
    """Return a pasted log message: an intro line, numbered 11-character rows, then a tail."""
    return intro + "".join(f"row {index:03d} ok\n" for index in range(rows)) + tail


def test_clip_ends_on_a_complete_sentence_or_whitespace():
    """A clipped text ends at its last complete sentence in the limit, else at its last whitespace; a short text is unchanged."""
    text = "Port 7311 is open. The deployed build is rel-2026.11-B7 on host kiln-2."
    assert module.clip(text, 40) == ("Port 7311 is open.", True)
    assert module.clip(text, len(text)) == (text, False)
    line = "build b-7 on host kiln-2 " * 4
    assert module.clip(line, 28) == ("build b-7 on host kiln-2", True)
    assert module.clip("x" * 50, 20) == ("x" * 20, True)


def test_assistant_reply_cut_inside_a_code_admits_no_truncated_value():
    """A reply clipped at 512 inside rel-2026.11-B7 is sent up to its last complete sentence, and that sentence is not quotable."""
    reply = (
        "Host kiln-2 runs agent a-41 today. "
        + "Build b-7 done. " * 26
        + "Port 7311 is open on kiln-2. "
        + "The deployed build is rel-2026.11-B7 on host kiln-2."
    )
    start = reply.index("rel-2026.11-B7")
    assert start < module.ASSISTANT_CLIP < start + len("rel-2026.11-B7")
    pairs = pair_rows([("Please list the deploy facts.", reply)])
    source, clipped, _, _, _ = module.packet(pairs)
    assert clipped == [1] and source["assistant"][0]["text"].endswith(
        "Port 7311 is open on kiln-2."
    )
    sent_text = module.sent_pairs(source, pairs)
    assert sent_text[1]["clipped"] == ["assistant"]
    for quote, reason in (
        ("The deployed build is rel-2026.1", "quote_not_in_source"),
        ("Port 7311 is open on kiln-2", "quote_context_dropped"),
        ("Host kiln-2 runs agent a-41 today", None),
    ):
        claim = item(quote, [quote], kind="assistant_claim")
        assert module.check(claim, sent_text) == reason, quote


@pytest.mark.parametrize(
    "intro,tail,rows,quote,reason",
    [
        (
            "Atlas-4 backups run on host vault-9.\n",
            "Run the Atlas-4 migration at 03:30 tonight unless the backup fails. I approve this.",
            179,
            "Run the Atlas-4 migration at 03:30 tonight",
            "quote_not_in_source",
        ),
        (
            "Atlas-4 backups go to host vault-9.\n",
            "Run the Atlas-4 migration at 03:30 tonight. I approve this.",
            179,
            "Run the Atlas-4 migration at 03:30 tonight",
            "quote_context_dropped",
        ),
        (
            "Atlas-4 backups go to host vault-9.\n",
            "Run the Atlas-4 migration at 03:30 tonight. I approve this.",
            179,
            "Atlas-4 backups go to host vault-9",
            None,
        ),
        (
            "Orion backups run on vault-9.\n",
            "The Orion intake port is 9446 for staging traffic.",
            181,
            "The Orion intake port is 94",
            "quote_not_in_source",
        ),
    ],
)
def test_user_message_cut_before_its_condition_or_approval(
    intro, tail, rows, quote, reason
):
    """A user message cut at 2,048 characters never yields a quote whose condition, approval or digits lie past the cut."""
    message = log_message(intro, tail, rows)
    raw_end = message[: module.CLIP_CHARS]
    assert raw_end.endswith(("tonight", "tonight.", "port is 94"))
    pairs = pair_rows([(message, "ok")])
    source, clipped, _, listed, _ = module.packet(pairs)
    assert listed == [1] and clipped == [1]
    assert message.startswith(source["user"][0]["text"])
    for kind in ("fact", "constraint"):
        entry = item(quote, [quote], kind=kind)
        assert module.check(entry, module.sent_pairs(source, pairs)) == reason


@pytest.mark.asyncio
async def test_clipped_last_sentence_is_dropped_end_to_end():
    """summarize() marks the clipped user message, so a quote from its last sent sentence, next to an unsent approval, is dropped."""
    message = log_message(
        "Atlas-4 backups go to host vault-9.\n",
        "Run the Atlas-4 migration at 03:30 tonight. I approve this.",
        179,
    )
    quote = "Run the Atlas-4 migration at 03:30 tonight"
    rows = conversation([(message, "ok")] + [(FILLER, "Received.")] * 9)
    port = Port(lynx_output(text=quote, quote=quote, kind="constraint"))
    fitted, report = await reduce(rows, port=port)
    summary = report["summary"]
    assert summary["listed_pairs"] == [1] and summary["clipped_pairs"] == [1]
    assert summary["status"] == "none_verified" and port.generations == 1
    assert summary["dropped"] == {"quote_context_dropped": 1}
    assert "untrusted_history_summary" not in fitted[-1]["content"]


def test_log_intro_filler_is_dropped():
    """'keep it for reference' quoted from a B2 log intro is dropped; its sentence also holds 'nothing'."""
    source = "Here is the ledger worker log from batch 8; nothing to act on, keep it for reference:\nrow ok"
    entry = item("keep it for reference", ["keep it for reference"])
    assert module.check(entry, sent(source)) == "quote_context_dropped"
    assert module.content_free(["keep it for reference"])


def kite_pairs():
    """Return sent text for an original value and two corrections."""
    return {
        1: dict(user="The Kite reports run in Frankfurt.", assistant=None),
        2: dict(user="Change: the Kite reports now run in Warsaw.", assistant=None),
        3: dict(user="Change again: the Kite reports now run in Oslo.", assistant=None),
    }


def kite_items(broken=()):
    """Return three chained notes; the listed pairs get an unquotable text."""
    items = [
        item("Kite reports run in Frankfurt", ["The Kite reports run in Frankfurt"]),
        item(
            "Kite reports now run in Warsaw",
            ["the Kite reports now run in Warsaw"],
            pair=2,
            replaces=1,
        ),
        item(
            "Kite reports now run in Oslo",
            ["the Kite reports now run in Oslo"],
            pair=3,
            replaces=2,
        ),
    ]
    for index in broken:
        items[index]["text"] += " Berlin"
    return items


def test_supersession_links_need_both_notes_and_drops_cascade():
    """A replaces link is rendered only between admitted notes; a dropped newer note drops what it replaces, down the chain."""
    kept, dropped = module.verify(kite_items(), kite_pairs())
    rows = module.admitted_rows(kept, [])
    assert dropped == [] and [row["pairs"] for row in rows] == [[1], [2], [3]]
    assert rows[0]["superseded_by_pairs"] == [2] and rows[1]["superseded_by_pairs"] == [
        3
    ]
    assert "superseded_by_pairs" not in rows[2]
    kept, dropped = module.verify(kite_items(broken=(2,)), kite_pairs())
    assert kept == [] and [entry["reason"] for entry in dropped] == [
        "replaced_by_dropped_note",
        "replaced_by_dropped_note",
        "value_not_quoted",
    ]
    assert dropped[0] == dict(
        index=0,
        slot="note",
        pair=1,
        kind="fact",
        quotes=["The Kite reports run in Frankfurt"],
        text="Kite reports run in Frankfurt",
        replaces=None,
        reason="replaced_by_dropped_note",
    )
    kept, dropped = module.verify(kite_items(broken=(0,)), kite_pairs())
    rows = module.admitted_rows(kept, [])
    assert [row["pairs"] for row in rows] == [[2], [3]]
    assert rows[0]["superseded_by_pairs"] == [3]
    kept, dropped = module.verify(kite_items(broken=(1,)), kite_pairs())
    rows = module.admitted_rows(kept, [])
    assert [row["pairs"] for row in rows] == [
        [3]
    ] and "superseded_by_pairs" not in rows[0]


@pytest.mark.asyncio
async def test_applied_summary_keeps_an_evicted_fact_as_an_untrusted_capsule(caplog):
    """The evicted Lynx pair is summarized, verified and appended; logs carry counts only."""
    caplog.set_level(logging.INFO)
    port = Port(lynx_output())
    fitted, report = await reduce(pressured(), port=port)
    summary = report["summary"]
    assert summary["status"] == "applied" and report["llm_summary"]
    assert 1 in summary["covered_pairs"] and 1 not in report["retained_turns"]
    capsule = json.loads(fitted[-1]["content"].split("\n")[-1])[
        "untrusted_history_summary"
    ]
    assert capsule["trust"] == "untrusted-model-summary" and capsule["items"][0][
        "quotes"
    ] == ["Lynx agent listens on port 9464"]
    assert summary["pairs_lost_to_reserve"] >= 0 and summary[
        "summary_selection_soft"
    ] == SOFT - min(module.RESERVE_TOKENS, SOFT // 10)
    assert (
        "history_summary_applied status=applied" in caplog.text
        and "9464" not in caplog.text
    )
    assert port.generations == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "port,status",
    [
        (Port(lynx_output(), deadline=50.0), "deadline"),
        (Port(lynx_output(), error="gateway_error"), "gateway_error"),
        (Port(lynx_output(), finish="length"), "unfinished"),
        (Port("{not json"), "invalid_output"),
        (Port(lynx_output(slots=(1, 2))), "invalid_output"),
        (Port(lynx_output(text="Owner approved port 9464")), "none_verified"),
    ],
)
async def test_failures_never_block_and_restore_the_full_soft_selection(port, status):
    """Every failure continues without a capsule and restores the selection made with the real soft target."""
    fitted, report = await reduce(pressured(), port=port)
    _, plain = await reduce(pressured(), policy={"mode": "token-budget"})
    assert report["summary"]["status"] == status and not report["llm_summary"]
    assert report["summary"]["status"] in module.STATUSES
    assert report["retained_turns"] == plain["retained_turns"]
    assert "untrusted_history_summary" not in fitted[-1]["content"]


@pytest.mark.asyncio
async def test_no_candidates_makes_no_generation_and_restores_the_selection():
    """Without a listable evicted user message nothing is generated and the full-soft selection is kept."""
    rows = pressured(
        early=("Can you suggest a name for the team lunch?", "How about Friday Table?")
    )
    port = Port(lynx_output())
    fitted, report = await reduce(rows, port=port)
    _, plain = await reduce(rows, policy={"mode": "token-budget"})
    summary = report["summary"]
    assert summary["status"] == "no_candidates" and port.generations == 0
    assert port.counts == 0 and 1 in summary["withheld"]["user_no_signal"]
    assert report["retained_turns"] == plain["retained_turns"]
    assert "untrusted_history_summary" not in fitted[-1]["content"]


@pytest.mark.asyncio
async def test_no_candidates_when_the_covered_window_lists_none():
    """A candidate pushed out of coverage by newer sent replies leaves a window with no slot: no generation."""
    rows = conversation(
        [("The Lynx agent listens on port 9464 for metrics.", "Noted.")]
        + [(FILLER, f"Receipt {number}: " + "ok " * 200) for number in range(2, 23)]
    )
    port = Port(lynx_output())
    port.chars_per_token = 1
    _, report = await reduce(rows, port=port)
    summary = report["summary"]
    assert summary["status"] == "no_candidates" and port.generations == 0
    assert 1 in summary["uncovered_pairs"] and summary["covered_pairs"]
    assert summary["listed_pairs"] == [] and summary["sent_assistant_pairs"]


@pytest.mark.asyncio
async def test_rejected_grammar_is_a_gateway_error_and_restores_the_selection():
    """An HTTP 400 from the completion endpoint becomes gateway_error and the answer proceeds unchanged."""

    def respond(request):
        """Reject the schema like a grammar compile failure."""
        return httpx.Response(400, json=dict(error="grammar"))

    async with httpx.AsyncClient(
        base_url="http://fixture", transport=httpx.MockTransport(respond)
    ) as client:
        port = GatewaySummarizer(
            FakeGateway(), client, deadline=1000.0, clock=lambda: 0.0
        )
        fitted, report = await reduce(pressured(), port=port)
    _, plain = await reduce(pressured(), policy={"mode": "token-budget"})
    assert report["summary"]["status"] == "gateway_error"
    assert report["retained_turns"] == plain["retained_turns"]
    assert "untrusted_history_summary" not in fitted[-1]["content"]


@pytest.mark.asyncio
async def test_receipts_debug_only_text_and_count_only_logs(caplog):
    """Receipts carry the v2 fields; raw output, request and drop texts appear only in debug mode; logs hold counts."""
    caplog.set_level(logging.INFO)
    claim = dict(
        pair=1,
        quotes=["Lynx metrics agent uses port 9464"],
        text="Lynx metrics agent uses port 9445",
    )
    output = lynx_output(claims=[claim])
    _, plain = await reduce(pressured(), port=Port(output))
    summary = plain["summary"]
    for key in (
        "packet_version",
        "schema_template_sha256",
        "schema_sha256",
        "listed_pairs",
        "over_cap_pairs",
        "sent_assistant_pairs",
        "withheld",
        "empty_slots",
        "notes_returned",
        "claims_returned",
        "raw_sha256",
    ):
        assert key in summary, key
    assert summary["listed_pairs"] == [1] and summary["sent_assistant_pairs"] == [1]
    assert summary["items_returned"] == 2 and summary["notes_returned"] == 1
    assert summary["claims_returned"] == 1 and summary["empty_slots"] == 0
    assert summary["dropped"] == {"value_not_quoted": 1}
    assert summary["schema_template_sha256"] == module.SCHEMA_TEMPLATE_SHA256
    assert summary["raw_sha256"] == module.raw_sha256(json.dumps(output))
    assert not any(key.startswith("debug_") for key in summary)
    port = Port(output)
    _, debug = await reduce(pressured(), port=port, summary_debug=True)
    summary = debug["summary"]
    assert summary["debug_raw"] == json.dumps(output)
    assert summary["debug_request"] == dict(
        messages=port.requests[0][0], schema=port.requests[0][1]
    )
    assert summary["debug_dropped"] == [
        dict(
            index=1,
            slot="claim",
            pair=1,
            kind="assistant_claim",
            quotes=claim["quotes"],
            text=claim["text"],
            replaces=None,
            reason="value_not_quoted",
        )
    ]
    lines = [line for line in caplog.text.splitlines() if "history_summary" in line]
    assert lines and all("listed=1" in line and "claims=1" in line for line in lines)
    assert "9464" not in caplog.text and "Lynx" not in caplog.text


@pytest.mark.asyncio
async def test_timeout_is_bounded_and_cancellation_propagates():
    """A slow generation times out inside its own scope; an outer cancellation is never swallowed."""
    port = Port(lynx_output(), deadline=60.0 + 0.05, delay=1.0)
    _, report = await reduce(pressured(), port=port)
    assert report["summary"]["status"] == "timeout"
    slow = Port(lynx_output(), delay=5.0)
    task = asyncio.create_task(reduce(pressured(), port=slow))
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.asyncio
async def test_no_evicted_no_room_and_flag_off_identity():
    """Short histories are untouched; without a port the flag is inert; with the flag off nothing changes."""
    short = conversation([("hello", "hi")] * 3)
    _, report = await reduce(short, port=Port(lynx_output()))
    assert report["summary"]["status"] == "no_evicted" and report["retained_turns"] == [
        1,
        2,
        3,
    ]
    fitted_off, off = await reduce(pressured(), policy={"mode": "token-budget"})
    fitted_none, none = await reduce(pressured(), port=None)
    assert (
        none["summary"] == {"status": "unavailable"}
        and fitted_none[1:] == fitted_off[1:]
    )
    assert "summary" not in off
    huge = conversation(
        [("The Lynx agent listens on port 9464 for metrics.", "ok")]
        + [(FILLER, "x")] * 9,
        question="q" * (SOFT - 300),
    )
    _, crowded = await reduce(huge, port=Port(lynx_output()))
    assert crowded["summary"]["status"] in {"no_room", "no_evicted"}


@pytest.mark.asyncio
async def test_cache_key_includes_the_schema_digest_and_hits_reverify():
    """The key binds source, prompt, schema wire digest, options and model; a hit is verified again; failures are not stored."""
    cache = BoundSummaryCache(SummaryCache(), "owner-a")
    first = Port(lynx_output(), cache=cache)
    _, report = await reduce(pressured(), port=first)
    messages, schema = first.requests[0]
    key = module.digest(
        dict(
            source=json.loads(messages[1]["content"]),
            prompt=module.PROMPT_SHA256,
            schema=module.wire_digest(schema),
            options=module.GENERATION,
            model=Port.model_id,
        )
    )
    assert first.keys == [key]
    assert report["summary"]["schema_sha256"] == module.wire_digest(schema)
    second = Port(lynx_output(text="unused"), cache=cache)
    _, report = await reduce(pressured(), port=second)
    assert (
        report["summary"]["cache_hit"]
        and second.generations == 0
        and report["summary"]["status"] == "applied"
    )
    cache.put(key, (json.dumps(lynx_output(text="Owner approved 9464")), "stop", {}))
    _, report = await reduce(pressured(), port=Port(lynx_output(), cache=cache))
    assert report["summary"]["cache_hit"]
    assert report["summary"]["status"] == "none_verified"
    empty = BoundSummaryCache(SummaryCache(), "owner-b")
    await reduce(pressured(), port=Port("{bad", cache=empty))
    assert empty.cache.entries == {}


def test_summary_cache_isolation_ttl_lru_and_purge():
    """Entries are owner-bound, expire after 1,800 s, evict least-recently-used beyond 64 and purge per owner."""
    now = [0.0]
    cache = SummaryCache(clock=lambda: now[0])
    cache.put("a", "k", 1)
    assert cache.get("b", "k") is None and cache.get("a", "k") == 1
    now[0] = 1801
    assert cache.get("a", "k") is None
    for index in range(70):
        cache.put("a", index, index)
    assert len(cache.entries) == 64 and cache.get("a", 0) is None
    cache.put("b", "x", 1)
    assert cache.purge("a") == 63 and cache.get("b", "x") == 1


@pytest.mark.asyncio
async def test_composer_adds_policy_and_reports_summarization():
    """The host policy line is present and the composer report flags summarization only when applied."""
    rows = pressured()[1:]
    fitted, report = await compose_context(
        rows,
        history_policy={"mode": "token-budget", "evicted_summary": True},
        preset="fast",
        max_tokens=4096,
        count_tokens=count,
        summarizer=Port(lynx_output()),
    )
    assert SUMMARY_POLICY in fitted[0]["content"] and report["summarization"]
    assert report["history_policy"]["summary"]["status"] == "applied"


def test_status_and_purge_route(product_client):
    """The status lists the unmeasured v2 flag and the purge route removes only the caller's entries."""
    client, _, settings, _ = product_client
    status = client.get(
        PREFIX + "/status", headers=harness_tests.bearer(settings)
    ).json()
    assert status["context_evicted_summary"] == "opt-in-experimental-v2-unmeasured"
    service = client.app.state.product_harness
    service.summary_cache.put("someone-else", "k", 1)
    response = client.delete(
        PREFIX + "/context/summaries", headers=harness_tests.bearer(settings)
    )
    assert response.status_code == 200 and response.json() == {"purged": 0}
    assert service.summary_cache.get("someone-else", "k") == 1


def test_cli_flag_forwards_and_requires_a_policy(monkeypatch, capsys):
    """The CLI sends evicted_summary only when asked and refuses it without a policy."""
    calls = []

    class Client:
        """Capture one request."""

        def __init__(self, url, token):
            """Accept the client contract."""

        def request(self, method, path, payload=None):
            """Record the policy."""
            calls.append(payload["history_policy"])
            return {
                "result": {"choices": [{"message": {"content": "a"}}]},
                "context": {},
            }

    monkeypatch.setattr(cli, "ApiClient", Client)
    monkeypatch.setattr(cli, "read_token", lambda path: "t" * 48)
    assert (
        cli.main(
            [
                "--json",
                "chat",
                "--message",
                "q",
                "--history-policy",
                "token-budget",
                "--evicted-summary",
            ]
        )
        == 0
    )
    assert calls[0]["evicted_summary"] is True and "carried_state" not in calls[0]
    assert cli.main(["chat", "--message", "PRIVATE", "--evicted-summary"]) == 2
    assert "PRIVATE" not in capsys.readouterr().err


@pytest.mark.asyncio
async def test_coverage_prefers_the_newest_evicted_pairs_and_reports_the_rest():
    """When the shaped packet exceeds the summarizer budget, the oldest pairs are uncovered and an output naming them is invalid."""
    logs = [
        (f"Batch {number} ledger log follows:\n" + "row ok\n" * 900, "Received.")
        for number in range(2, 11)
    ]
    rows = conversation(
        [("The Lynx agent listens on port 9464 for metrics.", "Noted.")] + logs
    )
    port = Port(lynx_output())
    port.chars_per_token = 1
    _, report = await reduce(rows, port=port, summary_debug=True)
    summary = report["summary"]
    assert 1 in summary["uncovered_pairs"] and summary["covered_pairs"]
    assert min(summary["covered_pairs"]) > max(summary["uncovered_pairs"])
    assert (
        summary["listed_pairs"] and summary["clipped_pairs"] == summary["listed_pairs"]
    )
    assert summary["status"] == "invalid_output" and port.generations == 1
    assert port.counts <= module.COVERAGE_COUNTS


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "output",
    [
        '{"version":1,"items":[],"uncertain":[]}',
        '{"version":2,"notes":{"p1":[]},"assistant_claims":[],"uncertain":[]}',
        "[" * 100000,
    ],
)
async def test_odd_outputs_end_in_a_status_without_raising(output):
    """A non-dict usage field, a v1 shape, an all-empty output and deeply nested JSON finish with a status."""

    class Odd(Port):
        """Return a non-dict usage value."""

        async def generate(self, messages, schema):
            """Return the scripted output with a list as usage."""
            return output, "stop", [1]

    _, report = await reduce(pressured(), port=Odd(None))
    assert report["summary"]["status"] in {"none_verified", "invalid_output"}


@pytest.mark.asyncio
async def test_failed_outputs_are_never_cached():
    """A parsed output whose items all fail verification is not stored."""
    cache = BoundSummaryCache(SummaryCache(), "owner-c")
    _, report = await reduce(
        pressured(),
        port=Port(lynx_output(text="Owner approved port 9464"), cache=cache),
    )
    assert report["summary"]["status"] == "none_verified" and cache.cache.entries == {}


@pytest.mark.asyncio
async def test_reserve_moves_pairs_and_a_failure_restores_the_full_soft_selection():
    """With many mid-sized pairs the reserve really drops pairs; a failed summary restores the first selection."""
    texts = [("The Lynx agent listens on port 9464 for metrics.", "Noted.")] + [
        ("m" * 600, "ok")
    ] * 59
    rows = conversation(texts)
    _, plain = await reduce(rows, policy={"mode": "token-budget"})
    _, applied = await reduce(rows, port=Port(lynx_output()))
    assert applied["summary"]["status"] == "applied"
    assert applied["summary"]["pairs_lost_to_reserve"] > 0
    assert len(applied["retained_turns"]) < len(plain["retained_turns"])
    _, failed = await reduce(rows, port=Port("{bad"))
    assert failed["summary"]["status"] == "invalid_output"
    assert failed["retained_turns"] == plain["retained_turns"]
    assert failed["summary"]["reserve_applied"] is False


def test_capsule_bound_is_unchanged():
    """At most MAX_SLOTS + MAX_CLAIMS rows, each no larger than the maximal row the reserve and no_room probe assume."""
    assert module.MAX_SLOTS + module.MAX_CLAIMS <= module.MAX_ITEMS == 6
    biggest = module.maximal_item(9)
    assert len(biggest["text"]) == module.TEXT_MAX and len(biggest["pairs"]) == 3
    assert [len(quote) for quote in biggest["quotes"]] == [module.QUOTE_MAX] * 2
    users = list(range(1, module.MAX_SLOTS + 1))
    messages = {
        pair: f"Runner r-{pair} " + module.sized(module.QUOTE_MAX, pair)
        for pair in users
    }
    kept = [
        (
            index,
            item(
                messages[pair][: module.QUOTE_MAX],
                [messages[pair][: module.QUOTE_MAX]],
                pair=pair,
                replaces=pair - 1 if pair > 1 else None,
            ),
        )
        for index, pair in enumerate(users)
    ]
    rows = module.admitted_rows(kept, [])
    assert len(rows) <= module.MAX_ITEMS
    for row in rows:
        assert set(row) <= set(biggest)
        assert len(row["text"]) <= module.TEXT_MAX and len(row["pairs"]) <= 3
        assert len(row["quotes"]) <= 2 and len(row.get("superseded_by_pairs", [])) <= 3


ALPHABET = (
    "aAzZ09 .!?;:,-_/'’\n\tđĐơưăâêôáàảãạếềểễệ̣́̀Không chưa nếu chỉ khi trừ khi not only if "
    "approve đồng ý gpu-07 3.14 rel-2026.11-B7 😀​ "
)


def random_text(rng, most=300):
    """Return seeded random text drawn from a mixed Unicode alphabet."""
    return "".join(rng.choice(ALPHABET) for _ in range(rng.randint(0, most)))


def random_value(rng, depth=0):
    """Return a seeded random JSON value of odd shape."""
    choices = [
        lambda: None,
        lambda: rng.choice([True, False]),
        lambda: rng.randint(-3, 12),
        lambda: rng.random(),
        lambda: random_text(rng, 140),
    ]
    if depth < 3:
        choices += [
            lambda: [random_value(rng, depth + 1) for _ in range(rng.randint(0, 3))],
            lambda: {
                rng.choice(
                    ["p1", "p2", "kind", "quotes", "text", "replaces", "pair", "x"]
                ): random_value(rng, depth + 1)
                for _ in range(rng.randint(0, 3))
            },
        ]
    return rng.choice(choices)()


def mutate(value, rng):
    """Replace one random leaf or member of a parsed output with an odd value."""
    if isinstance(value, dict) and value and rng.random() < 0.7:
        key = rng.choice(list(value))
        value[key] = mutate(value[key], rng)
        return value
    if isinstance(value, list) and value and rng.random() < 0.7:
        index = rng.randrange(len(value))
        value[index] = mutate(value[index], rng)
        return value
    return random_value(rng)


@pytest.mark.parametrize("seed", range(40))
def test_seeded_fuzz_never_raises(seed):
    """Random Unicode dialogue and odd output shapes pass candidates, packet, schema_for, parse, flatten and verify without raising."""
    rng = random.Random(seed)
    texts = [(random_text(rng, 2600), random_text(rng, 700)) for _ in range(8)]
    pairs = pair_rows(texts, start=rng.randint(1, 50))
    module.candidates(pairs)
    source, clipped, withheld, listed, over_cap = module.packet(pairs)
    replies = [row["pair"] for row in source["assistant"]]
    assert len(listed) <= module.MAX_SLOTS and set(clipped) <= {p for p, _ in pairs}
    module.schema_for(listed, replies)
    module.schema_for([rng.randint(-2, 9) for _ in range(rng.randint(0, 6))], [0, 0])
    base = dict(
        version=2,
        notes={
            f"p{pair}": [
                dict(
                    kind=rng.choice(module.NOTE_KINDS),
                    quotes=[random_text(rng, 120) or "x"],
                    text=random_text(rng, 160) or "x",
                    replaces=None,
                )
            ]
            for pair in listed
        },
        assistant_claims=[],
        uncertain=[],
    )
    sent_text = module.sent_pairs(source)
    data = module.parse(json.dumps(base, ensure_ascii=False), listed, replies)
    assert data is not None
    kept, dropped = module.verify(module.flatten(data), sent_text)
    assert len(kept) + len(dropped) == len(listed)
    for _ in range(25):
        candidate = mutate(json.loads(json.dumps(base)), rng)
        for raw in (json.dumps(candidate, ensure_ascii=False), random_text(rng, 80)):
            data = module.parse(raw, listed, replies)
            if data is not None:
                items = module.flatten(data)
                module.verify(items, sent_text)


def test_purge_route_removes_the_callers_entries(product_client):
    """DELETE /context/summaries removes the authenticated owner's cached outputs and nobody else's."""
    client, _, settings, _ = product_client
    service = client.app.state.product_harness
    owner = settings["principals"][0]
    service.summary_cache.put(owner, "mine", 1)
    service.summary_cache.put("someone-else", "theirs", 1)
    response = client.delete(
        PREFIX + "/context/summaries", headers=harness_tests.bearer(settings)
    )
    assert response.json() == {"purged": 1}
    assert (
        service.summary_cache.get(owner, "mine") is None
        and service.summary_cache.get("someone-else", "theirs") == 1
    )
