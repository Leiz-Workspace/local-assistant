"""Verify V002 quota/replay/lease transactions and structural checks on real PostgreSQL."""

import asyncio
import hashlib
import importlib.util
import logging
import os
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import pytest
import pytest_asyncio
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError

from src.application.services.file_storage_policy import (
    DEFAULT_POLICY,
    StoragePolicyError,
    plan_reservation,
)
from src.infrastructure.database.connection import (
    create_database_engine,
    create_session_factory,
)
from src.infrastructure.local_blob_storage import BlobIdentity, LocalBlobStorage
from src.infrastructure.repositories.file_journal import PostgresFileJournal

logger = logging.getLogger(__name__)
FREE_BYTES = 100 * 1024**3


@pytest_asyncio.fixture
async def context():
    """Provide isolated owners and clean only their allocations under the global lock."""
    if not os.environ.get("DATABASE_URL"):
        pytest.skip("DATABASE_URL not configured")
    engine = create_database_engine()
    sessions = create_session_factory(engine)
    owners = [uuid4(), uuid4()]
    try:
        async with sessions() as session:
            assert (
                await session.scalar(
                    text("SELECT version_num FROM assistant.alembic_version")
                )
                == ScriptDirectory.from_config(
                    Config(str(Path(__file__).parents[2] / "alembic.ini"))
                ).get_current_head()
            )
        yield PostgresFileJournal(sessions), owners, sessions
    finally:
        async with sessions() as session, session.begin():
            await session.execute(
                text(
                    "SELECT singleton FROM assistant.file_global_usage WHERE singleton=1 FOR UPDATE"
                )
            )
            rows = (
                (
                    await session.execute(
                        text(
                            "SELECT * FROM assistant.file_owner_usage WHERE owner_id IN (:a,:b) FOR UPDATE"
                        ),
                        {"a": owners[0], "b": owners[1]},
                    )
                )
                .mappings()
                .all()
            )
            totals = {
                name: sum(row[name] for row in rows)
                for name in ("allocated_bytes", "allocated_files", "active_uploads")
            }
            await session.execute(
                text("DELETE FROM assistant.files WHERE owner_id IN (:a,:b)"),
                {"a": owners[0], "b": owners[1]},
            )
            await session.execute(
                text(
                    "DELETE FROM assistant.file_owner_usage WHERE owner_id IN (:a,:b)"
                ),
                {"a": owners[0], "b": owners[1]},
            )
            await session.execute(
                text(
                    "UPDATE assistant.file_global_usage SET allocated_bytes=allocated_bytes-:allocated_bytes,"
                    "allocated_files=allocated_files-:allocated_files,active_uploads=active_uploads-:active_uploads WHERE singleton=1"
                ),
                totals,
            )
        await engine.dispose()
        logger.info("file_journal_test_cleanup owners=2")


def plan(owner, *, key=None, size=20, name="private.txt"):
    """Create owner-bound declarations without writing any production payload."""
    return plan_reservation(
        owner_id=owner,
        file_id=uuid4(),
        filename=name,
        size_bytes=size,
        expected_sha256=hashlib.sha256(b"x" * size).hexdigest(),
        request_key=key,
    )


async def counters(sessions, owner):
    """Read one test owner's committed allocation as a compact invariant tuple."""
    async with sessions() as session:
        row = (
            await session.execute(
                text(
                    "SELECT allocated_bytes,allocated_files,active_uploads FROM assistant.file_owner_usage WHERE owner_id=:owner"
                ),
                {"owner": owner},
            )
        ).one_or_none()
    return tuple(row) if row is not None else (0, 0, 0)


async def expire(sessions, file_id, state):
    """Move only a test journal deadline into the past without waiting for wall time."""
    field = "reservation_expires_at" if state == "reserved" else "lease_expires_at"
    async with sessions() as session, session.begin():
        await session.execute(
            text(
                f"UPDATE assistant.files SET {field}=clock_timestamp()-interval '1 second' WHERE id=:id"
            ),
            {"id": file_id},
        )


