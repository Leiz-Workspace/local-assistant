"""Reuse approved llama.cpp profiles and exact preset budgets for product chat and streaming."""

import asyncio
import contextlib
import json
import logging

import httpx

from apps.api.core.model_config import get_model_profile
from apps.api.runtime.presets import (
    ANSWER_RESERVE,
    CONTEXT_RESERVE,
    CONTEXT_SIZE,
    PresetError,
    RuntimePreset,
    build_generation_params,
    calculate_budget,
    classify_completion,
    get_preset,
)
from apps.api.services.llama_gateway import GatewayError, LlamaGateway
from apps.harness.summarizer import GatewaySummarizer
from src.application.services.context_composer import compose_context
from src.application.services.context_inspection import inspect_context
from src.application.services.context_reduction import HistoryPolicy
from src.application.services.context_reduction import (
    input_limit as reduced_input_limit,
)
from src.application.services import review_output_contract as review_contract
from src.application.services.special_literals import require_current_binding
from src.application.services.source_output_contract import (
    NAME,
    SourceContractError,
    quote_catalog,
    response_schema,
    validate_completion,
    digest,
)
from src.application.ports.inference import InferenceFailure
from src.infrastructure.inference.core_request_seal import seal_payload

LOGGER = logging.getLogger(__name__)


class IncompleteCompletion(GatewayError):
    """Report a native stream that ended without a verified complete answer."""

    code = "incomplete_completion"

    def __init__(self, status):
        """Keep only the finite completion classification."""
        super().__init__(self.code)
        self.status = status


def verify_stream_completion(finish_reason, parts):
    """Classify the streamed answer as the non-stream gateway does and refuse anything but PASS."""
    status = classify_completion(
        {
            "choices": [
                {
                    "finish_reason": finish_reason,
                    "message": {"content": "".join(parts)},
                }
            ]
        }
    )
    if status != "PASS":
        LOGGER.warning("product_stream_incomplete status=%s", status)
        raise IncompleteCompletion(status)


COMPAT_STREAM_BYTES = 262144
STREAM_BYTES_PER_TOKEN = 1024


def stream_limits(plan, product):
    """Return the SSE byte cap and timeout for one stream.

    The pinned-UI compatibility stream keeps its historical 256 KiB / 120 s bounds. The
    product stream scales with the granted output: llama.cpp spends about 250-300 bytes of
    SSE framing per generated token (reasoning included), so 1 KiB per granted token plus the
    historical base stays finite (about 33 MiB at the 32k context) without cutting long
    presets early. Its timeout is 60 s plus one second per 16 granted tokens, between 120 s
    and the gateway's 1200 s read timeout.
    """
    if not product:
        return COMPAT_STREAM_BYTES, 120.0
    seconds = min(1200.0, max(120.0, 60.0 + plan.max_tokens / 16))
    return COMPAT_STREAM_BYTES + plan.max_tokens * STREAM_BYTES_PER_TOKEN, seconds


def input_ceiling(preset, max_tokens, history_policy):
    """Return the input ceiling enforced for this request's composition path.

    The default path fits input while the output plan still has room for the answer reserve
    plus any finite reasoning budget (context_inspection._budget). The history-policy path
    reserves the full preset output first (context_reduction.input_limit).
    """
    if history_policy is not None:
        return reduced_input_limit(preset, max_tokens)
    config = get_preset(preset)
    finite = (
        config.thinking
        and config.reasoning_budget is not None
        and config.reasoning_budget >= 0
    )
    floor = ANSWER_RESERVE + (config.reasoning_budget if finite else 0)
    return CONTEXT_SIZE - CONTEXT_RESERVE - floor


def product_choices(event):
    """Keep only text, reasoning and finish fields from one upstream SSE event."""
    choices = []
    for choice in event.get("choices") or []:
        if not isinstance(choice, dict):
            continue
        delta = choice.get("delta") or {}
        kept = {
            key: delta[key]
            for key in ("content", "reasoning_content")
            if isinstance(delta.get(key), str) and delta[key]
        }
        item = {"delta": kept} if kept else {}
        if isinstance(choice.get("finish_reason"), str):
            item["finish_reason"] = choice["finish_reason"]
        if item:
            choices.append(item)
    return choices


