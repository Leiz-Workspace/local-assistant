
"""
Unit tests for the Auto V1 runtime router.

The tests run without a GPU or llama-server.
They verify deterministic routing policy, strict classifier
parsing, fallback and gateway integration.

Existing preset tests remain unchanged.
"""

import pytest
import httpx

from apps.api.runtime.presets import (
    AutoDecision,
    PresetError,
    RuntimePreset,
    calculate_budget,
    classify_simple_request,
    get_preset,
    parse_classifier_output,
)
from apps.api.services.llama_gateway import LlamaGateway

@pytest.fixture
def anyio_backend():
    return "asyncio"

def test_auto_is_not_a_concrete_preset():
    with pytest.raises(PresetError):
        get_preset("auto")


def test_auto_cannot_be_budgeted_directly():
    with pytest.raises(PresetError):
        calculate_budget(
            preset="auto",
            input_tokens=100,
        )


@pytest.mark.parametrize(
    "greeting",
    [
        "hi",
        "Hello!",
        "Xin chào",
        "Chào bạn.",
    ],
)
def test_simple_greeting_uses_fast(greeting):
    decision = classify_simple_request([
        {
            "role": "user",
            "content": greeting,
        }
    ])

    assert decision == AutoDecision(
        preset=RuntimePreset.FAST,
        source="simple_greeting_rule",
    )


def test_complex_request_does_not_use_rule():
    decision = classify_simple_request([
        {
            "role": "user",
            "content": (
                "Help me debug a Kubernetes cluster "
                "with several failing services."
            ),
        }
    ])

    assert decision is None


def test_multiturn_does_not_use_greeting_rule():
    decision = classify_simple_request([
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi"},
        {"role": "user", "content": "Hello"},
    ])

    assert decision is None


@pytest.mark.parametrize(
    "text,expected",
    [
        ("fast", RuntimePreset.FAST),
        ("balanced", RuntimePreset.BALANCED),
        ("deep", RuntimePreset.DEEP),
        (" DEEP \n", RuntimePreset.DEEP),
        ("unlimited", None),
        ("deep explanation", None),
        ("fast or balanced", None),
        ("", None),
    ],
)
def test_strict_classifier_parsing(text, expected):
    assert parse_classifier_output(text) == expected


@pytest.mark.anyio
async def test_auto_gateway_greeting_fast():
    """
    Greeting rule should avoid the classifier request.

    Mock /v1/models, /apply-template, /tokenize and
    the final chat completion.
    """

    calls = []

    def handler(request: httpx.Request):
        calls.append(request.url.path)

        if request.url.path == "/v1/models":
            return httpx.Response(
                200,
                json={
                    "data": [
                        {"id": "qwen3.5-9b-core"}
                    ]
                },
            )

        if request.url.path == "/apply-template":
            return httpx.Response(
                200,
                json={"prompt": "Hello"},
            )

        if request.url.path == "/tokenize":
            return httpx.Response(
                200,
                json={"tokens": [1, 2, 3]},
            )

        if request.url.path == "/v1/chat/completions":
            body = __import__("json").loads(
                request.content
            )

            assert body["max_tokens"] == 4096
            assert (
                body["chat_template_kwargs"]
                ["enable_thinking"] is False
            )

            return httpx.Response(
                200,
                json={
                    "model": "qwen3.5-9b-core",
                    "choices": [
                        {
                            "finish_reason": "stop",
                            "message": {
                                "role": "assistant",
                                "content": "Hello",
                            },
                        }
                    ],
                    "usage": {
                        "prompt_tokens": 3,
                        "completion_tokens": 1,
                    },
                },
            )

        return httpx.Response(404)

    gateway = LlamaGateway(
        base_url="http://127.0.0.1:8080",
        model_id="qwen3.5-9b-core",
        transport=httpx.MockTransport(handler),
    )

    result = await gateway.complete(
        messages=[
            {"role": "user", "content": "Hello"}
        ],
        preset="auto",
        max_tokens=None,
    )

    meta = result["local_assistant"]

    assert meta["preset_requested"] == "auto"
    assert meta["preset_selected"] == "fast"
    assert (
        meta["auto_source"]
        == "simple_greeting_rule"
    )

    # One final completion; no classifier call.
    assert calls.count("/v1/chat/completions") == 1


