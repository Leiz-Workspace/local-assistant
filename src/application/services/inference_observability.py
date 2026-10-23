"""Observe bounded aggregate inference counters and honest timing availability without retaining prompts, replies, credentials or exception text."""

import asyncio
import logging
import math
import time
from threading import Lock
from uuid import uuid4

from src.application.ports.inference import CompletionResult, InferenceFailure

logger = logging.getLogger(__name__)


class InferenceObservability:
    """Wrap an existing inference port with fixed-profile aggregate metrics and finite content-free completion traces."""

    def __init__(self, inference, *, clock=time.perf_counter):
        """Bind a trusted monotonic clock and existing port without changing model, request policy or resource ownership."""
        self.inference, self.clock = inference, clock
        self.lock = Lock()
        self.metrics = {
            profile: dict(
                started=0,
                completed=0,
                failed=0,
                cancelled=0,
                active=0,
                peak_active=0,
                latency_samples=0,
                latency_ms_total=0.0,
                input_tokens=0,
                output_tokens=0,
                usage_samples=0,
                timing_unavailable=0,
            )
            for profile in ("core", "unrestricted")
        }
        logger.info("inference_observability_initialized")

    def sample(self):
        """Read only a finite nonnegative host timing point without treating an invalid clock as zero latency."""
        try:
            value = self.clock()
            return (
                value
                if type(value) in (int, float) and math.isfinite(value) and value >= 0
                else None
            )
        except Exception:
            return None

    def snapshot(self):
        """Return fresh operator-only aggregate counters with explicit unavailable nonstreaming TTFT/decode measurements."""
        with self.lock:
            return dict(
                description="Operator-only aggregate nonstreaming inference metrics; no request/user/model content.",
                profiles={name: dict(values) for name, values in self.metrics.items()},
                ttft_ms=None,
                decode_tokens_per_second=None,
                timing_availability="nonstreaming_no_token_timestamps",
            )

    async def complete(self, **request):
        """Delegate unchanged and record finite complete/error/cancellation outcomes without storing request or result bodies."""
        profile = request.get("profile")
        if type(profile) is not str or profile not in self.metrics:
            raise InferenceFailure(
                "Invalid profile.", code="invalid_profile", status_code=422
            )
        trace = uuid4()
        started = self.sample()
        with self.lock:
            counters = self.metrics[profile]
            counters["started"] += 1
            counters["active"] += 1
            counters["peak_active"] = max(counters["peak_active"], counters["active"])
        outcome, result = "failed", None
        try:
            result = await self.inference.complete(**request)
            if (
                type(result) is not CompletionResult
                or result.finish_reason != "stop"
                or type(result.content) is not str
                or not result.content.strip()
                or type(result.model_id) is not str
                or not result.model_id
                or any(
                    v is not None and (type(v) is not int or v < 0)
                    for v in (
                        result.input_tokens,
                        result.output_tokens,
                        result.reasoning_tokens,
                        result.latency_ms,
                    )
                )
            ):
                raise InferenceFailure("Invalid completion.", code="invalid_completion")
            if asyncio.current_task().cancelling():
                raise asyncio.CancelledError()
            outcome = "completed"
            return result
        except asyncio.CancelledError:
            outcome = "cancelled"
            raise
        finally:
            finished = self.sample()
            elapsed = (
                (finished - started) * 1000
                if started is not None and finished is not None and finished >= started
                else None
            )
            with self.lock:
                if elapsed is not None and (
                    not math.isfinite(elapsed)
                    or not math.isfinite(counters["latency_ms_total"] + elapsed)
                ):
                    elapsed = None
                counters["active"] -= 1
                counters[outcome] += 1
                if elapsed is None:
                    counters["timing_unavailable"] += 1
                else:
                    counters["latency_samples"] += 1
                    counters["latency_ms_total"] += elapsed
                if (
                    outcome == "completed"
                    and result.input_tokens is not None
                    and result.output_tokens is not None
                ):
                    counters["usage_samples"] += 1
                    counters["input_tokens"] += result.input_tokens
                    counters["output_tokens"] += result.output_tokens
            logger.info(
                "inference_trace trace_id=%s profile=%s outcome=%s elapsed_ms=%s",
                trace,
                profile,
                outcome,
                elapsed,
            )
