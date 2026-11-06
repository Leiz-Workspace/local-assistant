"""Verify V003 durable admission, replay, leases and generation/source consistency on real PostgreSQL."""

import asyncio
import hashlib
import importlib.util
import json
import logging
import os
from pathlib import Path
from uuid import uuid4

import pytest
import pytest_asyncio
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from test_file_http import cleanup_owners

from src.application.services.document_chunks import (
    ChunkSource,
    build_chunks,
    text_unit,
)
from src.application.services.file_storage_policy import (
    StoragePolicyError,
    plan_reservation,
)
from src.application.services.ingestion_contract import plan_ingestion
from src.infrastructure.database.connection import (
    create_database_engine,
    create_session_factory,
)
from src.infrastructure.repositories.file_journal import PostgresFileJournal
from src.infrastructure.repositories.ingestion_journal import PostgresIngestionJournal

logger = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parents[2]


@pytest_asyncio.fixture
async def context():
    """Provide isolated owners/source namespace and remove only their journal/allocations after each test."""
    if not os.environ.get("DATABASE_URL"):
        pytest.skip("DATABASE_URL not configured")
    engine = create_database_engine()
    sessions = create_session_factory(engine)
    owners = [uuid4(), uuid4()]
    namespace = uuid4()
    files = PostgresFileJournal(sessions, namespace_id=namespace)
    journal = PostgresIngestionJournal(sessions, namespace)
    try:
        async with sessions() as session:
            assert (
                await session.scalar(
                    text("SELECT version_num FROM assistant.alembic_version")
                )
                == ScriptDirectory.from_config(
                    Config(str(ROOT / "alembic.ini"))
                ).get_current_head()
            )
        yield dict(
            sessions=sessions,
            owners=owners,
            namespace=namespace,
            files=files,
            journal=journal,
        )
    finally:
        async with sessions() as session, session.begin():
            for table in ("ingestion_heads", "ingestion_jobs"):
                await session.execute(
                    text(f"DELETE FROM assistant.{table} WHERE owner_id IN (:a,:b)"),
                    dict(a=owners[0], b=owners[1]),
                )
        await engine.dispose()
        await cleanup_owners(owners)
        logger.info("ingestion_journal_test_cleanup owners=2")


async def ready_source(context, *, owner=None):
    """Create real source-journal ready metadata through all accepted file repository transitions."""
    owner = owner or context["owners"][0]
    body = b"private source bytes"
    plan = plan_reservation(
        owner_id=owner,
        file_id=uuid4(),
        filename="ingest.txt",
        size_bytes=len(body),
        expected_sha256=hashlib.sha256(body).hexdigest(),
        request_key=None,
    )
    files = context["files"]
    await files.reserve(plan, free_bytes=100 * 1024**3)
    token = uuid4()
    await files.claim(owner, plan.file_id, token)
    await files.heartbeat(owner, plan.file_id, token, len(body))
    await files.verifying(owner, plan.file_id, token)
    return await files.ready(owner, plan.file_id, token, "text/plain")


def make_plan(context, row, *, label="private source bytes", max_bytes=256):
    """Build real D22 output for a trusted repository fixture and the unchanged selected Qwen profile."""
    source = ChunkSource(
        row["owner_id"],
        context["namespace"],
        row["id"],
        row["actual_sha256"],
        "utf8-text-v1",
    )
    view = build_chunks(source, [text_unit("file:fixture#text", label)], max_bytes)
    selected = json.loads((ROOT / "configs/embedding-selected.json").read_text())
    return plan_ingestion(row, row["owner_id"], context["namespace"], view, selected)


async def due(context, job_id, *, expired=False):
    """Move only an owned test lease/backoff into the past without waiting for wall time."""
    field = "lease_expires_at" if expired else "next_attempt_at"
    async with context["sessions"]() as session, session.begin():
        await session.execute(
            text(
                f"UPDATE assistant.ingestion_jobs SET {field}=clock_timestamp()-interval '1 second' WHERE id=:id AND namespace_id=:namespace"
            ),
            dict(id=job_id, namespace=context["namespace"]),
        )