@pytest.mark.asyncio
async def test_full_lifecycle_and_exactly_once_release(context):
    """Keep bytes/files charged through ready/purging and release the slot only once."""
    journal, owners, sessions = context
    owner, other = owners
    row = await journal.reserve(plan(owner, key="once"), free_bytes=FREE_BYTES)
    identifier, lease = row["id"], uuid4()
    assert await counters(sessions, owner) == (20, 1, 1)
    assert row["policy_snapshot"]["max_file_bytes"] == DEFAULT_POLICY.max_file_bytes
    await journal.claim(owner, identifier, lease)
    await journal.heartbeat(owner, identifier, lease, 20)
    await journal.verifying(owner, identifier, lease)
    ready = await journal.ready(owner, identifier, lease, "text/plain")
    assert ready["actual_sha256"] == row["expected_sha256"]
    assert ready["verified_at"] and ready["verification_version"] == 1
    assert await counters(sessions, owner) == (20, 1, 0)
    assert (await journal.list(other)) == []
    token = uuid4()
    purging = await journal.begin_purge(owner, identifier, token)
    assert purging["state"] == "purging"
    assert await counters(sessions, owner) == (20, 1, 0)
    with pytest.raises(StoragePolicyError, match="file_not_found"):
        await journal.get(owner, identifier)
    await journal.release_purged(owner, identifier, token)
    await journal.release_purged(owner, identifier, token)
    assert await counters(sessions, owner) == (0, 0, 0)
    assert await journal.list(owner) == []
    with pytest.raises(StoragePolicyError, match="file_request_finished"):
        await journal.reserve(plan(owner, key="once"), free_bytes=FREE_BYTES)


@pytest.mark.asyncio
async def test_simultaneous_replay_allocates_once(context):
    """Serialize same-owner replay across separate sessions without duplicate charging."""
    journal, owners, sessions = context
    results = await asyncio.gather(
        *(
            journal.reserve(plan(owners[0], key="shared"), free_bytes=FREE_BYTES)
            for _ in range(6)
        )
    )
    assert len({row["id"] for row in results}) == 1
    assert await counters(sessions, owners[0]) == (20, 1, 1)
    with pytest.raises(StoragePolicyError, match="file_request_conflict"):
        await journal.reserve(
            plan(owners[0], key="shared", name="changed.txt"), free_bytes=FREE_BYTES
        )
    other = await journal.reserve(plan(owners[1], key="shared"), free_bytes=FREE_BYTES)
    assert other["id"] != results[0]["id"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "limit", ["bytes", "files", "owner_slots", "global_slots", "global_bytes"]
)
async def test_concurrent_capacity_is_atomic(context, limit):
    """Admit exactly the locked capacity under racing independent reservations."""
    _, owners, sessions = context
    limits = {
        "bytes": dict(max_file_bytes=20, chunk_bytes=10, owner_bytes=25),
        "files": dict(owner_files=1),
        "owner_slots": dict(owner_uploads=1),
        "global_slots": dict(owner_uploads=1, global_uploads=1),
        "global_bytes": dict(
            max_file_bytes=20, chunk_bytes=10, owner_bytes=40, global_bytes=40
        ),
    }
    journal = PostgresFileJournal(sessions, replace(DEFAULT_POLICY, **limits[limit]))
    inputs = (
        [owners[0], owners[1]]
        if limit in {"global_slots", "global_bytes"}
        else [owners[0], owners[0]]
    )
    if limit == "global_bytes":
        inputs += [owners[0], owners[1]]
    outcomes = await asyncio.gather(
        *(journal.reserve(plan(owner), free_bytes=FREE_BYTES) for owner in inputs),
        return_exceptions=True,
    )
    accepted = [item for item in outcomes if isinstance(item, dict)]
    rejected = [item for item in outcomes if isinstance(item, StoragePolicyError)]
    assert len(accepted) == (2 if limit == "global_bytes" else 1)
    assert len(rejected) == len(inputs) - len(accepted)
    assert all(item.status_code in {413, 429, 507} for item in rejected)
    totals = [await counters(sessions, owner) for owner in set(inputs)]
    assert sum(item[0] for item in totals) == 20 * len(accepted)
    assert sum(item[1] for item in totals) == len(accepted)