@pytest.mark.anyio
async def test_auto_gateway_classifier_deep():
    """A valid Deep classification must be applied."""

    calls = []

    def handler(request: httpx.Request):
        path = request.url.path

        if path == "/v1/models":
            return httpx.Response(
                200,
                json={
                    "data": [
                        {"id": "qwen3.5-9b-core"}
                    ]
                },
            )

        if path == "/apply-template":
            return httpx.Response(
                200,
                json={"prompt": "formatted prompt"},
            )

        if path == "/tokenize":
            return httpx.Response(
                200,
                json={"tokens": [1, 2, 3]},
            )

        if path == "/v1/chat/completions":
            import json
            body = json.loads(request.content)
            calls.append(body)

            # First completion is classifier, second is answer.
            if len(calls) == 1:
                assert body["max_tokens"] == 96
                assert (
                    body["chat_template_kwargs"]
                    ["enable_thinking"] is False
                )

                return httpx.Response(
                    200,
                    json={
                        "choices": [
                            {
                                "finish_reason": "stop",
                                "message": {
                                    "content": "deep"
                                },
                            }
                        ]
                    },
                )

            assert body["max_tokens"] == 16384
            assert body["thinking_budget_tokens"] == 8192

            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "finish_reason": "stop",
                            "message": {
                                "content": "Completed."
                            },
                        }
                    ]
                },
            )

        return httpx.Response(404)

    gateway = LlamaGateway(
        base_url="http://127.0.0.1:8080",
        model_id="qwen3.5-9b-core",
        transport=httpx.MockTransport(handler),
    )

    result = await gateway.complete(
        messages=[
            {
                "role": "user",
                "content": (
                    "Design a complex distributed architecture."
                ),
            }
        ],
        preset="auto",
        max_tokens=None,
    )

    assert len(calls) == 2
    assert (
        result["local_assistant"]["preset_selected"]
        == "deep"
    )
    assert (
        result["local_assistant"]["auto_source"]
        == "llm_classifier"
    )


@pytest.mark.anyio
async def test_auto_invalid_classifier_fallback():
    """Unknown classifier labels must fall back to Balanced."""

    calls = []

    def handler(request: httpx.Request):
        path = request.url.path

        if path == "/v1/models":
            return httpx.Response(
                200,
                json={
                    "data": [
                        {"id": "qwen3.5-9b-core"}
                    ]
                },
            )

        if path == "/apply-template":
            return httpx.Response(
                200,
                json={"prompt": "prompt"},
            )

        if path == "/tokenize":
            return httpx.Response(
                200,
                json={"tokens": [1, 2, 3]},
            )

        if path == "/v1/chat/completions":
            import json
            body = json.loads(request.content)
            calls.append(body)

            if len(calls) == 1:
                return httpx.Response(
                    200,
                    json={
                        "choices": [
                            {
                                "finish_reason": "stop",
                                "message": {
                                    "content": "unlimited"
                                },
                            }
                        ]
                    },
                )

            assert body["thinking_budget_tokens"] == 4096

            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "finish_reason": "stop",
                            "message": {
                                "content": "Done"
                            },
                        }
                    ]
                },
            )

        return httpx.Response(404)

    gateway = LlamaGateway(
        base_url="http://127.0.0.1:8080",
        model_id="qwen3.5-9b-core",
        transport=httpx.MockTransport(handler),
    )

    result = await gateway.complete(
        messages=[
            {
                "role": "user",
                "content": "Explain concurrency in Python.",
            }
        ],
        preset="auto",
        max_tokens=None,
    )

    assert (
        result["local_assistant"]["preset_selected"]
        == "balanced"
    )
    assert (
        result["local_assistant"]["auto_source"]
        == "classifier_fallback"
    )