@pytest.mark.asyncio
async def test_exact_replay_claim_complete_publish_and_restart_read(context):
    """Persist one job/head and retain a complete published generation across repository reconstruction."""
    row = await ready_source(context)
    plan = make_plan(context, row)
    journal = context["journal"]
    admitted = await journal.admit(plan, [4])
    assert admitted["state"] == "pending" and admitted["attempts"] == 0
    assert (await journal.admit(plan, [4]))["id"] == admitted["id"]
    assert (
        await journal.active(plan.owner_id, plan.file_id, plan.model_fingerprint)
        is None
    )
    claimed = await journal.claim(plan.owner_id, plan.job_id)
    token = claimed["lease_token"]
    renewed = await journal.heartbeat(plan.owner_id, plan.job_id, token)
    assert renewed["lease_expires_at"] <= renewed["deadline_at"]
    with pytest.raises(StoragePolicyError, match="incomplete_acknowledgement"):
        await journal.publish(plan.owner_id, plan.job_id, token, [])
    published = await journal.publish(
        plan.owner_id, plan.job_id, token, admitted["point_ids"]
    )
    assert (
        published["state"] == "ready"
        and published["published_at"]
        and published["lease_token"] is None
    )
    fresh = PostgresIngestionJournal(context["sessions"], context["namespace"])
    assert (await fresh.active(plan.owner_id, plan.file_id, plan.model_fingerprint))[
        "id"
    ] == plan.job_id
    with pytest.raises(StoragePolicyError, match="ingestion_cleanup_not_terminal"):
        await journal.acknowledge_cleanup(plan.owner_id, plan.job_id)


@pytest.mark.asyncio
async def test_simultaneous_replay_and_claim_have_one_winner(context):
    """Serialize independent admission sessions and prevent concurrent workers claiming the same lease."""
    plan = make_plan(context, await ready_source(context))
    journal = context["journal"]
    rows = await asyncio.gather(*(journal.admit(plan, [4]) for _ in range(6)))
    assert {row["id"] for row in rows} == {plan.job_id}
    results = await asyncio.gather(
        *(journal.claim(plan.owner_id, plan.job_id) for _ in range(4)),
        return_exceptions=True,
    )
    assert sum(isinstance(result, dict) for result in results) == 1
    assert all(isinstance(result, (dict, StoragePolicyError)) for result in results)


@pytest.mark.asyncio
async def test_expired_worker_is_fenced_after_reclaim(context):
    """Recover expired work with a new attempt token and reject all transitions from the old worker."""
    plan = make_plan(context, await ready_source(context))
    journal = context["journal"]
    job = await journal.admit(plan, [4])
    first = await journal.claim(plan.owner_id, plan.job_id)
    await due(context, plan.job_id, expired=True)
    second = await journal.claim(plan.owner_id, plan.job_id)
    assert second["attempts"] == 2 and second["lease_token"] != first["lease_token"]
    for operation in (journal.heartbeat, journal.retry):
        with pytest.raises(StoragePolicyError, match="ingestion_lease_lost"):
            await operation(plan.owner_id, plan.job_id, first["lease_token"])
    with pytest.raises(StoragePolicyError, match="ingestion_lease_lost"):
        await journal.publish(
            plan.owner_id, plan.job_id, first["lease_token"], job["point_ids"]
        )
    assert (
        await journal.publish(
            plan.owner_id, plan.job_id, second["lease_token"], job["point_ids"]
        )
    )["state"] == "ready"


@pytest.mark.asyncio
async def test_bounded_retry_backoff_and_attempt_exhaustion(context):
    """Persist retry schedule without reviving a completed attempt or exceeding five claims."""
    plan = make_plan(context, await ready_source(context))
    journal = context["journal"]
    await journal.admit(plan, [4])
    for attempt in range(1, 6):
        claimed = await journal.claim(plan.owner_id, plan.job_id)
        result = await journal.retry(plan.owner_id, plan.job_id, claimed["lease_token"])
        assert result["attempts"] == attempt and result["lease_token"] is None
        if attempt < 5:
            assert (
                result["state"] == "pending"
                and result["next_attempt_at"] > result["updated_at"]
            )
            with pytest.raises(StoragePolicyError, match="retry_not_due"):
                await journal.claim(plan.owner_id, plan.job_id)
            await due(context, plan.job_id)
        else:
            assert result["state"] == "failed"
    assert (await journal.claim(plan.owner_id, plan.job_id))["state"] == "failed"


