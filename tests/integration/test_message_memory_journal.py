"""Verify actual owned user-message memory source fences and bounded expiry/orphan retention on V005."""

import asyncio
import hashlib
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import text
from test_memory_journal_postgres import memory_context as memory_context
from test_memory_journal_postgres import session_scope

from apps.api.services.memory_retention import MemoryRetention
from src.application.services.memory_contract import MemoryPolicyError
from src.infrastructure.repositories.message_memory_journal import (
    PostgresMessageMemoryJournal,
)


@pytest_asyncio.fixture
async def message_context(memory_context):
    """Extend owned app-role probes with the actual source-aware journal and delete only their test messages."""
    context = dict(
        memory_context, journal=PostgresMessageMemoryJournal(memory_context["sessions"])
    )
    try:
        yield context
    finally:
        if context["conversations"]:
            async with context["sessions"]() as session, session.begin():
                await session.execute(
                    text(
                        "DELETE FROM assistant.messages WHERE conversation_id=ANY(:ids)"
                    ),
                    dict(ids=context["conversations"]),
                )


async def message_source(
    context, *, owner=None, value="I prefer Vietnamese.", role="user"
):
    """Persist one synthetic actual message in an owned source conversation without model/history simulation."""
    owner = owner or context["owners"][0]
    conversation = await session_scope(context, owner)
    identifier = uuid4()
    async with context["sessions"]() as session, session.begin():
        await session.execute(
            text(
                "INSERT INTO assistant.messages(id,conversation_id,sequence,role,content) VALUES (:id,:conversation,1,:role,:content)"
            ),
            dict(id=identifier, conversation=conversation, role=role, content=value),
        )
    return conversation, identifier, value


async def extraction_receipt(
    context, *, owner=None, kind="preference", scope=None, seconds=300
):
    """Explicitly enable independent extraction and grant only the requested owned scope."""
    owner = owner or context["owners"][0]
    journal = context["journal"]
    settings = await journal.settings(owner)
    if not settings["enabled"]:
        settings = await journal.configure(
            owner,
            expected_revision=settings["revision"],
            enabled=True,
            extraction_enabled=True,
        )
    return await journal.grant(
        owner,
        kind=kind,
        scope_id=scope,
        expected_revision=settings["revision"],
        seconds=seconds,
        allow_extraction=True,
    )


@pytest.mark.asyncio
async def test_actual_source_quote_capture_provenance_and_final_version(
    message_context,
):
    """Capture only current owned user quotes and map exact Unicode offsets/hash/producer into real stored records."""
    context = message_context
    journal = context["journal"]
    owner = context["owners"][0]
    conversation, message, value = await message_source(
        context, value="Tôi thích a\u0301 và 𝄞."
    )
    receipt = await extraction_receipt(context)
    consent, snapshot = await journal.preflight_selection(
        owner, receipt.id, conversation, message
    )
    record = await journal.capture_selection(
        owner, consent.id, snapshot, "a\u0301 và 𝄞.", "controlled-producer"
    )
    assert record.text == "a\u0301 và 𝄞." and record.method == "extracted"
    evidence = record.provenance
    assert value[evidence.start : evidence.end] == record.text
    assert evidence.content_sha256 == hashlib.sha256(value.encode()).hexdigest()
    assert (
        evidence.role == "user"
        and evidence.message_id == message
        and evidence.conversation_id == conversation
    )
    await journal.validate_selection(owner, receipt.id, snapshot, record)
    await journal.edit_manual(owner, record.id, "Edited by owner.", expected_version=1)
    with pytest.raises(MemoryPolicyError, match="memory_source_changed"):
        await journal.validate_selection(owner, receipt.id, snapshot, record)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "fault", ["foreign", "assistant", "unowned", "archived", "deleted", "oversized"]
)
async def test_actual_source_refusal_before_inference(message_context, fault):
    """Reject unauthorized/non-user/inactive/oversized source snapshots before an extractor can invoke CORE."""
    context = message_context
    journal = context["journal"]
    owner = context["owners"][0]
    conversation, message, value = await message_source(
        context,
        role="assistant" if fault == "assistant" else "user",
        value="x" * 8193 if fault == "oversized" else "source fact",
    )
    if fault == "foreign":
        owner = context["owners"][1]
    receipt = await extraction_receipt(context, owner=owner)
    if fault in ("unowned", "archived", "deleted"):
        change = (
            "metadata='{}'::jsonb"
            if fault == "unowned"
            else "status='archived'"
            if fault == "archived"
            else "deleted_at=clock_timestamp()"
        )
        async with context["sessions"]() as session, session.begin():
            await session.execute(
                text("UPDATE assistant.conversations SET " + change + " WHERE id=:id"),
                dict(id=conversation),
            )
    with pytest.raises(
        MemoryPolicyError,
        match="memory_source_limit"
        if fault == "oversized"
        else "memory_source_not_found",
    ):
        await journal.preflight_selection(owner, receipt.id, conversation, message)
    assert await journal.list(owner) == []


