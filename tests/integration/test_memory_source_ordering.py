"""Verify actual source mutation/capture lock ordering and invoker-only trigger privileges on owned PostgreSQL probes."""

import asyncio
import logging

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from test_memory_journal_postgres import memory_context as memory_context
from test_message_memory_journal import extraction_receipt, message_source
from test_message_memory_journal import message_context as message_context

from src.application.services.memory_contract import MemoryPolicyError
from src.infrastructure.repositories.message_memory_journal import (
    PostgresMessageMemoryJournal,
)

logger = logging.getLogger(__name__)


class HeldCapture(PostgresMessageMemoryJournal):
    """Hold actual source locks after fresh revalidation to expose the source-update serialization boundary."""

    def __init__(self, sessions):
        """Add explicit entered/release barriers without changing production SQL or authorization."""
        super().__init__(sessions)
        self.entered = asyncio.Event()
        self.release = asyncio.Event()

    async def _revalidate_source(self, session, owner, source):
        """Retain actual conversation/message locks until the concurrent source statement is observed waiting."""
        result = await super()._revalidate_source(session, owner, source)
        self.entered.set()
        await self.release.wait()
        return result


@pytest.mark.asyncio
async def test_actual_capture_commit_then_waiting_source_change_removes_copy(
    message_context,
):
    """Observe PostgreSQL Lock wait and prove a later source commit removes the earlier authorized capture atomically."""
    context = message_context
    owner = context["owners"][0]
    journal = HeldCapture(context["sessions"])
    conversation, message, value = await message_source(context)
    receipt = await extraction_receipt(context)
    consent, source = await journal.preflight_selection(
        owner, receipt.id, conversation, message
    )
    capture = asyncio.create_task(
        journal.capture_selection(owner, receipt.id, source, value, "controlled-core")
    )
    mutation = None
    backend = []
    entered = asyncio.Event()

    async def mutate():
        """Submit one real source update from a distinct app-role transaction and expose only its backend identity."""
        async with context["sessions"]() as session, session.begin():
            backend.append(await session.scalar(text("SELECT pg_backend_pid()")))
            entered.set()
            await session.execute(
                text(
                    "UPDATE assistant.messages SET content='later source commit' WHERE id=:id"
                ),
                dict(id=message),
            )

    async def wait_for_lock():
        """Require the actual PostgreSQL wait state rather than inferring blocking from an unfinished task."""
        while True:
            async with context["sessions"]() as session:
                event = await session.scalar(
                    text("SELECT wait_event_type FROM pg_stat_activity WHERE pid=:pid"),
                    dict(pid=backend[0]),
                )
            if event == "Lock":
                return
            await asyncio.sleep(0.01)

    try:
        await asyncio.wait_for(journal.entered.wait(), 5)
        mutation = asyncio.create_task(mutate())
        await asyncio.wait_for(entered.wait(), 5)
        await asyncio.wait_for(wait_for_lock(), 5)
        journal.release.set()
        record = await asyncio.wait_for(capture, 5)
        await asyncio.wait_for(mutation, 5)
        with pytest.raises(MemoryPolicyError, match="memory_not_found"):
            await journal.inspect(owner, record.id)
        assert await journal.list(owner) == []
    finally:
        journal.release.set()
        await asyncio.gather(
            *[task for task in (capture, mutation) if task is not None],
            return_exceptions=True,
        )
    logger.info("memory_actual_source_lock_order_verified wait=Lock")


@pytest.mark.asyncio
async def test_actual_trigger_has_no_definer_or_direct_execute_authority(
    memory_context,
):
    """Verify fixed invoker trigger functions work without granting the app direct function execution or broadening SQL identity rights."""
    async with memory_context["sessions"]() as session:
        rows = (
            await session.execute(
                text(
                    "SELECT p.prosecdef,p.proconfig,has_function_privilege(current_user,p.oid,'EXECUTE') FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='assistant' AND p.proname IN ('invalidate_conversation_memory','invalidate_message_memory')"
                )
            )
        ).all()
        assert len(rows) == 2 and all(
            not row[0]
            and row[1] == ["search_path=pg_catalog, assistant"]
            and not row[2]
            for row in rows
        )
    with pytest.raises(DBAPIError) as error:
        async with memory_context["sessions"]() as session, session.begin():
            await session.execute(text("SELECT assistant.invalidate_message_memory()"))
    assert error.value.orig.sqlstate == "42501"
    logger.info("memory_actual_source_invoker_privileges_verified")
