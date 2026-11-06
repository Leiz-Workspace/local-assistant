"""Hold a bounded namespace/model worker lease through a pinned PostgreSQL session advisory lock."""

import asyncio
import hashlib
import logging

from sqlalchemy import text

from src.application.services.file_storage_policy import StoragePolicyError

logger = logging.getLogger(__name__)


class IngestionWorkerLock:
    """Exclude duplicate local workers without holding a database transaction during model or HTTP work."""

    def __init__(self, engine, namespace, model):
        """Derive a stable domain-separated signed advisory key for this source/model scope."""
        value = hashlib.sha256(
            f"local-assistant-worker-v1:{namespace}:{model}".encode()
        ).digest()
        self.key = int.from_bytes(value[:8], "big", signed=True)
        self.engine = engine
        self.connection = None
        self.backend = None
        self.acquired = False
        self.checking = asyncio.Lock()

    async def open(self):
        """Pin one connection and commit the lock acquisition while retaining session-level ownership."""
        self.connection = await self.engine.connect()
        try:
            result = (
                await self.connection.execute(
                    text("SELECT pg_try_advisory_lock(:key),pg_backend_pid()"),
                    dict(key=self.key),
                )
            ).one()
            self.acquired, self.backend = result
            await self.connection.commit()
            if not self.acquired:
                raise StoragePolicyError("ingestion_worker_already_running", 409)
        except BaseException:
            if not self.acquired:
                await self.connection.invalidate()
            await self.close()
            raise
        logger.info("ingestion_worker_lock_acquired")

    async def check(self):
        """Serialize shared connection checks between admission and the worker heartbeat."""
        async with self.checking:
            task = asyncio.create_task(self._check())
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                while not task.done():
                    try:
                        await asyncio.shield(task)
                    except asyncio.CancelledError:
                        continue
                task.result()
                raise

    async def _check(self):
        """Fail closed if the pinned backend disappeared or the connection was replaced."""
        if not self.acquired or self.connection is None or self.connection.invalidated:
            raise StoragePolicyError("ingestion_worker_lock_lost", 503)
        backend = await self.connection.scalar(text("SELECT pg_backend_pid()"))
        await self.connection.commit()
        if backend != self.backend:
            raise StoragePolicyError("ingestion_worker_lock_lost", 503)

    async def close(self):
        """Release only this session's acquired lock and return its connection even after failures."""
        if self.connection is not None:
            try:
                if self.acquired and not self.connection.invalidated:
                    await self.connection.execute(
                        text("SELECT pg_advisory_unlock(:key)"), dict(key=self.key)
                    )
                    await self.connection.commit()
            except BaseException:
                await self.connection.invalidate()
                raise
            finally:
                await self.connection.close()
                self.connection = None
                self.acquired = False
        logger.info("ingestion_worker_lock_released")
