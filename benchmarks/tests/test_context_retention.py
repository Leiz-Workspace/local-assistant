"""Verify the HAR-009-B1 corpus, scoring, schedule and freeze-before-inference runner without network, GPU or model calls."""

import asyncio
import json

import httpx
import pytest

from apps.api.core.model_config import get_model_profile
from apps.harness.inference import ProductInference
from benchmarks import context_retention as module
from src.application.services.context_reduction import HistoryPolicy
from src.application.services.conversation_context import select_whole_turns


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


def test_corpus_shape_and_balance():
    """Twelve cases, three per item type, one Vietnamese case per type, sixteen alternating pairs plus the question."""
    cases = module.corpus()
    assert len(cases) == 12 and len({item["id"] for item in cases}) == 12
    kinds = {}
    for item in cases:
        kinds.setdefault(item["kind"], []).append(item["language"])
        roles = [message["role"] for message in item["messages"]]
        assert roles == ["user", "assistant"] * module.PAIRS + ["user"]
    assert set(kinds) == {
        "early_fact",
        "pinned_constraint",
        "contradiction",
        "unfinished_citation",
    }
    assert all(
        len(languages) == 3 and languages.count("vi") == 1
        for languages in kinds.values()
    )


def test_evidence_lives_only_in_target_turns():
    """Every evidence token occurs in a target pair and in no filler, so presence measures retention of the targets."""
    for item in module.corpus():
        targets = " ".join(
            turn_text(item, number) for number in item["target_turns"]
        ).casefold()
        fillers = " ".join(
            turn_text(item, number)
            for number in range(1, module.PAIRS + 1)
            if number not in item["target_turns"]
        ).casefold()
        for token in item["evidence"]:
            assert token.casefold() in targets and token.casefold() not in fillers, (
                item["id"],
                token,
            )


def test_answers_are_in_target_turns_only_and_never_in_the_question():
    """Each required group occurs in a target pair, never in fillers or the question; distractors stay in targets."""
    for item in module.corpus():
        question = item["messages"][-1]["content"].casefold()
        targets = " ".join(
            turn_text(item, number) for number in item["target_turns"]
        ).casefold()
        fillers = " ".join(
            turn_text(item, number)
            for number in range(1, module.PAIRS + 1)
            if number not in item["target_turns"]
        ).casefold()
        for group in item["required"]:
            assert not any(option.casefold() in question for option in group), item[
                "id"
            ]
            assert not any(option.casefold() in fillers for option in group), item["id"]
        if item["kind"] != "pinned_constraint":
            for group in item["required"]:
                assert any(option.casefold() in targets for option in group), item["id"]
        for token in item["forbidden"]:
            assert (
                token.casefold() not in question and token.casefold() not in fillers
            ), item["id"]


def test_target_turns_sit_outside_the_legacy_and_short_windows_by_design():
    """Legacy keeps eleven recent pairs (6-16) and window3 keeps 14-16, so early targets are evicted by both."""
    expected = dict(
        early_fact=[2],
        pinned_constraint=[1, 15],
        contradiction=[3, 12],
        unfinished_citation=[4],
    )
    for item in module.corpus():
        assert item["target_turns"] == expected[item["kind"]], item["id"]
        legacy = select_whole_turns(item["messages"], 24)
        kept = (len(legacy) - 1) // 2
        assert kept == 11
        legacy_text = " ".join(message["content"] for message in legacy).casefold()
        assert turn_text(item, item["target_turns"][0]).casefold() not in legacy_text, (
            item["id"]
        )
        if item["kind"] == "contradiction":
            assert turn_text(item, 12).casefold() in legacy_text, item["id"]


def test_every_arm_policy_is_valid():
    """All arm policies parse with the production HistoryPolicy model; legacy sends none."""
    for name, policy in module.ARMS:
        if policy is None:
            assert name == "legacy"
            continue
        HistoryPolicy.model_validate(policy)


@pytest.mark.parametrize(
    "text,strict,missing,stale",
    [
        ("Atlas 2.4 uses G-17.", True, 0, 0),
        ("It uses g-17.", True, 0, 0),
        ("Snapshot G-18.", False, 1, 1),
        ("G-17, not G-18.", False, 0, 1),
        ("I do not know.", False, 1, 0),
    ],
)
def test_score_requires_all_groups_and_rejects_stale_tokens(
    text, strict, missing, stale
):
    """Strict success needs every required group and no forbidden token, case-insensitively."""
    item = next(item for item in module.corpus() if item["id"] == "early-fact-atlas")
    result = module.score(text, item)
    assert (result["strict"], len(result["missing"]), len(result["stale"])) == (
        strict,
        missing,
        stale,
    )


def test_score_accepts_listed_alternatives_and_requires_both_parts():
    """Alternatives inside one group are interchangeable; separate groups are all required."""
    saomai = next(item for item in module.corpus() if item["id"] == "constraint-saomai")
    assert module.score("4200000 đồng", saomai)["strict"]
    assert not module.score("4.200.000", saomai)["strict"]
    assert not module.score("4.200.000 VND (khoảng 165 USD)", saomai)["strict"]
    falcon = next(item for item in module.corpus() if item["id"] == "unfinished-falcon")
    assert module.score("Rebuild idx_invoice_date (ticket T-4821).", falcon)["strict"]
    assert not module.score("Rebuild idx_invoice_date.", falcon)["strict"]


