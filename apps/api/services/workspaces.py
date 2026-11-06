"""Own nonqueued bounded workspace snapshots and join cancelled file work through response delivery."""

import asyncio
import logging
import threading
from contextlib import asynccontextmanager

from apps.api.services.files import file_io, finish_task
from src.application.services.workspace_policy import WorkspaceAccessError
from src.infrastructure.workspace_reader import build_snapshot

logger = logging.getLogger(__name__)


async def joined_work(stop, function, *arguments, close_result=False):
    """Signal cooperative cancellation immediately and join the owned thread before exposing descriptor cleanup."""
    task = asyncio.create_task(file_io(function, *arguments, close_result=close_result))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        stop.set()
        task.cancel()
        try:
            result = await finish_task(task)
            if close_result and result is not None:
                await file_io(result.close)
        except BaseException:
            logger.info("workspace_cancelled_thread_joined")
        raise


class WorkspaceService:
    """Retain one explicitly configured catalog and one source snapshot until joined HTTP completion."""

    def __init__(self, catalog):
        """Initialize bounded nonqueued admission without opening roots or running repository tools."""
        self.catalog = catalog
        self.admission = asyncio.Lock()
        self.operations = set()
        self.closing = False

    @asynccontextmanager
    async def operation(self, owner, identifier, name, parameters):
        """Own authorization, cancellation event, retained root and delivery lifetime for one read-only operation."""
        if self.closing:
            raise WorkspaceAccessError("workspace_unavailable", 503)
        if self.admission.locked():
            raise WorkspaceAccessError("workspace_busy", 429)
        await self.admission.acquire()
        task = asyncio.current_task()
        self.operations.add(task)
        snapshot = None
        stop = threading.Event()
        try:
            snapshot = await joined_work(
                stop,
                build_snapshot,
                self.catalog,
                owner,
                identifier,
                name,
                parameters,
                stop,
                close_result=True,
            )
            yield snapshot
        finally:
            stop.set()
            try:
                if snapshot is not None:
                    await file_io(snapshot.close)
            finally:
                self.operations.discard(task)
                self.admission.release()
                logger.info("workspace_operation_closed operation=%s", name)

    async def validate(self, snapshot):
        """Join the final root/inode/hash/deadline fence before response headers."""
        await joined_work(snapshot.stop, snapshot.validate)

    async def shutdown(self):
        """Reject new requests and cancel/join every owned operation before resource teardown."""
        self.closing = True
        tasks = [task for task in self.operations if task is not asyncio.current_task()]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        logger.info("workspace_shutdown_complete")
