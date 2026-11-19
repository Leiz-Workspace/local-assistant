"""Verify memory mutations bound lock and statement waits before taking the global quota advisory lock."""

import asyncio
import hashlib
from contextlib import asynccontextmanager
from uuid import uuid4

import pytest
from sqlalchemy.exc import DBAPIError

from src.application.services.memory_selection import MessageMemorySource
from src.infrastructure.repositories.memory_journal import PostgresMemoryJournal
from src.infrastructure.repositories.message_memory_journal import (
    PostgresMessageMemoryJournal,
)

ADVISORY = "SELECT pg_advisory_xact_lock(1146310990,30)"
LOCK = "SET LOCAL lock_timeout='5s'"
STATEMENT = "SET LOCAL statement_timeout='10s'"
SETTINGS = "SELECT * FROM assistant.memory_settings WHERE owner_id=:owner FOR UPDATE"


class LockNotAvailable(Exception):
    """Stand in for the driver error PostgreSQL raises when lock_timeout expires."""

    sqlstate = "55P03"


def lock_timeout():
    """Build the wrapped driver error SQLAlchemy raises for an expired lock wait."""
    return DBAPIError(ADVISORY, {}, LockNotAvailable("lock timeout"))


class RecordingSession:
    """Record every statement and transaction boundary, failing at one chosen statement."""

    def __init__(self, fail_at, error):
        """Fail when the statement text equals fail_at; record everything before it."""
        self.fail_at = fail_at
        self.error = error
        self.events = []

    @asynccontextmanager
    async def begin(self):
        """Mark the transaction boundaries the journal opens and the rollback a failure causes."""
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

    async def scalar(self, statement, parameters=None):
        """Refuse reads: every scenario fails before the journal reads a scalar."""
        raise AssertionError("unexpected scalar read: " + str(statement))


def journal_for(cls, session):
    """Bind a journal class to a session factory that always yields the recording session."""

    @asynccontextmanager
    async def sessions():
        """Yield the shared recording session like an async session factory."""
        yield session

    return cls(sessions)


def mutation(name, journal, owner):
    """Start one memory mutation that takes the global quota lock."""
    if name == "grant":
        return journal.grant(owner, kind="preference", expected_revision=1, seconds=60)
    if name == "create_manual":
        return journal.create_manual(owner, uuid4(), "Tôi thích tiếng Việt.")
    text = "I prefer Vietnamese."
    source = MessageMemorySource(
        uuid4(), uuid4(), hashlib.sha256(text.encode()).hexdigest(), text
    )
    return journal.capture_selection(owner, uuid4(), source, text, "model")


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ["grant", "create_manual", "capture_selection"])
@pytest.mark.parametrize("failure", ["lock_timeout", "cancelled"])
async def test_production_journal_bounds_waits_before_the_global_advisory_lock(
    name, failure
):
    """Apply both SET LOCAL budgets first, then propagate a lock timeout or cancellation and roll back."""
    error = lock_timeout() if failure == "lock_timeout" else asyncio.CancelledError()
    session = RecordingSession(ADVISORY, error)
    journal = journal_for(PostgresMessageMemoryJournal, session)
    with pytest.raises(type(error)) as caught:
        await mutation(name, journal, uuid4())
    assert caught.value is error
    assert session.events == ["BEGIN", LOCK, STATEMENT, ADVISORY, "ROLLBACK"]


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ["grant", "create_manual"])
async def test_owner_settings_lock_still_follows_the_advisory_lock_under_budgets(name):
    """Keep the accepted lock order: bounded advisory lock first, then the bounded owner settings row lock."""
    error = lock_timeout()
    session = RecordingSession(SETTINGS, error)
    journal = journal_for(PostgresMessageMemoryJournal, session)
    with pytest.raises(DBAPIError):
        await mutation(name, journal, uuid4())
    assert session.events == [
        "BEGIN",
        LOCK,
        STATEMENT,
        ADVISORY,
        LOCK,
        STATEMENT,
        SETTINGS,
        "ROLLBACK",
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ["grant", "create_manual"])
async def test_base_journal_keeps_database_wait_defaults(name):
    """Leave the unbounded base journal unchanged: its first statement is still the advisory lock."""
    error = lock_timeout()
    session = RecordingSession(ADVISORY, error)
    journal = journal_for(PostgresMemoryJournal, session)
    with pytest.raises(DBAPIError):
        await mutation(name, journal, uuid4())
    assert session.events == ["BEGIN", ADVISORY, "ROLLBACK"]


@pytest.mark.asyncio
async def test_invalid_grant_is_rejected_before_any_transaction():
    """Refuse malformed consent input before opening a transaction or setting budgets."""
    from src.application.services.memory_contract import MemoryPolicyError

    session = RecordingSession(ADVISORY, lock_timeout())
    journal = journal_for(PostgresMessageMemoryJournal, session)
    with pytest.raises(MemoryPolicyError, match="memory_consent_invalid"):
        await journal.grant(
            uuid4(), kind="preference", expected_revision=1, seconds=True
        )
    assert session.events == []
