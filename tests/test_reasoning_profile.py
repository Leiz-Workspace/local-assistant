"""Test request-local native thinking, aligned token budgets, immutable final values and streaming separation without running models."""

import copy
import json

import httpx
import pytest

from src.infrastructure.inference.reasoning_profile import (
    BOOLEAN_ANSWER_CONTRACT,
    ReasoningProfileAdapter,
)
from src.infrastructure.inference.structured_profile import (
    StructuredProfileAdapter,
    StructuredProfileError,
)

SCHEMA = dict(
    type="object",
    properties=dict(answer=dict(type="integer")),
    required=["answer"],
    additionalProperties=False,
)


def reply(tokens=540, reasoning="Authored fixture reasoning.", answer=17):
    """Construct finite explicit fixture metadata with no claim that the reported usage was measured on a model."""
    return dict(
        model="qwen3.5-9b-core",
        choices=[
            dict(
                message=dict(
                    role="assistant",
                    content=json.dumps(dict(answer=answer)),
                    reasoning_content=reasoning,
                ),
                finish_reason="stop",
            )
        ],
        usage=dict(prompt_tokens=40, completion_tokens=tokens),
    )


@pytest.mark.parametrize("tokens", [513, 540, 1024])
def test_declared_request_budget_matches_native_validator_above_old_limit(tokens):
    """Accept complete thinking-plus-answer usage within 1024 without reproducing the first research adapter's 512-token validation bug."""
    adapter = ReasoningProfileAdapter(profile="core", schema=SCHEMA)
    payload = adapter.payload("Return the requested object.", (), False)
    content, usage = adapter.validate_reply(reply(tokens=tokens))
    assert payload["max_tokens"] == adapter.max_tokens == 1024
    assert usage["completion_tokens"] == tokens
    assert content == '{"answer": 17}'


def test_default_adapter_and_templates_are_unchanged():
    """Keep explicit thinking selection out of the passed default adapter and preserve exact profile/system/schema bindings."""
    baseline = StructuredProfileAdapter(profile="core", schema=SCHEMA)
    selected = ReasoningProfileAdapter(profile="core", schema=SCHEMA)
    a = baseline.payload("Question", (), False)
    b = selected.payload("Question", (), False)
    assert baseline.max_tokens == a["max_tokens"] == 256
    assert a["chat_template_kwargs"]["enable_thinking"] is False
    assert b["chat_template_kwargs"]["enable_thinking"] is True
    assert b["reasoning_budget_tokens"] == 512 and b["reasoning_format"] == "deepseek"
    for key in ["messages", "response_format", "model", "cache_prompt", "temperature"]:
        assert a[key] == b[key]


@pytest.mark.parametrize("kind", ["integer", "boolean"])
def test_optional_contract_is_host_selected_shape_based_and_never_embeds_answer_values(
    kind,
):
    """Clarify only boolean tasks under an explicit host option while retaining exact templates/schema and the unchanged default path."""
    schema = dict(
        type="object",
        properties=dict(answer=dict(type=kind)),
        required=["answer"],
        additionalProperties=False,
    )
    default = ReasoningProfileAdapter(profile="core", schema=schema)
    selected = ReasoningProfileAdapter(
        profile="core", schema=schema, boolean_answer_contract=True
    )
    plain = default.payload("User question", (), False)
    payload = selected.payload("User question", (), False)
    assert plain["messages"][1]["content"] == "User question"
    assert (
        payload["messages"][1]["content"]
        == (BOOLEAN_ANSWER_CONTRACT if kind == "boolean" else "") + "User question"
    )
    assert payload["messages"][0] == plain["messages"][0]
    assert payload["response_format"] == plain["response_format"]
    assert not any(
        key in json.dumps(payload["response_format"])
        for key in ['"enum"', '"const"', '"default"', '"description"']
    )


@pytest.mark.parametrize("value", [1, "true", None])
def test_answer_contract_cannot_be_selected_by_truthy_untyped_values(value):
    """Require an explicit literal host boolean rather than coercing caller input into the experimental contract mode."""
    with pytest.raises(StructuredProfileError, match="scope"):
        ReasoningProfileAdapter(
            profile="core", schema=SCHEMA, boolean_answer_contract=value
        )


@pytest.mark.parametrize("text", ["", "   ", None])
def test_contract_prefix_does_not_admit_an_empty_original_request(text):
    """Keep the original nonempty user-input requirement even when a host clarification would add its own text."""
    schema = dict(
        type="object",
        properties=dict(answer=dict(type="boolean")),
        required=["answer"],
        additionalProperties=False,
    )
    adapter = ReasoningProfileAdapter(
        profile="core", schema=schema, boolean_answer_contract=True
    )
    with pytest.raises(StructuredProfileError, match="input"):
        adapter.payload(text, (), False)