@pytest.mark.asyncio
async def test_new_generation_and_old_replay_cannot_publish_over_latest(context):
    """Keep desired generation monotonic while retaining the old active generation until replacement commits."""
    row = await ready_source(context)
    journal = context["journal"]
    first = make_plan(context, row)
    a = await journal.admit(first, [4])
    lease = await journal.claim(first.owner_id, first.job_id)
    await journal.publish(
        first.owner_id, first.job_id, lease["lease_token"], a["point_ids"]
    )
    second = make_plan(context, row, max_bytes=512)
    b = await journal.admit(second, [4])
    assert (
        await journal.active(first.owner_id, first.file_id, first.model_fingerprint)
    )["id"] == first.job_id
    assert (await journal.admit(first, [4]))["state"] == "ready"
    lease = await journal.claim(second.owner_id, second.job_id)
    await journal.publish(
        second.owner_id, second.job_id, lease["lease_token"], b["point_ids"]
    )
    assert (await journal.get(first.owner_id, first.job_id))["state"] == "tombstone"
    assert (
        await journal.active(first.owner_id, first.file_id, first.model_fingerprint)
    )["id"] == second.job_id
    cleanup = await journal.acknowledge_cleanup(first.owner_id, first.job_id)
    assert (
        cleanup["cleanup_done_at"]
        == (await journal.acknowledge_cleanup(first.owner_id, first.job_id))[
            "cleanup_done_at"
        ]
    )
    assert (await journal.admit(first, [4]))["state"] == "tombstone"


@pytest.mark.asyncio
async def test_pending_worker_superseded_and_token_replay_conflict(context):
    """Refuse different token counts on replay and fence in-flight work when a new desired plan arrives."""
    row = await ready_source(context)
    first = make_plan(context, row)
    journal = context["journal"]
    await journal.admit(first, [4])
    with pytest.raises(StoragePolicyError, match="ingestion_replay_conflict"):
        await journal.admit(first, [5])
    lease = await journal.claim(first.owner_id, first.job_id)
    second = make_plan(context, row, max_bytes=512)
    await journal.admit(second, [4])
    with pytest.raises(StoragePolicyError, match="ingestion_lease_lost"):
        await journal.publish(
            first.owner_id,
            first.job_id,
            lease["lease_token"],
            [point.point_id for point in first.points],
        )
    assert (await journal.claim(first.owner_id, first.job_id))["state"] == "stale"
    assert (await journal.claim(second.owner_id, second.job_id))["state"] == "running"


@pytest.mark.asyncio
async def test_deleted_source_is_hidden_before_reconcile_and_tombstones_are_durable(
    context,
):
    """Hide active data immediately through trusted file state and retain cleanup obligations after reconciliation."""
    row = await ready_source(context)
    plan = make_plan(context, row)
    journal = context["journal"]
    job = await journal.admit(plan, [4])
    lease = await journal.claim(plan.owner_id, plan.job_id)
    await journal.publish(
        plan.owner_id, plan.job_id, lease["lease_token"], job["point_ids"]
    )
    await context["files"].begin_purge(plan.owner_id, plan.file_id, uuid4())
    assert (
        await journal.active(plan.owner_id, plan.file_id, plan.model_fingerprint)
        is None
    )
    assert await journal.reconciliation_candidates() == [
        dict(file_id=plan.file_id, owner_id=plan.owner_id)
    ]
    result = await journal.reconcile_file(plan.owner_id, plan.file_id, limit=1)
    assert result["tombstoned"] == 1
    assert await journal.reconciliation_candidates() == []
    fresh = PostgresIngestionJournal(context["sessions"], context["namespace"])
    assert (await fresh.get(plan.owner_id, plan.job_id))["state"] == "tombstone"
    assert [item["id"] for item in await fresh.cleanup_candidates()] == [plan.job_id]
    await fresh.acknowledge_cleanup(plan.owner_id, plan.job_id)
    assert await fresh.cleanup_candidates() == []


