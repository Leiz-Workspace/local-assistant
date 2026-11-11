"""Verify the HAR-009-C summary v1 corpus, design check, faithfulness scoring and runner without model calls."""

import asyncio
import json

import httpx
import pytest

from apps.api.core.model_config import get_model_profile
from apps.harness.inference import ProductInference
from benchmarks import context_summary as module
from src.application.services import history_summary


class FixtureSampler:
    """Return explicitly synthetic resource counters."""

    def __init__(self, pid, *, expected_start):
        """Require the pinned native identity."""
        assert pid == 42 and expected_start == 7
        self.thread = object()

    def __enter__(self):
        """Begin a synthetic measurement."""
        return self

    def __exit__(self, *errors):
        """Finish without suppressing errors."""

    def report(self):
        """Report fixed synthetic peaks."""
        return dict(
            status="COMPLETE",
            sampled_peak_rss_kib=1,
            sampled_peak_gpu_process_mib=2,
            samples=[],
        )


def transport(output, tokens_per_char=0.5):
    """Serve templates and a length-proportional tokenizer, answer summaries with the gold output and stream answers."""
    calls = dict(answers=[], summaries=[])
    cases = module.corpus()

    def respond(request):
        """Route probes, counts, summary generations and streamed answers."""
        if request.url.path == "/v1/models":
            return httpx.Response(
                200, json={"data": [{"id": get_model_profile("core")["model_id"]}]}
            )
        if request.url.path == "/apply-template":
            body = json.loads(request.content)
            return httpx.Response(
                200,
                json={"prompt": "".join(row["content"] for row in body["messages"])},
            )
        if request.url.path == "/tokenize":
            text = json.loads(request.content)["content"]
            return httpx.Response(
                200, json={"tokens": [0] * int(len(text) * tokens_per_char)}
            )
        payload = json.loads(request.content)
        if not payload["stream"]:
            calls["summaries"].append(payload)
            assert payload["temperature"] == 0 and payload["chat_template_kwargs"] == {
                "enable_thinking": False
            }
            joined = payload["messages"][1]["content"]
            item = next(item for item in cases if item["gold"]["quote"] in joined)
            content = module.oracle_output(item)
            return httpx.Response(
                200,
                json=dict(
                    choices=[dict(message=dict(content=content), finish_reason="stop")],
                    usage=dict(completion_tokens=40),
                ),
            )
        calls["answers"].append(payload)
        joined = json.dumps(payload["messages"], ensure_ascii=False).casefold()
        text = "unknown"
        for item in cases:
            if item["messages"][-1]["content"].casefold() in joined:
                if all(token.casefold() in joined for token in item["evidence"]):
                    text = " ".join(group[0] for group in item["required"]) or "summary"
                break
        event = dict(choices=[dict(delta=dict(content=text), finish_reason="stop")])
        return httpx.Response(
            200,
            text="data: " + json.dumps(event) + "\n\ndata: [DONE]\n\n",
            headers={"content-type": "text/event-stream"},
        )

    return httpx.MockTransport(respond), calls


def test_corpus_gold_quotes_and_leakage():
    """Gold quotes sit verbatim in their source pair; answers and forbidden tokens never appear in fillers or questions."""
    cases = module.corpus()
    assert (
        len(cases) == 14
        and sum(item["kind"] == "authority_gate" for item in cases) == 2
    )
    for item in cases:
        gold = item["gold"]
        assert gold["quote"] in item["messages"][2 * (gold["pair"] - 1)]["content"]
        fillers = " ".join(
            row["content"]
            for number in range(1, module.PAIRS + 1)
            if number not in item["target_turns"]
            for row in item["messages"][2 * (number - 1) : 2 * number]
        ).casefold()
        question = item["messages"][-1]["content"].casefold()
        for group in item["required"]:
            assert not any(option.casefold() in fillers for option in group), item["id"]
        for token in item["forbidden"] + item["evidence"]:
            assert token.casefold() not in fillers, (item["id"], token)
        if item["kind"] not in {"authority_gate", "negation"}:
            for group in item["required"]:
                assert not any(option.casefold() in question for option in group), item[
                    "id"
                ]


