"""Run bounded periodic expiry/orphan cleanup on the existing memory pool without model or source writes."""

import asyncio
import logging

from apps.api.services.files import finish_task
from apps.api.services.memory_work import joined_memory_work

logger = logging.getLogger(__name__)


class MemoryRetention:
    """Rotate bounded owner pages and purge only expired records or orphan inactive receipts."""

    def __init__(self, journal, *, interval=30):
        """Bind existing storage and a bounded maintenance interval without starting any automatic extraction."""
        if type(interval) not in (int, float) or not 0 < interval <= 30:
            raise ValueError("memory_retention_interval_invalid")
        self.journal = journal
        self.interval = interval
        self.cursor = None
        self.task = None
        self.closing = False

    def start(self):
        """Start exactly one owned periodic task after enabled startup schema/grant validation."""
        if self.task is not None or self.closing:
            raise RuntimeError("Memory retention already started or closed")
        self.task = asyncio.create_task(self.run())
        logger.info("memory_retention_started")

    async def tick(self):
        """Process at most ten owners and one hundred record/receipt candidates per owner without source content."""
        owners = await joined_memory_work(
            self.journal.retention_owners(self.cursor, limit=10)
        )
        total = dict(records=0, receipts=0)
        for owner in owners:
            result = await joined_memory_work(
                self.journal.purge_owner(owner, limit=100)
            )
            total["records"] += result["records"]
            total["receipts"] += result["receipts"]
        self.cursor = owners[-1] if owners else None
        logger.info(
            "memory_retention_cycle owners=%d records=%d receipts=%d",
            len(owners),
            total["records"],
            total["receipts"],
        )
        return total

    async def run(self):
        """Continue safe bounded cleanup cycles and retry operational failures without retaining private diagnostics."""
        while not self.closing:
            try:
                await self.tick()
            except Exception as error:
                logger.warning(
                    "memory_retention_cycle_failed type=%s", type(error).__name__
                )
            await asyncio.sleep(self.interval)

    async def shutdown(self):
        """Stop scheduling and join the current database operation before the application pool is closed."""
        self.closing = True
        if self.task is not None:
            self.task.cancel()
            try:
                await finish_task(self.task)
            except BaseException:
                logger.info("memory_retention_task_joined")
        logger.info("memory_retention_shutdown_complete")
