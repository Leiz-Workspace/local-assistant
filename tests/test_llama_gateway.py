import asyncio
import json

import httpx
import pytest

from apps.api.core.model_config import get_model_profile
from apps.api.services.llama_gateway import (
    GatewayError,
    LlamaGateway,
)


def test_model_profiles():
    core = get_model_profile("core")
    unrestricted = get_model_profile("unrestricted")

    assert core["model_id"] == "qwen3.5-9b-core"
    assert unrestricted["model_id"] == "qwen3.5-9b-unrestricted"
    assert core["base_url"] == "http://127.0.0.1:8080"


def test_core_profile_accepts_a_loopback_override(monkeypatch):
    monkeypatch.setenv("AEVRA_CORE_BASE_URL", "http://localhost:18085/")

    assert get_model_profile("core")["base_url"] == "http://localhost:18085"


def test_core_profile_rejects_credentials_and_paths(monkeypatch):
    for value in (
        "http://core:8080",
        "http://192.168.1.5:8080",
        "http://user:secret@127.0.0.1:8080",
        "http://core:8080/private",
        "file:///tmp/core",
    ):
        monkeypatch.setenv("AEVRA_CORE_BASE_URL", value)
        with pytest.raises(Exception, match="Invalid model configuration"):
            get_model_profile("core")


def test_gateway_completion():
    def handler(request: httpx.Request):
        if request.url.path == "/v1/models":
            return httpx.Response(
                200,
                json={"data": [{"id": "qwen3.5-9b-core"}]},
            )

        if request.url.path == "/v1/chat/completions":
            payload = json.loads(request.content)

            assert payload["model"] == "qwen3.5-9b-core"

            return httpx.Response(
                200,
                json={
                    "model": "qwen3.5-9b-core",
                    "choices": [
                        {
                            "message": {
                                "role": "assistant",
                                "content": "Xin chào SHLDD!",
                            }
                        }
                    ],
                },
            )

        return httpx.Response(404)

    gateway = LlamaGateway(
        base_url="http://127.0.0.1:8080",
        model_id="qwen3.5-9b-core",
        transport=httpx.MockTransport(handler),
    )

    result = asyncio.run(
        gateway.complete(messages=[{"role": "user", "content": "Xin chào"}])
    )

    assert result["choices"][0]["message"]["content"] == "Xin chào SHLDD!"


def test_model_mismatch():
    def handler(request: httpx.Request):
        return httpx.Response(
            200,
            json={"data": [{"id": "qwen3.5-9b-unrestricted"}]},
        )

    gateway = LlamaGateway(
        base_url="http://127.0.0.1:8080",
        model_id="qwen3.5-9b-core",
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(GatewayError) as exc:
        asyncio.run(gateway.complete(messages=[{"role": "user", "content": "Test"}]))

    assert exc.value.status_code == 409
