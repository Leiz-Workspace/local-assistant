"""Verify the HAR-009-B2 corpus, design checks, schedule and freeze-before-inference runner without network, GPU or model calls."""

import asyncio
import json

import httpx
import pytest

from apps.api.core.model_config import get_model_profile
from apps.harness.inference import ProductInference
from benchmarks import context_budget as module
from src.application.services.context_reduction import (
    HistoryPolicy,
    history_parts,
    importance_marker,
)


class FixtureSampler:
    """Return explicitly synthetic resource counters without touching a native process or GPU."""

    def __init__(self, pid, *, expected_start):
        """Require the pinned native identity on every request measurement."""
        assert pid == 42 and expected_start == 7
        self.thread = object()

    def __enter__(self):
        """Begin a synthetic measurement with no side effects."""
        return self

    def __exit__(self, *errors):
        """Finish without suppressing the measured operation's exception."""

    def report(self):
        """Report fixed synthetic peaks in the real report shape."""
        return dict(
            status="COMPLETE",
            sampled_peak_rss_kib=120,
            sampled_peak_gpu_process_mib=210,
            samples=[],
        )


def turn_text(item, number):
    """Return the user and assistant text of one 1-based history pair."""
    pair = item["messages"][2 * (number - 1) : 2 * number]
    return pair[0]["content"] + " " + pair[1]["content"]


def split(item):
    """Return the casefolded target text, filler text and question of one case."""
    pairs = (len(item["messages"]) - 1) // 2
    targets = " ".join(turn_text(item, n) for n in item["target_turns"]).casefold()
    fillers = " ".join(
        turn_text(item, n) for n in range(1, pairs + 1) if n not in item["target_turns"]
    ).casefold()
    return targets, fillers, item["messages"][-1]["content"].casefold()


def test_corpus_shape_regimes_and_markers():
    """Eight long sixteen-pair cases and four short forty-pair cases; only declared pair-1 rules carry a marker."""
    cases = module.corpus()
    assert len(cases) == 12 and len({item["id"] for item in cases}) == 12
    assert [item["regime"] for item in cases].count("long") == 8
    for item in cases:
        pairs = module.LONG_PAIRS if item["regime"] == "long" else module.SHORT_PAIRS
        roles = [message["role"] for message in item["messages"]]
        assert roles == ["user", "assistant"] * pairs + ["user"]
        _, turns, _ = history_parts(item["messages"])
        marked = [turn["number"] for turn in turns if importance_marker(turn)]
        expected = (
            [1] if item["kind"] in {"marked_constraint", "stale_marked_rule"} else []
        )
        assert marked == expected, item["id"]
    long_kinds = {item["kind"] for item in cases if item["regime"] == "long"}
    assert long_kinds == {
        "early_fact",
        "marked_constraint",
        "unmarked_constraint",
        "stale_marked_rule",
    }


def test_facts_live_only_in_targets_and_never_in_the_question():
    """Evidence and stated answers occur only in target pairs; stale tokens never occur in fillers or the question."""
    derived = {"marked_constraint", "unmarked_constraint"}
    for item in module.corpus():
        targets, fillers, question = split(item)
        for token in item["evidence"]:
            assert token.casefold() in targets, (item["id"], token)
            assert token.casefold() not in fillers, (item["id"], token)
            assert token.casefold() not in question, (item["id"], token)
        for group in item["required"]:
            assert not any(option.casefold() in question for option in group)
            assert not any(option.casefold() in fillers for option in group)
            if item["kind"] not in derived:
                assert any(option.casefold() in targets for option in group)
        for token in item["forbidden"]:
            assert token.casefold() not in fillers and token.casefold() not in question


def test_long_fillers_are_deterministic_and_long():
    """Log fillers repeat exactly for the same seed and dominate the long-regime token cost."""
    first = module.log_block("long-fact-kestrel", 5, "en")
    assert first == module.log_block("long-fact-kestrel", 5, "en")
    assert first != module.log_block("long-fact-kestrel", 6, "en")
    assert len(first[0].splitlines()) == module.LOG_LINES + 1
    assert len(first[0]) > 5000


@pytest.mark.parametrize(
    "case_id,arm,retained,problems",
    [
        ("short-fact-lynx", "legacy", list(range(30, 41)), []),
        ("short-fact-lynx", "legacy", list(range(29, 41)), 1),
        ("short-fact-lynx", "budget", list(range(2, 41)), 1),
        ("long-stale-hydra", "legacy", list(range(6, 17)), []),
        ("long-stale-hydra", "legacy", list(range(7, 17)), 1),
        ("long-fact-kestrel", "legacy", list(range(4, 17)), 1),
        ("long-stale-hydra", "budget", [1] + list(range(9, 17)), []),
        ("long-stale-hydra", "budget", [1] + list(range(6, 17)), 1),
        ("long-marked-heron", "budget", list(range(9, 17)), 1),
        ("long-unmarked-osprey", "budget", [1] + list(range(9, 17)), 1),
        ("long-unmarked-osprey", "compact", [1, 2, 3], []),
    ],
)
def test_design_expectations(case_id, arm, retained, problems):
    """The design check names each misplaced window and accepts the intended placements."""
    item = next(item for item in module.corpus() if item["id"] == case_id)
    found = module.expectations(item, arm, retained)
    assert (found == []) if problems == [] else (len(found) == problems)


def test_arms_and_schedule():
    """All policies parse; thirty-six attempts run each case once per arm with a rotating first arm."""
    for name, policy in module.ARMS:
        if policy is not None:
            HistoryPolicy.model_validate(policy)
    plan = module.schedule(module.corpus())
    assert len(plan) == 36
    firsts = [plan[index * 3][1] for index in range(3)]
    assert firsts == [name for name, _ in module.ARMS]


