"""Offer an explicit same-CORE coding mode with bounded native reasoning and structural JSON, preserving first replies and existing approval boundaries."""

import json
import logging

import httpx

from apps.api.services.llama_gateway import LlamaGateway
from src.application.ports.inference import CompletionResult, InferenceFailure
from src.application.services.coding_workflow import SYSTEM, resolve_candidate
from src.infrastructure.inference.reasoning_profile import ReasoningProfileAdapter
from src.infrastructure.inference.structured_profile import StructuredProfileError

logger = logging.getLogger(__name__)
MODE = "coding_reasoning_v1"
CONTRACT = " Preserve the exact existing imports, logger binding, public function signatures and initial audit calls. Derive edge behavior from the supplied issue and selected tests. Check the proposed logic against that specification before returning; add no helpers, imports or default arguments."
SCHEMA = dict(
    type="object",
    properties=dict(
        plan=dict(type="array", items=dict(type="string", maxLength=512), maxItems=5),
        replacement=dict(type="string", maxLength=4096),
    ),
    required=["plan", "replacement"],
    additionalProperties=False,
)


class CodingRequest(ReasoningProfileAdapter):
    """Reuse spent-request, native identity, exact-content and joined HTTP ownership for one trusted utility-repair message snapshot."""

    def __init__(self, messages, *, endpoint=None, transport=None):
        """Snapshot only the established two-message coding contract and reject caller-added roles or oversized inputs."""
        if (
            type(messages) is not list
            or len(messages) != 2
            or any(
                type(row) is not dict
                or set(row) != {"role", "content"}
                or type(row["content"]) is not str
                for row in messages
            )
            or messages[0] != dict(role="system", content=SYSTEM)
            or messages[1]["role"] != "user"
            or not messages[1]["content"].strip()
            or sum(len(row["content"].encode()) for row in messages) > 32768
        ):
            raise StructuredProfileError("input")
        self.messages = json.loads(json.dumps(messages))
        self.messages[0]["content"] += CONTRACT
        super().__init__(
            profile="core",
            schema=SCHEMA,
            endpoint=endpoint,
            transport=transport,
            timeout=55,
        )
        logger.info("coding_reasoning_request_bound mode=%s", MODE)

    def payload(self, text, images, stream):
        """Keep the complete original source-only conversation and structural shape without answer enums or hidden-test data."""
        if text != self.messages[1]["content"] or images or stream:
            raise StructuredProfileError("input")
        value = super().payload(text, images, stream)
        value["messages"] = json.loads(json.dumps(self.messages))
        return value


class CodingReasoningAdapter:
    """Implement only the named coding mode; never impersonate fast, select a model or activate an API route."""

    def __init__(self, *, endpoint=None, transport=None):
        """Bind trusted native test seams without network activity, configuration writes or model loading."""
        self.endpoint, self.transport = endpoint, transport
        self.last_attempt = None
        logger.info("coding_reasoning_adapter_initialized mode=%s", MODE)

    async def complete(self, *, profile, messages, preset, temperature, max_tokens):
        """Count the exact thinking prompt, make one native request and preserve its original complete JSON without repair or retry."""
        if (
            profile != "core"
            or preset != MODE
            or type(temperature) not in (int, float)
            or temperature != 0
            or type(max_tokens) is not int
            or max_tokens != 2048
        ):
            raise InferenceFailure(
                "Unsupported coding mode.", code="coding_reasoning_scope"
            )
        try:
            attempt = CodingRequest(
                messages, endpoint=self.endpoint, transport=self.transport
            )
            self.last_attempt = attempt
            gateway = LlamaGateway(
                attempt.endpoint, attempt.model, transport=self.transport
            )
            async with httpx.AsyncClient(
                base_url=attempt.endpoint,
                transport=self.transport,
                trust_env=False,
                timeout=10,
            ) as client:
                count = await gateway._count_input_tokens(
                    client, attempt.messages, thinking=True
                )
            if count + 1024 + 256 > 32768:
                raise StructuredProfileError("input")
            result = await attempt.complete(attempt.messages[1]["content"])
            resolve_candidate(result.content)
        except (
            StructuredProfileError,
            httpx.HTTPError,
            ValueError,
            KeyError,
            TypeError,
        ) as exc:
            logger.warning("coding_reasoning_failed kind=%s", type(exc).__name__)
            raise InferenceFailure(
                "Coding reasoning request rejected.", code="coding_reasoning_failed"
            ) from None
        logger.info(
            "coding_reasoning_completed input_tokens=%d output_tokens=%d",
            result.input_tokens,
            result.output_tokens,
        )
        return CompletionResult(
            result.content,
            result.model_id,
            MODE,
            "stop",
            result.input_tokens,
            result.output_tokens,
            latency_ms=int(result.wall_seconds * 1000),
        )
