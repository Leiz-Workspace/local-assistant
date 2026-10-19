"""Verify actual runtime-role memory consent, CRUD, quota and concurrent-control transactions on owned probes."""

import asyncio
import hashlib
import json
import logging
import os
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from src.application.services.memory_contract import MemoryPolicyError
from src.infrastructure.database.connection import (
    create_database_engine,
    create_session_factory,
)
from src.infrastructure.repositories.memory_journal import PostgresMemoryJournal

logger = logging.getLogger(__name__)


@pytest_asyncio.fixture
async def memory_context():
    """Create only random owner probes and remove their child records/receipts/settings and conversations."""
    if not os.environ.get("DATABASE_URL"):
        pytest.skip("existing app DATABASE_URL required")
    engine = create_database_engine()
    sessions = create_session_factory(engine)
    owners = [uuid4() for _ in range(12)]
    conversations = []
    journal = PostgresMemoryJournal(sessions)
    async with sessions() as session:
        assert await session.scalar(
            text("SELECT version_num FROM assistant.alembic_version")
        ) in {"0005", "0006"}
        assert (
            await session.scalar(text("SELECT current_user")) == "local_assistant_app"
        )
    try:
        yield dict(
            journal=journal,
            sessions=sessions,
            owners=owners,
            conversations=conversations,
        )
    finally:
        async with sessions() as session, session.begin():
            for table in ("memories", "memory_consents", "memory_settings"):
                await session.execute(
                    text(
                        "DELETE FROM assistant."
                        + table
                        + " WHERE owner_id=ANY(:owners)"
                    ),
                    dict(owners=owners),
                )
            await session.execute(
                text(
                    "DELETE FROM assistant.conversations WHERE metadata->>'owner_id'=ANY(:owners)"
                ),
                dict(owners=[str(owner) for owner in owners]),
            )
            if conversations:
                await session.execute(
                    text("DELETE FROM assistant.conversations WHERE id=ANY(:ids)"),
                    dict(ids=conversations),
                )
        await engine.dispose()
        logger.info("memory_journal_owned_probes_cleaned")


async def session_scope(context, owner, *, unowned=False):
    """Create one exact test conversation using the accepted metadata ownership convention."""
    identifier = uuid4()
    context["conversations"].append(identifier)
    metadata = {} if unowned else dict(owner_id=str(owner))
    async with context["sessions"]() as session, session.begin():
        await session.execute(
            text(
                "INSERT INTO assistant.conversations(id,metadata) VALUES (:id,CAST(:metadata AS jsonb))"
            ),
            dict(id=identifier, metadata=json.dumps(metadata)),
        )
    return identifier


async def enabled_receipt(
    context, *, owner=None, kind="preference", scope=None, seconds=3600
):
    """Enable only a random test owner and grant an explicit fresh receipt through the actual repository."""
    owner = owner or context["owners"][0]
    journal = context["journal"]
    await journal.configure(
        owner, expected_revision=0, enabled=True, extraction_enabled=False
    )
    if kind == "session" and scope is None:
        scope = await session_scope(context, owner)
    if kind == "project" and scope is None:
        scope = uuid4()
    return await journal.grant(
        owner, kind=kind, scope_id=scope, expected_revision=1, seconds=seconds
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["session", "episodic", "preference", "project"])
async def test_owned_four_class_manual_crud_and_disabled_management(
    memory_context, kind
):
    """Persist exact Unicode hashes, fence stale edits and preserve inspection/deletion after disable."""
    context = memory_context
    journal = context["journal"]
    owner = context["owners"][0]
    assert (await journal.settings(owner))["revision"] == 0
    receipt = await enabled_receipt(context, kind=kind)
    value = "Tôi thích Unicode a\u0301 và 𝄞."
    record = await journal.create_manual(owner, receipt.id, value)
    assert (
        record.provenance.content_sha256 == hashlib.sha256(value.encode()).hexdigest()
    )
    assert (await journal.inspect(owner, record.id)).text == value
    listed = await journal.list(owner)
    assert (
        len(listed) == 1 and "text" not in listed[0] and "provenance" not in listed[0]
    )
    edited = await journal.edit_manual(
        owner, record.id, "Updated preference.", expected_version=1
    )
    assert edited.version == 2 and edited.model_id is None
    with pytest.raises(MemoryPolicyError, match="memory_conflict"):
        await journal.edit_manual(owner, record.id, "stale", expected_version=1)
    await journal.configure(
        owner, expected_revision=1, enabled=False, extraction_enabled=False
    )
    assert (await journal.inspect(owner, record.id)).text == "Updated preference."
    with pytest.raises(MemoryPolicyError):
        await journal.create_manual(owner, receipt.id, "disabled")
    await journal.delete(owner, record.id, expected_version=2)
    assert await journal.list(owner) == []