def fixture_transport(answers, tokens_per_char):
    """Serve native preparation with a length-proportional tokenizer and stream one scripted answer per completion."""
    calls = []

    def respond(request):
        """Answer model, template and tokenizer probes, then stream one scripted answer."""
        if request.url.path == "/v1/models":
            return httpx.Response(
                200, json={"data": [{"id": get_model_profile("core")["model_id"]}]}
            )
        if request.url.path == "/apply-template":
            body = json.loads(request.content)
            text = "".join(row["content"] for row in body["messages"])
            return httpx.Response(200, json={"prompt": text})
        if request.url.path == "/tokenize":
            text = json.loads(request.content)["content"]
            return httpx.Response(
                200, json={"tokens": [0] * int(len(text) * tokens_per_char)}
            )
        assert request.url.path == "/v1/chat/completions"
        payload = json.loads(request.content)
        assert payload["stream"] is True and payload["max_tokens"] == 512
        calls.append(payload)
        event = dict(
            choices=[dict(delta=dict(content=answers(payload)), finish_reason="stop")]
        )
        return httpx.Response(
            200,
            text="data: " + json.dumps(event) + "\n\ndata: [DONE]\n\n",
            headers={"content-type": "text/event-stream"},
        )

    return httpx.MockTransport(respond), calls


def oracle(output):
    """Answer canonically only when every evidence token reached the composed input."""

    def answers(payload):
        """Check the freeze exists, then answer from what the composed input actually holds."""
        assert (output / "frozen-inputs.json").is_file()
        joined = json.dumps(payload["messages"], ensure_ascii=False).casefold()
        for item in module.corpus():
            if item["messages"][-1]["content"].casefold() in joined:
                if all(token.casefold() in joined for token in item["evidence"]):
                    return " ".join(group[0] for group in item["required"])
                return "unknown"
        return "unknown"

    return answers


async def campaign(tmp_path, tokens_per_char=0.5, inference=None, calls=None):
    """Run one fixture campaign and return its result, rows and recorded completions."""
    output = tmp_path / "b2"
    if inference is None:
        transport, calls = fixture_transport(oracle(output), tokens_per_char)
        inference = ProductInference(transport=transport)
    result, rows = await module.run(
        inference,
        output,
        pid=42,
        sampler_factory=FixtureSampler,
        preflight=lambda pid: dict(pid=pid, start_ticks=7),
    )
    return output, result, rows, calls


@pytest.mark.asyncio
async def test_run_checks_design_freezes_and_retains_every_first_outcome(tmp_path):
    """With a realistic token density the design passes, the freeze precedes completions and 36 attempts run once."""
    output, result, rows, calls = await campaign(tmp_path)
    assert result["status"] == "COMPLETE" and result["attempts"] == 36
    assert len(calls) == 36 and len(rows) == 36 and result["retries"] == 0
    frozen = json.loads((output / "frozen-inputs.json").read_text())
    assert len(frozen["composition_plan"]) == 36 and frozen["options"]["retries"] == 0
    by_arm = result["summary"]["by_arm"]
    assert by_arm["budget"]["by_group"]["regime:short"] == "4/4"
    assert by_arm["legacy"]["by_group"]["regime:short"] == "0/4"
    assert by_arm["budget"]["by_group"]["marked_constraint"] == "2/2"
    assert by_arm["budget"]["by_group"]["stale_marked_rule"] == "0/2"
    assert by_arm["legacy"]["by_group"]["stale_marked_rule"] == "2/2"
    paired = result["summary"]["paired"]["budget"]
    assert sorted(paired["regressions_vs_legacy"]) == [
        "long-stale-daibang",
        "long-stale-hydra",
    ]
    budget_rows = [row for row in rows if row["arm"] == "budget"]
    assert all(row["history_policy"]["mode"] == "token-budget" for row in budget_rows)
    assert all(row["resources"]["sampled_peak_gpu_process_mib"] == 210 for row in rows)


@pytest.mark.asyncio
async def test_invalid_design_stops_before_any_completion(tmp_path):
    """A tokenizer that puts no pressure on the long regime fails the design check and runs nothing."""
    output, result, rows, calls = await campaign(tmp_path, tokens_per_char=0.01)
    assert result["status"] == "DESIGN_INVALID" and result["native_calls"] == 0
    assert rows == [] and calls == []
    assert not (output / "frozen-inputs.json").exists()
    assert (output / "design-invalid.json").is_file()


@pytest.mark.asyncio
async def test_failed_preparation_is_retained_and_not_retried(tmp_path, monkeypatch):
    """A preparation failure after the design check is recorded once and the campaign continues."""
    output = tmp_path / "b2"
    transport, calls = fixture_transport(oracle(output), 0.5)
    inference = ProductInference(transport=transport)
    original = inference.prepare
    seen = []

    async def flaky(messages, **options):
        """Fail exactly the first attempt's preparation, after the 36 design compositions."""
        seen.append(1)
        if len(seen) == 37:
            raise module.ContextError("context_overflow", 422)
        return await original(messages, **options)

    monkeypatch.setattr(inference, "prepare", flaky)
    _, result, rows, _ = await campaign(tmp_path, inference=inference, calls=calls)
    assert result["status"] == "INCOMPLETE" and len(rows) == 36 and len(calls) == 35
    assert (
        rows[0]["status"] == "PREPARE_FAILED" and rows[0]["error"] == "context_overflow"
    )


def test_existing_output_directory_is_refused(tmp_path):
    """A campaign never writes into an earlier result directory."""
    (tmp_path / "b2").mkdir()
    with pytest.raises(FileExistsError):
        asyncio.run(campaign(tmp_path))
