"""Test balanced value/proposition references, exact first native contract dispatch and fail-closed qualification without model calls."""

import copy
import json

import httpx
import pytest

from benchmarks.scripts import d14_boolean_contract as subject
from benchmarks.scripts.d14_structured_acceptance import PROVENANCE_IDS


def test_balanced_questions_require_both_values_and_truth_of_claims():
    """Independently verify boolean semantics and prevent an always-True or always-False strategy from qualifying."""
    cases = subject.make_cases()
    expected = [c["expected"]["answer"] for c in cases]
    assert len(cases) == len({c["id"] for c in cases}) == 12
    assert expected == [
        (2 > 7) and (5 / 0),
        ((8 < 3) and (7 // 0)) is False,
        (9 > 4) or (3 / 0),
        ((6 < 1) and (1 / 0)) is not False,
        ((5 > 2) or (5 / 0)) is True,
        bool([]) and (19 / 0),
        bool([0]) is False,
        not (False or False),
        bool("0") is False,
        False,
        True,
        not False,
    ]
    assert sum(v is True for v in expected) == sum(v is False for v in expected) == 6
    for case in cases:
        assert not any(
            key in json.dumps(case["schema"])
            for key in ['"enum"', '"const"', '"default"', '"description"']
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("fault", [None, "wrong_fact", "missing_reasoning"])
async def test_selected_contract_sends_one_exact_new_task_without_repair_or_retry(
    tmp_path, monkeypatch, fault
):
    """Verify host clarification is actually sent and that even a plausible typed boolean error remains an unchanged first failure."""
    case = subject.make_cases()[0]
    posts = []

    def handler(request):
        """Serve finite authored native metadata while counting actual adapter HTTP dispatches only."""
        model = "qwen3.5-9b-core"
        if request.method == "GET":
            return httpx.Response(200, json=dict(data=[dict(id=model)]))
        posts.append(json.loads(request.content))
        value = copy.deepcopy(case["expected"])
        if fault == "wrong_fact":
            value["answer"] = not value["answer"]
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
                            else "Authored fixture.",
                        ),
                        finish_reason="stop",
                    )
                ],
                usage=dict(prompt_tokens=100, completion_tokens=540),
            ),
        )

    original = httpx.AsyncClient

    def client_factory(**options):
        """Redirect inherited HTTP to the finite fixture without weakening native identity, reasoning or usage validation."""
        return original(
            base_url="http://localhost", transport=httpx.MockTransport(handler)
        )

    monkeypatch.setattr(httpx, "AsyncClient", client_factory)
    row = await subject.measure("core", case, tmp_path)
    assert len(posts) == row["model_requests"] == 1
    assert (
        posts[0]["messages"][1]["content"]
        == subject.BOOLEAN_ANSWER_CONTRACT + case["prompt"]
    )
    assert row["functional_passed"] is (fault is None)
    assert row["contract_verified"] is (fault != "missing_reasoning")
    assert json.loads((tmp_path / case["id"] / "measurement.json").read_text()) == row
    with pytest.raises(FileExistsError):
        await subject.measure("core", case, tmp_path)
    assert len(posts) == 1


@pytest.mark.parametrize(
    "fault",
    [
        None,
        "wrong",
        "always_true",
        "missing_reasoning",
        "missing_contract",
        "duplicate",
        "provenance",
        "cancel",
        "unreaped",
        "baseline",
    ],
)
def test_qualification_requires_balanced_first_answers_and_owned_retirement(fault):
    """Reject missing or false evidence and retain the original full42 gate state even when all twelve new answers qualify."""
    cases = subject.make_cases()
    summary = dict(
        status="MEASUREMENT_COMPLETE", runtime_baseline_restored=True, profiles={}
    )
    for profile in ("core", "unrestricted"):
        summary["profiles"][profile] = dict(
            rows=[
                dict(
                    id=c["id"],
                    category=c["category"],
                    model_requests=1,
                    format_passed=True,
                    functional_passed=True,
                    native_reasoning_verified=True,
                    contract_verified=True,
                )
                for c in cases
            ],
            runtime=dict(reaped=True, exit_code=0, guard_failure=None),
            provenance=[dict(id=p, passed=True) for p in PROVENANCE_IDS],
            cancellation=dict(native_slot_retired=True),
        )
    v = summary["profiles"]["core"]
    if fault == "wrong":
        v["rows"][0]["functional_passed"] = False
    elif fault == "always_true":
        for c in cases:
            c["expected"]["answer"] = True
    elif fault == "missing_reasoning":
        v["rows"][0]["native_reasoning_verified"] = False
    elif fault == "missing_contract":
        v["rows"][0]["contract_verified"] = False
    elif fault == "duplicate":
        v["rows"][1] = copy.deepcopy(v["rows"][0])
    elif fault == "provenance":
        v["provenance"][0]["passed"] = False
    elif fault == "cancel":
        v["cancellation"]["native_slot_retired"] = False
    elif fault == "unreaped":
        v["runtime"]["reaped"] = False
    elif fault == "baseline":
        summary["runtime_baseline_restored"] = False
    result = subject.assess(summary, cases)
    assert result["boolean_contract_qualification_passed"] is (fault is None)
    assert result["original_D14_scores_rewritten"] is False
    assert result["full42_quality_pass_claimed"] is False
