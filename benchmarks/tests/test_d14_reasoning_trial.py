"""Validate fresh references, matched request-only thinking conditions and fail-closed paired first accounting without model calls."""

import copy
import json

import httpx
import pytest

from benchmarks.scripts import d14_reasoning_trial as trial
from benchmarks.scripts.d14_structured_acceptance import PROVENANCE_IDS
from src.infrastructure.inference.structured_profile import (
    StructuredProfileError,
    matches_schema,
)


def test_new_corpus_independent_math_and_python_references():
    """Verify exact fresh hard-case references independently of any native generation or hidden answer feedback."""
    cases = trial.make_cases()
    assert len(cases) == len({c["id"] for c in cases}) == 12
    expected = {
        c["id"].removeprefix("reasoning-trial-"): c["expected"]["answer"] for c in cases
    }
    assert expected["tank"] == 140 - 140 * 3 // 7 + 9
    assert expected["equation"] == (103 + 14) // 9
    assert expected["xor"] is False
    assert expected["loop"] == sum(n if n % 2 else -n for n in [1, 2, 6, 9])
    x = [6, 12]
    y = x[:]
    y[0] = 31
    assert expected["slice"] == x
    assert expected["comprehension"] == [k * k for k in range(2, 9) if k % 2]
    assert expected["zero"] == {"m": 0}.get("m", 29)
    assert expected["shortcircuit"] is (True or (5 // 0))
    for case in cases:
        assert matches_schema(case["expected"], case["schema"])
        assert not any(
            key in json.dumps(case["schema"])
            for key in ['"enum"', '"const"', '"default"', '"description"']
        )


@pytest.mark.parametrize("profile", ["core", "unrestricted"])
def test_matched_payload_changes_only_declared_request_local_reasoning_fields(profile):
    """Keep original system/schema/question/model/temperature/cache settings identical with matched maximum generation budgets."""
    case = trial.make_cases()[0]
    direct = trial.TrialAdapter(
        profile=profile,
        schema=case["schema"],
        thinking=False,
        endpoint="http://127.0.0.1:18080",
    ).payload(case["prompt"], (), False)
    reasoned = trial.TrialAdapter(
        profile=profile,
        schema=case["schema"],
        thinking=True,
        endpoint="http://127.0.0.1:18080",
    ).payload(case["prompt"], (), False)
    assert direct["max_tokens"] == reasoned["max_tokens"] == 1024
    assert direct["reasoning_format"] == reasoned["reasoning_format"] == "deepseek"
    assert (
        direct["reasoning_budget_tokens"] == 0
        and reasoned["reasoning_budget_tokens"] == 512
    )
    assert direct["chat_template_kwargs"]["enable_thinking"] is False
    assert reasoned["chat_template_kwargs"]["enable_thinking"] is True
    for value in (direct, reasoned):
        del value["reasoning_budget_tokens"], value["chat_template_kwargs"]
    assert direct == reasoned


@pytest.mark.parametrize("thinking", [False, True])
@pytest.mark.parametrize("tokens", [540, 1024, 1025])
def test_request_and_validation_share_the_complete_declared_token_budget(
    thinking, tokens
):
    """Cover native usage above512 and reject only values beyond the declared1024 total budget."""
    case = trial.make_cases()[0]
    adapter = trial.TrialAdapter(
        profile="core",
        schema=case["schema"],
        thinking=thinking,
        endpoint="http://127.0.0.1:18080",
    )
    assert (
        adapter.max_tokens
        == adapter.payload(case["prompt"], (), False)["max_tokens"]
        == 1024
    )
    value = dict(
        model=adapter.model,
        choices=[
            dict(
                message=dict(role="assistant", content=json.dumps(case["expected"])),
                finish_reason="stop",
            )
        ],
        usage=dict(prompt_tokens=100, completion_tokens=tokens),
    )
    if tokens <= 1024:
        assert adapter.validate_reply(value)[1]["completion_tokens"] == tokens
    else:
        with pytest.raises(StructuredProfileError):
            adapter.validate_reply(value)


@pytest.mark.parametrize("fault", ["endpoint", "truthy", "image", "stream"])
def test_research_adapter_does_not_expand_scope(fault):
    """Confine this experiment to literal host conditions and one owned text endpoint without changing production adapter permissions."""
    case = trial.make_cases()[0]
    with pytest.raises(StructuredProfileError):
        adapter = trial.TrialAdapter(
            profile="core",
            schema=case["schema"],
            thinking=1 if fault == "truthy" else True,
            endpoint="http://127.0.0.1:8080"
            if fault == "endpoint"
            else "http://127.0.0.1:18080",
        )
        adapter.payload(
            case["prompt"], (b"image",) if fault == "image" else (), fault == "stream"
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "fault", [None, "wrong_fact", "missing_reasoning", "malformed", "truncated"]
)
async def test_native_shaped_first_attempt_keeps_failures_and_observes_reasoning_condition(
    tmp_path, monkeypatch, fault
):
    """Exercise inherited HTTP ownership/validation while retaining wrong facts and never retrying an absent, malformed or truncated thinking answer."""
    case = trial.make_cases()[0]
    posts = []

    def handler(request):
        """Return finite authored native metadata without running an actual model or producing trusted benchmark claims."""
        model = "qwen3.5-9b-core"
        if request.method == "GET":
            return httpx.Response(200, json=dict(data=[dict(id=model)]))
        posts.append(json.loads(request.content))
        value = copy.deepcopy(case["expected"])
        if fault == "wrong_fact":
            value["answer"] = -999
        return httpx.Response(
            200,
            json=dict(
                model=model,
                choices=[
                    dict(
                        message=dict(
                            role="assistant",
                            content="[]" if fault == "malformed" else json.dumps(value),
                            reasoning_content=""
                            if fault == "missing_reasoning"
                            else "Authored fixture reasoning.",
                        ),
                        finish_reason="length" if fault == "truncated" else "stop",
                    )
                ],
                usage=dict(prompt_tokens=100, completion_tokens=60),
            ),
        )

    original = httpx.AsyncClient

    def client_factory(**options):
        """Redirect the actual adapter to the finite fixture transport while preserving native request validation."""
        return original(
            base_url="http://localhost", transport=httpx.MockTransport(handler)
        )

    monkeypatch.setattr(httpx, "AsyncClient", client_factory)
    row = await trial.measure("core", case, True, tmp_path)
    assert len(posts) == row["model_requests"] == 1
    assert row["functional_passed"] is (fault in {None, "missing_reasoning"})
    assert row["reasoning_condition_observed"] is (fault in {None, "wrong_fact"})
    directory = tmp_path / case["id"] / "thinking"
    assert (directory / "native-response.bin").read_bytes()
    assert json.loads((directory / "measurement.json").read_text()) == row
    with pytest.raises(FileExistsError):
        await trial.measure("core", case, True, tmp_path)
    assert len(posts) == 1


@pytest.mark.parametrize(
    "fault",
    [
        None,
        "wrong_thinking",
        "missing_condition",
        "duplicate",
        "retry",
        "provenance",
        "unreaped",
        "baseline",
        "incomplete",
    ],
)
def test_paired_acceptance_cannot_close_original_gate_or_hide_missing_conditions(fault):
    """Admit larger fresh validation only after complete exact paired text evidence and keep historical D14 failures immutable even on success."""
    cases = trial.make_cases()
    summary = dict(
        status="MEASUREMENT_COMPLETE", runtime_baseline_restored=True, profiles={}
    )
    for profile in ("core", "unrestricted"):
        summary["profiles"][profile] = dict(
            rows=[
                dict(
                    id=c["id"],
                    category=c["category"],
                    thinking=flag,
                    model_requests=1,
                    reasoning_condition_observed=True,
                    format_passed=True,
                    functional_passed=True,
                    wall_seconds=1,
                    result=dict(output_tokens=20),
                )
                for c in cases
                for flag in (False, True)
            ],
            runtime=dict(reaped=True, exit_code=0, guard_failure=None),
            provenance=[dict(id=key, passed=True) for key in PROVENANCE_IDS],
        )
    value = summary["profiles"]["core"]
    if fault == "wrong_thinking":
        value["rows"][1]["functional_passed"] = False
    elif fault == "missing_condition":
        value["rows"][1]["reasoning_condition_observed"] = False
    elif fault == "duplicate":
        value["rows"][1] = copy.deepcopy(value["rows"][3])
    elif fault == "retry":
        value["rows"][1]["model_requests"] = 2
    elif fault == "provenance":
        value["provenance"][1] = copy.deepcopy(value["provenance"][0])
    elif fault == "unreaped":
        value["runtime"]["reaped"] = False
    elif fault == "baseline":
        summary["runtime_baseline_restored"] = False
    elif fault == "incomplete":
        summary["status"] = "INCOMPLETE"
    result = trial.assess(summary, cases)
    assert result["thinking_qualified_for_fresh_full_validation"] is (fault is None)
    assert result["original_D14_quality_gate_passed"] is False
    assert result["original_scores_rewritten"] is False
