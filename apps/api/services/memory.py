"""Own default-off memory management SQL operations and join them before application resource shutdown."""

import asyncio
import logging

from apps.api.services.files import finish_task
from apps.api.services.memory_work import joined_memory_work
from src.application.services.memory_contract import MemoryPolicyError

logger = logging.getLogger(__name__)
ACTIONS = frozenset(
    {
        "settings",
        "export",
        "configure",
        "grant",
        "revoke",
        "create_manual",
        "inspect",
        "list",
        "edit_manual",
        "delete",
    }
)


class MemoryService:
    """Expose only declared owner management operations without model inference, automatic learning or prompt use."""

    def __init__(self, journal, *, extractor=None, retention=None):
        """Bind the existing app repository without allocating a new pool, credential or worker."""
        self.journal = journal
        self.operations = set()
        self.closing = False
        self.extractor = extractor
        self.retention = retention

    async def run(self, owner, action, *args, **kwargs):
        """Track a single awaited SQL operation and release tracking only after commit/rollback cleanup."""
        if self.closing:
            raise MemoryPolicyError("memory_unavailable")
        if action not in ACTIONS:
            raise MemoryPolicyError("memory_action_invalid")
        task = asyncio.current_task()
        self.operations.add(task)
        try:
            if self.closing:
                raise MemoryPolicyError("memory_unavailable")
            result = await joined_memory_work(
                getattr(self.journal, action)(owner, *args, **kwargs)
            )
            if self.extractor is not None and action in {"configure", "revoke"}:
                await self.extractor.cancel_owner(
                    owner, args[0] if action == "revoke" else None
                )
            logger.info("memory_management_completed action=%s", action)
            return result
        finally:
            self.operations.discard(task)
            logger.info("memory_management_operation_closed")

    async def shutdown(self):
        """Stop admission and join cancelled management transactions before shared resources close."""
        self.closing = True
        if self.extractor is not None:
            await self.extractor.shutdown()
        if self.retention is not None:
            await self.retention.shutdown()
        tasks = list(self.operations)
        for task in tasks:
            task.cancel()
        for task in tasks:
            try:
                await finish_task(task)
            except BaseException:
                logger.info("memory_management_task_joined")
        logger.info("memory_management_shutdown_complete")