@pytest.mark.asyncio
async def test_empty_generation_and_owner_namespace_isolation(context):
    """Publish an explicit zero-point generation and reject foreign owner/root operations uniformly."""
    row = await ready_source(context)
    plan = make_plan(context, row, label="")
    journal = context["journal"]
    await journal.admit(plan, [])
    lease = await journal.claim(plan.owner_id, plan.job_id)
    assert (
        await journal.publish(plan.owner_id, plan.job_id, lease["lease_token"], [])
    )["state"] == "ready"
    foreign = PostgresIngestionJournal(context["sessions"], uuid4())
    for repository, owner in [
        (journal, context["owners"][1]),
        (foreign, plan.owner_id),
    ]:
        with pytest.raises(StoragePolicyError, match="ingestion_job_not_found"):
            await repository.get(owner, plan.job_id)
        assert (
            await repository.active(owner, plan.file_id, plan.model_fingerprint) is None
        )
    assert await foreign.candidates() == []


@pytest.mark.asyncio
async def test_app_cannot_mutate_immutable_manifest_or_truncate(context):
    """Enforce immutable plan/source identity and bounded grants in the actual database role."""
    plan = make_plan(context, await ready_source(context))
    await context["journal"].admit(plan, [4])
    async with context["sessions"]() as session:
        row = (
            await session.execute(
                text(
                    "SELECT current_user,has_column_privilege(current_user,'assistant.ingestion_jobs','manifest_json','UPDATE'),has_column_privilege(current_user,'assistant.ingestion_jobs','state','UPDATE'),has_table_privilege(current_user,'assistant.ingestion_jobs','TRUNCATE')"
                )
            )
        ).one()
        assert tuple(row) == ("local_assistant_app", False, True, False)
    with pytest.raises(DBAPIError) as error:
        async with context["sessions"]() as session, session.begin():
            await session.execute(
                text(
                    "UPDATE assistant.ingestion_jobs SET manifest_json='{}' WHERE id=:id"
                ),
                dict(id=plan.job_id),
            )
    assert error.value.orig.sqlstate == "42501"


@pytest.mark.asyncio
async def test_constraints_and_nonempty_downgrade_guard(context):
    """Reject structurally invalid transitions and preserve populated journals during rollback attempts."""
    plan = make_plan(context, await ready_source(context))
    await context["journal"].admit(plan, [4])
    with pytest.raises(DBAPIError) as error:
        async with context["sessions"]() as session, session.begin():
            await session.execute(
                text(
                    "UPDATE assistant.ingestion_jobs SET state='running' WHERE id=:id"
                ),
                dict(id=plan.job_id),
            )
    assert error.value.orig.sqlstate == "23514"
    filename = ROOT / "migrations/versions/0003_ingestion_journal.py"
    spec = importlib.util.spec_from_file_location("ingestion_migration", filename)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    with pytest.raises(DBAPIError) as error:
        async with context["sessions"]() as session, session.begin():
            connection = await session.connection()

            def downgrade(sync_connection):
                """Execute the actual protected downgrade inside a transaction that must fail unchanged."""
                with Operations.context(MigrationContext.configure(sync_connection)):
                    migration.downgrade()

            await connection.run_sync(downgrade)
    assert error.value.orig.sqlstate == "P0001"


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["heartbeat", "retry", "publish"])
async def test_source_delete_fences_each_live_transition(context, operation):
    """Persist source invalidation instead of renewing or publishing after a real source delete request."""
    plan = make_plan(context, await ready_source(context))
    journal = context["journal"]
    job = await journal.admit(plan, [4])
    claimed = await journal.claim(plan.owner_id, plan.job_id)
    await context["files"].begin_purge(plan.owner_id, plan.file_id, uuid4())
    arguments = [plan.owner_id, plan.job_id, claimed["lease_token"]]
    if operation == "publish":
        arguments.append(job["point_ids"])
    result = await getattr(journal, operation)(*arguments)
    assert result["state"] == "stale" and result["lease_token"] is None
    assert (
        await journal.active(plan.owner_id, plan.file_id, plan.model_fingerprint)
        is None
    )


