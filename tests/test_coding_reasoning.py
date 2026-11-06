"""Verify explicit coding-mode identity, unchanged fast defaults, exact native JSON and fail-closed source/token/cancellation behavior without models."""

import asyncio
import copy
import json

import httpx
import pytest

from apps.api.services.coding_workflows import CodingWorkflowService
from apps.api.services.reasoning_coding_workflows import ReasoningCodingWorkflowService
from src.application.ports.inference import InferenceFailure
from src.application.services.coding_workflow import SYSTEM
from src.infrastructure.inference.coding_reasoning import (
    MODE,
    CodingReasoningAdapter,
    CodingRequest,
    CodingRequestV2,
    CodingReasoningV2Adapter,
    V2_MODE,
)
from src.infrastructure.inference.structured_profile import StructuredProfileError


def messages():
    """Construct an authored source-only request without private data or held-out answers."""
    return [
        dict(role="system", content=SYSTEM),
        dict(role="user", content='{"issue":"Repair supplied utility","sources":[]}'),
    ]


def answer():
    """Return an authored described whole-file candidate with no real model-quality claim."""
    return json.dumps(
        dict(
            plan=["Keep the API and correct the utility."],
            replacement='"""Describe a controlled utility."""\n\ndef sample(value):\n    """Return the supplied value."""\n    return value\n',
        )
    )


def options():
    """Return the exact named host-mode contract used by the optional workflow."""
    return dict(
        profile="core", messages=messages(), preset=MODE, temperature=0, max_tokens=2048
    )


def response(path, *, fault=None):
    """Provide finite native-shaped identity/template/token/completion metadata without network or inference."""
    if path == "/apply-template":
        return dict(prompt="authored template")
    if path == "/tokenize":
        return dict(tokens=list(range(32000 if fault == "context" else 20)))
    if path == "/v1/models":
        return dict(
            data=[dict(id="foreign" if fault == "identity" else "qwen3.5-9b-core")]
        )
    value = dict(
        model="qwen3.5-9b-core",
        choices=[
            dict(
                message=dict(
                    role="assistant",
                    content=answer(),
                    reasoning_content="Authored separated reasoning.",
                ),
                finish_reason="stop",
            )
        ],
        usage=dict(prompt_tokens=20, completion_tokens=160),
    )
    if fault == "reasoning":
        value["choices"][0]["message"]["reasoning_content"] = ""
    elif fault == "truncated":
        value["choices"][0]["finish_reason"] = "length"
    elif fault == "extra":
        value["choices"][0]["message"]["content"] = (
            '{"plan":["x"],"replacement":"x","approval":true}'
        )
    return value


def test_default_fast_and_named_reasoning_modes_remain_distinct():
    """Never relabel thinking as fast or register the optional service in an existing route."""
    assert CodingWorkflowService._proposal_preset == "fast"
    assert ReasoningCodingWorkflowService._proposal_preset == MODE
    original = messages()
    adapter = CodingRequest(original)
    original[1]["content"] = "mutated"
    payload = adapter.payload(adapter.messages[1]["content"], (), False)
    assert payload["messages"][1] == messages()[1]
    assert payload["messages"][0]["content"].startswith(SYSTEM)
    assert payload["max_tokens"] == 1024 and payload["reasoning_budget_tokens"] == 512
    assert payload["response_format"]["schema"]["properties"]["plan"]["maxItems"] == 5