def test_schedule_runs_every_arm_once_per_case_with_rotating_first_arm():
    """Sixty attempts, each case once per arm, and the first arm rotates across cases."""
    plan = module.schedule(module.corpus())
    assert len(plan) == 60
    for item in module.corpus():
        assert sorted(
            name for case, name, _ in plan if case["id"] == item["id"]
        ) == sorted(name for name, _ in module.ARMS)
    firsts = [plan[index * 5][1] for index in range(12)]
    assert firsts[:5] == [name for name, _ in module.ARMS]


def fixture_transport(answers, prepared):
    """Serve native preparation endpoints and a complete stream per completion, recording every completion request."""
    calls = []

    def respond(request):
        """Answer model, template and tokenizer probes, then stream one scripted answer."""
        if request.url.path == "/v1/models":
            return httpx.Response(
                200, json={"data": [{"id": get_model_profile("core")["model_id"]}]}
            )
        if request.url.path == "/apply-template":
            prepared.append(1)
            return httpx.Response(200, json={"prompt": "prepared"})
        if request.url.path == "/tokenize":
            return httpx.Response(200, json={"tokens": [1, 2, 3]})
        assert request.url.path == "/v1/chat/completions"
        payload = json.loads(request.content)
        assert payload["stream"] is True and payload["max_tokens"] == 512
        calls.append(payload)
        text = answers(payload)
        event = dict(choices=[dict(delta=dict(content=text), finish_reason="stop")])
        return httpx.Response(
            200,
            text="data: " + json.dumps(event) + "\n\ndata: [DONE]\n\n",
            headers={"content-type": "text/event-stream"},
        )

    return httpx.MockTransport(respond), calls


@pytest.mark.asyncio
async def test_run_freezes_before_inference_and_retains_every_first_outcome(tmp_path):
    """The frozen manifest exists before preparation; sixty attempts run once each with real context composition."""
    prepared = []
    output = tmp_path / "b1"

    def answers(payload):
        """Give the canonical answer when every source fact reached the composed input, else answer unknown."""
        assert (output / "frozen-inputs.json").is_file()
        joined = json.dumps(payload["messages"], ensure_ascii=False).casefold()
        for item in module.corpus():
            if item["messages"][-1]["content"].casefold() in joined:
                if all(token.casefold() in joined for token in item["evidence"]):
                    return " ".join(group[0] for group in item["required"])
                return "unknown"
        return "unknown"

    transport, calls = fixture_transport(answers, prepared)
    result, rows = await module.run(
        ProductInference(transport=transport),
        output,
        pid=42,
        sampler_factory=FixtureSampler,
        preflight=lambda pid: dict(pid=pid, start_ticks=7),
    )
    assert (
        result["status"] == "COMPLETE"
        and result["attempts"] == 60
        and result["retries"] == 0
    )
    assert len(calls) == 60 and len(rows) == 60
    frozen = json.loads((output / "frozen-inputs.json").read_text())
    assert frozen["options"]["retries"] == 0 and len(frozen["corpus"]) == 12
    by_arm = result["summary"]["by_arm"]
    assert by_arm["full"]["present"] == 12 and by_arm["full"]["strict"] == 12
    assert by_arm["window3"]["present"] < by_arm["full"]["present"]
    assert by_arm["window3_pin1"]["by_type"]["pinned_constraint"] == "3/3"
    assert by_arm["legacy"]["by_type"]["contradiction"] == "3/3"
    assert by_arm["legacy"]["by_type"]["early_fact"] == "0/3"
    assert by_arm["compact3"]["present"] >= by_arm["window3"]["present"]
    assert all(row["resources"]["sampled_peak_gpu_process_mib"] == 210 for row in rows)
    assert (
        len(list(output.glob("*-request.json"))) == 60
        and (output / "summary.json").is_file()
    )


@pytest.mark.asyncio
async def test_failed_preparation_is_retained_and_not_retried(tmp_path, monkeypatch):
    """A preparation failure is recorded once and the campaign continues without repeating that attempt."""
    prepared = []
    transport, calls = fixture_transport(lambda payload: "unknown", prepared)
    inference = ProductInference(transport=transport)
    original = inference.prepare
    failed = []

    async def flaky(messages, **options):
        """Fail exactly the first preparation with a finite context error."""
        if not failed:
            failed.append(1)
            raise module.ContextError("context_overflow", 422)
        return await original(messages, **options)

    monkeypatch.setattr(inference, "prepare", flaky)
    result, rows = await module.run(
        inference,
        tmp_path / "b1",
        pid=42,
        sampler_factory=FixtureSampler,
        preflight=lambda pid: dict(pid=pid, start_ticks=7),
    )
    assert result["status"] == "INCOMPLETE" and len(rows) == 60 and len(calls) == 59
    assert (
        rows[0]["status"] == "PREPARE_FAILED" and rows[0]["error"] == "context_overflow"
    )


def test_existing_output_directory_is_refused(tmp_path):
    """A campaign never writes into an earlier result directory."""
    (tmp_path / "b1").mkdir()
    with pytest.raises(FileExistsError):
        asyncio.run(
            module.run(
                ProductInference(
                    transport=httpx.MockTransport(lambda request: httpx.Response(500))
                ),
                tmp_path / "b1",
                pid=42,
                sampler_factory=FixtureSampler,
                preflight=lambda pid: dict(pid=pid, start_ticks=7),
            )
        )
