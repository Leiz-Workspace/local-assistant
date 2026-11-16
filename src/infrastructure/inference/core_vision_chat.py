"""Send one normalized inline image to the existing advertised local CORE with no remote media, history, tools or response logging."""

import asyncio
import logging

import httpx

from apps.api.core.model_config import get_model_profile
from src.application.ports.inference import CompletionResult
from src.application.services.special_literals import (
    SpecialLiteralsStale,
    require_current_binding,
)
from src.application.services.vision_chat_policy import (
    MAX_TOKENS,
    SCHEMA,
    ImageChatError,
    model_messages,
    strict_json,
    validate_image,
)
from src.infrastructure.inference.core_request_seal import (
    CoreRequestRejected,
    seal_payload,
)

logger = logging.getLogger(__name__)
MAX_REPLY = 65536
TIMEOUT_SECONDS = 45


async def bounded_reply(client, method, path, *, payload=None, limit=MAX_REPLY):
    """Read one entire identity-encoded bounded JSON response and close its stream before returning or rejecting."""
    async with client.stream(method, path, json=payload) as response:
        if response.status_code != 200:
            raise ImageChatError("image_chat_unavailable")
        if (
            response.headers.get("content-encoding", "identity").strip().lower()
            not in {"", "identity"}
            or response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
            != "application/json"
        ):
            raise ImageChatError("image_chat_invalid_result")
        data = bytearray()
        async for chunk in response.aiter_bytes(16384):
            if len(data) + len(chunk) > limit:
                raise ImageChatError("image_chat_invalid_result")
            data.extend(chunk)
    try:
        return strict_json(bytes(data), limit)
    except Exception:
        raise ImageChatError("image_chat_invalid_result") from None


class CoreVisionChatAdapter:
    """Keep configured CORE and its advertised image capability fixed before disclosing one sanitized raster."""

    def __init__(self, *, expected_model="qwen3.5-9b-core", transport=None):
        """Bind trusted local model identity and an optional controlled HTTP transport without backend activity."""
        self.expected_model, self.transport = expected_model, transport
        logger.info("core_image_chat_adapter_initialized")

    async def complete_image(self, *, image, question):
        """Verify current original CORE capabilities and validate one complete structured native image completion."""
        require_current_binding()
        try:
            validate_image(image, image.source_sha256)
            messages = model_messages(question, image)
            profile = get_model_profile("core")
            if profile["model_id"] != self.expected_model:
                raise ImageChatError("image_chat_model_mismatch")
            if profile["base_url"] != "http://127.0.0.1:8080":
                raise ImageChatError("image_chat_unavailable")
            async with asyncio.timeout(TIMEOUT_SECONDS) as deadline:
                async with httpx.AsyncClient(
                    base_url=profile["base_url"],
                    trust_env=False,
                    follow_redirects=False,
                    transport=self.transport,
                    headers={"Accept-Encoding": "identity"},
                    timeout=httpx.Timeout(45, connect=2, pool=2),
                ) as client:
                    info = await bounded_reply(client, "GET", "/v1/models", limit=16384)
                    if asyncio.current_task().cancelling():
                        raise asyncio.CancelledError()
                    if deadline.expired():
                        raise ImageChatError("image_chat_model_timeout")
                    rows = info.get("data") if type(info) is dict else None
                    if (
                        type(rows) is not list
                        or len(rows) != 1
                        or type(rows[0]) is not dict
                        or rows[0].get("id") != self.expected_model
                    ):
                        raise ImageChatError("image_chat_model_mismatch")
                    architecture = rows[0].get("architecture")
                    if (
                        type(architecture) is not dict
                        or type(architecture.get("input_modalities")) is not list
                        or type(architecture.get("output_modalities")) is not list
                        or "image" not in architecture["input_modalities"]
                        or "text" not in architecture["output_modalities"]
                    ):
                        raise ImageChatError("image_chat_model_mismatch")
                    payload = dict(
                        model=self.expected_model,
                        messages=messages,
                        max_tokens=MAX_TOKENS,
                        temperature=0,
                        seed=7,
                        stream=False,
                        cache_prompt=False,
                        chat_template_kwargs=dict(enable_thinking=False),
                        response_format=dict(
                            type="json_schema",
                            json_schema=dict(
                                name="image_question_answer", strict=True, schema=SCHEMA
                            ),
                        ),
                    )
                    payload, _ = seal_payload(payload, "core_vision_chat")
                    reply = await bounded_reply(
                        client, "POST", "/v1/chat/completions", payload=payload
                    )
            if asyncio.current_task().cancelling():
                raise asyncio.CancelledError()
            if deadline.expired():
                raise ImageChatError("image_chat_model_timeout")
            if (
                type(reply) is not dict
                or reply.get("model") != self.expected_model
                or type(reply.get("choices")) is not list
                or len(reply["choices"]) != 1
            ):
                raise ImageChatError("image_chat_invalid_result")
            choice = reply["choices"][0]
            if (
                type(choice) is not dict
                or choice.get("finish_reason") != "stop"
                or type(choice.get("message")) is not dict
            ):
                raise ImageChatError("image_chat_invalid_result")
            message = choice["message"]
            if (
                message.get("role") != "assistant"
                or type(message.get("content")) is not str
                or not message["content"].strip()
                or message.get("tool_calls") is not None
                or message.get("function_call") is not None
            ):
                raise ImageChatError("image_chat_invalid_result")
            usage = reply.get("usage", {})
            if type(usage) is not dict:
                raise ImageChatError("image_chat_invalid_result")
            tokens = usage.get("completion_tokens")
            if tokens is not None and (
                type(tokens) is not int or not 0 <= tokens <= MAX_TOKENS
            ):
                raise ImageChatError("image_chat_invalid_result")
            logger.info("core_image_chat_completion_received")
            return CompletionResult(
                message["content"],
                self.expected_model,
                "fast",
                "stop",
                output_tokens=tokens,
            )
        except (ImageChatError, SpecialLiteralsStale, CoreRequestRejected):
            raise
        except asyncio.CancelledError:
            raise
        except TimeoutError:
            raise ImageChatError("image_chat_model_timeout") from None
        except Exception:
            raise ImageChatError("image_chat_model_failed") from None