def product_usage(event):
    """Return the final usage counters, if this upstream event carries them."""
    usage = event.get("usage")
    if not isinstance(usage, dict):
        return None
    counters = {
        key: usage[key]
        for key in ("prompt_tokens", "completion_tokens", "total_tokens")
        if type(usage.get(key)) is int
    }
    return counters or None


def sse(value, event=None):
    """Encode one JSON SSE frame."""
    head = f"event: {event}\n" if event else ""
    return (head + "data: " + json.dumps(value, ensure_ascii=False) + "\n\n").encode()


MAX_SSE_LINE_BYTES = 262144


async def sse_lines(response, deadline, byte_limit):
    """Yield upstream SSE lines split only on LF (CR stripped), so U+2028/U+0085 stay inside a frame.

    Each read is bounded by the absolute deadline; the bound never spans a consumer yield.
    """
    chunks = response.aiter_bytes()
    buffer, total = b"", 0
    while True:
        try:
            async with asyncio.timeout_at(deadline):
                chunk = await anext(chunks, None)
        except TimeoutError:
            raise GatewayError("stream_timeout") from None
        if chunk is None:
            break
        total += len(chunk)
        if total > byte_limit:
            raise GatewayError("stream_limit")
        buffer += chunk
        while (index := buffer.find(b"\n")) != -1:
            line, buffer = buffer[:index], buffer[index + 1 :]
            yield decode_sse_line(line)
        if len(buffer) > MAX_SSE_LINE_BYTES:
            raise GatewayError("stream_limit")
    if buffer:
        yield decode_sse_line(buffer)


def decode_sse_line(line):
    """Decode one LF-terminated upstream line; malformed bytes are an upstream fault."""
    if line.endswith(b"\r"):
        line = line[:-1]
    if len(line) > MAX_SSE_LINE_BYTES:
        raise GatewayError("stream_limit")
    try:
        return line.decode("utf-8")
    except UnicodeDecodeError:
        raise GatewayError("invalid_stream") from None


def upstream_event(value):
    """Parse one upstream data payload; malformed JSON is a gateway fault, never a client error."""
    try:
        event = json.loads(value)
    except ValueError:
        raise GatewayError("invalid_stream") from None
    if not isinstance(event, dict):
        raise GatewayError("invalid_stream")
    return event


