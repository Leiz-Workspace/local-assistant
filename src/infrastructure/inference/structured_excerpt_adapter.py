"""Generate opt-in typed extractive replies on the existing CORE with source-derived JSON grammar and unchanged runtime budgets."""

import asyncio
import hashlib
import json
import logging
import re
from dataclasses import dataclass
from types import MappingProxyType

import httpx

from apps.api.core.model_config import get_model_profile
from apps.api.runtime.presets import (
    build_generation_params,
    calculate_budget,
    classify_completion,
)
from apps.api.services.llama_gateway import LlamaGateway
from src.application.ports.inference import CompletionResult, InferenceFailure
from src.application.services.mcp_adapter import canonical
from src.application.services.profile_prompts import TEMPLATES, PromptInput
from src.application.services.workspace_requests import parse_workspace_json

logger = logging.getLogger(__name__)


class StructuredRefusal(ValueError):
    """Distinguish an explicit evidence refusal from malformed output without publishing an invented typed answer."""


def encoded(value):
    """Serialize finite JSON without changing Unicode or admitting unbounded request/schema artifacts."""
    raw = json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    ).encode()
    if len(raw) > 32768:
        raise ValueError("structured_frame_limit")
    return raw


def source_units(text, mode):
    """Select exact nonblank line/sentence substrings without normalizing interior text or rewriting generated quotes."""
    if (
        type(text) is not str
        or not 1 <= len(text) <= 4096
        or mode not in {"lines", "sentences"}
    ):
        raise ValueError("structured_unit_limit")
    boundaries = re.finditer(
        r"\r?\n" if mode == "lines" else r"[.!?](?=\s|$)|\r?\n", text
    )
    ends = [match.end() for match in boundaries] + [len(text)]
    start, units = 0, []
    for end in ends:
        left, right = start, end
        while left < right and text[left].isspace():
            left += 1
        while right > left and text[right - 1].isspace():
            right -= 1
        if left < right:
            unit = text[left:right]
            if len(unit) > 512:
                raise ValueError("structured_unit_limit")
            if unit not in units:
                units.append(unit)
        start = end
    units = [unit for unit in units if text.find(unit, text.find(unit) + 1) == -1]
    if not 1 <= len(units) <= 32:
        raise ValueError("structured_unit_limit")
    return tuple(units)


def whole_integers(text):
    """Read only signed 32-bit whole integer tokens using the same literal policy for grammar and publication."""
    tokens = re.findall(r"(?<![\w.+-])[+-]?[0-9]+(?![\w.])", text)
    return frozenset(
        value for token in tokens if -(2**31) <= (value := int(token)) < 2**31
    )


def literal_string_values(units):
    """Enumerate bounded whitespace-aligned source spans without Unicode normalization, expected answers or output repair."""
    values = {}
    for unit in units:
        words = list(re.finditer(r"\S+", unit))
        for first in range(len(words)):
            for last in range(first, len(words)):
                left, right = words[first].start(), words[last].end()
                if right - left > 32:
                    break
                spans = [(left, right)]
                while left < right and unit[left] in "\"'([{":
                    left += 1
                while right > left and unit[right - 1] in "\"')]}.,;:!?":
                    right -= 1
                spans.append((left, right))
                for start, end in spans:
                    if 1 <= end - start <= 24:
                        values[unit[start:end]] = None
                        if len(values) > 512:
                            raise ValueError("structured_value_limit")
    if not values:
        raise ValueError("structured_value_limit")
    logger.info("structured_literal_values_bound choices=%d", len(values))
    return tuple(values)


@dataclass(frozen=True, slots=True)
class StructuredProvenance:
    """Record prompt/schema/native-request/output digests as provenance, never as authorization or semantic certification."""

    prompt_sha256: str
    schema_sha256: str
    native_request_sha256: str
    content_sha256: str
    schema_enabled: bool
    literal_strings: bool