@pytest.mark.asyncio
async def test_foreign_receipts_records_and_controls_are_hidden(memory_context):
    """Deny another owner's guessed IDs for capture, inspect, edit, deletion and receipt revocation."""
    context = memory_context
    journal = context["journal"]
    owner, foreign = context["owners"][:2]
    receipt = await enabled_receipt(context)
    record = await journal.create_manual(owner, receipt.id, "private text")
    await enabled_receipt(context, owner=foreign)
    actions = [
        journal.create_manual(foreign, receipt.id, "foreign"),
        journal.inspect(foreign, record.id),
        journal.edit_manual(foreign, record.id, "foreign", expected_version=1),
        journal.delete(foreign, record.id, expected_version=1),
        journal.revoke(foreign, receipt.id),
    ]
    for action in actions:
        with pytest.raises(MemoryPolicyError, match="memory_not_found"):
            await action
    assert await journal.list(foreign) == []
    assert (await journal.inspect(owner, record.id)).text == "private text"


@pytest.mark.asyncio
async def test_session_scope_revalidates_owner_and_current_conversation(memory_context):
    """Reject foreign/deleted/archived session scope without assigning ownership to legacy records."""
    context = memory_context
    journal = context["journal"]
    owner, foreign = context["owners"][:2]
    receipt = await enabled_receipt(context, kind="session")
    foreign_scope = await session_scope(context, foreign)
    legacy_scope = await session_scope(context, owner, unowned=True)
    for scope in (foreign_scope, legacy_scope, uuid4()):
        with pytest.raises(MemoryPolicyError, match="memory_scope_not_found"):
            await journal.grant(
                owner, kind="session", scope_id=scope, expected_revision=1, seconds=60
            )
    async with context["sessions"]() as session, session.begin():
        await session.execute(
            text("UPDATE assistant.conversations SET status='archived' WHERE id=:id"),
            dict(id=receipt.scope_id),
        )
    with pytest.raises(MemoryPolicyError, match="memory_scope_not_found"):
        await journal.create_manual(owner, receipt.id, "session stale")


@pytest.mark.asyncio
async def test_revoke_and_epoch_changes_prevent_resurrection(memory_context):
    """Keep revocation idempotent and prevent re-enable from implicitly reusing previous owner receipts."""
    context = memory_context
    journal = context["journal"]
    owner = context["owners"][0]
    receipt = await enabled_receipt(context)
    record = await journal.create_manual(owner, receipt.id, "before revoke")
    first = await journal.revoke(owner, receipt.id)
    second = await journal.revoke(owner, receipt.id)
    assert first.revoked_at == second.revoked_at
    with pytest.raises(MemoryPolicyError, match="memory_consent_inactive"):
        await journal.edit_manual(owner, record.id, "after revoke", expected_version=1)
    fresh = await journal.grant(
        owner, kind="preference", expected_revision=1, seconds=3600
    )
    await journal.configure(
        owner, expected_revision=1, enabled=False, extraction_enabled=False
    )
    await journal.configure(
        owner, expected_revision=2, enabled=True, extraction_enabled=False
    )
    with pytest.raises(MemoryPolicyError, match="memory_consent_inactive"):
        await journal.create_manual(owner, fresh.id, "resurrected")
    latest = await journal.grant(
        owner, kind="preference", expected_revision=3, seconds=3600
    )
    assert (
        await journal.create_manual(owner, latest.id, "new explicit consent")
    ).text == "new explicit consent"


@pytest.mark.asyncio
async def test_invalid_capture_rolls_back_and_expiry_purge_is_bounded(memory_context):
    """Leave no failed rows and delete expired owned data without requiring memory use enabled."""
    context = memory_context
    journal = context["journal"]
    owner = context["owners"][0]
    receipt = await enabled_receipt(context)
    for value in ("", "ệ" * 1366, "bad\0text"):
        with pytest.raises(MemoryPolicyError):
            await journal.create_manual(owner, receipt.id, value)
    assert await journal.list(owner) == []
    record = await journal.create_manual(owner, receipt.id, "expires soon", seconds=1)
    await asyncio.sleep(1.1)
    with pytest.raises(MemoryPolicyError, match="memory_consent_inactive"):
        await journal.edit_manual(owner, record.id, "expired edit", expected_version=1)
    await journal.configure(
        owner, expected_revision=1, enabled=False, extraction_enabled=False
    )
    assert await journal.purge_expired(owner, limit=1) == 1
    assert await journal.purge_expired(owner, limit=1) == 0
    assert await journal.list(owner) == []


