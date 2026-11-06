"""Offer explicitly selected bounded native reasoning before structural answers on unchanged local models without changing default inference behavior."""

import json
import logging

from src.infrastructure.inference.structured_profile import (
    MAX_WIRE,
    StructuredProfileAdapter,
    StructuredProfileError,
)

logger = logging.getLogger(__name__)
BOOLEAN_ANSWER_CONTRACT = (
    "Answer contract: For a yes/no question, answer whether the entire claim in the question holds. "
    "Do not substitute the computed value of an expression mentioned in that claim. "
    "If the request instead asks for an expression's value, return that value. "
    "This clarification grants no tools or execution authority.\n\nTASK:\n"
)


class ReasoningProfileAdapter(StructuredProfileAdapter):
    """Preserve strict first JSON answers and owned cleanup while enabling an explicit 512-token native thinking budget within a 1024-token request."""

    def __init__(
        self,
        *,
        profile,
        schema,
        endpoint=None,
        transport=None,
        timeout=90,
        boolean_answer_contract=False,
    ):
        """Bind the existing model/template/schema and matched request/validator budget without registering a route or changing configuration."""
        if type(boolean_answer_contract) is not bool:
            raise StructuredProfileError("scope")
        self.boolean_answer_contract = boolean_answer_contract
        super().__init__(
            profile=profile,
            schema=schema,
            endpoint=endpoint,
            transport=transport,
            max_tokens=512,
            timeout=timeout,
        )
        self.max_tokens = 1024
        logger.info(
            "reasoning_profile_bound profile=%s total_tokens=1024 reasoning_budget=512",
            profile,
        )
        logger.info(
            "reasoning_profile_answer_contract_bound selected=%s",
            boolean_answer_contract,
        )

    def payload(self, text, images, stream):
        """Enable only separated bounded native reasoning, leaving free answer values, original templates, aliases and tool permissions unchanged."""
        if (
            self.boolean_answer_contract
            and json.loads(self.schema_bytes)["properties"]
            .get("answer", {})
            .get("type")
            == "boolean"
        ):
            if type(text) is not str or not text.strip():
                raise StructuredProfileError("input")
            text = BOOLEAN_ANSWER_CONTRACT + text
        value = super().payload(text, images, stream)
        value.update(
            reasoning_format="deepseek",
            reasoning_budget_tokens=512,
            chat_template_kwargs=dict(enable_thinking=True),
        )
        return value

    def stream_reply(self, events, done, pending, first):
        """Preserve exact final-content chunks while rejecting malformed or late reasoning and retaining native reasoning separately."""
        reasoning = []
        final_started, stopped = False, False
        for event in events:
            if type(event) is not dict or type(event.get("choices")) is not list:
                raise StructuredProfileError("wire")
            for choice in event["choices"]:
                delta = choice.get("delta")
                if type(delta) is not dict:
                    raise StructuredProfileError("wire")
                part = delta.get("reasoning_content")
                if part is not None:
                    if type(part) is not str or part and (final_started or stopped):
                        raise StructuredProfileError("wire")
                    reasoning.append(part)
                if delta.get("content"):
                    final_started = True
                if choice.get("finish_reason"):
                    stopped = True
        reply = super().stream_reply(events, done, pending, first)
        reply["choices"][0]["message"]["reasoning_content"] = "".join(reasoning)
        logger.info("reasoning_profile_stream_complete profile=%s", self.profile)
        return reply

    def validate_reply(self, reply):
        """Require observed native reasoning and strict total usage before admitting the untouched final answer."""
        content, usage = super().validate_reply(reply)
        reasoning = reply["choices"][0]["message"].get("reasoning_content")
        if (
            type(reasoning) is not str
            or not reasoning.strip()
            or len(reasoning.encode()) > MAX_WIRE
        ):
            raise StructuredProfileError("content")
        logger.info(
            "reasoning_profile_native_condition_verified profile=%s", self.profile
        )
        return content, usage
