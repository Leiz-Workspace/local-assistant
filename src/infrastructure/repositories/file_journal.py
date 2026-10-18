"""Persist owner-scoped file leases and exactly-once allocations in short PostgreSQL transactions.

Filesystem operations belong to the service outside these transactions. In
particular, claim requires a resource guard already held by the caller; release
requires successful physical purge under that guard's protocol from ADR-020.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict
from uuid import UUID

from sqlalchemy import text

from src.application.services.file_storage_policy import (
    DEFAULT_POLICY,
    FileReservationPlan,
    StoragePolicy,
    StoragePolicyError,
    UsageSnapshot,
    check_capacity,
    plan_reservation,
    validate_detected_media,
)

logger = logging.getLogger(__name__)
VISIBLE = "state IN ('reserved','receiving','verifying','ready') AND deleted_at IS NULL"
TERMINAL = frozenset({"deleted", "rejected", "interrupted"})
SAFE_ERRORS = frozenset(
    {
        "upload_interrupted",
        "upload_timeout",
        "file_size_mismatch",
        "file_hash_mismatch",
        "file_type_mismatch",
        "invalid_file_content",
        "archive_limits_exceeded",
        "insufficient_disk_space",
        "storage_unavailable",
        "verification_failed",
    }
)


def usage(row) -> UsageSnapshot:
    """Translate a locked database counter row into the executable policy contract."""
    return UsageSnapshot(
        *(
            row[name]
            for name in ("allocated_bytes", "allocated_files", "active_uploads")
        )
    )


def policy_from_snapshot(snapshot) -> StoragePolicy:
    """Separate immutable storage context from validated reservation policy limits."""
    values = dict(snapshot)
    namespace = values.pop("_storage_namespace", None)
    if namespace is not None and (
        not isinstance(namespace, str) or str(UUID(namespace)) != namespace
    ):
        raise ValueError("Invalid storage namespace snapshot")
    return StoragePolicy(**values)


class PostgresFileJournal:
    """Own atomic file admission, fencing and counter release without payload I/O."""

    def __init__(
        self,
        session_factory,
        policy: StoragePolicy = DEFAULT_POLICY,
        *,
        namespace_id: UUID | None = None,
    ):
        """Reuse the existing bounded application pool and versioned admission policy."""
        self.sessions = session_factory
        self.policy = policy
        if namespace_id is not None and not isinstance(namespace_id, UUID):
            raise ValueError("Invalid storage namespace")
        self.namespace_id = namespace_id

    def _belongs(self, row) -> bool:
        """Bind runtime operations to their root while preserving trusted unscoped maintenance."""
        return self.namespace_id is None or row["policy_snapshot"].get(
            "_storage_namespace"
        ) == str(self.namespace_id)

    @property
    def _namespace_filter(self) -> str:
        """Return only static SQL for an optional internal storage-namespace scope."""
        return (
            " AND policy_snapshot->>'_storage_namespace'=:namespace"
            if self.namespace_id is not None
            else ""
        )

    async def _lock_usage(self, session, owner_id: UUID):
        """Lock global then owner counters, initializing an owner under the global lock."""
        global_row = (
            (
                await session.execute(
                    text(
                        "SELECT * FROM assistant.file_global_usage WHERE singleton=1 FOR UPDATE"
                    )
                )
            )
            .mappings()
            .one()
        )
        await session.execute(
            text(
                "INSERT INTO assistant.file_owner_usage(owner_id) VALUES (:owner) ON CONFLICT DO NOTHING"
            ),
            {"owner": owner_id},
        )
        owner_row = (
            (
                await session.execute(
                    text(
                        "SELECT * FROM assistant.file_owner_usage WHERE owner_id=:owner FOR UPDATE"
                    ),
                    {"owner": owner_id},
                )
            )
            .mappings()
            .one()
        )
        return global_row, owner_row

    async def _lock_file(self, session, owner_id: UUID, file_id: UUID) -> dict:
        """Require the trusted owner in the same row lock used for all state changes."""
        row = (
            (
                await session.execute(
                    text(
                        "SELECT * FROM assistant.files WHERE id=:id AND owner_id=:owner FOR UPDATE"
                    ),
                    {"id": file_id, "owner": owner_id},
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is None or not self._belongs(row):
            raise StoragePolicyError("file_not_found", 404)
        return dict(row)

    async def _adjust(self, session, owner_id: UUID, *, size=0, files=0, slots=0):
        """Mutate both locked usage rows together; CHECK constraints reject corrupt counters."""
        values = {"owner": owner_id, "size": size, "files": files, "slots": slots}
        for table, selector in (
            ("file_global_usage", "singleton=1"),
            ("file_owner_usage", "owner_id=:owner"),
        ):
            await session.execute(
                text(
                    f"UPDATE assistant.{table} SET allocated_bytes=allocated_bytes+:size, "
                    "allocated_files=allocated_files+:files, active_uploads=active_uploads+:slots, "
                    f"updated_at=clock_timestamp() WHERE {selector}"
                ),
                values,
            )

    async def reserve(self, plan: FileReservationPlan, *, free_bytes: int) -> dict:
        """Serialize replay and quota reservation across independent database connections."""
        canonical = plan_reservation(
            owner_id=plan.owner_id,
            file_id=plan.file_id,
            filename=plan.display_name,
            size_bytes=plan.size_bytes,
            expected_sha256=plan.expected_sha256,
            request_key=plan.request_key,
            policy=self.policy,
        )
        if canonical != plan:
            raise StoragePolicyError("invalid_reservation_plan", 422)
        async with self.sessions() as session, session.begin():
            global_row, owner_row = await self._lock_usage(session, plan.owner_id)
            if plan.request_key is not None:
                existing = (
                    (
                        await session.execute(
                            text(
                                "SELECT *, reservation_expires_at>clock_timestamp() AS live_reservation "
                                "FROM assistant.files WHERE owner_id=:owner AND request_key=:key FOR UPDATE"
                            ),
                            {"owner": plan.owner_id, "key": plan.request_key},
                        )
                    )
                    .mappings()
                    .one_or_none()
                )
                if existing is not None:
                    if not self._belongs(existing):
                        raise StoragePolicyError("file_storage_namespace_mismatch", 503)
                    if existing["request_fingerprint"] != plan.fingerprint:
                        raise StoragePolicyError("file_request_conflict", 409)
                    if existing["state"] == "ready" or (
                        existing["state"] == "reserved" and existing["live_reservation"]
                    ):
                        logger.info(
                            "file_reservation_replayed file_id=%s", existing["id"]
                        )
                        result = dict(existing)
                        result.pop("live_reservation")
                        return result
                    raise StoragePolicyError("file_request_finished", 409)
            check_capacity(
                size_bytes=plan.size_bytes,
                owner=usage(owner_row),
                global_usage=usage(global_row),
                free_bytes=free_bytes,
                policy=self.policy,
            )
            result = (
                (
                    await session.execute(
                        text(
                            "INSERT INTO assistant.files(id,owner_id,uploaded_by,display_name,declared_size_bytes,"
                            "expected_sha256,request_key,request_fingerprint,storage_key,policy_snapshot,reservation_expires_at) "
                            "VALUES (:id,:owner,:owner,:name,:size,:sha,:key,:fingerprint,:storage,CAST(:policy AS jsonb),"
                            "clock_timestamp()+:ttl*interval '1 second') RETURNING *"
                        ),
                        {
                            "id": plan.file_id,
                            "owner": plan.owner_id,
                            "name": plan.display_name,
                            "size": plan.size_bytes,
                            "sha": plan.expected_sha256,
                            "key": plan.request_key,
                            "fingerprint": plan.fingerprint,
                            "storage": plan.storage_key,
                            "policy": json.dumps(
                                {
                                    **asdict(self.policy),
                                    **(
                                        {"_storage_namespace": str(self.namespace_id)}
                                        if self.namespace_id is not None
                                        else {}
                                    ),
                                }
                            ),
                            "ttl": self.policy.reservation_seconds,
                        },
                    )
                )
                .mappings()
                .one()
            )
            await self._adjust(
                session, plan.owner_id, size=plan.size_bytes, files=1, slots=1
            )
            result = dict(result)
        logger.info(
            "file_reserved owner_id=%s file_id=%s size_bytes=%d",
            plan.owner_id,
            plan.file_id,
            plan.size_bytes,
        )
        return result

    async def get(self, owner_id: UUID, file_id: UUID) -> dict:
        """Read visible metadata without exposing another owner's existence or tombstones."""
        async with self.sessions() as session:
            row = (
                (
                    await session.execute(
                        text(
                            f"SELECT * FROM assistant.files WHERE id=:id AND owner_id=:owner AND {VISIBLE}"
                        ),
                        {"id": file_id, "owner": owner_id},
                    )
                )
                .mappings()
                .one_or_none()
            )
        if row is None or not self._belongs(row):
            raise StoragePolicyError("file_not_found", 404)
        logger.info("file_metadata_read file_id=%s", file_id)
        return dict(row)

    async def list(self, owner_id: UUID, *, limit=50, offset=0) -> list[dict]:
        """List only visible owned resources with deterministic bounded pagination."""
        if (
            type(limit) is not int
            or not 1 <= limit <= 100
            or type(offset) is not int
            or offset < 0
        ):
            raise StoragePolicyError("invalid_pagination", 422)
        async with self.sessions() as session:
            rows = (
                (
                    await session.execute(
                        text(
                            f"SELECT * FROM assistant.files WHERE owner_id=:owner AND {VISIBLE} {self._namespace_filter} "
                            "ORDER BY created_at DESC,id DESC LIMIT :limit OFFSET :offset"
                        ),
                        {
                            "owner": owner_id,
                            "limit": limit,
                            "offset": offset,
                            "namespace": str(self.namespace_id),
                        },
                    )
                )
                .mappings()
                .all()
            )
        logger.info("files_listed owner_id=%s count=%d", owner_id, len(rows))
        return [dict(row) for row in rows]

    async def claim(self, owner_id: UUID, file_id: UUID, lease_owner: UUID) -> dict:
        """Claim a live reservation after the service acquires its FS resource guard."""
        if not isinstance(lease_owner, UUID):
            raise StoragePolicyError("invalid_lease", 422)
        async with self.sessions() as session, session.begin():
            await self._lock_usage(session, owner_id)
            row = await self._lock_file(session, owner_id, file_id)
            policy = policy_from_snapshot(row["policy_snapshot"])
            result = (
                (
                    await session.execute(
                        text(
                            "WITH stamp AS (SELECT clock_timestamp() AS moment) "
                            "UPDATE assistant.files SET state='receiving',lease_owner=:lease,"
                            "claimed_at=stamp.moment,stream_deadline_at=stamp.moment+:wall*interval '1 second',"
                            "lease_expires_at=stamp.moment+:ttl*interval '1 second',updated_at=stamp.moment FROM stamp "
                            "WHERE id=:id AND owner_id=:owner AND state='reserved' AND deleted_at IS NULL "
                            "AND reservation_expires_at>clock_timestamp() RETURNING files.*"
                        ),
                        {
                            "id": file_id,
                            "owner": owner_id,
                            "lease": lease_owner,
                            "wall": policy.upload_seconds,
                            "ttl": policy.lease_seconds,
                        },
                    )
                )
                .mappings()
                .one_or_none()
            )
            if result is None:
                raise StoragePolicyError("file_not_claimable", 409)
            result = dict(result)
        logger.info("file_upload_claimed file_id=%s", file_id)
        return result

    async def heartbeat(
        self, owner_id: UUID, file_id: UUID, lease_owner: UUID, received: int
    ) -> dict:
        """Renew only a live upload while preserving monotonic byte progress and wall deadline."""
        if type(received) is not int or received < 0:
            raise StoragePolicyError("invalid_progress", 422)
        async with self.sessions() as session, session.begin():
            await self._lock_usage(session, owner_id)
            row = await self._lock_file(session, owner_id, file_id)
            policy = policy_from_snapshot(row["policy_snapshot"])
            result = (
                (
                    await session.execute(
                        text(
                            "UPDATE assistant.files SET bytes_received=:received,lease_expires_at=LEAST("
                            "stream_deadline_at,clock_timestamp()+:ttl*interval '1 second'),updated_at=clock_timestamp() "
                            "WHERE id=:id AND owner_id=:owner AND lease_owner=:lease AND state IN ('receiving','verifying') "
                            "AND deleted_at IS NULL AND lease_expires_at>clock_timestamp() AND stream_deadline_at>clock_timestamp() "
                            "AND :received BETWEEN bytes_received AND declared_size_bytes RETURNING *"
                        ),
                        {
                            "id": file_id,
                            "owner": owner_id,
                            "lease": lease_owner,
                            "received": received,
                            "ttl": policy.lease_seconds,
                        },
                    )
                )
                .mappings()
                .one_or_none()
            )
            if result is None:
                raise StoragePolicyError("file_lease_lost", 409)
            result = dict(result)
        logger.info(
            "file_upload_heartbeat file_id=%s bytes_received=%d", file_id, received
        )
        return result

    async def verifying(self, owner_id: UUID, file_id: UUID, lease_owner: UUID) -> dict:
        """Fence completed receiving before a bounded verifier inspects sealed bytes."""
        async with self.sessions() as session, session.begin():
            await self._lock_usage(session, owner_id)
            await self._lock_file(session, owner_id, file_id)
            result = (
                (
                    await session.execute(
                        text(
                            "UPDATE assistant.files SET state='verifying',updated_at=clock_timestamp() "
                            "WHERE id=:id AND owner_id=:owner AND lease_owner=:lease AND state='receiving' "
                            "AND deleted_at IS NULL AND lease_expires_at>clock_timestamp() "
                            "AND stream_deadline_at>clock_timestamp() AND bytes_received=declared_size_bytes RETURNING *"
                        ),
                        {"id": file_id, "owner": owner_id, "lease": lease_owner},
                    )
                )
                .mappings()
                .one_or_none()
            )
            if result is None:
                raise StoragePolicyError("file_lease_lost", 409)
            result = dict(result)
        logger.info("file_verification_started file_id=%s", file_id)
        return result

    async def ready(
        self, owner_id: UUID, file_id: UUID, lease_owner: UUID, media_type: str
    ) -> dict:
        """Release only the upload slot after caller-verification and durable FS publication."""
        async with self.sessions() as session, session.begin():
            await self._lock_usage(session, owner_id)
            row = await self._lock_file(session, owner_id, file_id)
            validate_detected_media(row["display_name"], media_type)
            result = (
                (
                    await session.execute(
                        text(
                            "UPDATE assistant.files SET state='ready',actual_size_bytes=declared_size_bytes,"
                            "actual_sha256=expected_sha256,detected_media_type=:media,verification_version=1,"
                            "verified_at=clock_timestamp(),upload_slot_released_at=clock_timestamp(),updated_at=clock_timestamp() "
                            "WHERE id=:id AND owner_id=:owner AND lease_owner=:lease AND state='verifying' "
                            "AND deleted_at IS NULL AND lease_expires_at>clock_timestamp() "
                            "AND stream_deadline_at>clock_timestamp() AND upload_slot_released_at IS NULL RETURNING *"
                        ),
                        {
                            "id": file_id,
                            "owner": owner_id,
                            "lease": lease_owner,
                            "media": media_type,
                        },
                    )
                )
                .mappings()
                .one_or_none()
            )
            if result is None:
                raise StoragePolicyError("file_lease_lost", 409)
            await self._adjust(session, owner_id, slots=-1)
            result = dict(result)
        logger.info("file_ready file_id=%s", file_id)
        return result

    async def begin_purge(
        self,
        owner_id: UUID,
        file_id: UUID,
        purge_token: UUID,
        *,
        target="deleted",
        error_code=None,
        lease_owner=None,
        expired_only=False,
    ) -> dict:
        """Hide/fence a resource while retaining all allocation until confirmed physical purge."""
        if target not in TERMINAL or not isinstance(purge_token, UUID):
            raise StoragePolicyError("invalid_purge", 422)
        if error_code is not None and error_code not in SAFE_ERRORS:
            raise StoragePolicyError("invalid_error_code", 422)
        if (
            target != "deleted"
            and not expired_only
            and not isinstance(lease_owner, UUID)
        ):
            raise StoragePolicyError("invalid_lease", 422)
        async with self.sessions() as session, session.begin():
            await self._lock_usage(session, owner_id)
            row = await self._lock_file(session, owner_id, file_id)
            if row["state"] in TERMINAL:
                return row
            if row["state"] == "purging":
                if target == "deleted" and not expired_only:
                    await session.execute(
                        text(
                            "UPDATE assistant.files SET purge_target='deleted',deleted_at=clock_timestamp(),updated_at=clock_timestamp() "
                            "WHERE id=:id AND owner_id=:owner"
                        ),
                        {"id": file_id, "owner": owner_id},
                    )
                    row = await self._lock_file(session, owner_id, file_id)
                return row
            if expired_only:
                expired = await session.scalar(
                    text(
                        "SELECT (state='reserved' AND reservation_expires_at<=clock_timestamp()) "
                        "OR (state IN ('receiving','verifying') AND lease_expires_at<=clock_timestamp()) "
                        "FROM assistant.files WHERE id=:id AND owner_id=:owner"
                    ),
                    {"id": file_id, "owner": owner_id},
                )
                if not expired or target != "interrupted":
                    raise StoragePolicyError("file_lease_active", 409)
            elif target != "deleted" and (
                row["lease_owner"] != lease_owner
                or row["state"] not in {"receiving", "verifying"}
            ):
                raise StoragePolicyError("file_lease_lost", 409)
            result = (
                (
                    await session.execute(
                        text(
                            "UPDATE assistant.files SET state='purging',purge_token=:token,purge_target=:target,"
                            "error_code=:error,deleted_at=CASE WHEN :target='deleted' THEN clock_timestamp() ELSE deleted_at END,"
                            "lease_expires_at=NULL,updated_at=clock_timestamp() WHERE id=:id AND owner_id=:owner RETURNING *"
                        ),
                        {
                            "id": file_id,
                            "owner": owner_id,
                            "token": purge_token,
                            "target": target,
                            "error": error_code,
                        },
                    )
                )
                .mappings()
                .one()
            )
            result = dict(result)
        logger.info("file_purge_fenced file_id=%s target=%s", file_id, target)
        return result

    async def release_purged(
        self, owner_id: UUID, file_id: UUID, purge_token: UUID
    ) -> dict:
        """Release counters once after the caller proves every owned name/FD is gone."""
        async with self.sessions() as session, session.begin():
            await self._lock_usage(session, owner_id)
            row = await self._lock_file(session, owner_id, file_id)
            if row["purge_token"] != purge_token:
                raise StoragePolicyError("file_purge_fence_lost", 409)
            if row["quota_released_at"] is not None:
                return row
            if row["state"] != "purging":
                raise StoragePolicyError("file_not_purging", 409)
            await self._adjust(
                session,
                owner_id,
                size=-row["declared_size_bytes"],
                files=-1,
                slots=-int(row["upload_slot_released_at"] is None),
            )
            result = (
                (
                    await session.execute(
                        text(
                            "UPDATE assistant.files SET state=purge_target,quota_released_at=clock_timestamp(),"
                            "upload_slot_released_at=COALESCE(upload_slot_released_at,clock_timestamp()),updated_at=clock_timestamp() "
                            "WHERE id=:id AND owner_id=:owner RETURNING *"
                        ),
                        {"id": file_id, "owner": owner_id},
                    )
                )
                .mappings()
                .one()
            )
            result = dict(result)
        logger.info("file_allocation_released file_id=%s", file_id)
        return result

    async def recovery_candidates(self, *, limit=50) -> list[dict]:
        """Return a bounded trusted-maintenance batch; each candidate still needs fencing."""
        if type(limit) is not int or not 1 <= limit <= 100:
            raise StoragePolicyError("invalid_pagination", 422)
        async with self.sessions() as session:
            rows = (
                (
                    await session.execute(
                        text(
                            "SELECT * FROM assistant.files WHERE (state='purging' OR "
                            "(state='reserved' AND reservation_expires_at<=clock_timestamp()) OR "
                            "(state IN ('receiving','verifying') AND lease_expires_at<=clock_timestamp())) "
                            f"{self._namespace_filter} "
                            "ORDER BY updated_at,id LIMIT :limit"
                        ),
                        {"limit": limit, "namespace": str(self.namespace_id)},
                    )
                )
                .mappings()
                .all()
            )
        logger.info("file_recovery_candidates count=%d", len(rows))
        return [dict(row) for row in rows]