@pytest.mark.parametrize(
    "fault",
    [
        "no_reasoning",
        "null_reasoning",
        "wrong_reasoning_type",
        "too_many_tokens",
        "truncated",
        "tool",
        "wrong_model",
    ],
)
def test_native_condition_and_existing_metadata_remain_mandatory(fault):
    """Reject unsupported reasoning, usage overflow and invalid finish/identity/authority evidence without accepting a plausible final answer."""
    adapter = ReasoningProfileAdapter(profile="core", schema=SCHEMA)
    value = reply()
    message = value["choices"][0]["message"]
    if fault == "no_reasoning":
        del message["reasoning_content"]
    elif fault == "null_reasoning":
        message["reasoning_content"] = None
    elif fault == "wrong_reasoning_type":
        message["reasoning_content"] = ["fixture"]
    elif fault == "too_many_tokens":
        value["usage"]["completion_tokens"] = 1025
    elif fault == "truncated":
        value["choices"][0]["finish_reason"] = "length"
    elif fault == "tool":
        message["tool_calls"] = [dict(id="untrusted")]
    elif fault == "wrong_model":
        value["model"] = "other"
    with pytest.raises(StructuredProfileError):
        adapter.validate_reply(value)


@pytest.mark.parametrize(
    "fault",
    [None, "late_reasoning", "reasoning_type", "missing_reasoning", "missing_done"],
)
def test_streaming_separates_reasoning_from_exact_native_final_chunks(fault):
    """Preserve final JSON byte content through native role-null/think/content frames while refusing late or invalid reasoning and incomplete streams."""
    adapter = ReasoningProfileAdapter(profile="core", schema=SCHEMA)
    events = [
        dict(
            model=adapter.model,
            choices=[
                dict(
                    index=0,
                    delta=dict(role="assistant", content=None),
                    finish_reason=None,
                )
            ],
        ),
        dict(
            model=adapter.model,
            choices=[
                dict(
                    index=0,
                    delta=dict(reasoning_content="Fixture reasoning."),
                    finish_reason=None,
                )
            ],
        ),
        dict(
            model=adapter.model,
            choices=[
                dict(index=0, delta=dict(content='{"answer":'), finish_reason=None)
            ],
        ),
        dict(
            model=adapter.model,
            choices=[dict(index=0, delta=dict(content="17}"), finish_reason=None)],
        ),
        dict(
            model=adapter.model,
            choices=[dict(index=0, delta={}, finish_reason="stop")],
            usage=dict(prompt_tokens=40, completion_tokens=540),
        ),
    ]
    if fault == "late_reasoning":
        events[3]["choices"][0]["delta"]["reasoning_content"] = "late"
    elif fault == "reasoning_type":
        events[1]["choices"][0]["delta"]["reasoning_content"] = 7
    elif fault == "missing_reasoning":
        del events[1]["choices"][0]["delta"]["reasoning_content"]
    if fault is None:
        result = adapter.stream_reply(events, True, b"", 0.1)
        assert adapter.validate_reply(result)[0] == '{"answer":17}'
    else:
        with pytest.raises(StructuredProfileError):
            adapter.validate_reply(
                adapter.stream_reply(events, fault != "missing_done", b"", 0.1)
            )


@pytest.mark.asyncio
@pytest.mark.parametrize("fault", [None, "wrong_fact", "missing_reasoning", "overflow"])
async def test_actual_owned_http_path_keeps_first_content_without_fallback(fault):
    """Exercise complete inherited admission/discovery/cleanup with above512 usage and retain a wrong integer rather than silently repairing it."""
    requests = []

    def handler(request):
        """Provide finite authored loopback wire fixtures and count actual adapter dispatches only."""
        if request.method == "GET":
            return httpx.Response(200, json=dict(data=[dict(id="qwen3.5-9b-core")]))
        requests.append(json.loads(request.content))
        value = reply(answer=-777 if fault == "wrong_fact" else 17)
        if fault == "missing_reasoning":
            value["choices"][0]["message"].pop("reasoning_content")
        elif fault == "overflow":
            value["usage"]["completion_tokens"] = 1025
        return httpx.Response(200, json=value)

    adapter = ReasoningProfileAdapter(
        profile="core",
        schema=copy.deepcopy(SCHEMA),
        transport=httpx.MockTransport(handler),
    )
    if fault in {"missing_reasoning", "overflow"}:
        with pytest.raises(StructuredProfileError):
            await adapter.complete("Return the requested integer.")
    else:
        result = await adapter.complete("Return the requested integer.")
        assert result.value == dict(answer=-777 if fault == "wrong_fact" else 17)
        assert result.output_tokens == 540
    assert len(requests) == 1 and adapter.active is None
    assert adapter.last_response and adapter.last_request
    with pytest.raises(StructuredProfileError, match="spent"):
        await adapter.complete("Do not retry.")
    assert len(requests) == 1
