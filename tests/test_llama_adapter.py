"""Verify persistent inference context preparation, failure mapping and preset selection."""

import json
import logging

import httpx
import pytest

from apps.api.services.llama_gateway import LlamaGateway
from src.application.ports.inference import InferenceFailure
from src.infrastructure.inference import llama_adapter

logger = logging.getLogger(__name__)


@pytest.mark.asyncio
@pytest.mark.parametrize("preset", ["fast", "auto"])
async def test_adapter_trims_whole_turns_using_gateway_tokenizer(monkeypatch, preset):
    """Preserve system/current input and call Auto classification only once before trimming."""
    generated = []
    classified = []
    context = [
        {"role": "system", "content": "Keep system"},
        {"role": "user", "content": "old"},
        {"role": "assistant", "content": "reply"},
        {"role": "user", "content": "Current request"},
    ]

    def handler(request):
        """Provide template/token counts and capture only the final generation request."""
        data = json.loads(request.content) if request.content else {}
        if request.url.path == "/v1/models":
            return httpx.Response(200, json={"data": [{"id": "qwen3.5-9b-core"}]})
        if request.url.path == "/apply-template":
            return httpx.Response(200, json={"prompt": str(len(data["messages"]))})
        if request.url.path == "/tokenize":
            return httpx.Response(
                200, json={"tokens": [1] * (32700 if data["content"] == "4" else 100)}
            )
        if request.url.path == "/v1/chat/completions":
            if data["max_tokens"] == 96:
                classified.append(data)
                return httpx.Response(
                    200,
                    json={
                        "choices": [
                            {"message": {"content": "fast"}, "finish_reason": "stop"}
                        ]
                    },
                )
            generated.append(data)
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "content": "Verified",
                                "reasoning_content": "not persisted",
                            },
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {"prompt_tokens": 100, "completion_tokens": 10},
                },
            )
        raise AssertionError("Unexpected gateway request")

    gateway = LlamaGateway(
        "http://127.0.0.1:8080",
        "qwen3.5-9b-core",
        transport=httpx.MockTransport(handler),
    )
    monkeypatch.setattr(llama_adapter, "LlamaGateway", lambda **parameters: gateway)
    result = await llama_adapter.LlamaInferenceAdapter().complete(
        profile="core", messages=context, preset=preset, temperature=0, max_tokens=512
    )
    assert result.content == "Verified" and result.preset_selected == "fast"
    assert len(classified) == (1 if preset == "auto" else 0)
    assert generated[0]["messages"] == [context[0], context[-1]]
    assert context[1]["content"] == "old"
    assert not hasattr(result, "reasoning_content")
    logger.info("adapter_trim_verified preset=%s", preset)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure,status",
    [("timeout", 504), ("connection", 503), ("model", 409), ("malformed", 502)],
)
async def test_context_preparation_errors_are_controlled(monkeypatch, failure, status):
    """Map tokenizer transport errors and loaded-model mismatch to stable inference failures."""

    def handler(request):
        """Inject backend failures at template preparation or model verification."""
        if failure == "timeout":
            raise httpx.ReadTimeout("private backend details", request=request)
        if failure == "connection":
            raise httpx.ConnectError("private backend details", request=request)
        if request.url.path == "/apply-template":
            return (
                httpx.Response(200, json={"prompt": "ok"})
                if failure == "model"
                else httpx.Response(200, content=b"not-json")
            )
        if request.url.path == "/tokenize":
            return httpx.Response(200, json={"tokens": [1]})
        if request.url.path == "/v1/models":
            return httpx.Response(200, json={"data": [{"id": "another-model"}]})
        raise AssertionError("Unexpected request")

    gateway = LlamaGateway(
        "http://127.0.0.1:8080",
        "qwen3.5-9b-core",
        transport=httpx.MockTransport(handler),
    )
    monkeypatch.setattr(llama_adapter, "LlamaGateway", lambda **parameters: gateway)
    with pytest.raises(InferenceFailure) as error:
        await llama_adapter.LlamaInferenceAdapter().complete(
            profile="core",
            messages=[{"role": "user", "content": "Hello"}],
            preset="fast",
            temperature=0,
            max_tokens=512,
        )
    assert error.value.status_code == status