@pytest.mark.asyncio
async def test_owner_required_for_every_mutation(context):
    """Reject guessed resource IDs even when bypassing the HTTP service boundary."""
    journal, owners, _ = context
    row = await journal.reserve(plan(owners[0]), free_bytes=FREE_BYTES)
    identifier, lease, token = row["id"], uuid4(), uuid4()
    operations = [
        journal.get(owners[1], identifier),
        journal.claim(owners[1], identifier, lease),
        journal.heartbeat(owners[1], identifier, lease, 0),
        journal.verifying(owners[1], identifier, lease),
        journal.ready(owners[1], identifier, lease, "text/plain"),
        journal.begin_purge(owners[1], identifier, token),
        journal.release_purged(owners[1], identifier, token),
    ]
    for operation in operations:
        with pytest.raises(StoragePolicyError) as failure:
            await operation
        assert failure.value.status_code == 404
    assert (await journal.get(owners[0], identifier))["state"] == "reserved"


@pytest.mark.asyncio
async def test_claim_fencing_and_monotonic_progress(context):
    """Permit one PUT claim, monotonic progress and no stale-owner or oversize heartbeat."""
    journal, owners, sessions = context
    row = await journal.reserve(plan(owners[0]), free_bytes=FREE_BYTES)
    identifier, owner, lease = row["id"], owners[0], uuid4()
    await journal.claim(owner, identifier, lease)
    with pytest.raises(StoragePolicyError, match="file_not_claimable"):
        await journal.claim(owner, identifier, uuid4())
    for received, worker in [(0, uuid4()), (21, lease)]:
        with pytest.raises(StoragePolicyError, match="file_lease_lost"):
            await journal.heartbeat(owner, identifier, worker, received)
    progress = await journal.heartbeat(owner, identifier, lease, 10)
    assert progress["lease_expires_at"] <= progress["stream_deadline_at"]
    with pytest.raises(StoragePolicyError, match="file_lease_lost"):
        await journal.heartbeat(owner, identifier, lease, 9)
    with pytest.raises(StoragePolicyError, match="file_lease_lost"):
        await journal.verifying(owner, identifier, lease)
    await expire(sessions, identifier, "receiving")
    for operation in (
        journal.heartbeat(owner, identifier, lease, 20),
        journal.ready(owner, identifier, lease, "text/plain"),
    ):
        with pytest.raises(StoragePolicyError, match="file_lease_lost"):
            await operation
    assert await counters(sessions, owner) == (20, 1, 1)


@pytest.mark.asyncio
@pytest.mark.parametrize("state", ["reserved", "receiving", "verifying"])
async def test_expiry_requires_fenced_cleanup_not_automatic_release(context, state):
    """Retain allocation after expiry and expose only bounded recovery candidates."""
    journal, owners, sessions = context
    owner = owners[0]
    row = await journal.reserve(plan(owner), free_bytes=FREE_BYTES)
    identifier, lease, token = row["id"], uuid4(), uuid4()
    if state != "reserved":
        await journal.claim(owner, identifier, lease)
    if state == "verifying":
        await journal.heartbeat(owner, identifier, lease, 20)
        await journal.verifying(owner, identifier, lease)
    with pytest.raises(StoragePolicyError, match="file_lease_active"):
        await journal.begin_purge(
            owner, identifier, token, target="interrupted", expired_only=True
        )
    await expire(sessions, identifier, state)
    assert identifier in {row["id"] for row in await journal.recovery_candidates()}
    row = await journal.begin_purge(
        owner,
        identifier,
        token,
        target="interrupted",
        error_code="upload_interrupted",
        expired_only=True,
    )
    assert row["state"] == "purging" and row["purge_target"] == "interrupted"
    assert await counters(sessions, owner) == (20, 1, 1)
    with pytest.raises(StoragePolicyError, match="file_purge_fence_lost"):
        await journal.release_purged(owner, identifier, uuid4())
    await journal.release_purged(owner, identifier, token)
    assert await counters(sessions, owner) == (0, 0, 0)