@pytest.mark.asyncio
async def test_independent_consent_and_session_scope_before_source_capture(
    message_context,
):
    """Require extraction settings/receipt separately and bind session capture to its exact conversation."""
    context = message_context
    journal = context["journal"]
    owner = context["owners"][0]
    conversation, message, value = await message_source(context)
    await journal.configure(
        owner, expected_revision=0, enabled=True, extraction_enabled=False
    )
    receipt = await journal.grant(
        owner, kind="preference", expected_revision=1, seconds=300
    )
    with pytest.raises(MemoryPolicyError, match="memory_extraction_disabled"):
        await journal.preflight_selection(owner, receipt.id, conversation, message)
    await journal.configure(
        owner, expected_revision=1, enabled=True, extraction_enabled=True
    )
    other = await session_scope(context, owner)
    receipt = await journal.grant(
        owner,
        kind="session",
        scope_id=other,
        expected_revision=2,
        seconds=300,
        allow_extraction=True,
    )
    with pytest.raises(MemoryPolicyError, match="memory_scope_invalid"):
        await journal.preflight_selection(owner, receipt.id, conversation, message)


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["text", "deleted", "disabled", "revoked"])
async def test_actual_source_and_consent_changes_fence_capture(message_context, change):
    """Refuse capture after real source/hash/owner control changes while keeping every attempted write atomic."""
    context = message_context
    journal = context["journal"]
    owner = context["owners"][0]
    conversation, message, value = await message_source(context)
    receipt = await extraction_receipt(context)
    consent, snapshot = await journal.preflight_selection(
        owner, receipt.id, conversation, message
    )
    if change in ("text", "deleted"):
        async with context["sessions"]() as session, session.begin():
            if change == "text":
                await session.execute(
                    text(
                        "UPDATE assistant.messages SET content='changed source' WHERE id=:id"
                    ),
                    dict(id=message),
                )
            else:
                await session.execute(
                    text(
                        "UPDATE assistant.conversations SET deleted_at=clock_timestamp() WHERE id=:id"
                    ),
                    dict(id=conversation),
                )
    elif change == "disabled":
        await journal.configure(
            owner, expected_revision=1, enabled=False, extraction_enabled=False
        )
    else:
        await journal.revoke(owner, receipt.id)
    with pytest.raises(MemoryPolicyError):
        await journal.capture_selection(
            owner, consent.id, snapshot, value, "controlled-producer"
        )
    assert await journal.list(owner) == []


@pytest.mark.asyncio
async def test_actual_expiry_and_orphan_cleanup_bounds_preserve_referenced_receipts(
    message_context,
):
    """Delete no more than each requested batch and retain inactive receipts still proving unexpired owned records."""
    context = message_context
    journal = context["journal"]
    owner = context["owners"][0]
    await journal.configure(
        owner, expected_revision=0, enabled=True, extraction_enabled=False
    )
    expired = await journal.grant(
        owner, kind="preference", expected_revision=1, seconds=1
    )
    for _ in range(3):
        await journal.create_manual(owner, expired.id, "expires")
    referenced = await journal.grant(
        owner, kind="preference", expected_revision=1, seconds=300
    )
    keep = await journal.create_manual(owner, referenced.id, "retain explicit record")
    orphan = await journal.grant(
        owner, kind="preference", expected_revision=1, seconds=300
    )
    await journal.configure(
        owner, expected_revision=1, enabled=False, extraction_enabled=False
    )
    await asyncio.sleep(1.05)
    first = await journal.purge_owner(owner, limit=2)
    assert first["records"] == 2 and first["receipts"] == 1
    second = await journal.purge_owner(owner, limit=2)
    assert second == dict(records=1, receipts=1)
    assert (await journal.inspect(owner, keep.id)).text == "retain explicit record"
    async with context["sessions"]() as session:
        assert (
            await session.scalar(
                text("SELECT count(*) FROM assistant.memory_consents WHERE id=:id"),
                dict(id=referenced.id),
            )
            == 1
        )
        assert (
            await session.scalar(
                text("SELECT count(*) FROM assistant.memory_consents WHERE id=:id"),
                dict(id=orphan.id),
            )
            == 0
        )


@pytest.mark.asyncio
async def test_actual_background_retention_purges_disabled_owner_and_joins(
    message_context,
):
    """Run actual bounded scheduled cleanup against expired owned records without a model or enabled owner use."""
    context = message_context
    journal = context["journal"]
    owner = context["owners"][0]
    await journal.configure(
        owner, expected_revision=0, enabled=True, extraction_enabled=False
    )
    receipt = await journal.grant(
        owner, kind="preference", expected_revision=1, seconds=1
    )
    await journal.create_manual(owner, receipt.id, "expired background probe")
    await journal.configure(
        owner, expected_revision=1, enabled=False, extraction_enabled=False
    )
    await asyncio.sleep(1.05)
    worker = MemoryRetention(journal, interval=0.01)
    worker.start()

    async def emptied():
        """Wait for actual automatic deletion rather than invoking the purge method directly."""
        while await journal.list(owner):
            await asyncio.sleep(0.01)

    try:
        await asyncio.wait_for(emptied(), 5)
    finally:
        await worker.shutdown()
    assert worker.task.done() and context["sessions"].kw["bind"].pool.checkedout() == 0