@pytest.mark.asyncio
async def test_admission_rechecks_changed_source_namespace_under_lock(context):
    """Reject a once-valid plan after the trusted root changed before durable admission."""
    plan = make_plan(context, await ready_source(context))
    async with context["sessions"]() as session, session.begin():
        await session.execute(
            text(
                "UPDATE assistant.files SET policy_snapshot=policy_snapshot || CAST(:scope AS jsonb) WHERE id=:id"
            ),
            dict(
                id=plan.file_id, scope=json.dumps({"_storage_namespace": str(uuid4())})
            ),
        )
    with pytest.raises(StoragePolicyError, match="file_not_found"):
        await context["journal"].admit(plan, [4])


@pytest.mark.asyncio
async def test_due_and_cleanup_cursors_are_bounded_and_restartable(context):
    """Use real typed NULL/keyset cursors without returning foreign or not-yet-due work."""
    journal = context["journal"]
    plans = [make_plan(context, await ready_source(context)) for _ in range(3)]
    for plan in plans:
        await journal.admit(plan, [4])
    first = await journal.candidates(limit=1)
    second = await journal.candidates(after_id=first[-1]["id"], limit=1)
    assert len(first) == len(second) == 1 and first[0]["id"] < second[0]["id"]
    owner = context["owners"][0]
    for entry in first + second:
        claimed = await journal.claim(owner, entry["id"])
        await journal.retry(owner, entry["id"], claimed["lease_token"])
    assert len(await journal.candidates()) == 1
    for plan in plans:
        await context["files"].begin_purge(owner, plan.file_id, uuid4())
        result = await journal.reconcile_file(owner, plan.file_id, limit=1)
        assert result["processed"] == result["tombstoned"] == 1
        assert (
            await journal.reconcile_file(
                owner, plan.file_id, after_id=result["next_after"], limit=1
            )
        )["processed"] == 0
    seen = []
    cursor = None
    while True:
        page = await journal.cleanup_candidates(after_id=cursor, limit=1)
        if not page:
            break
        seen.append(page[0]["id"])
        cursor = seen[-1]
    assert len(seen) == 3 and set(seen) == {plan.job_id for plan in plans}


@pytest.mark.asyncio
async def test_capacity_race_stops_at_owner_limit_and_keeps_replay(context):
    """Serialize competing admissions at the real limit while allowing existing immutable replay."""
    journal = context["journal"]
    plans = [make_plan(context, await ready_source(context)) for _ in range(33)]
    for plan in plans[:31]:
        await journal.admit(plan, [4])
    results = await asyncio.gather(
        *(journal.admit(plan, [4]) for plan in plans[31:]), return_exceptions=True
    )
    assert sum(isinstance(result, dict) for result in results) == 1
    failure = next(
        result for result in results if isinstance(result, StoragePolicyError)
    )
    assert failure.code == "ingestion_capacity_exceeded" and failure.status_code == 429
    assert (await journal.admit(plans[0], [4]))["id"] == plans[0].job_id
    async with context["sessions"]() as session:
        assert (
            await session.scalar(
                text(
                    "SELECT count(*) FROM assistant.ingestion_jobs WHERE namespace_id=:namespace AND state IN ('pending','running')"
                ),
                dict(namespace=context["namespace"]),
            )
            == 32
        )


@pytest.mark.asyncio
async def test_composite_pointer_fk_rejects_foreign_owner_job(context):
    """Enforce cross-owner/file model pointer isolation inside PostgreSQL as well as repository queries."""
    journal = context["journal"]
    first = make_plan(context, await ready_source(context))
    second = make_plan(context, await ready_source(context, owner=context["owners"][1]))
    await journal.admit(first, [4])
    await journal.admit(second, [4])
    with pytest.raises(DBAPIError) as error:
        async with context["sessions"]() as session, session.begin():
            await session.execute(
                text(
                    "UPDATE assistant.ingestion_heads SET active_job_id=:foreign WHERE owner_id=:owner AND namespace_id=:namespace AND file_id=:file"
                ),
                dict(
                    foreign=first.job_id,
                    owner=second.owner_id,
                    namespace=context["namespace"],
                    file=second.file_id,
                ),
            )
    assert error.value.orig.sqlstate == "23503"


