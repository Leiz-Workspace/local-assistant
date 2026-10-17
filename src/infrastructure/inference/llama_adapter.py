"""Adapt existing model inference with token-aware whole-turn context preparation."""

from __future__ import annotations

import logging
from time import perf_counter
from typing import Any

import httpx

from apps.api.core.model_config import (
    ModelConfigError,
    get_model_profile,
)
from apps.api.runtime.presets import RuntimePreset, get_preset
from apps.api.services.llama_gateway import (
    GatewayError,
    LlamaGateway,
)
from src.application.ports.inference import (
    CompletionResult,
    InferenceFailure,
)
from src.application.services.conversation_context import fit_token_budget

logger = logging.getLogger(__name__)


class LlamaInferenceAdapter:
    """
    Adapts the existing LlamaGateway to the application port.

    The adapter does not:
    - Change runtime presets.
    - Persist reasoning_content.
    - Manage PostgreSQL sessions.
    - Start or stop any llama.cpp container.
    """

    @staticmethod
    def _nonnegative_int(value: Any) -> int | None:
        """Accept only nonnegative integer usage counters."""
        if type(value) is int and value >= 0:
            return value
        return None

    async def complete(
        self,
        *,
        profile: str,
        messages: list[dict[str, str]],
        preset: str,
        temperature: float,
        max_tokens: int | None,
    ) -> CompletionResult:
        """Verify and persist the completed inference or final model response."""
        try:
            config = get_model_profile(profile)
        except ModelConfigError as exc:
            raise InferenceFailure(
                str(exc),
                code="model_configuration_error",
                status_code=500,
            ) from exc

        gateway = LlamaGateway(
            base_url=config["base_url"],
            model_id=config["model_id"],
        )

        started = perf_counter()

        try:
            async with httpx.AsyncClient(
                base_url=gateway.base_url,
                timeout=gateway._timeout(),
                transport=gateway.transport,
                trust_env=False,
            ) as client:
                selected = RuntimePreset(preset)
                if selected == RuntimePreset.AUTO:
                    decision = await gateway._select_auto_preset(client, messages)
                    selected = decision.preset

                async def count_tokens(candidate):
                    """Use the existing chat template and tokenizer with selected thinking mode."""
                    return await gateway._count_input_tokens(
                        client,
                        candidate,
                        thinking=get_preset(selected).thinking,
                    )

                messages = await fit_token_budget(
                    messages,
                    preset=selected.value,
                    max_tokens=max_tokens,
                    count_tokens=count_tokens,
                )
            result = await gateway.complete(
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                preset=selected,
            )
        except httpx.TimeoutException as exc:
            raise InferenceFailure(
                "Context preparation timed out.",
                code="llama_gateway_timeout",
                status_code=504,
            ) from exc
        except httpx.ConnectError as exc:
            raise InferenceFailure(
                "Model backend unavailable.",
                code="llama_gateway_unavailable",
                status_code=503,
            ) from exc
        except httpx.HTTPError as exc:
            raise InferenceFailure(
                "Context preparation failed.",
                code="llama_gateway_error",
                status_code=502,
            ) from exc
        except GatewayError as exc:
            raise InferenceFailure(
                str(exc),
                code="llama_gateway_error",
                status_code=exc.status_code,
            ) from exc

        except (ValueError, KeyError, TypeError) as exc:
            raise InferenceFailure(
                "Invalid context backend response.",
                code="invalid_gateway_response",
                status_code=502,
            ) from exc

        logger.info(
            "persistent_inference_completed profile=%s preset=%s",
            profile,
            selected.value,
        )
        elapsed_ms = int((perf_counter() - started) * 1000)

        if not isinstance(result, dict):
            raise InferenceFailure(
                "Gateway returned an invalid response.",
                code="invalid_gateway_response",
            )

        choices = result.get("choices")

        if not isinstance(choices, list) or not choices:
            raise InferenceFailure(
                "Gateway returned no completion choices.",
                code="empty_completion",
            )

        first = choices[0]

        if not isinstance(first, dict):
            raise InferenceFailure(
                "Gateway returned an invalid choice.",
                code="invalid_completion",
            )

        finish_reason = first.get("finish_reason")
        message = first.get("message")

        if not isinstance(message, dict):
            raise InferenceFailure(
                "Gateway returned no assistant message.",
                code="invalid_completion",
            )

        content = message.get("content")

        if (
            finish_reason != "stop"
            or not isinstance(content, str)
            or not content.strip()
        ):
            raise InferenceFailure(
                "Model did not produce a verified final answer.",
                code="incomplete_completion",
            )

        local_meta = result.get("local_assistant")

        if not isinstance(local_meta, dict):
            raise InferenceFailure(
                "Runtime completion metadata is missing.",
                code="missing_runtime_metadata",
            )

        if local_meta.get("status") != "PASS":
            raise InferenceFailure(
                "Completion has not passed runtime verification.",
                code="unverified_completion",
            )

        selected = local_meta.get("preset_selected") or local_meta.get("preset")

        if selected not in {
            "fast",
            "balanced",
            "deep",
            "unlimited",
        }:
            raise InferenceFailure(
                "Gateway returned an invalid selected preset.",
                code="invalid_selected_preset",
            )

        # Explicit presets must not silently switch to another.
        if preset != "auto" and selected != preset:
            raise InferenceFailure(
                "Gateway selected a different runtime preset.",
                code="preset_mismatch",
            )

        usage = result.get("usage") or {}

        if not isinstance(usage, dict):
            usage = {}

        prompt_tokens = self._nonnegative_int(usage.get("prompt_tokens"))
        completion_tokens = self._nonnegative_int(usage.get("completion_tokens"))

        # llama.cpp/OpenAI-compatible reasoning token details
        # are optional and can vary by runtime version.
        output_details = usage.get("completion_tokens_details") or {}

        if not isinstance(output_details, dict):
            output_details = {}

        reasoning_tokens = self._nonnegative_int(output_details.get("reasoning_tokens"))

        # Use the configured model alias rather than blindly
        # trusting a potentially different response model id.
        return CompletionResult(
            content=content,
            model_id=config["model_id"],
            preset_selected=selected,
            finish_reason=finish_reason,
            input_tokens=prompt_tokens,
            output_tokens=completion_tokens,
            reasoning_tokens=reasoning_tokens,
            latency_ms=elapsed_ms,
        )
