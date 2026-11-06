"""Persist source-fenced ingestion admission, bounded leases and scoped publication in short PostgreSQL transactions."""

import hashlib
import json
import logging
from contextlib import asynccontextmanager
from datetime import timedelta
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from sqlalchemy import text

from src.application.services.document_chunks import canonical
from src.application.services.file_storage_policy import StoragePolicyError
from src.application.services.ingestion_contract import (
    validate_source_fence,
    validate_token_counts,
)

logger = logging.getLogger(__name__)
SCOPE = "owner_id=:owner AND namespace_id=:namespace AND file_id=:file AND model_fingerprint=:model"
TERMINAL = frozenset({"failed", "stale", "tombstone"})


def admission_values(plan, counts):
    """Reject malformed internal snapshots with a fixed safe error before database admission."""
    try:
        return _admission_values(plan, counts)
    except (
        ValueError,
        TypeError,
        KeyError,
        AttributeError,
        OverflowError,
        RecursionError,
    ):
        logger.warning("ingestion_plan_snapshot_rejected")
        raise StoragePolicyError("ingestion_plan_invalid", 422) from None


def _admission_values(plan, counts):
    """Validate immutable plan identity and create bounded database values without storing source text."""
    validate_token_counts(plan, counts)
    manifest = json.loads(plan.manifest_json)
    if (
        canonical(manifest) != plan.manifest_json
        or len(plan.manifest_json.encode()) > 16384
    ):
        raise StoragePolicyError("ingestion_plan_invalid", 422)
    if (
        hashlib.sha256(plan.manifest_json.encode()).hexdigest() != plan.generation
        or uuid5(NAMESPACE_URL, "local-assistant:ingestion:" + plan.generation)
        != plan.job_id
    ):
        raise StoragePolicyError("ingestion_plan_invalid", 422)
    source = manifest["source"]
    if (
        source["owner"] != str(plan.owner_id)
        or source["namespace"] != str(plan.namespace_id)
        or source["file"] != str(plan.file_id)
        or source["sha256"] != plan.source_sha256
        or manifest["model_fingerprint"] != plan.model_fingerprint
        or manifest["collection_name"] != plan.collection_name
    ):
        raise StoragePolicyError("ingestion_plan_invalid", 422)
    ids = [point.point_id for point in plan.points]
    if (
        len(ids) > 1000
        or len(set(ids)) != len(ids)
        or any(
            point.point_id != uuid5(plan.job_id, point.chunk_id)
            for point in plan.points
        )
    ):
        raise StoragePolicyError("ingestion_plan_invalid", 422)
    binding = canonical(
        dict(
            manifest=manifest,
            point_ids=[str(value) for value in ids],
            token_counts=counts,
        )
    )
    return dict(
        id=plan.job_id,
        owner=plan.owner_id,
        namespace=plan.namespace_id,
        file=plan.file_id,
        sha=plan.source_sha256,
        model=plan.model_fingerprint,
        collection=plan.collection_name,
        generation=plan.generation,
        manifest=plan.manifest_json,
        fingerprint=hashlib.sha256(binding.encode()).hexdigest(),
        points=ids,
        counts=counts,
    )