class StructuredExcerptAdapter:
    """Own one explicit CORE extraction request with host field definitions, source-derived quote choices and strict output publication."""

    def __init__(
        self,
        *,
        request,
        fields,
        source_modes,
        model_id,
        facts_key,
        schema_enabled,
        literal_strings=False,
        transport=None,
    ):
        """Require immutable bounded host contracts and an explicit grammar choice without loading or selecting another model."""
        if (
            type(request) is not str
            or not 1 <= len(request) <= 4096
            or type(fields) is not tuple
            or not 1 <= len(fields) <= 8
            or type(source_modes) is not dict
            or type(model_id) is not str
            or model_id != "qwen3.5-9b-core"
            or facts_key not in {None, "facts"}
            or type(schema_enabled) is not bool
            or type(literal_strings) is not bool
            or (literal_strings and not schema_enabled)
        ):
            raise ValueError("structured_host_contract")
        names, sources = set(), set()
        for field in fields:
            if type(field) is not tuple or len(field) != 3:
                raise ValueError("structured_host_contract")
            name, kind, source = field
            if (
                type(name) is not str
                or re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,63}", name) is None
                or name in names
                or name == "citations"
                or type(kind) is not str
                or kind not in {"string", "integer"}
                or type(source) is not str
                or re.fullmatch(r"[A-Za-z0-9_-]{1,64}", source) is None
                or source in sources
            ):
                raise ValueError("structured_host_contract")
            names.add(name)
            sources.add(source)
        if set(source_modes) != sources or any(
            value not in {"lines", "sentences"} for value in source_modes.values()
        ):
            raise ValueError("structured_host_contract")
        self.request, self.fields, self.model_id, self.facts_key = (
            request,
            fields,
            model_id,
            facts_key,
        )
        self.source_modes = MappingProxyType(dict(source_modes))
        self.schema_enabled, self.transport = schema_enabled, transport
        self.literal_strings = literal_strings
        self.calls, self.last_error, self.provenance = 0, None, None
        logger.info(
            "structured_excerpt_bound fields=%d grammar=%s", len(fields), schema_enabled
        )

    def prepare(self, messages):
        """Validate exact existing CORE template/question and derive quote enums from all source units, without expected-answer oracles."""
        copied = json.loads(encoded(dict(messages=messages)))["messages"]
        if (
            type(copied) is not list
            or len(copied) != 2
            or copied[0] != dict(role="system", content=TEMPLATES["core"])
            or type(copied[1]) is not dict
            or set(copied[1]) != {"role", "content"}
            or copied[1]["role"] != "user"
            or type(copied[1]["content"]) is not str
        ):
            raise ValueError("structured_prompt_scope")
        data = PromptInput.model_validate(
            parse_workspace_json(copied[1]["content"].encode())
        )
        if (
            data.request != self.request
            or len(data.sources) != len(self.fields)
            or {row.source_id for row in data.sources} != set(self.source_modes)
        ):
            raise ValueError("structured_prompt_scope")
        units = {
            row.source_id: source_units(row.text, self.source_modes[row.source_id])
            for row in data.sources
        }
        integer_sources = {
            source for _, kind, source in self.fields if kind == "integer"
        }
        eligible = {
            source: tuple(
                unit
                for unit in choices
                if source not in integer_sources or whole_integers(unit)
            )
            for source, choices in units.items()
        }
        logger.info(
            "structured_quote_eligibility sources=%d removed=%d",
            len(units),
            sum(len(units[key]) - len(eligible[key]) for key in units),
        )
        properties = {
            name: dict(type=kind, minimum=-(2**31), maximum=2**31 - 1)
            if kind == "integer"
            else dict(type="string", minLength=1, maxLength=24)
            for name, kind, _ in self.fields
        }
        if self.literal_strings:
            for name, kind, source in self.fields:
                if kind == "string":
                    properties[name]["enum"] = list(
                        literal_string_values(units[source])
                    )
        facts = dict(
            type="object",
            properties=properties,
            required=list(properties),
            additionalProperties=False,
        )
        citation = dict(
            anyOf=[
                dict(
                    type="object",
                    properties=dict(
                        source_id=dict(type="string", enum=[source]),
                        quote=dict(type="string", enum=list(choices)),
                    ),
                    required=["source_id", "quote"],
                    additionalProperties=False,
                )
                for source, choices in eligible.items()
                if choices
            ]
        )
        citations = dict(
            type="array", items=citation, minItems=len(units), maxItems=len(units)
        )
        if self.facts_key is None:
            schema = dict(facts)
            schema["properties"] = dict(properties, citations=citations)
            schema["required"] = [*properties, "citations"]
        else:
            schema = dict(
                type="object",
                properties=dict(facts=facts, citations=citations),
                required=["facts", "citations"],
                additionalProperties=False,
            )
        refusal_properties = (
            {name: dict(type="null") for name, _, _ in self.fields}
            if self.facts_key is None
            else dict(facts=dict(type="null"))
        )
        refusal_properties["citations"] = dict(type="array", maxItems=0)
        refusal = dict(
            type="object",
            properties=refusal_properties,
            required=list(refusal_properties),
            additionalProperties=False,
        )
        schema = dict(anyOf=[schema, refusal]) if all(eligible.values()) else refusal
        encoded(schema)
        return copied, schema, units

    def validate_content(self, content, units):
        """Require declared scalar types, one exact source unit per citation and literal value consistency without asserting general semantics."""
        body = parse_workspace_json(content.encode())
        names = {name for name, _, _ in self.fields}
        if (self.facts_key == "facts" and body == dict(facts=None, citations=[])) or (
            self.facts_key is None
            and set(body) == names | {"citations"}
            and body["citations"] == []
            and all(body[name] is None for name in names)
        ):
            raise StructuredRefusal("structured_insufficient_evidence")
        if self.facts_key is None:
            if set(body) != names | {"citations"}:
                raise ValueError("structured_reply_fields")
            facts = {name: body[name] for name in names}
        else:
            if (
                set(body) != {"facts", "citations"}
                or type(body["facts"]) is not dict
                or set(body["facts"]) != names
            ):
                raise ValueError("structured_reply_fields")
            facts = body["facts"]
        citations = body["citations"]
        if type(citations) is not list or len(citations) != len(units):
            raise ValueError("structured_reply_citations")
        quotes = {}
        for row in citations:
            if type(row) is not dict or set(row) != {"source_id", "quote"}:
                raise ValueError("structured_reply_citations")
            identifier, quote = row["source_id"], row["quote"]
            if (
                type(identifier) is not str
                or identifier not in units
                or identifier in quotes
                or type(quote) is not str
                or quote not in units[identifier]
            ):
                raise ValueError("structured_reply_citations")
            quotes[identifier] = quote
        for name, kind, source in self.fields:
            value = facts[name]
            if kind == "integer":
                if type(value) is not int or not -(2**31) <= value < 2**31:
                    raise ValueError("structured_reply_type")
                if value not in whole_integers(quotes[source]):
                    raise ValueError("structured_reply_literal")
            elif (
                type(value) is not str
                or not 1 <= len(value) <= 24
                or value not in quotes[source]
            ):
                raise ValueError("structured_reply_literal")
            elif self.literal_strings and value not in literal_string_values(
                units[source]
            ):
                raise ValueError("structured_reply_literal_domain")
        logger.info("structured_excerpt_content_verified fields=%d", len(facts))

    async def complete(self, **request):
        """Perform one original-model Fast512 inference with an optional per-request JSON grammar and no fallback, repair or retry."""
        self.calls += 1
        self.provenance = None
        phase = "invalid_request"
        try:
            if self.calls != 1 or any(
                request.get(key) != value
                for key, value in dict(
                    profile="core", preset="fast", max_tokens=512, temperature=0
                ).items()
            ):
                raise ValueError("structured_request_scope")
            messages, schema, units = self.prepare(request.get("messages"))
            config = get_model_profile("core")
            if (
                config["model_id"] != self.model_id
                or config["base_url"] != "http://127.0.0.1:8080"
            ):
                raise ValueError("structured_model_scope")
            gateway = LlamaGateway(config["base_url"], self.model_id)
            phase = "backend_failed"
            async with httpx.AsyncClient(
                base_url=config["base_url"],
                transport=self.transport,
                timeout=httpx.Timeout(20, connect=5),
                trust_env=False,
                follow_redirects=False,
            ) as client:
                await gateway._verify_model(client)
                count = await gateway._count_input_tokens(
                    client, messages, thinking=False
                )
                plan = calculate_budget(
                    preset="fast", input_tokens=count, requested_max_tokens=512
                )
                native = dict(
                    model=self.model_id,
                    messages=messages,
                    temperature=0,
                    stream=False,
                    **build_generation_params(plan),
                )
                if self.schema_enabled:
                    native["response_format"] = dict(type="json_object", schema=schema)
                raw_request = encoded(native)
                chunks, size = [], 0
                async with client.stream(
                    "POST",
                    "/v1/chat/completions",
                    content=raw_request,
                    headers={"Content-Type": "application/json"},
                ) as response:
                    response.raise_for_status()
                    async for chunk in response.aiter_bytes():
                        size += len(chunk)
                        if size > 65536:
                            raise ValueError("structured_response_limit")
                        chunks.append(chunk)
                phase = "invalid_reply"
                result = parse_workspace_json(b"".join(chunks))
            if result.get("model") != self.model_id:
                phase = "model_mismatch"
                raise ValueError("structured_response_identity")
            if classify_completion(result) != "PASS" or len(result["choices"]) != 1:
                raise ValueError("structured_response_identity")
            content, usage = result["choices"][0]["message"]["content"], result["usage"]
            if (
                any(
                    type(usage.get(key)) is not int or usage[key] < 0
                    for key in ("prompt_tokens", "completion_tokens")
                )
                or not 1 <= usage["completion_tokens"] <= 512
            ):
                raise ValueError("structured_usage")
            self.validate_content(content, units)
            if asyncio.current_task().cancelling():
                raise asyncio.CancelledError()
            self.provenance = StructuredProvenance(
                hashlib.sha256(canonical(dict(messages=messages))).hexdigest(),
                hashlib.sha256(encoded(schema)).hexdigest(),
                hashlib.sha256(raw_request).hexdigest(),
                hashlib.sha256(content.encode()).hexdigest(),
                self.schema_enabled,
                self.literal_strings,
            )
            logger.info("structured_excerpt_completed grammar=%s", self.schema_enabled)
            return CompletionResult(
                content,
                self.model_id,
                "fast",
                "stop",
                usage["prompt_tokens"],
                usage["completion_tokens"],
            )
        except asyncio.CancelledError:
            self.last_error = "cancelled"
            logger.info("structured_excerpt_cancelled")
            raise
        except StructuredRefusal:
            self.last_error = "insufficient_evidence"
            logger.info("structured_excerpt_refused")
            raise InferenceFailure(
                "Supporting evidence is absent.",
                code="structured_insufficient_evidence",
                status_code=422,
            ) from None
        except Exception:
            self.last_error = phase
            logger.warning("structured_excerpt_rejected code=%s", phase)
            raise InferenceFailure(
                "Structured extraction unavailable.",
                code="structured_" + phase,
                status_code=503,
            ) from None
