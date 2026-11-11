"""Verify the opt-in evicted-history summary (ADR-192) with fake ports: flags, verifier, statuses, reserve, cache and routes."""

import asyncio
import json
import logging

import pytest
from pydantic import ValidationError

from apps.cli import main as cli
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


async def count(messages):
    """Count characters as deterministic fake tokens."""
    return sum(len(row["content"]) for row in messages)


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
        """Return the scripted output after an optional real delay."""
        self.generations += 1
        assert (
            messages[0]["content"] == module.SYSTEM_PROMPT and schema == module.SCHEMA
        )
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
        """Read the optional cache."""
        return None if self.cache is None else self.cache.get(key)

    def cache_put(self, key, value):
        """Write the optional cache."""
        if self.cache is not None:
            self.cache.put(key, value)


def lynx_output(
    text="Lynx agent listens on port 9464",
    quote="Lynx agent listens on port 9464",
    pair=1,
    **extra,
):
    """Return a schema-valid output with one fact item."""
    item = dict(
        kind="fact", text=text, pairs=[pair], quotes=[quote], superseded_by=None
    )
    item.update(extra)
    return dict(version=1, items=[item], uncertain=[])


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


def covered(user, assistant="ok", pair=1):
    """Build the verifier's covered-pair map for one pair."""
    return {pair: dict(user=user, assistant=assistant)}


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
    """Whole-token values, contractions, NFD, negation questions, conditions and the authority lexicon."""
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
    assert module.summary_tokens("Café") == ["café"]
    assert module.has_negation("chưa được deploy staging")
    assert not module.has_negation("Có deploy staging không?")
    assert module.has_negation("Không deploy staging.")
    assert module.has_condition("chỉ khi có duyệt") and module.has_condition(
        "only on Friday"
    )
    assert not module.has_condition("chỉ đường khi nào")
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


@pytest.mark.parametrize(
    "item,source,reason",
    [
        (
            dict(
                text="Lynx uses port 9464",
                quotes=["Lynx agent listens on port 9464"],
                pairs=[2],
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
def test_each_drop_reason_at_its_boundary(item, source, reason):
    """Every deterministic check fires on its own case and a grounded item passes."""
    full = dict(kind="fact", pairs=[1], superseded_by=None)
    full.update(item)
    assert module.check(full, covered(source)) == reason


def test_supersession_must_point_to_a_wholly_later_item():
    """A supersession target must exist, differ and cite only later pairs."""
    old = dict(
        kind="fact",
        text="Reports run in Frankfurt",
        pairs=[1],
        quotes=["reports run in Frankfurt"],
        superseded_by=1,
    )
    new = dict(
        kind="fact",
        text="Reports run in Warsaw",
        pairs=[2],
        quotes=["reports run in Warsaw"],
        superseded_by=None,
    )
    pairs = {
        1: dict(user="The reports run in Frankfurt.", assistant="ok"),
        2: dict(user="The reports run in Warsaw.", assistant="ok"),
    }
    kept, dropped = module.verify(
        dict(version=1, items=[old, new], uncertain=[]), pairs
    )
    assert len(kept) == 2 and dropped == []
    old["superseded_by"] = 0
    kept, dropped = module.verify(
        dict(version=1, items=[old, new], uncertain=[]), pairs
    )
    assert [entry["reason"] for entry in dropped] == ["invalid_supersession"]


@pytest.mark.parametrize(
    "raw",
    [
        "not json",
        "{}",
        json.dumps(dict(version=1, items=[dict(kind="fact")], uncertain=[])),
    ],
)
def test_invalid_output_is_rejected_by_shape(raw):
    """Anything not exactly the schema is invalid output."""
    assert module.parse(raw) is None


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
        (Port(lynx_output(text="Owner approved port 9464")), "none_verified"),
    ],
)
async def test_failures_never_block_and_restore_the_full_soft_selection(port, status):
    """Every failure continues without a capsule and restores the selection made with the real soft target."""
    fitted, report = await reduce(pressured(), port=port)
    _, plain = await reduce(pressured(), policy={"mode": "token-budget"})
    assert report["summary"]["status"] == status and not report["llm_summary"]
    assert report["retained_turns"] == plain["retained_turns"]
    assert "untrusted_history_summary" not in fitted[-1]["content"]


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
async def test_cache_hits_reverify_and_failures_are_not_cached():
    """A repeated identical request reuses the raw output (verified again); a failed output is never stored."""
    cache = BoundSummaryCache(SummaryCache(), "owner-a")
    first = Port(lynx_output(), cache=cache)
    await reduce(pressured(), port=first)
    second = Port(lynx_output(text="unused"), cache=cache)
    _, report = await reduce(pressured(), port=second)
    assert (
        report["summary"]["cache_hit"]
        and second.generations == 0
        and report["summary"]["status"] == "applied"
    )
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

    async def ready():
        """Unused helper to keep the event loop active."""

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
    """The status lists the unmeasured flag and the purge route removes only the caller's entries."""
    client, _, settings, _ = product_client
    status = client.get(
        PREFIX + "/status", headers=harness_tests.bearer(settings)
    ).json()
    assert (
        status["context_evicted_summary"] == "opt-in-experimental-v1-measured-no-gain"
    )
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
    """When evicted pairs exceed the summarizer budget, the oldest are uncovered and items citing them are dropped."""
    port = Port(lynx_output())
    port.chars_per_token = 1
    _, report = await reduce(pressured(), port=port, summary_debug=True)
    summary = report["summary"]
    assert 1 in summary["uncovered_pairs"] and summary["covered_pairs"]
    assert min(summary["covered_pairs"]) > max(summary["uncovered_pairs"])
    assert summary["status"] == "none_verified"
    assert summary["dropped"] == {"pair_not_summarized": 1}
    assert port.counts <= module.COVERAGE_COUNTS + 0


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
    item = dict(kind="fact", text=text, pairs=[1], quotes=[quote], superseded_by=None)
    assert module.check(item, covered(source)) == "quote_not_in_source"


def test_value_tokens_share_the_contraction_normalization():
    """A capitalized contraction is normalized on both sides, so an identical quote is grounded."""
    source = "We Cannot ship the beta build tonight."
    item = dict(
        kind="constraint",
        text="We Cannot ship the beta build tonight",
        pairs=[1],
        quotes=["We Cannot ship the beta build tonight"],
        superseded_by=None,
    )
    assert module.check(item, covered(source)) is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "output", ['{"version":1,"items":[],"uncertain":[]}', "[" * 100000]
)
async def test_odd_outputs_end_in_a_status_without_raising(output):
    """A non-dict usage field and deeply nested JSON finish with a status instead of an exception."""

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


def test_supersession_by_a_dropped_item_is_not_rendered():
    """An admitted item never carries supersession pairs taken from an item that failed verification."""
    old = dict(
        kind="fact",
        text="Reports run in Frankfurt",
        pairs=[1],
        quotes=["reports run in Frankfurt"],
        superseded_by=1,
    )
    fake = dict(
        kind="fact",
        text="Reports run in Oslo",
        pairs=[999],
        quotes=["reports run in Oslo"],
        superseded_by=None,
    )
    data = dict(version=1, items=[old, fake], uncertain=[])
    pairs = {1: dict(user="The reports run in Frankfurt.", assistant="ok")}
    kept, dropped = module.verify(data, pairs)
    assert [entry["reason"] for entry in dropped] == ["pair_not_summarized"]
    rows = module.admitted_rows(kept, data, [])
    assert "superseded_by_pairs" not in rows[0]


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