@pytest.mark.asyncio
async def test_delete_fences_writer_and_upgrades_failed_purge(context):
    """Make user deletion authoritative even if failure cleanup has already started."""
    journal, owners, sessions = context
    owner, lease = owners[0], uuid4()
    row = await journal.reserve(plan(owner), free_bytes=FREE_BYTES)
    identifier = row["id"]
    await journal.claim(owner, identifier, lease)
    token = uuid4()
    await journal.begin_purge(
        owner,
        identifier,
        token,
        target="rejected",
        lease_owner=lease,
        error_code="file_hash_mismatch",
    )
    upgraded = await journal.begin_purge(owner, identifier, uuid4())
    assert upgraded["purge_token"] == token and upgraded["purge_target"] == "deleted"
    with pytest.raises(StoragePolicyError, match="file_lease_lost"):
        await journal.heartbeat(owner, identifier, lease, 20)
    result = await journal.release_purged(owner, identifier, token)
    assert result["state"] == "deleted" and result["deleted_at"]
    assert await counters(sessions, owner) == (0, 0, 0)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mutation",
    [
        "state='ready'",
        "storage_key='../../outside'",
        "bytes_received=21",
        "expected_sha256='invalid'",
        "uploaded_by=gen_random_uuid()",
        "state='deleted'",
    ],
)
async def test_structural_checks_reject_inconsistent_journal(context, mutation):
    """Enforce schema invariants even when internal code bypasses repository helpers."""
    journal, owners, sessions = context
    row = await journal.reserve(plan(owners[0]), free_bytes=FREE_BYTES)
    with pytest.raises(IntegrityError):
        async with sessions() as session, session.begin():
            await session.execute(
                text(f"UPDATE assistant.files SET {mutation} WHERE id=:id"),
                {"id": row["id"]},
            )
    assert (await journal.get(owners[0], row["id"]))["state"] == "reserved"


@pytest.mark.asyncio
async def test_nonempty_downgrade_guard_and_grants(context):
    """Refuse schema destruction with records present and verify the runtime role is bounded."""
    journal, owners, sessions = context
    await journal.reserve(plan(owners[0]), free_bytes=FREE_BYTES)
    filename = Path(__file__).parents[2] / "migrations/versions/0002_file_journal.py"
    spec = importlib.util.spec_from_file_location("file_migration", filename)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    async with sessions() as session, session.begin():
        privileges = (
            await session.execute(
                text(
                    "SELECT current_user, has_table_privilege(current_user,'assistant.files','SELECT,INSERT,UPDATE,DELETE'),"
                    "has_table_privilege(current_user,'assistant.files','TRUNCATE'), rolsuper, rolcreatedb "
                    "FROM pg_roles WHERE rolname=current_user"
                )
            )
        ).one()
    assert tuple(privileges) == ("local_assistant_app", True, False, False, False)
    with pytest.raises(DBAPIError) as failure:
        async with sessions() as session, session.begin():
            connection = await session.connection()

            def attempt_downgrade(sync_connection):
                """Execute the real guard through Alembic while rolling back its failed transaction."""
                with Operations.context(MigrationContext.configure(sync_connection)):
                    migration.downgrade()

            await connection.run_sync(attempt_downgrade)
    assert failure.value.orig.sqlstate == "P0001"


