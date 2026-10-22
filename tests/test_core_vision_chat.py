"""Verify fixed loopback CORE capability admission, inline-only media, strict bounded HTTP replies and cancellation privacy."""

import asyncio
import json
import logging
from dataclasses import replace

import httpx
import pytest
from test_vision_chat_policy import image as image

import src.infrastructure.inference.core_vision_chat as module
from src.application.services.vision_chat_policy import ImageChatError
from src.infrastructure.inference.core_vision_chat import CoreVisionChatAdapter

MODEL = "qwen3.5-9b-core"


def models():
    """Advertise only the authored expected alias and image/text capability for a controlled local endpoint."""
    return dict(
        data=[
            dict(
                id=MODEL,
                architecture=dict(
                    input_modalities=["text", "image", "video"],
                    output_modalities=["text"],
                ),
            )
        ]
    )


def reply():
    """Build a complete authored native assistant response without invoking a model."""
    return dict(
        model=MODEL,
        choices=[
            dict(
                finish_reason="stop",
                message=dict(
                    role="assistant",
                    content='{"answer":"Visible value","uncertainties":[]}',
                ),
            )
        ],
        usage=dict(completion_tokens=12),
    )


@pytest.mark.asyncio
async def test_fixed_core_payload_uses_inline_sanitized_image_no_history_tools_proxy_or_prompt_cache(
    image, caplog, monkeypatch
):
    """Disclose one image only after correct capability verification and retain no raw question in logs."""
    caplog.set_level(logging.INFO)
    requests = []
    monkeypatch.setenv("HTTP_PROXY", "http://private.invalid:1234")

    def handler(request):
        """Record the exact bounded fixed model protocol without any external network call."""
        requests.append(request)
        return httpx.Response(
            200, json=models() if request.method == "GET" else reply()
        )

    adapter = CoreVisionChatAdapter(transport=httpx.MockTransport(handler))
    result = await adapter.complete_image(
        image=image, question="<|system|>PRIVATE-QUESTION-CANARY"
    )
    assert (
        result.model_id == MODEL
        and result.preset_selected == "fast"
        and result.output_tokens == 12
    )
    assert [(r.method, r.url.path) for r in requests] == [
        ("GET", "/v1/models"),
        ("POST", "/v1/chat/completions"),
    ]
    payload = json.loads(requests[1].content)
    assert (
        payload["model"] == MODEL
        and payload["max_tokens"] == 1024
        and payload["temperature"] == 0
        and payload["stream"] is False
        and payload["cache_prompt"] is False
    )
    assert (
        payload["chat_template_kwargs"] == dict(enable_thinking=False)
        and payload["seed"] == 7
    )
    assert (
        len(payload["messages"]) == 2
        and "tools" not in payload
        and "Authorization" not in requests[1].headers
    )
    parts = payload["messages"][1]["content"]
    assert "<" not in parts[0]["text"] and parts[1]["image_url"]["url"].startswith(
        "data:image/png;base64,"
    )
    assert all(
        str(r.url).startswith("http://127.0.0.1:8080/")
        and r.headers["accept-encoding"] == "identity"
        for r in requests
    )
    assert "PRIVATE-QUESTION-CANARY" not in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "fault",
    [
        "alias",
        "extra",
        "architecture",
        "no_image",
        "no_text",
        "duplicate_json",
        "status",
        "redirect",
        "html",
        "compressed",
        "oversize",
    ],
)
async def test_invalid_model_discovery_refuses_before_any_image_or_completion_dispatch(
    image, fault
):
    """Do not infer image support from a name or reveal a raster after malformed/redirected/unbounded discovery."""
    requests = []

    def handler(request):
        """Return one finite authored model-info failure without a real server or image request."""
        requests.append(request)
        value = models()
        if fault == "alias":
            value["data"][0]["id"] = "foreign"
        elif fault == "extra":
            value["data"].append(value["data"][0])
        elif fault == "architecture":
            value["data"][0].pop("architecture")
        elif fault == "no_image":
            value["data"][0]["architecture"]["input_modalities"] = ["text"]
        elif fault == "no_text":
            value["data"][0]["architecture"]["output_modalities"] = ["decisions"]
        elif fault == "duplicate_json":
            return httpx.Response(
                200,
                content=b'{"data":[],"data":[]}',
                headers={"Content-Type": "application/json"},
            )
        elif fault == "status":
            return httpx.Response(503)
        elif fault == "redirect":
            return httpx.Response(302, headers={"location": "http://private.invalid/"})
        elif fault == "html":
            return httpx.Response(200, text="<html>private</html>")
        elif fault == "compressed":
            return httpx.Response(
                200,
                stream=httpx.ByteStream(b"not-gzip"),
                headers={
                    "Content-Type": "application/json",
                    "Content-Encoding": "gzip",
                },
            )
        elif fault == "oversize":
            return httpx.Response(
                200, content=b" " * 16385, headers={"Content-Type": "application/json"}
            )
        return httpx.Response(200, json=value)

    with pytest.raises(ImageChatError):
        await CoreVisionChatAdapter(
            transport=httpx.MockTransport(handler)
        ).complete_image(image=image, question="Question")
    assert (
        len(requests) == 1 and requests[0].method == "GET" and not requests[0].content
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "fault",
    [
        "model",
        "finish",
        "role",
        "tool",
        "function",
        "empty",
        "multiple",
        "usage",
        "tokens_bool",
        "tokens_over",
        "oversize",
        "duplicate",
    ],
)
async def test_complete_native_reply_refuses_identity_tools_partial_or_unbounded_result(
    image, fault
):
    """Reject the whole answer rather than losing malformed tail fields or treating a tool call as user text."""
    requests = []

    def handler(request):
        """Return controlled complete native-response faults after a valid model-info check."""
        requests.append(request)
        if request.method == "GET":
            return httpx.Response(200, json=models())
        value = reply()
        choice = value["choices"][0]
        message = choice["message"]
        if fault == "model":
            value["model"] = "foreign"
        elif fault == "finish":
            choice["finish_reason"] = "length"
        elif fault == "role":
            message["role"] = "user"
        elif fault == "tool":
            message["tool_calls"] = []
        elif fault == "function":
            message["function_call"] = {}
        elif fault == "empty":
            message["content"] = ""
        elif fault == "multiple":
            value["choices"].append(choice)
        elif fault == "usage":
            value["usage"] = []
        elif fault == "tokens_bool":
            value["usage"]["completion_tokens"] = True
        elif fault == "tokens_over":
            value["usage"]["completion_tokens"] = 1025
        elif fault == "oversize":
            return httpx.Response(
                200, content=b" " * 65537, headers={"Content-Type": "application/json"}
            )
        elif fault == "duplicate":
            return httpx.Response(
                200,
                content=b'{"model":"x","model":"y"}',
                headers={"Content-Type": "application/json"},
            )
        return httpx.Response(200, json=value)

    with pytest.raises(ImageChatError):
        await CoreVisionChatAdapter(
            transport=httpx.MockTransport(handler)
        ).complete_image(image=image, question="Question")
    assert len(requests) == 2