class PostgresIngestionJournal:
    """Own namespace-bound durable jobs without embedding, filesystem or vector-service I/O."""

    def __init__(self, sessions, namespace_id):
        """Bind all repository operations to one existing trusted source-storage namespace."""
        if not isinstance(namespace_id, UUID):
            raise ValueError("ingestion_namespace_required")
        self.sessions = sessions
        self.namespace_id = namespace_id

    @asynccontextmanager
    async def _transaction(self):
        """Bound lock/statement/idle waits for each short source and journal mutation transaction."""
        async with self.sessions() as session, session.begin():
            for setting in (
                "lock_timeout='5s'",
                "statement_timeout='15s'",
                "idle_in_transaction_session_timeout='15s'",
            ):
                await session.execute(text("SET LOCAL " + setting))
            yield session

    async def _row(self, session, sql, values):
        """Read at most one bound SQL mapping without retaining or logging private parameters."""
        result = (await session.execute(text(sql), values)).mappings().one_or_none()
        return dict(result) if result is not None else None

    def _values(self, row):
        """Extract only immutable trusted scope parameters from a journal row."""
        return dict(
            owner=row["owner_id"],
            namespace=self.namespace_id,
            file=row["file_id"],
            model=row["model_fingerprint"],
            id=row["id"],
        )

    async def _source(self, session, owner, file_id):
        """Lock the source before jobs/heads using the same owner and namespace at every transition."""
        return await self._row(
            session,
            "SELECT * FROM assistant.files WHERE id=:file AND owner_id=:owner AND policy_snapshot->>'_storage_namespace'=:namespace_text FOR UPDATE",
            dict(file=file_id, owner=owner, namespace_text=str(self.namespace_id)),
        )

    def _source_valid(self, row, source):
        """Compare a locked job's identity against current trusted ready source metadata."""
        return (
            source is not None
            and source["state"] == "ready"
            and source["deleted_at"] is None
            and source["actual_sha256"] == row["source_sha256"]
        )

    async def _job(self, session, owner, job_id, *, lock=False):
        """Require namespace/owner scope on every job read and optional row lock."""
        row = await self._row(
            session,
            "SELECT * FROM assistant.ingestion_jobs WHERE id=:id AND owner_id=:owner AND namespace_id=:namespace"
            + (" FOR UPDATE" if lock else ""),
            dict(id=job_id, owner=owner, namespace=self.namespace_id),
        )
        if row is None:
            raise StoragePolicyError("ingestion_job_not_found", 404)
        return row

    async def _head(self, session, row):
        """Lock the single scoped requested/active generation pointer after its source and job."""
        return await self._row(
            session,
            f"SELECT * FROM assistant.ingestion_heads WHERE {SCOPE} FOR UPDATE",
            self._values(row),
        )

    async def _finish(self, session, row, state, error):
        """Fence unfinished work and persist its terminal cleanup obligation without touching vectors."""
        result = await self._row(
            session,
            "UPDATE assistant.ingestion_jobs SET state=:state,error_code=:error,lease_token=NULL,lease_expires_at=NULL,updated_at=clock_timestamp() WHERE id=:id RETURNING *",
            dict(id=row["id"], state=state, error=error),
        )
        logger.info("ingestion_job_terminal job_id=%s state=%s", row["id"], state)
        return result

    async def admit(self, plan, counts):
        """Serialize bounded durable admission and replay without resurrecting superseded generations."""
        if plan.namespace_id != self.namespace_id:
            raise StoragePolicyError("file_not_found", 404)
        values = admission_values(plan, counts)
        async with self._transaction() as session:
            await session.execute(text("SELECT pg_advisory_xact_lock(734025002)"))
            source = await self._source(session, plan.owner_id, plan.file_id)
            validate_source_fence(plan, source)
            previous = await self._row(
                session,
                "SELECT * FROM assistant.ingestion_jobs WHERE id=:id FOR UPDATE",
                values,
            )
            if previous is not None:
                if (
                    previous["owner_id"] != plan.owner_id
                    or previous["namespace_id"] != self.namespace_id
                    or previous["plan_sha256"] != values["fingerprint"]
                ):
                    raise StoragePolicyError("ingestion_replay_conflict", 409)
                logger.info(
                    "ingestion_admission_replayed job_id=%s state=%s",
                    plan.job_id,
                    previous["state"],
                )
                return previous
            count = (
                await session.execute(
                    text(
                        "SELECT count(*),count(*) FILTER (WHERE owner_id=:owner AND namespace_id=:namespace) FROM assistant.ingestion_jobs WHERE state IN ('pending','running')"
                    ),
                    values,
                )
            ).one()
            if count[0] >= 128 or count[1] >= 32:
                raise StoragePolicyError("ingestion_capacity_exceeded", 429)
            old_head = await self._row(
                session,
                f"SELECT * FROM assistant.ingestion_heads WHERE {SCOPE} FOR UPDATE",
                values,
            )
            values["revision"] = old_head["admission_revision"] + 1 if old_head else 1
            job = await self._row(
                session,
                "INSERT INTO assistant.ingestion_jobs(id,owner_id,namespace_id,file_id,source_sha256,model_fingerprint,collection_name,generation,manifest_json,plan_sha256,point_ids,token_counts,admission_revision) VALUES (:id,:owner,:namespace,:file,:sha,:model,:collection,:generation,:manifest,:fingerprint,CAST(:points AS uuid[]),CAST(:counts AS integer[]),:revision) RETURNING *",
                values,
            )
            await session.execute(
                text(
                    f"UPDATE assistant.ingestion_jobs SET state='stale',error_code='superseded',lease_token=NULL,lease_expires_at=NULL,updated_at=clock_timestamp() WHERE {SCOPE} AND id<>:id AND state IN ('pending','running')"
                ),
                values,
            )
            await session.execute(
                text(
                    "INSERT INTO assistant.ingestion_heads(owner_id,namespace_id,file_id,model_fingerprint,desired_job_id,admission_revision) VALUES (:owner,:namespace,:file,:model,:id,:revision) ON CONFLICT (owner_id,namespace_id,file_id,model_fingerprint) DO UPDATE SET desired_job_id=EXCLUDED.desired_job_id,admission_revision=EXCLUDED.admission_revision,updated_at=clock_timestamp()"
                ),
                values,
            )
        logger.info(
            "ingestion_admitted job_id=%s points=%d", plan.job_id, len(plan.points)
        )
        return job

    async def get(self, owner, job_id):
        """Return only an owner/root-scoped job, including its durable terminal state."""
        async with self.sessions() as session:
            return await self._job(session, owner, job_id)

    async def _locked(self, session, owner, job_id):
        """Discover immutable file identity then lock source before re-reading the job."""
        initial = await self._job(session, owner, job_id)
        source = await self._source(session, owner, initial["file_id"])
        row = await self._job(session, owner, job_id, lock=True)
        return row, source

    async def candidates(self, *, after_id=None, limit=25):
        """Page bounded pending/expired work in one namespace without claiming or exposing foreign jobs."""
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("ingestion_page_invalid")
        async with self.sessions() as session:
            result = await session.execute(
                text(
                    "SELECT id,owner_id FROM assistant.ingestion_jobs WHERE namespace_id=:namespace AND (CAST(:after AS uuid) IS NULL OR id>CAST(:after AS uuid)) AND ((state='pending' AND (next_attempt_at<=clock_timestamp() OR deadline_at<=clock_timestamp())) OR (state='running' AND lease_expires_at<=clock_timestamp())) ORDER BY id LIMIT :limit"
                ),
                dict(namespace=self.namespace_id, after=after_id, limit=limit),
            )
            return [dict(row) for row in result.mappings()]

    async def claim(self, owner, job_id):
        """Claim or recover due work using database time and a fresh attempt token under source locks."""
        token = uuid4()
        async with self._transaction() as session:
            row, source = await self._locked(session, owner, job_id)
            now = await session.scalar(text("SELECT clock_timestamp()"))
            if row["state"] in TERMINAL or row["state"] == "ready":
                return row
            head = await self._head(session, row)
            if not self._source_valid(row, source):
                return await self._finish(session, row, "stale", "source_changed")
            if (
                head["desired_job_id"] != job_id
                or head["admission_revision"] != row["admission_revision"]
            ):
                return await self._finish(session, row, "stale", "superseded")
            if row["state"] == "running" and row["lease_expires_at"] > now:
                raise StoragePolicyError("ingestion_job_busy", 409)
            if row["deadline_at"] <= now or row["attempts"] >= 5:
                return await self._finish(
                    session,
                    row,
                    "failed",
                    "deadline_exceeded"
                    if row["deadline_at"] <= now
                    else "attempts_exhausted",
                )
            if row["next_attempt_at"] > now:
                raise StoragePolicyError("ingestion_retry_not_due", 409)
            result = await self._row(
                session,
                "UPDATE assistant.ingestion_jobs SET state='running',attempts=attempts+1,lease_token=:token,lease_expires_at=LEAST(:now+interval '120 seconds',deadline_at),updated_at=:now,error_code=NULL WHERE id=:id RETURNING *",
                dict(id=job_id, token=token, now=now),
            )
        logger.info(
            "ingestion_job_claimed job_id=%s attempt=%d", job_id, result["attempts"]
        )
        return result

    def _lease(self, row, token, now):
        """Reject expired/replaced tokens before any successful heartbeat, retry or publication."""
        if (
            row["state"] != "running"
            or row["lease_token"] != token
            or row["lease_expires_at"] <= now
            or row["deadline_at"] <= now
        ):
            raise StoragePolicyError("ingestion_lease_lost", 409)

    async def heartbeat(self, owner, job_id, token):
        """Renew only a live attempt without crossing its absolute deadline or changed source."""
        async with self._transaction() as session:
            row, source = await self._locked(session, owner, job_id)
            now = await session.scalar(text("SELECT clock_timestamp()"))
            self._lease(row, token, now)
            if not self._source_valid(row, source):
                return await self._finish(session, row, "stale", "source_changed")
            result = await self._row(
                session,
                "UPDATE assistant.ingestion_jobs SET lease_expires_at=LEAST(:now+interval '120 seconds',deadline_at),updated_at=:now WHERE id=:id RETURNING *",
                dict(id=job_id, now=now),
            )
        logger.info("ingestion_lease_renewed job_id=%s", job_id)
        return result

    async def retry(self, owner, job_id, token):
        """Persist bounded backoff after a trusted worker failure while fencing its completed attempt."""
        async with self._transaction() as session:
            row, source = await self._locked(session, owner, job_id)
            now = await session.scalar(text("SELECT clock_timestamp()"))
            self._lease(row, token, now)
            if not self._source_valid(row, source):
                return await self._finish(session, row, "stale", "source_changed")
            if row["attempts"] >= 5:
                return await self._finish(session, row, "failed", "attempts_exhausted")
            due = min(
                now + timedelta(seconds=min(30, 2 ** row["attempts"])),
                row["deadline_at"],
            )
            result = await self._row(
                session,
                "UPDATE assistant.ingestion_jobs SET state='pending',lease_token=NULL,lease_expires_at=NULL,next_attempt_at=:due,error_code='worker_failed',updated_at=:now WHERE id=:id RETURNING *",
                dict(id=job_id, due=due, now=now),
            )
        logger.info(
            "ingestion_retry_scheduled job_id=%s attempt=%d", job_id, row["attempts"]
        )
        return result

    async def publish(self, owner, job_id, token, acknowledged_ids):
        """Atomically publish only exact complete acknowledgements for the latest ready-source generation."""
        async with self._transaction() as session:
            row, source = await self._locked(session, owner, job_id)
            now = await session.scalar(text("SELECT clock_timestamp()"))
            self._lease(row, token, now)
            if not self._source_valid(row, source):
                return await self._finish(session, row, "stale", "source_changed")
            head = await self._head(session, row)
            if (
                head["desired_job_id"] != job_id
                or head["admission_revision"] != row["admission_revision"]
            ):
                return await self._finish(session, row, "stale", "superseded")
            if (
                not isinstance(acknowledged_ids, list)
                or acknowledged_ids != row["point_ids"]
            ):
                raise StoragePolicyError("ingestion_incomplete_acknowledgement", 409)
            previous = head["active_job_id"]
            if previous is not None and previous != job_id:
                old = await self._job(session, owner, previous, lock=True)
                await self._finish(session, old, "tombstone", "superseded")
            result = await self._row(
                session,
                "UPDATE assistant.ingestion_jobs SET state='ready',lease_token=NULL,lease_expires_at=NULL,published_at=:now,updated_at=:now,error_code=NULL WHERE id=:id RETURNING *",
                dict(id=job_id, now=now),
            )
            await session.execute(
                text(
                    f"UPDATE assistant.ingestion_heads SET active_job_id=:id,updated_at=:now WHERE {SCOPE}"
                ),
                dict(self._values(row), now=now),
            )
        logger.info(
            "ingestion_generation_published job_id=%s points=%d",
            job_id,
            len(acknowledged_ids),
        )
        return result

    async def active(self, owner, file_id, model):
        """Hide stale/deleted/foreign source generations even before asynchronous cleanup reconciles them."""
        async with self.sessions() as session:
            return await self._row(
                session,
                "SELECT j.* FROM assistant.ingestion_heads h JOIN assistant.ingestion_jobs j ON j.id=h.active_job_id JOIN assistant.files f ON f.id=h.file_id AND f.owner_id=h.owner_id WHERE h.owner_id=:owner AND h.namespace_id=:namespace AND h.file_id=:file AND h.model_fingerprint=:model AND j.state='ready' AND f.state='ready' AND f.deleted_at IS NULL AND f.actual_sha256=j.source_sha256 AND f.policy_snapshot->>'_storage_namespace'=:namespace_text",
                dict(
                    owner=owner,
                    namespace=self.namespace_id,
                    namespace_text=str(self.namespace_id),
                    file=file_id,
                    model=model,
                ),
            )

    async def reconciliation_candidates(self, *, after_id=None, limit=25):
        """Discover a bounded page of invalid sources even when their jobs were already published."""
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("ingestion_page_invalid")
        async with self.sessions() as session:
            result = await session.execute(
                text(
                    "SELECT DISTINCT j.file_id,j.owner_id FROM assistant.ingestion_jobs j LEFT JOIN assistant.files f ON f.id=j.file_id AND f.owner_id=j.owner_id WHERE j.namespace_id=:namespace AND j.state IN ('pending','running','ready') AND (CAST(:after AS uuid) IS NULL OR j.file_id>CAST(:after AS uuid)) AND (f.id IS NULL OR f.state<>'ready' OR f.deleted_at IS NOT NULL OR f.actual_sha256<>j.source_sha256 OR f.policy_snapshot->>'_storage_namespace' IS DISTINCT FROM :namespace_text) ORDER BY j.file_id LIMIT :limit"
                ),
                dict(
                    namespace=self.namespace_id,
                    namespace_text=str(self.namespace_id),
                    after=after_id,
                    limit=limit,
                ),
            )
            return [dict(row) for row in result.mappings()]

    async def reconcile_file(self, owner, file_id, *, after_id=None, limit=25):
        """Persist source-invalid cleanup obligations and clear stale pointers without mutating source rows."""
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("ingestion_page_invalid")
        async with self._transaction() as session:
            source = await self._source(session, owner, file_id)
            values = dict(
                owner=owner,
                namespace=self.namespace_id,
                file=file_id,
                after=after_id,
                limit=limit,
            )
            rows = (
                (
                    await session.execute(
                        text(
                            "SELECT * FROM assistant.ingestion_jobs WHERE owner_id=:owner AND namespace_id=:namespace AND file_id=:file AND state IN ('pending','running','ready') AND (CAST(:after AS uuid) IS NULL OR id>CAST(:after AS uuid)) ORDER BY id LIMIT :limit FOR UPDATE"
                        ),
                        values,
                    )
                )
                .mappings()
                .all()
            )
            count = 0
            for row in rows:
                if not self._source_valid(row, source) and row["state"] not in TERMINAL:
                    await self._finish(session, row, "tombstone", "source_deleted")
                    count += 1
            await session.execute(
                text(
                    "UPDATE assistant.ingestion_heads h SET active_job_id=CASE WHEN EXISTS (SELECT 1 FROM assistant.ingestion_jobs j WHERE j.id=h.active_job_id AND j.state<>'ready') THEN NULL ELSE active_job_id END,desired_job_id=CASE WHEN EXISTS (SELECT 1 FROM assistant.ingestion_jobs j WHERE j.id=h.desired_job_id AND j.state IN ('failed','stale','tombstone')) THEN NULL ELSE desired_job_id END,updated_at=clock_timestamp() WHERE h.owner_id=:owner AND h.namespace_id=:namespace AND h.file_id=:file"
                ),
                values,
            )
        logger.info(
            "ingestion_source_reconciled file_id=%s terminal_jobs=%d", file_id, count
        )
        return dict(
            processed=len(rows),
            tombstoned=count,
            next_after=rows[-1]["id"] if len(rows) == limit else None,
        )

    async def cleanup_candidates(self, *, after_id=None, limit=25):
        """Page retained terminal generation cleanup obligations without deleting any point or journal row."""
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("ingestion_page_invalid")
        async with self.sessions() as session:
            rows = await session.execute(
                text(
                    "SELECT id,owner_id FROM assistant.ingestion_jobs WHERE namespace_id=:namespace AND state IN ('failed','stale','tombstone') AND cleanup_done_at IS NULL AND (CAST(:after AS uuid) IS NULL OR id>CAST(:after AS uuid)) ORDER BY id LIMIT :limit"
                ),
                dict(namespace=self.namespace_id, after=after_id, limit=limit),
            )
            return [dict(row) for row in rows.mappings()]

    async def acknowledge_cleanup(self, owner, job_id):
        """Record a trusted exact-generation deletion acknowledgement idempotently for terminal work only."""
        async with self._transaction() as session:
            row, source = await self._locked(session, owner, job_id)
            if row["state"] not in TERMINAL:
                raise StoragePolicyError("ingestion_cleanup_not_terminal", 409)
            result = await self._row(
                session,
                "UPDATE assistant.ingestion_jobs SET cleanup_done_at=COALESCE(cleanup_done_at,clock_timestamp()),updated_at=clock_timestamp() WHERE id=:id RETURNING *",
                dict(id=job_id),
            )
        logger.info("ingestion_cleanup_acknowledged job_id=%s", job_id)
        return result

    async def reject(self, owner, job_id, token, *, source_changed=False):
        """Terminalize only a live owned attempt when reconstruction is permanently invalid."""
        async with self._transaction() as session:
            row, source = await self._locked(session, owner, job_id)
            now = await session.scalar(text("SELECT clock_timestamp()"))
            self._lease(row, token, now)
            return await self._finish(
                session,
                row,
                "stale" if source_changed else "failed",
                "source_changed" if source_changed else "worker_failed",
            )

    async def terminal_candidates(self, model, *, after_id=None, limit=10):
        """Retain repeat cleanup visibility even after an earlier zero-count acknowledgement."""
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("ingestion_page_invalid")
        async with self.sessions() as session:
            rows = await session.execute(
                text(
                    "SELECT id,owner_id FROM assistant.ingestion_jobs WHERE namespace_id=:namespace AND model_fingerprint=:model AND state IN ('failed','stale','tombstone') AND (CAST(:after AS uuid) IS NULL OR id>CAST(:after AS uuid)) ORDER BY id LIMIT :limit"
                ),
                dict(
                    namespace=self.namespace_id,
                    model=model,
                    after=after_id,
                    limit=limit,
                ),
            )
            return [dict(row) for row in rows.mappings()]

    async def defer(self, owner, job_id, token):
        """Release an owned busy-source claim without charging a model attempt or extending its deadline."""
        async with self._transaction() as session:
            row, source = await self._locked(session, owner, job_id)
            now = await session.scalar(text("SELECT clock_timestamp()"))
            self._lease(row, token, now)
            if not self._source_valid(row, source):
                return await self._finish(session, row, "stale", "source_changed")
            result = await self._row(
                session,
                "UPDATE assistant.ingestion_jobs SET state='pending',attempts=attempts-1,lease_token=NULL,lease_expires_at=NULL,next_attempt_at=LEAST(:now+interval '2 seconds',deadline_at),updated_at=:now,error_code=NULL WHERE id=:id RETURNING *",
                dict(id=job_id, now=now),
            )
        logger.info("ingestion_busy_source_deferred job_id=%s", job_id)
        return result