@pytest.mark.asyncio
async def test_settings_compare_and_swap_has_one_winner(memory_context):
    """Serialize concurrent bootstrap and subsequent configuration so exactly one expected revision wins."""
    context = memory_context
    journal = context["journal"]
    owner = context["owners"][0]
    for revision in (0, 1):
        results = await asyncio.gather(
            *(
                journal.configure(
                    owner,
                    expected_revision=revision,
                    enabled=True,
                    extraction_enabled=False,
                )
                for _ in range(2)
            ),
            return_exceptions=True,
        )
        assert sum(isinstance(result, dict) for result in results) == 1
        assert (
            sum(
                isinstance(result, MemoryPolicyError)
                and result.code == "memory_conflict"
                for result in results
            )
            == 1
        )
    assert (await journal.settings(owner))["revision"] == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("control", ["disable", "revoke"])
async def test_owner_lock_orders_capture_before_concurrent_control(
    memory_context, monkeypatch, control
):
    """Prove disable/revoke waits for admitted capture and prevents every later write after its commit."""
    context = memory_context
    journal = context["journal"]
    owner = context["owners"][0]
    receipt = await enabled_receipt(context)
    entered, release = asyncio.Event(), asyncio.Event()
    original = journal._receipt

    async def held(*args):
        """Hold an actual owner/receipt SQL lock at a deterministic test barrier."""
        result = await original(*args)
        entered.set()
        await release.wait()
        return result

    monkeypatch.setattr(journal, "_receipt", held)
    capture = asyncio.create_task(
        journal.create_manual(owner, receipt.id, "ordered capture")
    )
    await asyncio.wait_for(entered.wait(), 5)
    mutation = asyncio.create_task(
        journal.configure(
            owner, expected_revision=1, enabled=False, extraction_enabled=False
        )
        if control == "disable"
        else journal.revoke(owner, receipt.id)
    )
    await asyncio.sleep(0.05)
    assert not mutation.done()
    release.set()
    record = await asyncio.wait_for(capture, 5)
    await asyncio.wait_for(mutation, 5)
    assert (await journal.inspect(owner, record.id)).text == "ordered capture"
    with pytest.raises(MemoryPolicyError):
        await journal.create_manual(owner, receipt.id, "after control")


async def bulk_owned_records(context, owner, receipt, count):
    """Seed only owned synthetic rows to reach real quota boundaries without thousands of HTTP/model calls."""
    async with context["sessions"]() as session, session.begin():
        await session.execute(
            text(
                "WITH stamp AS (SELECT clock_timestamp() t) INSERT INTO assistant.memories(id,owner_id,kind,scope_id,consent_id,text,method,provenance,created_at,updated_at,expires_at) SELECT gen_random_uuid(),:owner,'preference',:owner,:consent,'quota','manual',CAST(:provenance AS jsonb),stamp.t,stamp.t,:expires FROM generate_series(1,:count),stamp"
            ),
            dict(
                owner=owner,
                consent=receipt.id,
                provenance=json.dumps(
                    dict(
                        kind="manual",
                        content_sha256=hashlib.sha256(b"quota").hexdigest(),
                    )
                ),
                expires=receipt.expires_at,
                count=count,
            ),
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("scope", ["owner", "global"])
async def test_actual_owner_and_global_quota_caps(memory_context, scope):
    """Reject real full owner/global inventories while preserving all seeded owned records for cleanup."""
    context = memory_context
    journal = context["journal"]
    owner = context["owners"][0]
    target = await enabled_receipt(context)
    if scope == "owner":
        await bulk_owned_records(context, owner, target, 1000)
    else:
        for other in context["owners"][1:11]:
            receipt = await enabled_receipt(context, owner=other)
            await bulk_owned_records(context, other, receipt, 1000)
        assert await journal.list(owner) == []
    with pytest.raises(MemoryPolicyError, match="memory_limit"):
        await journal.create_manual(owner, target.id, "above cap")


@pytest.mark.asyncio
async def test_runtime_privileges_keep_receipt_and_owner_identity_immutable(
    memory_context,
):
    """Verify actual app grants reject identity mutation/TRUNCATE while allowing only declared mutable fields."""
    context = memory_context
    journal = context["journal"]
    owner = context["owners"][0]
    receipt = await enabled_receipt(context)
    record = await journal.create_manual(owner, receipt.id, "immutable owner")
    async with context["sessions"]() as session, session.begin():
        permissions = (
            await session.execute(
                text(
                    "SELECT has_table_privilege(current_user,'assistant.memories','TRUNCATE'),has_column_privilege(current_user,'assistant.memories','owner_id','UPDATE'),has_column_privilege(current_user,'assistant.memories','text','UPDATE'),has_column_privilege(current_user,'assistant.memory_consents','expires_at','UPDATE'),has_column_privilege(current_user,'assistant.memory_consents','revoked_at','UPDATE')"
                )
            )
        ).one()
        assert tuple(permissions) == (False, False, True, False, True)
        with pytest.raises(DBAPIError):
            async with session.begin_nested():
                await session.execute(
                    text("UPDATE assistant.memories SET owner_id=:owner WHERE id=:id"),
                    dict(owner=context["owners"][1], id=record.id),
                )
    assert (await journal.inspect(owner, record.id)).owner_id == owner
