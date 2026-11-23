"""Verify the HAR-009-C1 corpus, client window replay, design checks and freeze-before-inference runner without model calls."""

import json

import httpx
import pytest

from apps.api.core.model_config import get_model_profile
from apps.harness.inference import ProductInference
from benchmarks import context_budget as budget_module
from benchmarks import context_state as module
from src.application.services.working_state import extract


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
            sampled_peak_rss_kib=1,
            sampled_peak_gpu_process_mib=2,
            samples=[],
        )


def transport(answers, tokens_per_char=0.5):
    """Serve native preparation with a length-proportional tokenizer and one scripted streamed answer per completion."""
    calls = []

    def respond(request):
        """Answer probes, templates and tokenizer calls, then stream one answer."""
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
    cases = budget_module.corpus() + module.multiwindow_corpus()

    def answers(payload):
        """Check the freeze exists, then answer from what the composed input holds."""
        assert (output / "frozen-inputs.json").is_file()
        joined = json.dumps(payload["messages"], ensure_ascii=False).casefold()
        last = payload["messages"][-1]["content"].casefold()
        for item in cases:
            question = (
                item.get("question") or item["messages"][-1]["content"]
            ).casefold()
            if last.startswith(question):
                if all(token.casefold() in joined for token in item["evidence"]):
                    return " ".join(group[0] for group in item["required"])
                return "unknown"
        return "unknown"

    return answers


def test_multiwindow_corpus_places_marked_targets_only_in_dropped_pairs():
    """Six 199-pair histories; marked lines exist only in target pairs and answers never leak into fillers or questions."""
    cases = module.multiwindow_corpus()
    assert len(cases) == 6 and len({item["id"] for item in cases}) == 6
    for item in cases:
        assert len(item["pairs"]) == module.QUESTION_PAIR - 1
        turns = [
            dict(
                number=n,
                messages=[
                    dict(role="user", content=u),
                    dict(role="assistant", content=a),
                ],
            )
            for n, (u, a) in enumerate(item["pairs"], start=1)
        ]
        marked = sorted({entry["turn"] for entry in extract(turns, 0)[0]})
        expected = (
            []
            if item["kind"] == "unmarked_fact"
            else [t for t in item["target_turns"] if t < 199]
        )
        assert marked == expected, item["id"]
        fillers = " ".join(
            u + " " + a
            for n, (u, a) in enumerate(item["pairs"], start=1)
            if n not in item["target_turns"]
        ).casefold()
        for group in item["required"]:
            assert not any(
                option.casefold() in item["question"].casefold() for option in group
            )
            assert not any(option.casefold() in fillers for option in group)
        for token in item["evidence"] + item["forbidden"]:
            assert token.casefold() not in fillers, (item["id"], token)


@pytest.mark.asyncio
async def test_client_replay_drops_three_windows_and_carries_state():
    """The CLI rule drops 32 pairs before requests 129, 161 and 193 and the state arm carries the dropped items."""
    fake, _ = transport(lambda payload: "x")
    inference = ProductInference(transport=fake)
    item = module.multiwindow_corpus()[0]
    messages, final, drops, offset = await module.client_requests(
        inference, item, dict(module.ARMS_B[2][1])
    )
    assert drops == [129, 161, 193] and offset == 96
    assert len(messages) == 2 * (199 - 96) + 1
    carried = {entry["text"]: entry["status"] for entry in final["carried_state"]}
    assert carried == {
        "Decision[db-region]: the reporting database runs in Frankfurt.": "superseded",
        "Decision[db-region]: the reporting database moves to Warsaw.": "active",
    }
    legacy, none, _, _ = await module.client_requests(inference, item, None)
    assert none is None and len(legacy) == 23


@pytest.mark.parametrize(
    "case_id,arm,offset,carried,problems",
    [
        ("mw-decision-region", "budget_state", 96, 2, 0),
        ("mw-decision-region", "budget_state", 64, 2, 2),
        ("mw-decision-region", "budget_state", 96, 0, 1),
        ("mw-unmarked-control", "budget_state", 96, 0, 0),
        ("mw-rule-invoice", "budget_drop", 96, 0, 0),
    ],
)
def test_design_expectations_b(case_id, arm, offset, carried, problems):
    """The multi-window design check names a missing drop, a target left in the window and an empty carry."""
    item = next(item for item in module.multiwindow_corpus() if item["id"] == case_id)
    found = module.expectations_b(
        item, arm, dict(history_offset=offset, carried_items=carried)
    )
    assert len(found) == problems


@pytest.mark.asyncio
async def test_run_freezes_then_runs_every_attempt_once(tmp_path):
    """The design passes with realistic token density; 54 attempts run once after the freeze; state fixes the planted cases."""
    output = tmp_path / "c1"
    fake, calls = transport(oracle(output))
    result, rows = await module.run(
        ProductInference(transport=fake),
        output,
        pid=42,
        sampler_factory=FixtureSampler,
        preflight=lambda pid: dict(pid=pid, start_ticks=7),
    )
    assert (
        result["status"] == "COMPLETE" and result["attempts"] == 54 and len(calls) == 54
    )
    frozen = json.loads((output / "frozen-inputs.json").read_text())
    assert frozen["options"]["retries"] == 0 and len(frozen["composition_plan"]) == 54
    part_a, part_b = result["summary"]["A"], result["summary"]["B"]
    assert part_a["by_arm"]["budget_state"]["by_kind"]["stale_marked_rule"] == "2/2"
    assert part_a["by_arm"]["budget"]["by_kind"]["stale_marked_rule"] == "0/2"
    assert part_b["by_arm"]["budget_state"]["strict"] == 5
    assert part_b["by_arm"]["budget_drop"]["strict"] == 0
    assert part_b["by_arm"]["legacy"]["strict"] == 0
    assert part_b["by_arm"]["budget_state"]["by_kind"]["unmarked_fact"] == "0/1"


@pytest.mark.asyncio
async def test_design_violation_stops_before_any_completion(tmp_path, monkeypatch):
    """A violated placement writes design-invalid.json and makes no completion."""
    monkeypatch.setattr(module, "expectations_b", lambda item, arm, plan: ["forced"])
    output = tmp_path / "c1"
    fake, calls = transport(oracle(output))
    result, rows = await module.run(
        ProductInference(transport=fake),
        output,
        pid=42,
        sampler_factory=FixtureSampler,
        preflight=lambda pid: dict(pid=pid, start_ticks=7),
    )
    assert result["status"] == "DESIGN_INVALID" and rows == [] and calls == []
    assert not (output / "frozen-inputs.json").exists()


def test_existing_output_directory_is_refused(tmp_path):
    """A campaign never writes into an earlier result directory."""
    import asyncio

    (tmp_path / "c1").mkdir()
    fake, _ = transport(lambda payload: "x")
    with pytest.raises(FileExistsError):
        asyncio.run(
            module.run(
                ProductInference(transport=fake),
                tmp_path / "c1",
                pid=42,
                sampler_factory=FixtureSampler,
                preflight=lambda pid: dict(pid=pid, start_ticks=7),
            )
        )
