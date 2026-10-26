"""Verify opt-in structural decoding does not embed expected answers, repair output, retry, leak prompts or expand profile/tool authority."""

import asyncio
import copy
import json
import logging

import httpx
import pytest

from src.infrastructure.inference.structured_profile import (
    StructuredProfileAdapter,
    StructuredProfileError,
    compile_schema,
    matches_schema,
    strict_json,
)

SCHEMA = dict(
    type="object",
    properties=dict(answer=dict(type="integer")),
    required=["answer"],
    additionalProperties=False,
)
MODEL = "qwen3.5-9b-core"


def reply(content='{"answer":17}'):
    """Create a complete authored native fixture whose answer remains free of the decoder schema."""
    return dict(
        model=MODEL,
        choices=[
            dict(
                index=0,
                message=dict(role="assistant", content=content),
                finish_reason="stop",
            )
        ],
        usage=dict(prompt_tokens=20, completion_tokens=8),
    )


def discovery():
    """Advertise only the fixed selected alias and bounded native text/image capabilities."""
    return dict(
        data=[
            dict(
                id=MODEL,
                architecture=dict(
                    input_modalities=["text", "image"], output_modalities=["text"]
                ),
            )
        ]
    )


@pytest.mark.parametrize(
    "fault",
    ["enum", "const", "default", "$ref", "description", "oneOf", "pattern", "minimum"],
)
def test_host_schema_rejects_gold_values_and_unsupported_keywords(fault):
    """Refuse answer-bearing or alternate grammar features rather than hiding correct values in constrained decoding."""
    value = copy.deepcopy(SCHEMA)
    value["properties"]["answer"][fault] = [17] if fault == "enum" else 17
    with pytest.raises(StructuredProfileError):
        compile_schema(value)


@pytest.mark.parametrize(
    "fault",
    [
        "root",
        "extras",
        "optional",
        "duplicate_required",
        "large_array",
        "deep",
        "field_name",
    ],
)
def test_schema_shape_and_complexity_are_bounded(fault):
    """Reject an unbounded, ambiguous or unsupported host contract before any native request."""
    value = copy.deepcopy(SCHEMA)
    if fault == "root":
        value = dict(type="integer")
    if fault == "extras":
        value["additionalProperties"] = True
    if fault == "optional":
        value["required"] = []
    if fault == "duplicate_required":
        value["required"] = ["answer", "answer"]
    if fault == "large_array":
        value["properties"]["answer"] = dict(
            type="array", items=dict(type="integer"), maxItems=10000
        )
    if fault == "deep":
        for _ in range(8):
            value = dict(
                type="object",
                properties=dict(child=value),
                required=["child"],
                additionalProperties=False,
            )
    if fault == "field_name":
        value["properties"] = {"tool;run": dict(type="integer")}
    with pytest.raises(StructuredProfileError):
        compile_schema(value)


@pytest.mark.parametrize(
    "content",
    [
        '{"answer":17,"answer":18}',
        '{"answer":NaN}',
        '```json\n{"answer":17}\n```',
        'prefix {"answer":17}',
    ],
)
def test_strict_json_never_extracts_repairs_or_selects_duplicate_answer(content):
    """Preserve invalid raw answers as failures instead of changing their bytes before validation."""
    with pytest.raises(ValueError):
        strict_json(content)


@pytest.mark.parametrize(
    "value",
    [
        dict(answer=True),
        dict(answer="17"),
        dict(answer=17, extra=1),
        [17],
        dict(wrong=17),
    ],
)
def test_valid_json_with_wrong_type_or_structure_remains_failed(value):
    """Keep structural validation independent from native grammar claims without coercion or object filling."""
    assert not matches_schema(value, SCHEMA)


