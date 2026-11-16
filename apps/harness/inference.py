"""Reuse approved llama.cpp profiles and exact preset budgets for product chat and streaming."""

import asyncio
import json
import logging

import httpx

from apps.api.core.model_config import get_model_profile
from apps.api.runtime.presets import (
    RuntimePreset,
    build_generation_params,
    calculate_budget,
    get_preset,
)
from apps.api.services.llama_gateway import GatewayError, LlamaGateway
from apps.harness.summarizer import GatewaySummarizer
from src.application.services.context_composer import compose_context
from src.application.services.context_inspection import inspect_context
from src.application.services.context_reduction import HistoryPolicy
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
from src.infrastructure.inference.core_request_seal import seal_payload

LOGGER = logging.getLogger(__name__)


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

    async def stream(self, messages, *, max_tokens=None):
        """Stream bounded native SSE and close the upstream request on cancellation or timeout."""
        require_current_binding()
        gateway, fitted, report = await self.prepare(
            messages, preset="fast", max_tokens=max_tokens
        )
        plan = calculate_budget(
            preset=report["preset_selected"],
            input_tokens=report["input_tokens"],
            requested_max_tokens=max_tokens,
        )
        payload = build_generation_params(plan)
        payload.update(model=gateway.model_id, messages=fitted, stream=True)
        payload, _ = seal_payload(payload, "harness_stream")
        total, finished = 0, False
        async with asyncio.timeout(120):
            async with httpx.AsyncClient(
                base_url=gateway.base_url,
                transport=self.transport,
                timeout=gateway._timeout(),
                trust_env=False,
            ) as client:
                async with client.stream(
                    "POST", "/v1/chat/completions", json=payload
                ) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        total += len(line.encode())
                        if total > 262144 or len(line) > 65536:
                            raise GatewayError("stream_limit")
                        if not line.startswith("data: "):
                            continue
                        value = line[6:]
                        if value == "[DONE]":
                            finished = True
                            yield b"data: [DONE]\n\n"
                            break
                        event = json.loads(value)
                        for choice in event.get("choices", []):
                            if choice.get("delta", {}).get("tool_calls"):
                                raise GatewayError("unexpected_tool_call")
                        yield ("data: " + json.dumps(event) + "\n\n").encode()
        if not finished:
            raise GatewayError("incomplete_stream")
        LOGGER.info("product_stream_completed bytes=%d", total)
