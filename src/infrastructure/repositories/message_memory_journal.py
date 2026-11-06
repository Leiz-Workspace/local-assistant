"""Extend accepted memory controls with fresh owned user-message capture fences and bounded retention transactions."""

import hashlib
import json
import logging
from uuid import UUID, uuid4

from sqlalchemy import text

from src.application.services.memory_contract import (
    MemoryBundle,
    MemoryPolicyError,
    MemoryRecord,
    authorize_memory,
)
from src.application.services.memory_export import memory_export_payload
from src.application.services.memory_selection import (
    MessageMemorySource,
    parse_selection,
)
from src.infrastructure.repositories.memory_journal import (
    PostgresMemoryJournal,
    record_from_row,
    record_values,
    typed_owner,
)

logger = logging.getLogger(__name__)


class PostgresMessageMemoryJournal(PostgresMemoryJournal):
    """Reuse manual controls while adding explicit source authority and bounded cleanup without source/history mutations."""

    async def _bounded(self, session):
        """Apply transaction-local statement and lock budgets without altering shared database defaults."""
        await session.execute(text("SET LOCAL lock_timeout='5s'"))
        await session.execute(text("SET LOCAL statement_timeout='10s'"))

    async def _settings(self, session, owner, *, lock=False):
        """Bound owner/source lock waits and SQL statements before following the accepted owner lock protocol."""
        typed_owner(owner)
        await self._bounded(session)
        return await super()._settings(session, owner, lock=lock)

    async def _message_source(self, session, owner, conversation_id, message_id):
        """Lock active owned conversation then user message and avoid retrieving oversized source content."""
        if not isinstance(conversation_id, UUID) or not isinstance(message_id, UUID):
            raise MemoryPolicyError("memory_source_invalid")
        conversation = await session.scalar(
            text(
                "SELECT id FROM assistant.conversations WHERE id=:id AND metadata->>'owner_id'=:owner AND status='active' AND deleted_at IS NULL FOR UPDATE"
            ),
            dict(id=conversation_id, owner=str(owner)),
        )
        if conversation is None:
            raise MemoryPolicyError("memory_source_not_found")
        row = (
            (
                await session.execute(
                    text(
                        "SELECT id,conversation_id,CASE WHEN octet_length(content)<=8192 THEN content ELSE NULL END AS content,octet_length(content) AS bytes FROM assistant.messages WHERE id=:id AND conversation_id=:conversation AND role='user' FOR SHARE"
                    ),
                    dict(id=message_id, conversation=conversation_id),
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise MemoryPolicyError("memory_source_not_found")
        if row["bytes"] > 8192:
            raise MemoryPolicyError("memory_source_limit")
        return MessageMemorySource(
            row["conversation_id"],
            row["id"],
            hashlib.sha256(row["content"].encode()).hexdigest(),
            row["content"],
        )

    async def _revalidate_source(self, session, owner, source):
        """Turn a missing, oversized or changed previously authorized message into a stable capture fence."""
        if not isinstance(source, MessageMemorySource):
            raise MemoryPolicyError("memory_source_invalid")
        try:
            current = await self._message_source(
                session, owner, source.conversation_id, source.message_id
            )
        except MemoryPolicyError as error:
            if error.code in {"memory_source_not_found", "memory_source_limit"}:
                raise MemoryPolicyError("memory_source_changed") from None
            raise
        if current != source:
            raise MemoryPolicyError("memory_source_changed")
        return current

    async def preflight_selection(self, owner, consent_id, conversation_id, message_id):
        """Require independent extraction consent and actual source ownership before any model call."""
        async with self.sessions() as session, session.begin():
            settings = await self._settings(session, owner, lock=True)
            now = await self._now(session)
            consent = await self._receipt(session, owner, consent_id, settings, now)
            if not settings["extraction_enabled"] or not consent.allow_extraction:
                raise MemoryPolicyError("memory_extraction_disabled")
            if consent.kind == "session" and consent.scope_id != conversation_id:
                raise MemoryPolicyError("memory_scope_invalid")
            source = await self._message_source(
                session, owner, conversation_id, message_id
            )
            if await self._now(session) >= consent.expires_at:
                raise MemoryPolicyError("memory_consent_inactive")
        logger.info("memory_selection_preflight_authorized kind=%s", consent.kind)
        return consent, source

    async def capture_selection(self, owner, consent_id, source, quote, model_id):
        """Revalidate source/consent and atomically persist the exact selected quote with verified producer identity."""
        if not isinstance(source, MessageMemorySource):
            raise MemoryPolicyError("memory_source_invalid")
        async with self.sessions() as session, session.begin():
            await self._bounded(session)
            await session.execute(text("SELECT pg_advisory_xact_lock(1146310990,30)"))
            settings = await self._settings(session, owner, lock=True)
            now = await self._now(session)
            consent = await self._receipt(session, owner, consent_id, settings, now)
            if not settings["extraction_enabled"] or not consent.allow_extraction:
                raise MemoryPolicyError("memory_extraction_disabled")
            current = await self._revalidate_source(session, owner, source)
            parse_selection(
                json.dumps(dict(status="selected", quote=quote), ensure_ascii=False),
                current,
            )
            counts = (
                await session.execute(
                    text(
                        "SELECT count(*),count(*) FILTER (WHERE owner_id=:owner) FROM assistant.memories"
                    ),
                    dict(owner=owner),
                )
            ).one()
            if counts[0] >= 10000 or counts[1] >= 1000:
                raise MemoryPolicyError("memory_limit")
            now = await self._now(session)
            if now >= consent.expires_at:
                raise MemoryPolicyError("memory_consent_inactive")
            start = current.text.find(quote)
            record = MemoryRecord(
                id=uuid4(),
                owner_id=owner,
                kind=consent.kind,
                scope_id=consent.scope_id,
                consent_id=consent.id,
                text=quote,
                method="extracted",
                model_id=model_id,
                provenance=dict(
                    kind="conversation_message",
                    conversation_id=current.conversation_id,
                    message_id=current.message_id,
                    role="user",
                    content_sha256=current.content_sha256,
                    quote=quote,
                    start=start,
                    end=start + len(quote),
                ),
                created_at=now,
                updated_at=now,
                expires_at=consent.expires_at,
            )
            authorize_memory(
                MemoryBundle(settings=dict(settings), consent=consent, record=record),
                owner,
                now,
                action="write",
            )
            await session.execute(
                text(
                    "INSERT INTO assistant.memories(id,owner_id,kind,scope_id,consent_id,text,method,model_id,provenance,content_trust,created_at,updated_at,expires_at,version) VALUES (:id,:owner_id,:kind,:scope_id,:consent_id,:text,:method,:model_id,CAST(:provenance AS jsonb),:content_trust,:created_at,:updated_at,:expires_at,:version)"
                ),
                record_values(record),
            )
        logger.info("memory_selected_quote_captured kind=%s", record.kind)
        return record

    async def validate_selection(self, owner, consent_id, source, record=None):
        """Authorize current source/consent and exact record version immediately before generated response headers."""
        async with self.sessions() as session, session.begin():
            settings = await self._settings(session, owner, lock=True)
            now = await self._now(session)
            consent = await self._receipt(session, owner, consent_id, settings, now)
            await self._revalidate_source(session, owner, source)
            if await self._now(session) >= consent.expires_at:
                raise MemoryPolicyError("memory_consent_inactive")
            if record is not None:
                version = await session.scalar(
                    text(
                        "SELECT version FROM assistant.memories WHERE owner_id=:owner AND id=:id FOR SHARE"
                    ),
                    dict(owner=owner, id=record.id),
                )
                if version != record.version:
                    raise MemoryPolicyError("memory_source_changed")
                authorize_memory(
                    MemoryBundle(
                        settings=dict(settings), consent=consent, record=record
                    ),
                    owner,
                    await self._now(session),
                    action="use",
                )
        logger.info("memory_selection_delivery_authorized")

    async def retention_owners(self, after=None, *, limit=10):
        """Read one rotating bounded page of owner identities without source text or implicit owner creation."""
        if (
            type(limit) is not int
            or not 1 <= limit <= 10
            or after is not None
            and not isinstance(after, UUID)
        ):
            raise MemoryPolicyError("memory_list_invalid")
        async with self.sessions() as session, session.begin():
            await session.execute(text("SET LOCAL statement_timeout='10s'"))
            rows = (
                await session.execute(
                    text(
                        "SELECT owner_id FROM assistant.memory_settings WHERE CAST(:after AS uuid) IS NULL OR owner_id>CAST(:after AS uuid) ORDER BY owner_id LIMIT :limit"
                    ),
                    dict(after=after, limit=limit),
                )
            ).all()
        logger.info("memory_retention_owners_selected count=%d", len(rows))
        return [row[0] for row in rows]

    async def purge_owner(self, owner, *, limit=100):
        """Delete bounded expired records and only orphan inactive receipts under the owner control lock."""
        if type(limit) is not int or not 1 <= limit <= 100:
            raise MemoryPolicyError("memory_list_invalid")
        async with self.sessions() as session, session.begin():
            settings = await self._settings(session, owner, lock=True)
            if settings is None:
                return dict(records=0, receipts=0)
            records = (
                await session.execute(
                    text(
                        "DELETE FROM assistant.memories WHERE owner_id=:owner AND id IN (SELECT id FROM assistant.memories WHERE owner_id=:owner AND expires_at<=clock_timestamp() ORDER BY expires_at,id LIMIT :limit) RETURNING id"
                    ),
                    dict(owner=owner, limit=limit),
                )
            ).all()
            receipts = (
                await session.execute(
                    text(
                        "DELETE FROM assistant.memory_consents WHERE owner_id=:owner AND id IN (SELECT c.id FROM assistant.memory_consents c WHERE c.owner_id=:owner AND (c.revoked_at IS NOT NULL OR c.expires_at<=clock_timestamp() OR c.settings_revision<>:revision) AND NOT EXISTS (SELECT 1 FROM assistant.memories m WHERE m.consent_id=c.id) ORDER BY c.id LIMIT :limit) RETURNING id"
                    ),
                    dict(owner=owner, revision=settings["revision"], limit=limit),
                )
            ).all()
        logger.info(
            "memory_retention_purged records=%d receipts=%d",
            len(records),
            len(receipts),
        )
        return dict(records=len(records), receipts=len(receipts))

    async def export(self, owner):
        """Read one consistent bounded principal-only snapshot even when owner use or consent is inactive."""
        typed_owner(owner)
        async with self.sessions() as session, session.begin():
            await session.execute(
                text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
            )
            settings = await self._settings(session, owner)
            consents = (
                (
                    await session.execute(
                        text(
                            "SELECT * FROM assistant.memory_consents WHERE owner_id=:owner ORDER BY id LIMIT 1001"
                        ),
                        dict(owner=owner),
                    )
                )
                .mappings()
                .all()
            )
            records = (
                (
                    await session.execute(
                        text(
                            "SELECT * FROM assistant.memories WHERE owner_id=:owner ORDER BY id LIMIT 1001"
                        ),
                        dict(owner=owner),
                    )
                )
                .mappings()
                .all()
            )
            observed_at = await self._now(session)
            if len(consents) > 1000 or len(records) > 1000:
                raise MemoryPolicyError("memory_export_limit")
            payload = memory_export_payload(
                dict(settings)
                if settings is not None
                else dict(
                    owner_id=owner,
                    revision=0,
                    enabled=False,
                    extraction_enabled=False,
                    updated_at=None,
                ),
                [dict(row) for row in consents],
                [record_from_row(row) for row in records],
                observed_at,
            )
        logger.info("memory_owner_export_completed")
        return payload