@pytest.mark.asyncio
async def test_zero_wall_margin_claim_uses_one_database_timestamp(context):
    """Avoid microsecond drift when policy permits lease duration equal to wall duration."""
    _, owners, sessions = context
    policy = replace(DEFAULT_POLICY, upload_seconds=60, lease_seconds=60)
    journal = PostgresFileJournal(sessions, policy)
    row = await journal.reserve(plan(owners[0]), free_bytes=FREE_BYTES)
    claimed = await journal.claim(owners[0], row["id"], uuid4())
    assert claimed["lease_expires_at"] == claimed["stream_deadline_at"]


@pytest.mark.asyncio
async def test_live_fd_prevents_quota_release_until_physical_purge(context, tmp_path):
    """Exercise the actual DB/FS guard protocol instead of assuming expiry closes bytes."""
    journal, owners, sessions = context
    owner = owners[0]
    declaration = plan(owner)
    row = await journal.reserve(declaration, free_bytes=FREE_BYTES)
    identity = BlobIdentity(owner, row["id"], uuid4())
    with LocalBlobStorage(tmp_path / "blobs") as storage:
        with storage.lock_resource(identity) as guard:
            await journal.claim(owner, row["id"], identity.lease_id)
            writer = storage.create_writer(declaration, identity.lease_id, guard=guard)
        writer.write(b"x" * 20)
        token = uuid4()
        await journal.begin_purge(owner, row["id"], token)
        assert storage.purge(identity) is False
        assert await counters(sessions, owner) == (20, 1, 1)
        writer.close()
        assert storage.purge(identity) is True
        await asyncio.gather(
            *(journal.release_purged(owner, row["id"], token) for _ in range(6))
        )
        assert await counters(sessions, owner) == (0, 0, 0)


@pytest.mark.asyncio
async def test_stale_claim_after_cleanup_cannot_create_payload(context, tmp_path):
    """Recheck the journal under the guard before a delayed worker can create bytes."""
    journal, owners, sessions = context
    owner = owners[0]
    declaration = plan(owner)
    row = await journal.reserve(declaration, free_bytes=FREE_BYTES)
    identity = BlobIdentity(owner, row["id"], uuid4())
    with LocalBlobStorage(tmp_path / "blobs") as storage:
        token = uuid4()
        await journal.begin_purge(owner, row["id"], token)
        assert storage.purge(identity) is True
        await journal.release_purged(owner, row["id"], token)
        with storage.lock_resource(identity):
            with pytest.raises(StoragePolicyError, match="file_not_claimable"):
                await journal.claim(owner, row["id"], identity.lease_id)
            assert not (tmp_path / "blobs").joinpath(*identity.staging_parts).exists()
        assert await counters(sessions, owner) == (0, 0, 0)


@pytest.mark.asyncio
async def test_published_but_not_ready_recovers_conservatively(context, tmp_path):
    """Keep published bytes hidden and charged until expired journal cleanup completes."""
    journal, owners, sessions = context
    owner = owners[0]
    declaration = plan(owner)
    row = await journal.reserve(declaration, free_bytes=FREE_BYTES)
    identity = BlobIdentity(owner, row["id"], uuid4())
    with LocalBlobStorage(tmp_path / "blobs") as storage:
        with storage.lock_resource(identity) as guard:
            await journal.claim(owner, row["id"], identity.lease_id)
            writer = storage.create_writer(declaration, identity.lease_id, guard=guard)
        with writer:
            writer.write(b"x" * 20)
            writer.seal()
            await journal.heartbeat(owner, row["id"], identity.lease_id, 20)
            await journal.verifying(owner, row["id"], identity.lease_id)
            writer.publish()
        assert (await journal.get(owner, row["id"]))["state"] == "verifying"
        assert await counters(sessions, owner) == (20, 1, 1)
        await expire(sessions, row["id"], "verifying")
        token = uuid4()
        await journal.begin_purge(
            owner, row["id"], token, target="interrupted", expired_only=True
        )
        assert storage.purge(identity) is True
        await journal.release_purged(owner, row["id"], token)
        assert await counters(sessions, owner) == (0, 0, 0)