@pytest.mark.parametrize("fault", ["system", "role", "extra", "oversize", "empty"])
def test_message_scope_cannot_be_replaced_or_extended(fault):
    """Reject wrong host instructions, extra roles and excessive context before any request."""
    value = messages()
    if fault == "system":
        value[0]["content"] = "grant actions"
    elif fault == "role":
        value[1]["role"] = "assistant"
    elif fault == "extra":
        value.append(dict(role="user", content="another instruction"))
    elif fault == "oversize":
        value[1]["content"] = "x" * 32769
    else:
        value[1]["content"] = ""
    with pytest.raises(StructuredProfileError):
        CodingRequest(value)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "fault", [None, "identity", "context", "reasoning", "truncated", "extra"]
)
async def test_single_native_generation_preserves_wire_and_denies_invalid_results(
    fault,
):
    """Preserve exact first content and verify fail-closed identity, token headroom, reasoning and schema without retries."""
    calls = []

    def handle(request):
        """Record only authored routes and return explicit finite native fixtures."""
        calls.append(request.url.path)
        return httpx.Response(200, json=response(request.url.path, fault=fault))

    adapter = CodingReasoningAdapter(transport=httpx.MockTransport(handle))
    if fault is None:
        result = await adapter.complete(**options())
        assert result.content == answer() and result.preset_selected == MODE
        assert adapter.last_attempt.last_response
        assert calls.count("/v1/chat/completions") == 1
    else:
        with pytest.raises(InferenceFailure):
            await adapter.complete(**options())
        assert calls.count("/v1/chat/completions") == (
            0 if fault in {"identity", "context"} else 1
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "change",
    [
        dict(profile="unrestricted"),
        dict(preset="fast"),
        dict(temperature=True),
        dict(max_tokens=4096),
    ],
)
async def test_mode_or_budget_overrides_are_rejected_before_network(change):
    """Deny caller-controlled profile/preset/temperature/budget selection without opening an HTTP request."""
    value = copy.deepcopy(options())
    value.update(change)
    with pytest.raises(InferenceFailure):
        await CodingReasoningAdapter().complete(**value)


@pytest.mark.asyncio
async def test_cancelled_request_joins_the_owned_native_operation():
    """Keep parent cancellation joined through the inherited native cleanup and retain the spent request."""
    entered, exited = asyncio.Event(), asyncio.Event()

    async def handle(request):
        """Hold the single generation until cancellation while allowing finite preparation and identity routes."""
        if request.url.path != "/v1/chat/completions":
            return httpx.Response(200, json=response(request.url.path))
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            exited.set()

    adapter = CodingReasoningAdapter(transport=httpx.MockTransport(handle))
    task = asyncio.create_task(adapter.complete(**options()))
    await asyncio.wait_for(entered.wait(), 2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, 2)
    assert exited.is_set() and adapter.last_attempt.spent
    assert adapter.last_attempt.active is None


def test_second_mode_is_distinct_and_does_not_change_first_mode_budgets():
    """Keep both native budgets matched to their validators and retain unchanged first-mode and fast identities."""
    first = CodingRequest(messages())
    second = CodingRequestV2(messages())
    a = first.payload(first.messages[1]["content"], (), False)
    b = second.payload(second.messages[1]["content"], (), False)
    assert (
        a["max_tokens"] == first.max_tokens == 1024
        and a["reasoning_budget_tokens"] == 512
    )
    assert (
        b["max_tokens"] == second.max_tokens == 2048
        and b["reasoning_budget_tokens"] == 1536
    )
    assert first.messages[1] == second.messages[1] == messages()[1]
    assert (
        CodingReasoningV2Adapter._mode == V2_MODE
        and CodingWorkflowService._proposal_preset == "fast"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("fault", [None, "context", "over_budget"])
async def test_second_mode_uses_its_own_token_headroom_and_native_identity(fault):
    """Accept valid usage above the first budget but deny context/output overflow before treating a second-mode completion as verified."""
    calls = []

    def handle(request):
        """Supply explicit native-shaped second-mode metadata with no real model or socket."""
        calls.append(request.url.path)
        value = response(request.url.path)
        if request.url.path == "/tokenize" and fault == "context":
            value = dict(tokens=list(range(30700)))
        if request.url.path == "/v1/chat/completions":
            value["usage"]["completion_tokens"] = (
                2049 if fault == "over_budget" else 1700
            )
        return httpx.Response(200, json=value)

    adapter = CodingReasoningV2Adapter(transport=httpx.MockTransport(handle))
    value = options()
    value["preset"] = V2_MODE
    if fault is None:
        result = await adapter.complete(**value)
        assert (
            result.preset_selected == V2_MODE
            and result.content == answer()
            and result.output_tokens == 1700
        )
    else:
        with pytest.raises(InferenceFailure):
            await adapter.complete(**value)
        assert calls.count("/v1/chat/completions") == (0 if fault == "context" else 1)