@pytest.mark.asyncio
async def test_real_http_interface_sends_only_host_structure_and_preserves_exact_first_content(
    caplog,
):
    """Use bounded native discovery/POST without proxy, secrets, answers-in-schema, tools, retries or response rewriting."""
    caplog.set_level(logging.INFO)
    calls = []

    def handler(request):
        """Capture the declared actual HTTP payload and return a complete finite native-shaped fixture."""
        calls.append(request)
        return httpx.Response(
            200,
            json=discovery()
            if request.method == "GET"
            else reply(' { "answer" : 17 } '),
        )

    schema = copy.deepcopy(SCHEMA)
    adapter = StructuredProfileAdapter(
        profile="core", schema=schema, transport=httpx.MockTransport(handler)
    )
    schema["properties"]["answer"]["enum"] = [17]
    result = await adapter.complete(
        "PRIVATE-PROMPT-642 calculate the requested answer."
    )
    assert result.content == ' { "answer" : 17 } ' and result.value == dict(answer=17)
    assert [r.method for r in calls] == ["GET", "POST"]
    payload = json.loads(calls[1].content)
    assert payload["response_format"] == dict(type="json_object", schema=SCHEMA)
    assert "17" not in json.dumps(payload["response_format"])
    assert "tools" not in payload and calls[1].headers.get("authorization") is None
    assert "PRIVATE-PROMPT-642" not in caplog.text and '"answer"' not in caplog.text
    with pytest.raises(StructuredProfileError, match="spent"):
        await adapter.complete("Do not retry.")
    assert len(calls) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "fault",
    [
        "model",
        "length",
        "role",
        "tool",
        "usage_bool",
        "usage_missing",
        "overflow",
        "array",
        "fence",
        "wrong_field",
        "native_schema_400",
        "duplicate_wire",
    ],
)
async def test_native_failure_is_retained_without_fallback_or_second_generation(fault):
    """Refuse identity, completion, usage, action or shape failures while keeping the first wire bytes and spent slot."""
    calls = []

    def handler(request):
        """Return one authored failure while recording every attempted operation."""
        calls.append(request.method)
        if request.method == "GET":
            return httpx.Response(200, json=discovery())
        value = reply()
        if fault == "model":
            value["model"] = "foreign"
        if fault == "length":
            value["choices"][0]["finish_reason"] = "length"
        if fault == "role":
            value["choices"][0]["message"]["role"] = "tool"
        if fault == "tool":
            value["choices"][0]["message"]["tool_calls"] = [dict(name="run")]
        if fault == "usage_bool":
            value["usage"]["prompt_tokens"] = True
        if fault == "usage_missing":
            value.pop("usage")
        if fault == "overflow":
            value["usage"]["completion_tokens"] = 99999
        if fault == "array":
            value["choices"][0]["message"]["content"] = "[17]"
        if fault == "fence":
            value["choices"][0]["message"]["content"] = '```json\n{"answer":17}\n```'
        if fault == "wrong_field":
            value["choices"][0]["message"]["content"] = '{"wrong":17}'
        if fault == "duplicate_wire":
            return httpx.Response(
                200,
                headers={"content-type": "application/json"},
                content=b'{"model":"wrong","model":"qwen3.5-9b-core"}',
            )
        return httpx.Response(400 if fault == "native_schema_400" else 200, json=value)

    adapter = StructuredProfileAdapter(
        profile="core", schema=SCHEMA, transport=httpx.MockTransport(handler)
    )
    with pytest.raises(StructuredProfileError):
        await adapter.complete("request")
    assert calls == ["GET", "POST"] and adapter.last_request and adapter.last_response
    assert adapter.spent


@pytest.mark.asyncio
@pytest.mark.parametrize("fault", ["wrong_alias", "huge", "redirect", "no_image"])
async def test_discovery_failure_stops_before_disclosing_prompt_or_image(fault):
    """Refuse an unexpected local model or unsupported image capability before generation disclosure."""
    calls = []

    def handler(request):
        """Return only one finite discovery failure without dispatching a model response."""
        calls.append(request.method)
        value = discovery()
        if fault == "wrong_alias":
            value["data"][0]["id"] = "foreign"
        if fault == "huge":
            return httpx.Response(
                200, headers={"content-type": "application/json"}, content=b"x" * 16385
            )
        if fault == "no_image":
            value["data"][0]["architecture"]["input_modalities"] = ["text"]
        return httpx.Response(302 if fault == "redirect" else 200, json=value)

    adapter = StructuredProfileAdapter(
        profile="core", schema=SCHEMA, transport=httpx.MockTransport(handler)
    )
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 8 + (4).to_bytes(4, "big") * 2
    with pytest.raises(StructuredProfileError):
        await adapter.complete("private", images=(png,))
    assert calls == ["GET"] and adapter.last_response == b""


def frame(*, text="", finish=None, model=MODEL, usage=None):
    """Create a bounded native SSE fixture with explicit model identity and choice metadata."""
    return (
        b"data: "
        + json.dumps(
            dict(
                model=model,
                choices=[dict(index=0, delta=dict(content=text), finish_reason=finish)],
                usage=usage,
            )
        ).encode()
        + b"\n\n"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "fault", [None, "model", "no_done", "late_content", "tool", "usage"]
)
async def test_streaming_constraints_validate_complete_fragmented_native_output(fault):
    """Preserve native content across byte boundaries while rejecting incomplete, foreign or post-completion events."""
    raw = (
        frame()
        + frame(text='{"answer":17}')
        + frame(finish="stop", usage=dict(prompt_tokens=20, completion_tokens=8))
    )
    if fault == "model":
        raw = raw.replace(MODEL.encode(), b"foreign")
    if fault == "late_content":
        raw += frame(text="unexpected")
    if fault == "tool":
        raw = raw.replace(b'"content": ""', b'"tool_calls": []')
    if fault == "usage":
        raw = raw.replace(b'"completion_tokens": 8', b'"completion_tokens": true')
    if fault != "no_done":
        raw += b"data: [DONE]\n\n"

    class Wire(httpx.AsyncByteStream):
        """Split SSE frames independently of UTF-8 and event boundaries without network use."""

        async def __aiter__(self):
            """Yield exact original bytes in seven-byte fragments and terminate normally."""
            for offset in range(0, len(raw), 7):
                yield raw[offset : offset + 7]

    def handler(request):
        """Serve native-shaped discovery then the declared finite streaming response."""
        return (
            httpx.Response(200, json=discovery())
            if request.method == "GET"
            else httpx.Response(
                200, headers={"content-type": "text/event-stream"}, stream=Wire()
            )
        )

    adapter = StructuredProfileAdapter(
        profile="core", schema=SCHEMA, transport=httpx.MockTransport(handler)
    )
    if fault is None:
        result = await adapter.complete("request", stream=True)
        assert (
            result.content == '{"answer":17}' and result.first_content_frame_seconds > 0
        )
    else:
        with pytest.raises(StructuredProfileError):
            await adapter.complete("request", stream=True)
    assert adapter.last_response == raw


