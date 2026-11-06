"""Verify the complete contract-selected cohort uses fresh inputs, trusted references and a fail-closed qualification prerequisite."""

import json

import httpx
import pytest

from benchmarks.scripts import d14_contract_full_gate as subject
from src.infrastructure.inference.structured_profile import matches_schema


@pytest.fixture
def corpus(tmp_path, monkeypatch):
    """Create private new text/PNG fixtures without reading ignored model artifacts or changing the original cohort."""
    monkeypatch.setattr(subject, "ROOT", tmp_path)
    monkeypatch.setattr(subject, "OUTPUT", tmp_path / "full")
    return subject.make_corpus()


def test_complete_new_references_and_prior_question_disjointness(corpus):
    """Check independent math/Python answers and prevent a selected repair from silently replaying the observed failure."""
    cases = {c["id"]: c for c in corpus}
    previous = json.loads(subject.PRIOR_CASES.read_text())["cases"]
    assert len(corpus) == len(cases) == 42
    assert all(
        c.get("prompt") not in {p["prompt"] for p in previous if "prompt" in p}
        for c in corpus
    )
    assert [
        cases[f"contract-full-reasoning-{n}"]["expected"]["answer"] for n in range(1, 9)
    ] == [
        163 * 24,
        168 - 168 * 3 // 8 + 11,
        (142 - 16) // 7,
        False,
        "15:26",
        False,
        7 * 12,
        84,
    ]
    a = [5, 11]
    b = a
    b.append(18)
    x = [7, 16]
    y = x[:]
    y[1] = 34
    assert [
        cases[f"contract-full-coding-{n}"]["expected"]["answer"] for n in range(1, 9)
    ] == [
        a,
        sum(n if n % 2 else -n for n in [2, 5, 8, 11]),
        list(range(6, 23, 6)),
        sorted({"v": 4, "d": 2, "p": 9}),
        x,
        [k * k for k in range(2, 11) if k % 2],
        {"s": 0}.get("s", 37),
        ((4 > 9) and (12 / 0)) is False,
    ]
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
    for case in corpus:
        assert matches_schema(case["expected"], case["schema"])
        assert not any(
            key in json.dumps(case["schema"])
            for key in ['"enum"', '"const"', '"default"', '"description"']
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("fault", [None, "wrong_fact", "missing_reasoning"])
async def test_selected_contract_full_first_measurement_never_repairs_booleans(
    corpus, tmp_path, monkeypatch, fault
):
    """Verify the actual selected host prefix and preserve a typed incorrect boolean as a full quality failure."""
    case = next(c for c in corpus if c["id"] == "contract-full-coding-8")
    calls = []

    def handler(request):
        """Serve a finite above512 usage fixture with no native inference or benchmark-result claims."""
        model = "qwen3.5-9b-core"
        if request.method == "GET":
            return httpx.Response(200, json=dict(data=[dict(id=model)]))
        calls.append(json.loads(request.content))
        value = dict(case["expected"])
        if fault == "wrong_fact":
            value["answer"] = False
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
                            else "Authored fixture reasoning.",
                        ),
                        finish_reason="stop",
                    )
                ],
                usage=dict(prompt_tokens=200, completion_tokens=540),
            ),
        )

    original = httpx.AsyncClient

    def client_factory(**options):
        """Redirect only fixture HTTP while retaining the actual adapter's request and reply validation."""
        return original(
            base_url="http://localhost", transport=httpx.MockTransport(handler)
        )

    monkeypatch.setattr(httpx, "AsyncClient", client_factory)
    row = await subject.measure(None, "core", case, tmp_path)
    assert len(calls) == row["model_requests"] == 1
    assert (
        calls[0]["messages"][1]["content"]
        == subject.BOOLEAN_ANSWER_CONTRACT + case["prompt"]
    )
    assert row["functional_passed"] is (fault is None)
    assert row["request_contract_verified"] is (fault != "missing_reasoning")
    with pytest.raises(FileExistsError):
        await subject.measure(None, "core", case, tmp_path)
    assert len(calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "fault",
    [None, "not_qualified", "result_hash", "already_attempted", "controller_failure"],
)
async def test_independent_qualification_is_required_before_any_full_dispatch(
    tmp_path, monkeypatch, fault
):
    """Reject missing qualification, modified prior evidence and any old execution while restoring shared controller state on failure."""
    output = tmp_path / "output"
    output.mkdir()
    result = tmp_path / "qualified-result.json"
    result.write_text("{}")
    qualification = tmp_path / "qualification.json"
    qualification.write_text(
        json.dumps(
            dict(
                acceptance=dict(
                    boolean_contract_qualification_passed=fault != "not_qualified"
                ),
                first_result=dict(
                    path=result.name,
                    sha256="0" * 64
                    if fault == "result_hash"
                    else subject.shared.BASE["digest"](result),
                ),
            )
        )
    )
    monkeypatch.setattr(subject, "ROOT", tmp_path)
    monkeypatch.setattr(subject, "OUTPUT", output)
    monkeypatch.setattr(subject, "QUALIFICATION", qualification)
    if fault == "already_attempted":
        (output / "execution-freeze.json").write_text("{}")
    original = subject.shared.OUTPUT, subject.shared.FREEZE, subject.shared.measure
    calls = []

    async def execute():
        """Count a finite fixture controller entry without native/model work."""
        calls.append(True)
        assert subject.shared.measure is subject.measure
        if fault == "controller_failure":
            raise ValueError("authored_controller_failure")
        return dict(fixture_only=True)

    monkeypatch.setattr(subject.shared, "run", execute)
    if fault:
        with pytest.raises(ValueError):
            await subject.run()
    else:
        assert (await subject.run())["fixture_only"] is True
    assert len(calls) == (1 if fault in {None, "controller_failure"} else 0)
    assert (
        subject.shared.OUTPUT,
        subject.shared.FREEZE,
        subject.shared.measure,
    ) == original
