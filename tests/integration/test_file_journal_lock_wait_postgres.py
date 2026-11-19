"""Verify on real PostgreSQL that file journal mutations stop waiting on a held global quota row lock."""

import asyncio
import logging
import time

import pytest
from sqlalchemy import text
from test_file_journal import FREE_BYTES, plan
from test_file_journal import context as context

from src.application.services.file_storage_policy import StoragePolicyError

logger = logging.getLogger(__name__)


async def hold_global_usage(sessions, entered, release):
    """Hold the global file quota row lock in a separate transaction until released."""
    async with sessions() as session, session.begin():
        await session.execute(
            text(
                "SELECT singleton FROM assistant.file_global_usage WHERE singleton=1 FOR UPDATE"
            )
        )
        entered.set()
        await release.wait()


@pytest.mark.asyncio
async def test_mutation_transactions_set_a_local_lock_budget(context):
    """Confirm the transaction-local lock_timeout without changing pool or role defaults."""
    journal, _, sessions = context
    setting = text("SELECT current_setting('lock_timeout')")
    async with sessions() as session:
        default = await session.scalar(setting)
    async with journal._transaction() as session:
        assert await session.scalar(setting) == "5s"
    async with sessions() as session:
        assert await session.scalar(setting) == default


@pytest.mark.asyncio
async def test_held_global_row_times_out_as_unavailable_store_then_recovers(context):
    """Report 503 file_storage_unavailable within the budget, reserve nothing, and succeed once the lock is free."""
    journal, owners, sessions = context
    declared = plan(owners[0])
    entered, release = asyncio.Event(), asyncio.Event()
    holder = asyncio.create_task(hold_global_usage(sessions, entered, release))
    try:
        await asyncio.wait_for(entered.wait(), 5)
        started = time.monotonic()
        with pytest.raises(StoragePolicyError) as caught:
            await asyncio.wait_for(journal.reserve(declared, free_bytes=FREE_BYTES), 20)
        elapsed = time.monotonic() - started
        assert caught.value.code == "file_storage_unavailable"
        assert caught.value.status_code == 503
        assert 4 <= elapsed < 12
    finally:
        release.set()
        await asyncio.wait_for(holder, 10)
    async with sessions() as session:
        assert (
            await session.scalar(
                text("SELECT count(*) FROM assistant.files WHERE id=:id"),
                {"id": declared.file_id},
            )
            == 0
        )
    row = await asyncio.wait_for(journal.reserve(declared, free_bytes=FREE_BYTES), 10)
    assert row["id"] == declared.file_id and row["state"] == "reserved"
    logger.info("file_journal_lock_timeout_verified")
