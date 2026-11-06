"""Evaluate fixed request spacing and stop-after-error around an unchanged search port without production wiring or retries."""

import asyncio
import logging
import math
import time

from src.application.services.search_pipeline import validate_query

logger = logging.getLogger(__name__)
MINIMUM_SECONDS = 5.0


class SpacingError(Exception):
    """Report finite evaluation admission and clock failures without request text or provider diagnostics."""

    def __init__(self, code):
        """Retain only fixed evaluator failure codes suitable for metadata-only logging."""
        self.code = (
            code
            if code
            in {"spacing_busy", "spacing_stopped", "spacing_clock", "spacing_options"}
            else "spacing_options"
        )
        super().__init__(self.code)


class SpacedSearchEvaluation:
    """Admit one port call at a time, space actual starts and stop backend dispatch after an error without owning its dependency."""

    def __init__(self, provider, *, clock=time.monotonic, sleep=asyncio.sleep):
        """Bind a trusted port and time seams with empty metadata counters and no I/O or background task."""
        self.provider, self.clock, self.sleep = provider, clock, sleep
        self.busy = self.stopped = False
        self.previous_tick = self.last_started = None
        self.admissions = self.backend_attempts = self.blocked_calls = 0
        self.starts = []
        logger.info("search_spacing_evaluation_initialized minimum_seconds=5")

    def tick(self):
        """Refuse invalid or decreasing monotonic values before any backend dispatch."""
        value = self.clock()
        if (
            type(value) not in {int, float}
            or not math.isfinite(value)
            or value < 0
            or (self.previous_tick is not None and value < self.previous_tick)
        ):
            self.stopped = True
            raise SpacingError("spacing_clock")
        self.previous_tick = value
        return value

    async def search(self, *, query, max_results):
        """Wait inside the caller's existing timeout, delegate once and never replay a failed or cancelled backend attempt."""
        validate_query(query)
        if type(max_results) is not int or max_results != 5:
            raise SpacingError("spacing_options")
        if self.stopped:
            self.blocked_calls += 1
            logger.info("search_spacing_backend_dispatch_blocked")
            raise SpacingError("spacing_stopped")
        if self.busy:
            raise SpacingError("spacing_busy")
        self.busy = True
        self.admissions += 1
        dispatched = False
        try:
            now = self.tick()
            if self.last_started is not None:
                remaining = max(0.0, self.last_started + MINIMUM_SECONDS - now)
                if remaining:
                    logger.info("search_spacing_wait_started")
                    await self.sleep(remaining)
                now = self.tick()
                if now < self.last_started + MINIMUM_SECONDS:
                    self.stopped = True
                    raise SpacingError("spacing_clock")
            if asyncio.current_task().cancelling():
                raise asyncio.CancelledError()
            self.last_started = now
            self.starts.append(now)
            self.backend_attempts += 1
            dispatched = True
            logger.info(
                "search_spacing_backend_started ordinal=%d", self.backend_attempts
            )
            result = await self.provider.search(query=query, max_results=max_results)
            if asyncio.current_task().cancelling():
                raise asyncio.CancelledError()
            return result
        except BaseException:
            if dispatched:
                self.stopped = True
                logger.info("search_spacing_backend_failed_dispatch_stopped")
            raise
        finally:
            self.busy = False
            logger.info("search_spacing_port_call_closed")
