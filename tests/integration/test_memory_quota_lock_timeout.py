"""Verify on owned PostgreSQL probes that memory grant/create_manual stop waiting on a held global quota lock."""

import asyncio
import logging
import time

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from test_memory_journal_postgres import memory_context as memory_context
from test_message_memory_journal import message_context as message_context

logger = logging.getLogger(__name__)
ADVISORY = "SELECT pg_advisory_xact_lock(1146310990,30)"


async def hold_quota_lock(context, entered, release):
    """Hold the global memory quota advisory lock in a separate app-role transaction until released."""
    async with context["sessions"]() as session, session.begin():
        await session.execute(text(ADVISORY))
        entered.set()
        await release.wait()


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["grant", "create_manual"])
async def test_held_quota_lock_times_out_instead_of_waiting_unbounded(
    message_context, operation
):
    """Raise lock_not_available within the 5s budget, leave no record and succeed once the lock is free."""
    context = message_context
    journal = context["journal"]
    owner = context["owners"][0]
    settings = await journal.configure(
        owner, expected_revision=0, enabled=True, extraction_enabled=False
    )
    receipt = None
    if operation == "create_manual":
        receipt = await journal.grant(
            owner,
            kind="preference",
            expected_revision=settings["revision"],
            seconds=300,
        )

    def attempt():
        """Start the selected mutation that must take the global quota lock."""
        if operation == "grant":
            return journal.grant(
                owner,
                kind="preference",
                expected_revision=settings["revision"],
                seconds=300,
            )
        return journal.create_manual(owner, receipt.id, "Bounded quota wait.")

    entered, release = asyncio.Event(), asyncio.Event()
    holder = asyncio.create_task(hold_quota_lock(context, entered, release))
    try:
        await asyncio.wait_for(entered.wait(), 5)
        started = time.monotonic()
        with pytest.raises(DBAPIError) as error:
            await asyncio.wait_for(attempt(), 20)
        elapsed = time.monotonic() - started
        assert error.value.orig.sqlstate == "55P03"
        assert 4 <= elapsed < 12
    finally:
        release.set()
        await asyncio.wait_for(holder, 10)
    assert await journal.list(owner) == []
    result = await asyncio.wait_for(attempt(), 10)
    assert result.owner_id == owner
    logger.info("memory_quota_lock_timeout_verified operation=%s", operation)
