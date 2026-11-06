"""Verify full fresh reasoning-gate coverage, independent references and first native response accounting without model execution."""

import json

import httpx
import pytest

from benchmarks.scripts import d14_reasoning_gate as subject
from src.infrastructure.inference.structured_profile import (
    compile_schema,
    matches_schema,
)


@pytest.fixture
def corpus(tmp_path, monkeypatch):
    """Create only private deterministic new image/text fixtures, never real campaign outputs."""
    monkeypatch.setattr(subject, "ROOT", tmp_path)
    monkeypatch.setattr(subject, "OUTPUT", tmp_path / "gate")
    return subject.make_corpus()


def test_complete_new_corpus_and_independent_hard_references(corpus):
    """Retain original category denominators and independently check new calculations, Python state and structural-only schemas."""
    assert len(corpus) == len({c["id"] for c in corpus}) == 42
    assert {
        name: sum(c["category"] == name for c in corpus)
        for name in [
            "reasoning",
            "coding",
            "agent",
            "vietnamese",
            "multimodal",
            "memory_context",
            "performance",
        ]
    } == dict(
        reasoning=8,
        coding=8,
        agent=8,
        vietnamese=6,
        multimodal=5,
        memory_context=4,
        performance=3,
    )
    cases = {c["id"]: c for c in corpus}
    assert [
        cases[f"reasoned-reasoning-{n}"]["expected"]["answer"] for n in range(1, 9)
    ] == [
        148 * 29,
        120 - 120 * 5 // 8 + 7,
        (127 + 17) // 8,
        False,
        "11:44",
        True,
        5 * 17,
        72,
    ]
    a = [2, 9]
    b = a
    b.append(14)
    x = [9, 15]
    y = x[:]
    y[1] = 27
    assert [
        cases[f"reasoned-coding-{n}"]["expected"]["answer"] for n in range(1, 9)
    ] == [
        a,
        sum(n if n % 2 else -n for n in [3, 4, 7, 10]),
        list(range(4, 18, 5)),
        sorted({"w": 1, "c": 7, "j": 3}),
        x,
        [n * n for n in range(1, 8) if n % 2],
        {"r": 0}.get("r", 21),
        (False and (1 / 0)) is False,
    ]
    for case in corpus:
        assert matches_schema(
            case["expected"], json.loads(compile_schema(case["schema"]))
        )
        assert not any(
            word in json.dumps(case["schema"])
            for word in ['"enum"', '"const"', '"default"', '"description"']
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("fault", [None, "wrong_fact", "missing_reasoning", "overflow"])
async def test_full_gate_measurement_does_not_repair_native_answer_or_hide_condition_failure(
    corpus, tmp_path, monkeypatch, fault
):
    """Exercise one actual new component dispatch with600total tokens and preserve wrong or unsupported native responses as first failures."""
    case = corpus[0]
    posts = []

    def handler(request):
        """Return one finite native fixture and count dispatches rather than fabricating a measured model outcome."""
        model = "qwen3.5-9b-core"
        if request.method == "GET":
            return httpx.Response(200, json=dict(data=[dict(id=model)]))
        posts.append(json.loads(request.content))
        value = dict(case["expected"])
        if fault == "wrong_fact":
            value["answer"] = -900
        return httpx.Response(
            200,
            json=dict(
                model=model,
                choices=[
                    dict(
                        message=dict(
                            role="assistant",
                            content=json.dumps(value),
                            reasoning_content=""
                            if fault == "missing_reasoning"
                            else "Fixture reasoning.",
                        ),
                        finish_reason="stop",
                    )
                ],
                usage=dict(
                    prompt_tokens=200,
                    completion_tokens=1025 if fault == "overflow" else 600,
                ),
            ),
        )

    original = httpx.AsyncClient

    def client_factory(**options):
        """Bind the inherited HTTP client to finite fixture traffic with no external/native service."""
        return original(
            base_url="http://localhost", transport=httpx.MockTransport(handler)
        )

    monkeypatch.setattr(httpx, "AsyncClient", client_factory)
    row = await subject.measure(None, "core", case, tmp_path)
    assert len(posts) == row["model_requests"] == 1
    assert row["format_passed"] is (fault not in {"missing_reasoning", "overflow"})
    assert row["functional_passed"] is (fault is None)
    assert row["native_reasoning_verified"] is (
        fault not in {"missing_reasoning", "overflow"}
    )
    assert json.loads((tmp_path / case["id"] / "measurement.json").read_text()) == row
    with pytest.raises(FileExistsError):
        await subject.measure(None, "core", case, tmp_path)
    assert len(posts) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("fault", [None, "controller_failure", "already_attempted"])
async def test_controller_binding_is_scoped_and_refuses_any_execution_replay(
    tmp_path, monkeypatch, fault
):
    """Restore imported benchmark defaults after either outcome and reject a prior execution before invoking any controller."""
    output = tmp_path / "trial"
    output.mkdir()
    monkeypatch.setattr(subject, "OUTPUT", output)
    original = subject.gate.OUTPUT, subject.gate.FREEZE, subject.gate.measure
    calls = []

    async def controller():
        """Assert exact experiment binding without generating a request or writing real artifacts."""
        calls.append(True)
        assert subject.gate.OUTPUT == output and subject.gate.measure is subject.measure
        if fault == "controller_failure":
            raise ValueError("authored_controller_failure")
        return dict(fixture_only=True)

    monkeypatch.setattr(subject.gate, "run", controller)
    if fault == "already_attempted":
        (output / "execution-freeze.json").write_text("{}")
    if fault:
        with pytest.raises(ValueError):
            await subject.run()
    else:
        assert (await subject.run())["fixture_only"] is True
    assert (subject.gate.OUTPUT, subject.gate.FREEZE, subject.gate.measure) == original
    assert len(calls) == (0 if fault == "already_attempted" else 1)