class ProductInference:
    """Own finite CORE requests without changing the established gateway or model configuration."""

    def __init__(self, *, transport=None):
        """Allow isolated HTTP transports for tests without loading a model."""
        self.transport = transport

    async def prepare(
        self,
        messages,
        *,
        preset="fast",
        max_tokens=None,
        skill=None,
        evidence=(),
        context_strategy="evidence-first",
        output_contract="text",
        review_target=None,
        history_policy=None,
        archive=None,
        recall=None,
        summary_deadline=None,
        summary_cache=None,
        summary_debug=False,
        inspect_layers=False,
    ):
        """Verify the loaded CORE and fit actual templated input to one resolved preset."""
        config = get_model_profile("core")
        gateway = LlamaGateway(config["base_url"], config["model_id"], self.transport)
        async with httpx.AsyncClient(
            base_url=gateway.base_url,
            transport=self.transport,
            timeout=gateway._timeout(),
            trust_env=False,
        ) as client:
            await gateway._verify_model(client)
            selected = RuntimePreset(preset)
            if selected == RuntimePreset.AUTO:
                selected = (await gateway._select_auto_preset(client, messages)).preset

            async def count(candidate):
                """Count the exact approved backend template with the resolved thinking mode."""
                return await gateway._count_input_tokens(
                    client, candidate, thinking=get_preset(selected).thinking
                )

            summarizer = None
            if (
                history_policy is not None
                and summary_deadline is not None
                and HistoryPolicy.model_validate(history_policy).evicted_summary
            ):
                summarizer = GatewaySummarizer(
                    gateway, client, deadline=summary_deadline, cache=summary_cache
                )
            fitted, report = await compose_context(
                messages,
                count_tokens=count,
                preset=selected,
                max_tokens=max_tokens,
                skill=skill,
                evidence=evidence,
                strategy=context_strategy,
                output_contract=output_contract,
                review_target=review_target,
                history_policy=history_policy,
                archive=archive,
                recall=recall,
                summarizer=summarizer,
                summary_debug=summary_debug,
            )
            if inspect_layers:
                report["inspection"] = await inspect_context(
                    messages,
                    fitted,
                    report,
                    count_tokens=count,
                    preset=selected,
                    max_tokens=max_tokens,
                    skill=skill,
                    evidence=evidence,
                    output_contract=output_contract,
                )
        report["preset_selected"] = selected.value
        report["model_id"] = config["model_id"]
        return gateway, fitted, report

    async def complete(self, messages, **options):
        """Return one verified gateway completion together with a redacted context report."""
        require_current_binding()
        gateway, fitted, report = await self.prepare(messages, **options)
        contract_name = options.get("output_contract", "text")
        review_mode = contract_name in {
            review_contract.NAME,
            review_contract.QUOTE_FIRST_NAME,
        }
        if contract_name == NAME or review_mode:
            catalog = quote_catalog(
                options.get("evidence", ()), report["included_evidence"]
            )
            if review_mode:
                catalog = review_contract.target_catalog(
                    catalog, options.get("review_target")
                )
                schema = review_contract.response_schema(
                    catalog,
                    quote_first=contract_name == review_contract.QUOTE_FIRST_NAME,
                )
            else:
                schema = response_schema(catalog)
            plan = calculate_budget(
                preset=report["preset_selected"],
                input_tokens=report["input_tokens"],
                requested_max_tokens=options.get("max_tokens"),
            )
            payload = build_generation_params(plan)
            payload.update(
                model=gateway.model_id,
                messages=fitted,
                temperature=0.7,
                stream=False,
                response_format={
                    "type": "json_schema",
                    "json_schema": {"schema": schema},
                },
            )
            payload, _ = seal_payload(payload, "harness_structured")
            async with httpx.AsyncClient(
                base_url=gateway.base_url,
                transport=self.transport,
                timeout=gateway._timeout(),
                trust_env=False,
            ) as client:
                response = await client.post("/v1/chat/completions", json=payload)
                response.raise_for_status()
                if len(response.content) > 262144:
                    raise SourceContractError("source_contract_invalid")
                try:
                    result = response.json()
                except ValueError:
                    raise SourceContractError("source_contract_invalid") from None
            contract = (
                review_contract.validate_review(
                    result,
                    catalog,
                    options["review_target"],
                    contract_name=contract_name,
                )
                if review_mode
                else validate_completion(result, catalog)
            )
            contract["schema_sha256"] = digest(schema)
            report["output_contract"] = contract
            result["local_assistant"] = dict(
                preset=report["preset_selected"],
                thinking_requested=plan.thinking,
                reasoning_budget_requested=plan.reasoning_budget,
                max_tokens_requested=plan.max_tokens,
                input_tokens_counted=plan.input_tokens,
                context_size=plan.context_size,
                status="PASS",
                output_contract=contract_name,
            )
            LOGGER.info(
                "product_structured_inference_completed preset=%s",
                report["preset_selected"],
            )
            return result, report
        result = await gateway.complete(
            fitted,
            preset=report["preset_selected"],
            max_tokens=options.get("max_tokens"),
        )
        LOGGER.info("product_inference_completed preset=%s", report["preset_selected"])
        return result, report

    async def stream(
        self, messages, *, max_tokens=None, product=False, deadline=None, **options
    ):
        """Stream bounded native SSE and close the upstream request on cancellation or timeout.

        Without ``product`` this is the pinned-UI compatibility stream: preset fast unless
        given, upstream events forwarded unchanged. With ``product`` it honours the chat
        options, emits a context event first, forwards only text/reasoning/finish fields and
        the final usage, and scales its limits with the granted output. ``deadline`` (loop
        time) bounds the whole request; otherwise preparation gets 120 s and the upstream
        stream its preset-scaled time. No timeout scope ever spans a yield.
        """
        require_current_binding()
        options.setdefault("preset", "fast")
        loop = asyncio.get_running_loop()
        try:
            async with asyncio.timeout_at(deadline or loop.time() + 120):
                gateway, fitted, report = await self.prepare(
                    messages, max_tokens=max_tokens, **options
                )
        except TimeoutError:
            raise GatewayError("stream_timeout") from None
        try:
            plan = calculate_budget(
                preset=report["preset_selected"],
                input_tokens=report["input_tokens"],
                requested_max_tokens=max_tokens,
            )
        except PresetError:
            raise InferenceFailure(
                "Input exceeds the preset capacity.",
                code="context_overflow",
                status_code=422,
            ) from None
        byte_limit, seconds = stream_limits(plan, product)
        if deadline is None:
            deadline = loop.time() + seconds
        payload = build_generation_params(plan)
        payload.update(model=gateway.model_id, messages=fitted, stream=True)
        if product:
            payload["stream_options"] = {"include_usage": True}
            receipt = report.get("history_policy") or {}
            yield sse(
                dict(
                    input_tokens=report["input_tokens"],
                    input_limit=input_ceiling(
                        report["preset_selected"],
                        max_tokens,
                        options.get("history_policy"),
                    ),
                    context_size=plan.context_size,
                    preset_selected=report["preset_selected"],
                    max_tokens=plan.max_tokens,
                    thinking=plan.thinking,
                    retained_messages=report.get("retained_messages"),
                    trimmed_messages=report.get("trimmed_messages"),
                    included_evidence=[
                        entry["index"] for entry in report.get("included_evidence", [])
                    ],
                    omitted_evidence=[
                        dict(index=entry["index"], reason=entry["reason"])
                        for entry in report.get("omitted_evidence", [])
                    ],
                    skill_sha256=report.get("skill_sha256"),
                    archive_id=(receipt.get("archive") or {}).get("id"),
                ),
                event="context",
            )
        payload, _ = seal_payload(payload, "harness_stream")
        finished, total = False, 0
        async with contextlib.AsyncExitStack() as stack:
            client = await stack.enter_async_context(
                httpx.AsyncClient(
                    base_url=gateway.base_url,
                    transport=self.transport,
                    timeout=gateway._timeout(),
                    trust_env=False,
                )
            )
            try:
                async with asyncio.timeout_at(deadline):
                    response = await stack.enter_async_context(
                        client.stream("POST", "/v1/chat/completions", json=payload)
                    )
            except TimeoutError:
                raise GatewayError("stream_timeout") from None
            response.raise_for_status()
            finish, parts = None, []
            lines = await stack.enter_async_context(
                contextlib.aclosing(sse_lines(response, deadline, byte_limit))
            )
            async for line in lines:
                total += len(line.encode()) + 1
                if not line.startswith("data: "):
                    continue
                value = line[6:]
                if value == "[DONE]":
                    verify_stream_completion(finish, parts)
                    finished = True
                    yield b"data: [DONE]\n\n"
                    break
                event = upstream_event(value)
                for choice in event.get("choices") or []:
                    if not isinstance(choice, dict):
                        raise GatewayError("invalid_stream")
                    delta = choice.get("delta") or {}
                    if not isinstance(delta, dict):
                        raise GatewayError("invalid_stream")
                    if delta.get("tool_calls"):
                        raise GatewayError("unexpected_tool_call")
                    content = delta.get("content")
                    if isinstance(content, str):
                        parts.append(content)
                    if choice.get("finish_reason") is not None:
                        finish = choice["finish_reason"]
                if not product:
                    yield ("data: " + json.dumps(event) + "\n\n").encode()
                    continue
                choices = product_choices(event)
                if choices:
                    yield sse({"choices": choices})
                usage = product_usage(event)
                if usage is not None:
                    yield sse({"usage": usage})
        if not finished:
            raise GatewayError("incomplete_stream")
        LOGGER.info(
            "product_stream_completed bytes=%d product=%s preset=%s",
            total,
            product,
            report["preset_selected"],
        )
