"""Verify file journal mutations bound row-lock waits and report an expired wait as the existing 503 store code."""

import asyncio
import hashlib
from contextlib import asynccontextmanager
from uuid import uuid4

import pytest
from sqlalchemy.exc import DBAPIError, IntegrityError

from src.application.services.file_storage_policy import (
    StoragePolicyError,
    plan_reservation,
)
from src.infrastructure.repositories.file_journal import PostgresFileJournal

LOCK = "SET LOCAL lock_timeout='5s'"
GLOBAL = "SELECT * FROM assistant.file_global_usage WHERE singleton=1 FOR UPDATE"
MUTATIONS = [
    "reserve",
    "claim",
    "heartbeat",
    "verifying",
    "ready",
    "begin_purge",
    "release_purged",
    "note_purge_retry",
]


class DriverError(Exception):
    """Stand in for a psycopg error that carries a PostgreSQL SQLSTATE."""

    def __init__(self, sqlstate):
        """Record only the SQLSTATE the journal inspects."""
        super().__init__(sqlstate)
        self.sqlstate = sqlstate


class EmptyResult:
    """Return no mapping rows, as a missing file would."""

    def mappings(self):
        """Expose the mapping protocol the journal reads."""
        return self

    def one_or_none(self):
        """Report no row."""
        return None


class RecordingSession:
    """Record transaction boundaries and SQL text, failing at one chosen statement."""

    def __init__(self, fail_at=None, error=None):
        """Fail when the statement text equals fail_at; otherwise return an empty result."""
        self.fail_at = fail_at
        self.error = error
        self.events = []

    @asynccontextmanager
    async def begin(self):
        """Mark BEGIN, then COMMIT or the ROLLBACK a failure causes."""
        self.events.append("BEGIN")
        try:
            yield self
        except BaseException:
            self.events.append("ROLLBACK")
            raise
        self.events.append("COMMIT")

    async def execute(self, statement, parameters=None):
        """Record the SQL text and raise the injected error at the chosen statement."""
        sql = str(statement)
        self.events.append(sql)
        if sql == self.fail_at:
            raise self.error
        return EmptyResult()


def journal_for(session):
    """Bind the real journal to a factory that always yields the recording session."""

    @asynccontextmanager
    async def sessions():
        """Yield the shared recording session like an async session factory."""
        yield session

    return PostgresFileJournal(sessions)


def call(journal, name):
    """Start one file journal mutation with valid arguments up to its first lock."""
    owner, file_id, token = uuid4(), uuid4(), uuid4()
    if name == "reserve":
        plan = plan_reservation(
            owner_id=owner,
            file_id=file_id,
            filename="private.txt",
            size_bytes=20,
            expected_sha256=hashlib.sha256(b"x" * 20).hexdigest(),
        )
        return journal.reserve(plan, free_bytes=100 * 1024**3)
    if name == "heartbeat":
        return journal.heartbeat(owner, file_id, token, 0)
    if name == "ready":
        return journal.ready(owner, file_id, token, "text/plain")
    if name == "begin_purge":
        return journal.begin_purge(owner, file_id, token)
    return getattr(journal, name)(owner, file_id, token)


def lock_error(sqlstate):
    """Wrap a driver error the way SQLAlchemy raises it from a statement."""
    return DBAPIError(GLOBAL, {}, DriverError(sqlstate))


@pytest.mark.asyncio
@pytest.mark.parametrize("name", MUTATIONS)
async def test_lock_timeout_is_set_before_the_global_quota_row_lock(name):
    """Apply the transaction-local lock budget first, then take the global singleton row lock."""
    session = RecordingSession(GLOBAL, lock_error("55P03"))
    with pytest.raises(StoragePolicyError) as caught:
        await call(journal_for(session), name)
    assert caught.value.code == "file_storage_unavailable"
    assert caught.value.status_code == 503
    assert caught.value.__cause__ is None and caught.value.__suppress_context__
    assert session.events == ["BEGIN", LOCK, GLOBAL, "ROLLBACK"]


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ["claim", "begin_purge"])
async def test_lock_timeout_on_the_file_row_maps_to_the_same_store_code(name):
    """Map an expired wait on the per-file row lock, not only the global row, to the unavailable store."""
    statement = (
        "SELECT * FROM assistant.files WHERE id=:id AND owner_id=:owner FOR UPDATE"
    )
    session = RecordingSession(statement, lock_error("55P03"))

    class Row(dict):
        """Return the counter rows the usage lock reads."""

    class CounterResult(EmptyResult):
        """Return one counter row for the global and owner usage queries."""

        def one(self):
            """Report a zeroed counter row."""
            return Row(allocated_bytes=0, allocated_files=0, active_uploads=0)

    original = session.execute

    async def execute(statement_object, parameters=None):
        """Serve counter rows before failing at the file row lock."""
        await original(statement_object, parameters)
        return CounterResult()

    session.execute = execute
    with pytest.raises(StoragePolicyError, match="file_storage_unavailable"):
        await call(journal_for(session), name)
    assert session.events[:3] == ["BEGIN", LOCK, GLOBAL]
    assert session.events[-2:] == [statement, "ROLLBACK"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error",
    [
        lock_error("08006"),
        lock_error("57014"),
        IntegrityError(GLOBAL, {}, DriverError("23505")),
        DBAPIError(GLOBAL, {}, Exception("no sqlstate")),
    ],
)
async def test_other_database_errors_are_not_relabelled(error):
    """Re-raise the exact connection, statement-timeout, integrity or unknown driver error unchanged."""
    session = RecordingSession(GLOBAL, error)
    with pytest.raises(DBAPIError) as caught:
        await call(journal_for(session), "claim")
    assert caught.value is error
    assert session.events == ["BEGIN", LOCK, GLOBAL, "ROLLBACK"]


