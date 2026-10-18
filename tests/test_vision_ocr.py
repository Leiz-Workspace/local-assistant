"""Verify bounded loopback model protocol, schema constraints and fail-closed VLM errors."""

import json

import httpx
import pytest

from apps.api.services.vision_ocr import transcribe_image
from src.application.services.file_storage_policy import StoragePolicyError


@pytest.mark.asyncio
async def test_schema_constrained_transcription_without_tools_or_history():
    """Use only fixed transcription prompts and a sanitized inline image with a strict output schema."""

    def handler(request):
        """Serve a configured CORE identity and inspect its restricted transcription request."""
        assert request.url.host == "127.0.0.1"
        if request.url.path == "/v1/models":
            return httpx.Response(200, json={"data": [{"id": "qwen3.5-9b-core"}]})
        payload = json.loads(request.content)
        assert payload["response_format"]["type"] == "json_schema"
        assert payload["max_tokens"] == 1024 and payload["temperature"] == 0
        assert not payload["chat_template_kwargs"]["enable_thinking"]
        assert "tools" not in payload and len(payload["messages"]) == 2
        assert (
            payload["messages"][1]["content"][1]["image_url"]["url"]
            == "data:image/png;base64,sanitized"
        )
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "content": json.dumps(
                                {
                                    "text": "sample",
                                    "tables": [],
                                    "uncertain_regions": ["blurred"],
                                }
                            )
                        },
                    }
                ]
            },
        )

    result = await transcribe_image("sanitized", transport=httpx.MockTransport(handler))
    assert result["text"] == "sample" and result["engine"] == "qwen3.5-9b-core"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kind",
    [
        "model",
        "status",
        "redirect",
        "timeout",
        "length",
        "malformed",
        "schema",
        "large",
        "choices",
    ],
)
async def test_model_failures_are_sanitized(kind):
    """Reject identity drift, redirects, incomplete generation and malformed/oversized model replies."""

    def handler(request):
        """Inject only controlled failures and never echo request raster content into an error."""
        if request.url.path == "/v1/models":
            return httpx.Response(
                200,
                json={
                    "data": [{"id": "wrong" if kind == "model" else "qwen3.5-9b-core"}]
                },
            )
        if kind == "timeout":
            raise httpx.ReadTimeout("private-response", request=request)
        if kind in ("status", "redirect"):
            return httpx.Response(
                503 if kind == "status" else 302,
                headers={"Location": "https://example.invalid"},
            )
        if kind == "large":
            return httpx.Response(200, content=b"x" * 65537)
        if kind == "choices":
            return httpx.Response(200, json={"choices": []})
        content = (
            "broken"
            if kind == "malformed"
            else json.dumps(
                {
                    "text": "x",
                    "tables": [],
                    "uncertain_regions": [],
                    **({"confidence": 99} if kind == "schema" else {}),
                }
            )
        )
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "length" if kind == "length" else "stop",
                        "message": {"content": content},
                    }
                ]
            },
        )

    with pytest.raises(StoragePolicyError) as error:
        await transcribe_image("sanitized", transport=httpx.MockTransport(handler))
    assert error.value.code in (
        "vision_unavailable",
        "vision_model_mismatch",
        "vision_invalid_result",
        "vision_incomplete_result",
    )
