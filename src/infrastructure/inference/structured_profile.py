"""Provide opt-in host-schema native decoding for existing local profiles with strict unchanged-content validation and no tool, retry or default-selection authority."""

import asyncio
import base64
import hashlib
import json
import logging
import math
import re
import time
from dataclasses import dataclass, field

import httpx

from apps.api.core.model_config import get_model_profile
from src.application.services.profile_prompts import TEMPLATES
from src.application.services.web_fetch_tasks import finish_owned, spawn_owned

logger = logging.getLogger(__name__)
MAX_WIRE = 262144


class StructuredProfileError(Exception):
    """Expose finite audit errors without logging prompts, images, answers or backend exception strings."""

    def __init__(self, code):
        """Retain only a known bounded failure classification for caller audit."""
        self.code = (
            code
            if code
            in {
                "scope",
                "schema",
                "input",
                "spent",
                "unavailable",
                "identity",
                "wire",
                "incomplete",
                "content",
                "timeout",
                "failed",
            }
            else "failed"
        )
        super().__init__(self.code)
        logger.warning("structured_profile_rejected code=%s", self.code)


def strict_json(raw):
    """Decode complete finite JSON while rejecting duplicate keys, invalid UTF-8 and extraction or repair."""

    def pairs(items):
        """Reject duplicate keys at every object depth instead of silently choosing one value."""
        value = {}
        for key, item in items:
            if key in value:
                raise ValueError("duplicate_key")
            value[key] = item
        return value

    def constant(value):
        """Reject NaN and infinity tokens before schema or value comparison."""
        raise ValueError("nonfinite_json")

    if type(raw) not in (str, bytes) or not 0 < len(raw) <= MAX_WIRE:
        raise ValueError("json_size")
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)


def compile_schema(schema):
    """Snapshot a bounded structural-only object schema, refusing answer enums, constants, references, descriptions and executable keywords."""
    nodes = 0

    def visit(value, depth):
        """Accept only the finite supported shape vocabulary with exact object keys and bounded arrays or strings."""
        nonlocal nodes
        nodes += 1
        if type(value) is not dict or depth > 6 or nodes > 64:
            raise ValueError("schema_bound")
        kind = value.get("type")
        if kind == "object":
            if (
                set(value) != {"type", "properties", "required", "additionalProperties"}
                or value["additionalProperties"] is not False
            ):
                raise ValueError("object_schema")
            fields = value["properties"]
            if (
                type(fields) is not dict
                or not 1 <= len(fields) <= 16
                or any(
                    type(key) is not str
                    or re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}", key) is None
                    for key in fields
                )
            ):
                raise ValueError("schema_fields")
            if (
                type(value["required"]) is not list
                or len(value["required"]) != len(fields)
                or set(value["required"]) != set(fields)
            ):
                raise ValueError("schema_required")
            for child in fields.values():
                visit(child, depth + 1)
        elif kind == "array":
            if (
                set(value) != {"type", "items", "maxItems"}
                or type(value["maxItems"]) is not int
                or not 1 <= value["maxItems"] <= 64
            ):
                raise ValueError("array_schema")
            visit(value["items"], depth + 1)
        elif kind == "string":
            if (
                set(value) != {"type", "maxLength"}
                or type(value["maxLength"]) is not int
                or not 1 <= value["maxLength"] <= 4096
            ):
                raise ValueError("string_schema")
        elif kind not in {"integer", "number", "boolean"} or set(value) != {"type"}:
            raise ValueError("schema_keyword")

    try:
        raw = json.dumps(
            schema, sort_keys=True, allow_nan=False, separators=(",", ":")
        ).encode()
        if len(raw) > 16384 or schema.get("type") != "object":
            raise ValueError("schema_root")
        visit(strict_json(raw), 0)
    except Exception:
        raise StructuredProfileError("schema") from None
    logger.info("structured_profile_host_schema_compiled nodes=%d", nodes)
    return raw