@pytest.mark.asyncio
async def test_publish_delete_race_never_exposes_deleted_source(context):
    """Serialize competing source deletion/publication transactions and keep final active reads hidden."""
    journal = context["journal"]
    plan = make_plan(context, await ready_source(context))
    job = await journal.admit(plan, [4])
    claimed = await journal.claim(plan.owner_id, plan.job_id)
    result, _ = await asyncio.gather(
        journal.publish(
            plan.owner_id, plan.job_id, claimed["lease_token"], job["point_ids"]
        ),
        context["files"].begin_purge(plan.owner_id, plan.file_id, uuid4()),
    )
    assert result["state"] in {"ready", "stale"}
    assert (
        await journal.active(plan.owner_id, plan.file_id, plan.model_fingerprint)
        is None
    )


@pytest.mark.asyncio
async def test_absolute_deadline_expires_without_extra_attempt(context, tmp_path):
    """Inject only the owned job deadline through the operator and prove database-time failure fencing."""
    from scripts.postgres_recovery_acceptance import RecoveryAcceptance, literal

    journal = context["journal"]
    plan = make_plan(context, await ready_source(context))
    await journal.admit(plan, [4])
    operator = RecoveryAcceptance(tmp_path / "deadline-fault")
    operator.sql(
        "local_assistant",
        "UPDATE assistant.ingestion_jobs SET deadline_at=created_at+interval '1 microsecond' WHERE id="
        + literal(str(plan.job_id))
        + " AND owner_id="
        + literal(str(plan.owner_id))
        + ";",
    )
    failed = await journal.claim(plan.owner_id, plan.job_id)
    assert (
        failed["state"] == "failed"
        and failed["error_code"] == "deadline_exceeded"
        and failed["attempts"] == 0
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["admit", "publish"])
async def test_transaction_fault_does_not_leave_partial_job_or_pointer(
    context, monkeypatch, stage
):
    """Roll back a real PostgreSQL transaction after its job write and before the corresponding head write."""
    journal = context["journal"]
    plan = make_plan(context, await ready_source(context))
    if stage == "publish":
        job = await journal.admit(plan, [4])
        lease = await journal.claim(plan.owner_id, plan.job_id)
    original = journal._row

    async def fail_after_job_write(session, sql, values):
        """Inject a controlled failure only after the selected real job mutation executed."""
        result = await original(session, sql, values)
        if stage == "admit" and sql.startswith("INSERT INTO assistant.ingestion_jobs"):
            raise RuntimeError("controlled_transaction_fault")
        if stage == "publish" and "SET state='ready'" in sql:
            raise RuntimeError("controlled_transaction_fault")
        return result

    monkeypatch.setattr(journal, "_row", fail_after_job_write)
    with pytest.raises(RuntimeError, match="controlled_transaction_fault"):
        if stage == "admit":
            await journal.admit(plan, [4])
        else:
            await journal.publish(
                plan.owner_id, plan.job_id, lease["lease_token"], job["point_ids"]
            )
    monkeypatch.setattr(journal, "_row", original)
    assert (
        await journal.active(plan.owner_id, plan.file_id, plan.model_fingerprint)
        is None
    )
    if stage == "admit":
        with pytest.raises(StoragePolicyError, match="ingestion_job_not_found"):
            await journal.get(plan.owner_id, plan.job_id)
        assert (await journal.admit(plan, [4]))["state"] == "pending"
    else:
        assert (await journal.get(plan.owner_id, plan.job_id))["state"] == "running"
        assert (
            await journal.publish(
                plan.owner_id, plan.job_id, lease["lease_token"], job["point_ids"]
            )
        )["state"] == "ready"


@pytest.mark.asyncio
async def test_journal_mutation_transactions_have_database_wait_bounds(context):
    """Confirm real transaction-local wait limits without changing existing pool or database role settings."""
    async with context["journal"]._transaction() as session:
        values = (
            await session.execute(
                text(
                    "SELECT current_setting('lock_timeout'),current_setting('statement_timeout'),current_setting('idle_in_transaction_session_timeout')"
                )
            )
        ).one()
        assert tuple(values) == ("5s", "15s", "15s")
