"""Validate real streaming protocol, exact template budgeting and failure closure with a fake HTTP backend."""

import json
import logging

import httpx
import pytest

from apps.api.core.model_config import get_model_profile
from apps.api.services.llama_gateway import GatewayError
from apps.harness.inference import ProductInference

LOGGER = logging.getLogger(__name__)


@pytest.mark.asyncio
@pytest.mark.parametrize("terminal", [True, False])
async def test_native_stream_budget_and_incomplete_detection(terminal):
    """Require the approved model, exact template/tokenization and a final native DONE sentinel."""
    calls = []
    model = get_model_profile("core")["model_id"]

    def respond(request):
        """Serve a tiny tokenizer and stream while recording the actual inference payload."""
        path = request.url.path
        if path == "/v1/models":
            return httpx.Response(200, json={"data": [{"id": model}]})
        if path == "/apply-template":
            assert (
                json.loads(request.content)["chat_template_kwargs"]["enable_thinking"]
                is False
            )
            return httpx.Response(200, json={"prompt": "templated"})
        if path == "/tokenize":
            return httpx.Response(200, json={"tokens": [1, 2, 3]})
        if path == "/v1/chat/completions":
            payload = json.loads(request.content)
            calls.append(payload)
            text = 'data: {"choices":[{"delta":{"content":"hello"}}]}\n\n'
            text += 'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\n'
            if terminal:
                text += "data: [DONE]\n\n"
            return httpx.Response(
                200, text=text, headers={"content-type": "text/event-stream"}
            )
        raise AssertionError(path)

    inference = ProductInference(transport=httpx.MockTransport(respond))
    chunks = []
    if terminal:
        async for chunk in inference.stream(
            [{"role": "user", "content": "Hello"}], max_tokens=512
        ):
            chunks.append(chunk)
        assert chunks[-1] == b"data: [DONE]\n\n"
    else:
        with pytest.raises(GatewayError, match="incomplete_stream"):
            async for chunk in inference.stream(
                [{"role": "user", "content": "Hello"}], max_tokens=512
            ):
                chunks.append(chunk)
    assert len(calls) == 1 and calls[0]["model"] == model
    assert calls[0]["stream"] is True and calls[0]["max_tokens"] == 512
    LOGGER.info("test_product_stream_native_contract_verified terminal=%s", terminal)


def sse(*events, done=True):
    """Encode native SSE events and the optional terminal sentinel."""
    text = "".join("data: " + json.dumps(event) + "\n\n" for event in events)
    return text + ("data: [DONE]\n\n" if done else "")


def streaming_backend(body):
    """Serve the tokenizer and model routes and stream the given SSE body."""
    model = get_model_profile("core")["model_id"]

    def respond(request):
        """Answer the preparation calls and the streamed completion."""
        path = request.url.path
        if path == "/v1/models":
            return httpx.Response(200, json={"data": [{"id": model}]})
        if path == "/apply-template":
            return httpx.Response(200, json={"prompt": "templated"})
        if path == "/tokenize":
            return httpx.Response(200, json={"tokens": [1, 2, 3]})
        if path == "/v1/chat/completions":
            return httpx.Response(
                200, text=body, headers={"content-type": "text/event-stream"}
            )
        raise AssertionError(path)

    return httpx.MockTransport(respond)


def delta(content=None, finish=None):
    """Return one streamed chat chunk."""
    choice = {"index": 0, "delta": {} if content is None else {"content": content}}
    choice["finish_reason"] = finish
    return {"choices": [choice]}


async def collect(body):
    """Drain ProductInference.stream over a fake backend and return the forwarded chunks."""
    chunks = []
    inference = ProductInference(transport=streaming_backend(body))
    async for chunk in inference.stream([{"role": "user", "content": "Hi"}]):
        chunks.append(chunk)
    return chunks


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body",
    [
        sse(delta("hel"), delta("lo"), delta(finish="stop")),
        sse(delta("hello", finish="stop")),
        sse(delta("hello"), delta(finish="stop"), {"choices": [], "usage": {}}),
    ],
)
async def test_stream_with_stop_and_text_completes(body):
    """A stream that ends with finish_reason stop and some text passes through to DONE."""
    chunks = await collect(body)
    assert chunks[-1] == b"data: [DONE]\n\n"
    assert b"hel" in b"".join(chunks)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("body", "status"),
    [
        (sse(delta("partial"), delta(finish="length")), "INCOMPLETE"),
        (sse(delta("partial", finish="length")), "INCOMPLETE"),
        (sse(delta("partial")), "UNVERIFIED"),
        (sse(delta("partial"), delta(finish="tool_calls")), "UNVERIFIED"),
        (sse(delta("partial", finish="stop"), delta(finish="length")), "INCOMPLETE"),
        (sse(delta(" \n"), delta(finish="stop")), "INCOMPLETE"),
        (sse(delta(finish="stop")), "INCOMPLETE"),
    ],
)
async def test_unverified_stream_end_raises_incomplete_completion(body, status, caplog):
    """A stream that reaches DONE without a verified complete answer raises before forwarding DONE."""
    from apps.harness.inference import IncompleteCompletion

    chunks = []
    inference = ProductInference(transport=streaming_backend(body))
    with (
        caplog.at_level(logging.WARNING),
        pytest.raises(IncompleteCompletion) as raised,
    ):
        async for chunk in inference.stream([{"role": "user", "content": "Hi"}]):
            chunks.append(chunk)
    assert (
        raised.value.status == status and raised.value.code == "incomplete_completion"
    )
    assert isinstance(raised.value, GatewayError)
    assert b"data: [DONE]\n\n" not in chunks
    assert f"product_stream_incomplete status={status}" in caplog.text
    assert "partial" not in caplog.text


@pytest.mark.asyncio
async def test_stream_without_done_keeps_incomplete_stream():
    """A stream cut before DONE still fails as incomplete_stream, even after finish_reason stop."""
    with pytest.raises(GatewayError, match="incomplete_stream"):
        await collect(sse(delta("hello", finish="stop"), done=False))