def matches_schema(value, schema):
    """Validate complete decoded output against the trusted shape without coercion, answer filling or content normalization."""
    kind = schema["type"]
    if kind == "object":
        return (
            type(value) is dict
            and set(value) == set(schema["properties"])
            and all(
                matches_schema(value[key], child)
                for key, child in schema["properties"].items()
            )
        )
    if kind == "array":
        return (
            type(value) is list
            and len(value) <= schema["maxItems"]
            and all(matches_schema(item, schema["items"]) for item in value)
        )
    if kind == "string":
        return type(value) is str and len(value) <= schema["maxLength"]
    if kind == "integer":
        return type(value) is int
    if kind == "number":
        return type(value) in (int, float) and math.isfinite(value)
    return kind == "boolean" and type(value) is bool


@dataclass(frozen=True, slots=True)
class StructuredProfileResult:
    """Retain exact valid native content and independently parsed value with bounded first-observation metadata, never a repaired answer."""

    content: str = field(repr=False)
    value: dict = field(repr=False)
    model_id: str
    schema_sha256: str
    request_sha256: str
    wire_sha256: str
    input_tokens: int
    output_tokens: int
    wall_seconds: float
    first_content_frame_seconds: float | None


class StructuredProfileAdapter:
    """Bind one explicit trusted schema and existing profile to a single-use loopback request with joined cleanup and no model/action selection."""

    def __init__(
        self,
        *,
        profile,
        schema,
        endpoint=None,
        transport=None,
        max_tokens=256,
        timeout=90,
    ):
        """Validate host-only schema, endpoint and budgets without opening a connection or changing existing inference behavior."""
        if (
            type(profile) is not str
            or profile not in TEMPLATES
            or type(max_tokens) is not int
            or not 1 <= max_tokens <= 512
            or type(timeout) not in (int, float)
            or not 0 < timeout <= 90
        ):
            raise StructuredProfileError("scope")
        config = get_model_profile(profile)
        if config["model_id"] != "qwen3.5-9b-" + profile:
            raise StructuredProfileError("scope")
        endpoint = config["base_url"] if endpoint is None else endpoint
        if endpoint not in {"http://127.0.0.1:8080", "http://127.0.0.1:18080"}:
            raise StructuredProfileError("scope")
        self.profile, self.model, self.endpoint = profile, config["model_id"], endpoint
        self.schema_bytes = compile_schema(schema)
        self.transport, self.max_tokens, self.timeout = transport, max_tokens, timeout
        self.spent, self.last_request, self.last_response = False, None, b""
        self.active = None
        self.generation_dispatched = False
        logger.info("structured_profile_bound profile=%s", profile)

    def payload(self, text, images, stream):
        """Accept only bounded text and trusted inline PNG fixtures, with fixed roles/model/schema and no tools, remote image URLs or caller overrides."""
        if (
            type(text) is not str
            or not text.strip()
            or len(text.encode()) > 524288
            or type(images) is not tuple
            or len(images) > 4
            or type(stream) is not bool
        ):
            raise StructuredProfileError("input")
        parts = [dict(type="text", text=text)]
        for image in images:
            if (
                type(image) is not bytes
                or not 24 <= len(image) <= 1048576
                or image[:8] != b"\x89PNG\r\n\x1a\n"
                or not 0 < int.from_bytes(image[16:20], "big") <= 2000
                or not 0 < int.from_bytes(image[20:24], "big") <= 2000
            ):
                raise StructuredProfileError("input")
            parts.append(
                dict(
                    type="image_url",
                    image_url=dict(
                        url="data:image/png;base64," + base64.b64encode(image).decode()
                    ),
                )
            )
        value = dict(
            model=self.model,
            messages=[
                dict(role="system", content=TEMPLATES[self.profile]),
                dict(role="user", content=parts if images else text),
            ],
            temperature=0,
            max_tokens=self.max_tokens,
            stream=stream,
            cache_prompt=False,
            chat_template_kwargs=dict(enable_thinking=False),
            response_format=dict(
                type="json_object", schema=json.loads(self.schema_bytes)
            ),
        )
        if stream:
            value["stream_options"] = dict(include_usage=True)
        if len(json.dumps(value).encode()) > 2 * 1048576:
            raise StructuredProfileError("input")
        return value

    async def complete(self, text, *, images=(), stream=False):
        """Own one spent native child and join its HTTP cleanup even when caller cancellation repeats or a backend suppresses cancellation."""
        if self.spent:
            raise StructuredProfileError("spent")
        payload = self.payload(text, images, stream)
        self.spent = True
        self.last_request = json.dumps(
            payload, ensure_ascii=False, separators=(",", ":")
        ).encode()
        child = spawn_owned(self._complete_native(payload, images, stream))
        self.active = child
        try:
            result = await asyncio.shield(child)
            if asyncio.current_task().cancelling():
                raise asyncio.CancelledError()
            return result
        except asyncio.CancelledError:
            if not child.done() and not child.cancelling():
                child.cancel()
            try:
                await finish_owned(child)
            except BaseException:
                logger.info("structured_profile_owned_cancel_joined")
            raise
        finally:
            self.active = None

    async def _complete_native(self, payload, images, stream):
        """Perform exactly one bounded native generation and preserve first bytes before strict validation without repair or fallback."""
        start, first, raw, pending = time.monotonic(), None, bytearray(), bytearray()
        events, done = [], False
        try:
            async with asyncio.timeout(self.timeout) as deadline:
                async with httpx.AsyncClient(
                    base_url=self.endpoint,
                    transport=self.transport,
                    trust_env=False,
                    follow_redirects=False,
                    timeout=httpx.Timeout(self.timeout, connect=2, pool=2),
                    headers={"Accept-Encoding": "identity"},
                ) as client:
                    model_raw = bytearray()
                    async with client.stream("GET", "/v1/models") as info:
                        if (
                            info.status_code != 200
                            or info.headers.get("content-type", "")
                            .split(";", 1)[0]
                            .strip()
                            .lower()
                            != "application/json"
                            or info.headers.get("content-encoding", "identity")
                            .strip()
                            .lower()
                            not in {"", "identity"}
                        ):
                            raise StructuredProfileError("identity")
                        async for chunk in info.aiter_bytes():
                            if len(model_raw) + len(chunk) > 16384:
                                raise StructuredProfileError("identity")
                            model_raw.extend(chunk)
                    data = strict_json(bytes(model_raw))
                    advertised = data.get("data") if type(data) is dict else None
                    if (
                        type(advertised) is not list
                        or len(advertised) != 1
                        or advertised[0].get("id") != self.model
                    ):
                        raise StructuredProfileError("identity")
                    if images and "image" not in advertised[0].get(
                        "architecture", {}
                    ).get("input_modalities", []):
                        raise StructuredProfileError("identity")
                    self.generation_dispatched = True
                    async with client.stream(
                        "POST",
                        "/v1/chat/completions",
                        content=self.last_request,
                        headers={"Content-Type": "application/json"},
                    ) as response:
                        media = (
                            response.headers.get("content-type", "")
                            .split(";", 1)[0]
                            .strip()
                            .lower()
                        )
                        invalid_wire = (
                            response.status_code != 200
                            or media
                            != ("text/event-stream" if stream else "application/json")
                            or response.headers.get("content-encoding", "identity")
                            .strip()
                            .lower()
                            not in {"", "identity"}
                        )
                        async for block in response.aiter_bytes():
                            if len(raw) + len(block) > MAX_WIRE:
                                raise StructuredProfileError("wire")
                            raw.extend(block)
                            if stream and not invalid_wire:
                                pending.extend(block)
                                while b"\n" in pending:
                                    line, _, tail = pending.partition(b"\n")
                                    pending[:] = tail
                                    line = line.rstrip(b"\r")
                                    if not line or line.startswith(b":"):
                                        continue
                                    if not line.startswith(b"data: ") or done:
                                        raise StructuredProfileError("wire")
                                    if line == b"data: [DONE]":
                                        done = True
                                        continue
                                    event = strict_json(bytes(line[6:]))
                                    events.append(event)
                                    if first is None and any(
                                        c.get("delta", {}).get("content")
                                        for c in event.get("choices", [])
                                    ):
                                        first = time.monotonic() - start
                    if invalid_wire:
                        raise StructuredProfileError("wire")
            if asyncio.current_task().cancelling():
                raise asyncio.CancelledError()
            if deadline.expired():
                raise StructuredProfileError("timeout")
            self.last_response = bytes(raw)
            reply = (
                self.stream_reply(events, done, bytes(pending), first)
                if stream
                else strict_json(bytes(raw))
            )
            content, usage = self.validate_reply(reply)
            value = strict_json(content)
            if not matches_schema(value, json.loads(self.schema_bytes)):
                raise StructuredProfileError("content")
            result = StructuredProfileResult(
                content,
                value,
                self.model,
                hashlib.sha256(self.schema_bytes).hexdigest(),
                hashlib.sha256(self.last_request).hexdigest(),
                hashlib.sha256(raw).hexdigest(),
                usage["prompt_tokens"],
                usage["completion_tokens"],
                time.monotonic() - start,
                first,
            )
            logger.info(
                "structured_profile_completed profile=%s streaming=%s",
                self.profile,
                stream,
            )
            return result
        except asyncio.CancelledError:
            logger.info(
                "structured_profile_cancelled_work_joined profile=%s", self.profile
            )
            raise
        except StructuredProfileError:
            raise
        except (TimeoutError, httpx.TimeoutException):
            raise StructuredProfileError("timeout") from None
        except Exception:
            raise StructuredProfileError("failed") from None
        finally:
            self.last_response = bytes(raw)

    def stream_reply(self, events, done, pending, first):
        """Require complete native SSE identity, one answer choice, final usage and stop before exposing the exact concatenated content."""
        if not done or pending.strip() or first is None:
            raise StructuredProfileError("incomplete")
        texts, finish, usage = [], None, None
        for event in events:
            if (
                type(event) is not dict
                or event.get("model") != self.model
                or type(event.get("choices")) is not list
                or len(event["choices"]) > 1
            ):
                raise StructuredProfileError("identity")
            if event.get("usage") is not None:
                if usage is not None:
                    raise StructuredProfileError("wire")
                usage = event["usage"]
            for choice in event["choices"]:
                delta = choice.get("delta")
                if (
                    choice.get("index") != 0
                    or type(delta) is not dict
                    or delta.get("role", "assistant") != "assistant"
                    or delta.get("tool_calls") is not None
                    or delta.get("function_call") is not None
                ):
                    raise StructuredProfileError("wire")
                text = delta.get("content", "")
                if (
                    text is None
                    and delta.get("role") == "assistant"
                    and not texts
                    and finish is None
                ):
                    text = ""
                if type(text) is not str or text and finish is not None:
                    raise StructuredProfileError("wire")
                texts.append(text)
                if choice.get("finish_reason"):
                    if finish is not None:
                        raise StructuredProfileError("wire")
                    finish = choice["finish_reason"]
        return dict(
            model=self.model,
            choices=[
                dict(
                    message=dict(role="assistant", content="".join(texts)),
                    finish_reason=finish,
                )
            ],
            usage=usage,
        )

    def validate_reply(self, reply):
        """Require exact native model/assistant/stop/usage metadata and preserve content verbatim before host-schema validation."""
        if (
            type(reply) is not dict
            or reply.get("model") != self.model
            or type(reply.get("choices")) is not list
            or len(reply["choices"]) != 1
        ):
            raise StructuredProfileError("identity")
        choice = reply["choices"][0]
        if type(choice) is not dict or choice.get("finish_reason") != "stop":
            raise StructuredProfileError("incomplete")
        message, usage = choice.get("message"), reply.get("usage")
        if (
            type(message) is not dict
            or message.get("role") != "assistant"
            or type(message.get("content")) is not str
            or not message["content"].strip()
            or message.get("tool_calls") is not None
            or message.get("function_call") is not None
        ):
            raise StructuredProfileError("content")
        if (
            type(usage) is not dict
            or type(usage.get("prompt_tokens")) is not int
            or usage["prompt_tokens"] <= 0
            or type(usage.get("completion_tokens")) is not int
            or not 1 <= usage["completion_tokens"] <= self.max_tokens
        ):
            raise StructuredProfileError("incomplete")
        return message["content"], usage