@pytest.mark.asyncio
async def test_cancel_joins_http_cleanup_and_never_reopens_spent_request():
    """Retain caller cancellation while awaiting stream closure, with no retry or leaked network child."""
    entered, closed = asyncio.Event(), asyncio.Event()

    class Wire(httpx.AsyncByteStream):
        """Hold one explicit native response until cancellation while tracking final cleanup."""

        async def __aiter__(self):
            """Block after admission so cancellation exercises the original response ownership path."""
            entered.set()
            await asyncio.Event().wait()
            yield b"unreachable"

        async def aclose(self):
            """Record that response cleanup completed before caller cancellation returns."""
            closed.set()

    def handler(request):
        """Return valid discovery and a single intentionally pending response."""
        return (
            httpx.Response(200, json=discovery())
            if request.method == "GET"
            else httpx.Response(
                200, headers={"content-type": "application/json"}, stream=Wire()
            )
        )

    adapter = StructuredProfileAdapter(
        profile="core", schema=SCHEMA, transport=httpx.MockTransport(handler)
    )
    task = asyncio.create_task(adapter.complete("request"))
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert closed.is_set() and adapter.spent


@pytest.mark.asyncio
async def test_schema_does_not_supply_or_certify_correct_factual_answer():
    """A structurally valid wrong value remains model-produced and must fail the separate evaluator rather than being filled with a reference."""

    def handler(request):
        """Produce an intentionally incorrect integer using the same entirely value-free schema."""
        return httpx.Response(
            200,
            json=discovery() if request.method == "GET" else reply('{"answer":999}'),
        )

    adapter = StructuredProfileAdapter(
        profile="core", schema=SCHEMA, transport=httpx.MockTransport(handler)
    )
    result = await adapter.complete("Compute without supplied answers.")
    assert result.value == dict(answer=999) and adapter.generation_dispatched
    assert "999" not in adapter.schema_bytes.decode()


@pytest.mark.parametrize(
    "endpoint",
    [
        "https://example.org",
        "http://localhost:18080",
        "http://127.0.0.1:18080/path",
        "http://127.0.0.1:8080?key=secret",
    ],
)
def test_untrusted_endpoint_cannot_redirect_or_disclose_request(endpoint):
    """Keep endpoint selection in the finite trusted local set without arbitrary network authority."""
    with pytest.raises(StructuredProfileError, match="scope"):
        StructuredProfileAdapter(profile="core", schema=SCHEMA, endpoint=endpoint)


@pytest.mark.asyncio
async def test_repeat_cancellation_waits_for_owned_http_close_before_returning():
    """A second caller cancellation cannot release the spent request before the owned stream completes its teardown."""
    entered, closing, release, finished = (asyncio.Event() for _ in range(4))

    class Wire(httpx.AsyncByteStream):
        """Expose an explicitly delayed teardown to exercise repeated-cancellation ownership."""

        async def __aiter__(self):
            """Wait indefinitely after response admission until the owning child is cancelled."""
            entered.set()
            await asyncio.Event().wait()
            yield b"unreachable"

        async def aclose(self):
            """Keep cleanup observable and blocked until the test releases its independent barrier."""
            closing.set()
            await release.wait()
            finished.set()

    def handler(request):
        """Serve trusted discovery followed by a native response with delayed explicit cleanup."""
        return (
            httpx.Response(200, json=discovery())
            if request.method == "GET"
            else httpx.Response(
                200, headers={"content-type": "application/json"}, stream=Wire()
            )
        )

    adapter = StructuredProfileAdapter(
        profile="core", schema=SCHEMA, transport=httpx.MockTransport(handler)
    )
    task = asyncio.create_task(adapter.complete("request"))
    await entered.wait()
    task.cancel()
    await closing.wait()
    task.cancel()
    await asyncio.sleep(0)
    assert not task.done() and adapter.active is not None
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert finished.is_set() and adapter.active is None
