"""Adapt the approved CORE gateway to the evicted-history summary port (ADR-192)."""

import asyncio

import httpx

from apps.api.services.llama_gateway import GatewayError
from src.application.services.special_literals import require_current_binding
from src.application.services.history_summary import MAX_TOKENS, SummaryUnavailable
from src.infrastructure.inference.core_request_seal import seal_payload

RESPONSE_LIMIT = 262144
FAILURES = (GatewayError, httpx.HTTPError, ValueError, KeyError, TypeError, IndexError)


class GatewaySummarizer:
    """Count and generate through the caller's open client with thinking off, temperature 0 and a JSON schema."""

    def __init__(self, gateway, client, *, deadline, cache=None, clock=None):
        """Bind the verified gateway, its client, the request deadline and an optional owner-bound cache."""
        self.gateway, self.client = gateway, client
        self.deadline = deadline
        self.model_id = gateway.model_id
        self.clock = clock or asyncio.get_running_loop().time
        self.cache = cache

    async def count(self, messages):
        """Count summarizer input with the native template, thinking off."""
        try:
            return await self.gateway._count_input_tokens(
                self.client, messages, thinking=False
            )
        except FAILURES:
            raise SummaryUnavailable("gateway_error") from None

    async def generate(self, messages, schema):
        """Run one non-streaming schema-constrained completion and return content, finish reason and usage."""
        require_current_binding()
        payload = dict(
            model=self.model_id,
            messages=messages,
            temperature=0,
            max_tokens=MAX_TOKENS,
            stream=False,
            chat_template_kwargs={"enable_thinking": False},
            response_format={"type": "json_schema", "json_schema": {"schema": schema}},
        )
        # Sealed outside FAILURES: a refusal must not read as a gateway error.
        # history_summary records pre-seal digests (source_sha256, pair_sha256);
        # its file hash is frozen by the summary v2 campaign, so the label lives here.
        payload, _ = seal_payload(payload, "summarizer")
        try:
            response = await self.client.post("/v1/chat/completions", json=payload)
            response.raise_for_status()
            if len(response.content) > RESPONSE_LIMIT:
                raise SummaryUnavailable("invalid_output")
            data = response.json()
            choice = data["choices"][0]
            return (
                choice["message"]["content"],
                choice.get("finish_reason"),
                data.get("usage") or {},
            )
        except FAILURES:
            raise SummaryUnavailable("gateway_error") from None

    def cache_get(self, key):
        """Read a cached raw output, or None without a cache."""
        return None if self.cache is None else self.cache.get(key)

    def cache_put(self, key, value):
        """Store a successful raw output when a cache is bound."""
        if self.cache is not None:
            self.cache.put(key, value)
