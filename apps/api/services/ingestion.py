"""Coordinate trusted source-held ingestion, journal leases and repeat terminal-generation cleanup."""

import asyncio
import json
import logging

from sqlalchemy import text

from apps.api.services.chunks import chunk_operation
from apps.api.services.files import file_io, finish_task
from src.application.services.file_storage_policy import StoragePolicyError
from src.application.services.ingestion_contract import IngestionPlan, plan_ingestion
from src.infrastructure.ingestion_worker_lock import IngestionWorkerLock
from src.infrastructure.qwen_embedding import QwenEmbedding
from src.infrastructure.qwen_token_preflight import preflight_plan
from src.infrastructure.repositories.ingestion_journal import (
    PostgresIngestionJournal,
    admission_values,
)

logger = logging.getLogger(__name__)


class IngestionService:
    """Own one explicit namespace/model worker and its joined source/model/network lifetimes."""

    def __init__(
        self, files, selection, vectors, *, encoder=None, interval=2, heartbeat=20
    ):
        """Reuse trusted file resources and bounded existing database pool without automatic startup."""
        self.files = files
        self.selection = selection
        self.vectors = vectors
        self.encoder = encoder or QwenEmbedding()
        self.model = selection["collection"]["model_fingerprint"]
        self.journal = PostgresIngestionJournal(
            files.journal.sessions, files.storage.namespace_id
        )
        self.guard = IngestionWorkerLock(
            files.journal.sessions.kw["bind"], files.storage.namespace_id, self.model
        )
        self.interval = interval
        self.heartbeat_interval = heartbeat
        self.closing = False
        self.task = None
        self.admissions = set()
        self.job_cursor = self.cleanup_cursor = self.source_cursor = None

    async def start(self, *, background=True):
        """Validate schema/grants, acquire single-worker scope and prepare only the owned vector schema."""
        async with self.journal.sessions() as session:
            row = (
                await session.execute(
                    text(
                        "SELECT (SELECT version_num FROM assistant.alembic_version),has_column_privilege(current_user,'assistant.ingestion_jobs','manifest_json','UPDATE'),has_column_privilege(current_user,'assistant.ingestion_jobs','state','UPDATE')"
                    )
                )
            ).one()
            if row[0] not in {"0004", "0005"} or tuple(row)[1:] != (False, True):
                raise StoragePolicyError("ingestion_schema_unavailable", 503)
        try:
            await self.guard.open()
            await self.vectors.ensure()
            if background:
                self.task = asyncio.create_task(self.run())
        except BaseException:
            await self.guard.close()
            raise
        logger.info("ingestion_worker_started background=%s", background)

    async def admit(self, owner, file_id, *, max_bytes=256):
        """Extract only trusted auto sources and persist an immutable job after actual complete token counts."""
        if self.closing:
            raise StoragePolicyError("ingestion_unavailable", 503)
        task = asyncio.current_task()
        self.admissions.add(task)
        try:
            await self.guard.check()
            if self.closing:
                raise StoragePolicyError("ingestion_unavailable", 503)
            async with chunk_operation(
                self.files, owner, file_id, max_bytes=max_bytes
            ) as (row, view):
                plan = plan_ingestion(
                    row, owner, self.files.storage.namespace_id, view, self.selection
                )
                counts = await file_io(preflight_plan, plan)
                job = await self.journal.admit(plan, list(counts))
            logger.info("ingestion_source_admitted job_id=%s", job["id"])
            return job
        finally:
            self.admissions.discard(task)

    async def _heartbeat(self, owner, job_id, token, work):
        """Interrupt joined work if its namespace lock/source/attempt stops being valid."""
        try:
            while True:
                await asyncio.sleep(self.heartbeat_interval)
                await self.guard.check()
                row = await self.journal.heartbeat(owner, job_id, token)
                if row["state"] != "running":
                    raise StoragePolicyError("ingestion_lease_lost", 409)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.warning("ingestion_heartbeat_fenced job_id=%s", job_id)
            work.cancel()

    async def _write(self, plan, job):
        """Recheck exact model/counts then verify staged/active points before final atomic SQL publication."""
        batch = await self.encoder.encode(plan)
        values = admission_values(plan, list(batch.counts))
        if values["fingerprint"] != job["plan_sha256"]:
            raise StoragePolicyError("ingestion_reconstruction_changed", 409)
        live = await self.journal.heartbeat(
            job["owner_id"], job["id"], job["lease_token"]
        )
        if live["state"] != "running":
            raise StoragePolicyError("ingestion_source_changed", 409)
        await self.vectors.upsert(plan, batch)
        live = await self.journal.heartbeat(
            job["owner_id"], job["id"], job["lease_token"]
        )
        if live["state"] != "running":
            raise StoragePolicyError("ingestion_source_changed", 409)
        ids = await self.vectors.activate(plan, batch)
        return await self.journal.publish(
            job["owner_id"], job["id"], job["lease_token"], ids
        )

    async def process(self, owner, job_id):
        """Reconstruct a claimed source under its retained reader and fence/record every failure path."""
        job = await self.journal.get(owner, job_id)
        if job["model_fingerprint"] != self.model:
            return job
        job = await self.journal.claim(owner, job_id)
        if job["state"] != "running":
            return job
        work, heartbeat = None, None
        try:
            options = json.loads(job["manifest_json"])["source"]
            async with chunk_operation(
                self.files, owner, job["file_id"], max_bytes=options["max_bytes"]
            ) as (row, view):
                plan = plan_ingestion(
                    row, owner, self.files.storage.namespace_id, view, self.selection
                )
                if plan.job_id != job_id or plan.manifest_json != job["manifest_json"]:
                    raise StoragePolicyError("ingestion_reconstruction_changed", 409)
                work = asyncio.create_task(self._write(plan, job))
                heartbeat = asyncio.create_task(
                    self._heartbeat(owner, job_id, job["lease_token"], work)
                )
                try:
                    result = await asyncio.shield(work)
                except BaseException:
                    work.cancel()
                    try:
                        await finish_task(work)
                    except BaseException:
                        logger.warning("ingestion_owned_work_joined job_id=%s", job_id)
                    raise
                finally:
                    heartbeat.cancel()
                    try:
                        await finish_task(heartbeat)
                    except asyncio.CancelledError:
                        pass
            logger.info(
                "ingestion_job_processed job_id=%s state=%s", job_id, result["state"]
            )
            return result
        except BaseException as error:
            if (
                isinstance(error, asyncio.CancelledError)
                and not asyncio.current_task().cancelling()
            ):
                error = StoragePolicyError("ingestion_lease_lost", 409)
            try:
                current = await self.journal.get(owner, job_id)
                if current["state"] == "running":
                    if (
                        isinstance(error, StoragePolicyError)
                        and error.status_code == 429
                    ):
                        await self.journal.defer(owner, job_id, job["lease_token"])
                    elif isinstance(error, StoragePolicyError) and error.code in {
                        "ingestion_reconstruction_changed",
                        "ingestion_source_changed",
                        "file_not_found",
                        "file_not_ready",
                    }:
                        await self.journal.reject(
                            owner, job_id, job["lease_token"], source_changed=True
                        )
                    else:
                        await self.journal.retry(owner, job_id, job["lease_token"])
            except Exception:
                logger.warning("ingestion_attempt_fence_retained job_id=%s", job_id)
            if isinstance(error, asyncio.CancelledError):
                raise
            logger.warning("ingestion_job_failed_safely job_id=%s", job_id)
            return await self.journal.get(owner, job_id)

    def cleanup_plan(self, row):
        """Build a deletion-only generation scope from immutable journal metadata without source text."""
        return IngestionPlan(
            row["id"],
            row["owner_id"],
            row["namespace_id"],
            row["file_id"],
            row["source_sha256"],
            row["model_fingerprint"],
            row["collection_name"],
            row["generation"],
            row["manifest_json"],
            (),
        )

    async def sweep(self):
        """Discover invalid sources and repeat exact terminal deletions including earlier acknowledgements."""
        for item in await self.journal.reconciliation_candidates(
            after_id=self.source_cursor, limit=10
        ):
            self.source_cursor = item["file_id"]
            cursor = None
            while True:
                page = await self.journal.reconcile_file(
                    item["owner_id"], item["file_id"], after_id=cursor, limit=25
                )
                cursor = page["next_after"]
                if cursor is None:
                    break
        self.source_cursor = None
        rows = await self.journal.terminal_candidates(
            self.model, after_id=self.cleanup_cursor, limit=10
        )
        if not rows:
            self.cleanup_cursor = None
        for item in rows:
            self.cleanup_cursor = item["id"]
            row = await self.journal.get(item["owner_id"], item["id"])
            await self.vectors.delete(self.cleanup_plan(row))
            if row["cleanup_done_at"] is None:
                await self.journal.acknowledge_cleanup(item["owner_id"], item["id"])
        logger.info("ingestion_terminal_sweep_completed generations=%d", len(rows))

    async def tick(self):
        """Run one bounded reconciliation and due-job page under the live namespace worker guard."""
        await self.guard.check()
        await self.sweep()
        rows = await self.journal.candidates(after_id=self.job_cursor, limit=10)
        if not rows:
            self.job_cursor = None
        for item in rows:
            self.job_cursor = item["id"]
            try:
                await self.process(item["owner_id"], item["id"])
            except StoragePolicyError:
                logger.warning("ingestion_due_job_fenced")

    async def run(self):
        """Poll bounded work until shutdown, retaining durable retries after transient service errors."""
        while not self.closing:
            try:
                await self.tick()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.warning("ingestion_worker_cycle_failed")
            await asyncio.sleep(self.interval)

    async def shutdown(self):
        """Stop admissions and join model/source work before releasing vector and namespace resources."""
        self.closing = True
        for admission in list(self.admissions):
            admission.cancel()
        for admission in list(self.admissions):
            try:
                await finish_task(admission)
            except BaseException:
                logger.warning("ingestion_admission_joined")
        if self.task is not None:
            self.task.cancel()
            try:
                await finish_task(self.task)
            except asyncio.CancelledError:
                pass
        try:
            await self.vectors.close()
        finally:
            await self.guard.close()
        logger.info("ingestion_worker_shutdown_complete")
