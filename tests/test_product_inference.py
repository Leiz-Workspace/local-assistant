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