@pytest.mark.asyncio
async def test_cancellation_while_waiting_propagates_unchanged():
    """Keep cancellation as cancellation and roll the transaction back."""
    error = asyncio.CancelledError()
    session = RecordingSession(GLOBAL, error)
    with pytest.raises(asyncio.CancelledError) as caught:
        await call(journal_for(session), "heartbeat")
    assert caught.value is error
    assert session.events == ["BEGIN", LOCK, GLOBAL, "ROLLBACK"]


@pytest.mark.asyncio
async def test_policy_rejection_inside_the_transaction_is_unchanged():
    """Pass a journal policy error raised after the locks through without relabelling it."""
    session = RecordingSession()

    class Row(dict):
        """Return the counter rows the usage lock reads."""

    class CounterResult(EmptyResult):
        """Return one counter row for the usage queries and no file row."""

        def one(self):
            """Report a zeroed counter row."""
            return Row(allocated_bytes=0, allocated_files=0, active_uploads=0)

    original = session.execute

    async def execute(statement_object, parameters=None):
        """Serve counter rows and a missing file row."""
        await original(statement_object, parameters)
        return CounterResult()

    session.execute = execute
    with pytest.raises(StoragePolicyError) as caught:
        await call(journal_for(session), "claim")
    assert caught.value.code == "file_not_found" and caught.value.status_code == 404
    assert session.events[:3] == ["BEGIN", LOCK, GLOBAL]
    assert session.events[-1] == "ROLLBACK"


@pytest.mark.asyncio
async def test_reads_keep_their_unbounded_nontransactional_path():
    """Leave get without a transaction or lock budget, as before."""
    session = RecordingSession()
    with pytest.raises(StoragePolicyError, match="file_not_found"):
        await journal_for(session).get(uuid4(), uuid4())
    assert "BEGIN" not in session.events and LOCK not in session.events


class RecoverySession(RecordingSession):
    """Serve one expired recovery candidate, no ready rows, and fail the global lock with a lock timeout."""

    def __init__(self, candidate):
        """Fail at the global usage row lock with lock_not_available."""
        super().__init__(GLOBAL, lock_error("55P03"))
        self.candidate = candidate

    async def execute(self, statement, parameters=None):
        """Return candidate rows for the read queries and fail at the global lock."""
        await super().execute(statement, parameters)
        rows = [self.candidate] if "lease_expires_at<=" in str(statement) else []

        class Rows:
            """Expose the mapping protocol the recovery reads use."""

            def mappings(self):
                """Return this row set."""
                return self

            def all(self):
                """Return the served rows."""
                return rows

        return Rows()


@pytest.mark.asyncio
async def test_recovery_counts_a_lock_timeout_as_pending_instead_of_aborting():
    """Keep a startup or periodic recovery batch running when one fence waits too long for the quota lock."""
    from apps.api.services.files import FileService

    candidate = dict(id=uuid4(), owner_id=uuid4(), state="receiving")
    session = RecoverySession(candidate)
    service = FileService.__new__(FileService)
    service.journal = journal_for(session)
    service._ready_cursor = None
    assert await service.recover_once() == {"completed": 0, "pending": 1}
    assert session.events.count("ROLLBACK") == 1 and LOCK in session.events


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error",
    [
        StoragePolicyError("file_storage_unavailable", 503),
        DBAPIError(GLOBAL, {}, DriverError("08006")),
    ],
)
async def test_route_reports_a_lock_timeout_with_the_existing_store_code(error):
    """Return the same 503 file_storage_unavailable the API already returns for other database failures."""
    from types import SimpleNamespace

    from fastapi import HTTPException

    from apps.api.routes.files import get_file_service

    service = SimpleNamespace(closing=False)
    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(file_service=service))
    )
    dependency = get_file_service(request)
    assert await dependency.__anext__() is service
    with pytest.raises(HTTPException) as caught:
        await dependency.athrow(error)
    assert caught.value.status_code == 503
    assert caught.value.detail == {"code": "file_storage_unavailable"}