def test_oracle_items_pass_the_real_verifier():
    """Every gold item is admitted by the production verifier on its own source pair."""
    for item in module.corpus():
        data = history_summary.parse(module.oracle_output(item))
        pair = item["gold"]["pair"]
        messages = item["messages"][2 * (pair - 1) : 2 * pair]
        covered = {
            pair: dict(user=messages[0]["content"], assistant=messages[1]["content"])
        }
        kept, dropped = history_summary.verify(data, covered)
        assert len(kept) == 1, (item["id"], dropped)


def test_faithfulness_counts_gold_forbidden_and_defects():
    """Faithfulness flags the gold value, forbidden tokens and verifier self-check defects."""
    item = next(item for item in module.corpus() if item["id"] == "num-lynx")
    good = dict(
        admitted_items=[
            dict(
                text="Lynx metrics agent listens on port 9464",
                quotes=["Lynx metrics agent listens on port 9464"],
            )
        ]
    )
    assert module.faithfulness(item, good) == dict(
        admitted=1,
        gold_value_admitted=True,
        forbidden_admitted=[],
        self_check_defects=0,
    )
    bad = dict(
        admitted_items=[dict(text="approved port 9446", quotes=["port 9464 is used"])]
    )
    result = module.faithfulness(item, bad)
    assert (
        result["forbidden_admitted"] == ["9446"] and result["self_check_defects"] == 2
    )


@pytest.mark.asyncio
async def test_run_freezes_after_an_oracle_design_and_measures_every_cell(tmp_path):
    """The design check passes with realistic token density; 84 answer cells run once; summaries recover the targets."""
    output = tmp_path / "c-summary"
    fake, calls = transport(None)
    result, rows = await module.run(
        ProductInference(transport=fake),
        output,
        pid=42,
        sampler_factory=FixtureSampler,
        preflight=lambda pid: dict(pid=pid, start_ticks=7),
    )
    assert result["status"] == "COMPLETE", result.get("violations")
    assert (
        result["attempts"] == 84
        and len(calls["answers"]) == 84
        and len(calls["summaries"]) == 28
    )
    frozen = json.loads((output / "frozen-inputs.json").read_text())
    assert frozen["options"]["retries"] == 0 and len(frozen["composition_plan"]) == 84
    by_arm = result["summary"]["by_arm"]
    assert by_arm["full"]["strict"] == 12 and by_arm["budget"]["strict"] == 0
    assert by_arm["budget_summary"]["strict"] == 12 and by_arm["budget_summary"][
        "summary_statuses"
    ] == {"applied": 14}
    assert by_arm["budget_summary"]["self_check_defects"] == 0


@pytest.mark.asyncio
async def test_design_violation_stops_before_any_completion(tmp_path, monkeypatch):
    """A violated placement writes design-invalid.json and calls no model."""
    monkeypatch.setattr(module, "expectations", lambda item, name, plan: ["forced"])
    fake, calls = transport(None)
    result, rows = await module.run(
        ProductInference(transport=fake),
        tmp_path / "c",
        pid=42,
        sampler_factory=FixtureSampler,
        preflight=lambda pid: dict(pid=pid, start_ticks=7),
    )
    assert (
        result["status"] == "DESIGN_INVALID"
        and rows == []
        and calls["answers"] == []
        and calls["summaries"] == []
    )


def test_existing_output_directory_is_refused(tmp_path):
    """A campaign never writes into an earlier result directory."""
    (tmp_path / "c").mkdir()
    fake, _ = transport(None)
    with pytest.raises(FileExistsError):
        asyncio.run(
            module.run(
                ProductInference(transport=fake),
                tmp_path / "c",
                pid=42,
                sampler_factory=FixtureSampler,
                preflight=lambda pid: dict(pid=pid, start_ticks=7),
            )
        )