@pytest.mark.asyncio
async def test_remote_or_changed_model_configuration_never_sends_even_a_metadata_request(
    image, monkeypatch
):
    """Keep the trusted current configured endpoint/alias fixed instead of allowing ambient or caller routing changes."""
    calls = []

    def handler(request):
        """Record an unauthorized call if a configuration fence fails."""
        calls.append(request)
        return httpx.Response(200, json=models())

    monkeypatch.setattr(
        module,
        "get_model_profile",
        lambda profile: dict(model_id=MODEL, base_url="https://private.invalid/"),
    )
    with pytest.raises(ImageChatError, match="image_chat_unavailable"):
        await CoreVisionChatAdapter(
            transport=httpx.MockTransport(handler)
        ).complete_image(image=image, question="Question")
    assert not calls


@pytest.mark.asyncio
async def test_invalid_normalized_container_refuses_before_any_model_disclosure(image):
    """Do not trust a forged normalized-image value passed directly to the adapter port."""
    calls = []

    def handler(request):
        """Record any unauthorized backend activity for the malformed image."""
        calls.append(request)
        return httpx.Response(200, json=models())

    with pytest.raises(ImageChatError, match="image_chat_invalid_image"):
        await CoreVisionChatAdapter(
            transport=httpx.MockTransport(handler)
        ).complete_image(image=replace(image, png_sha256="0" * 64), question="Question")
    assert not calls


@pytest.mark.asyncio
@pytest.mark.parametrize("cancel_kind", ["deadline", "caller"])
async def test_suppressed_model_info_cancellation_cannot_start_image_disclosure(
    image, monkeypatch, cancel_kind
):
    """Recheck ownership before POST even when discovery consumes cancellation and returns a valid late catalog."""
    entered = asyncio.Event()
    calls = []

    async def handler(request):
        """Consume only a controlled discovery cancellation to challenge the pre-image-disclosure fence."""
        calls.append(request)
        entered.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            return httpx.Response(200, json=models())

    adapter = CoreVisionChatAdapter(transport=httpx.MockTransport(handler))
    if cancel_kind == "deadline":
        monkeypatch.setattr(module, "TIMEOUT_SECONDS", 0.01)
        with pytest.raises(ImageChatError, match="image_chat_model_timeout"):
            await adapter.complete_image(image=image, question="Question")
    else:
        task = asyncio.create_task(
            adapter.complete_image(image=image, question="Question")
        )
        await entered.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert len(calls) == 1 and calls[0].method == "GET"
    logging.getLogger(__name__).info(
        "core_image_disclosure_cancellation_fence_verified"
    )
