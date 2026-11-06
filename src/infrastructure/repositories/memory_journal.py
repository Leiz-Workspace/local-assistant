"""Persist owner-scoped consent controls and bounded manual memory in fresh serialized PostgreSQL transactions."""

import hashlib
import json
import logging
from datetime import timedelta
from uuid import UUID, uuid4

from sqlalchemy import text

from src.application.services.memory_contract import (
    MemoryBundle,
    MemoryConsent,
    MemoryPolicyError,
    MemoryRecord,
    MemorySettings,
    authorize_memory,
)

logger = logging.getLogger(__name__)


def typed_owner(owner):
    """Reject untyped principal arguments before any database operation."""
    if not isinstance(owner, UUID):
        raise MemoryPolicyError("memory_owner_invalid")
    return owner


def record_values(record):
    """Serialize exact typed record fields while encoding nested UUID provenance as JSON strings."""
    record = MemoryRecord.model_validate(record)
    values = record.model_dump()
    values["provenance"] = json.dumps(
        record.model_dump(mode="json")["provenance"],
        ensure_ascii=False,
        allow_nan=False,
    )
    return values


def record_from_row(row):
    """Decode only persisted provenance UUID strings while retaining strict SQL field and JSON shape validation."""
    values = dict(row)
    provenance = values.get("provenance")
    if isinstance(provenance, dict):
        provenance = dict(provenance)
        kind = provenance.get("kind")
        fields = (
            {
                "conversation_message": ("conversation_id", "message_id"),
                "file_quote": ("file_id",),
            }.get(kind, ())
            if isinstance(kind, str)
            else ()
        )
        for field in fields:
            value = provenance.get(field)
            if isinstance(value, str):
                provenance[field] = UUID(value)
        values["provenance"] = provenance
    record = MemoryRecord.model_validate(values)
    logger.info("memory_record_decoded")
    return record


class PostgresMemoryJournal:
    """Serialize owner controls and consented manual records without implicit extraction or model prompt use."""

    def __init__(self, sessions):
        """Reuse the existing bounded runtime pool without acquiring a new credential or opening resources."""
        self.sessions = sessions

    async def _now(self, session):
        """Read DB wall time after locks rather than a potentially stale transaction-start timestamp."""
        return await session.scalar(text("SELECT clock_timestamp()"))

    async def _settings(self, session, owner, *, lock=False):
        """Read only one authenticated owner's settings with optional mutation serialization."""
        return (
            (
                await session.execute(
                    text(
                        "SELECT * FROM assistant.memory_settings WHERE owner_id=:owner"
                        + (" FOR UPDATE" if lock else "")
                    ),
                    dict(owner=typed_owner(owner)),
                )
            )
            .mappings()
            .one_or_none()
        )

    async def _session_scope(self, session, owner, kind, scope):
        """Fence session capture against the existing active owned conversation without adopting legacy rows."""
        if kind == "session":
            found = await session.scalar(
                text(
                    "SELECT id FROM assistant.conversations WHERE id=:scope "
                    "AND metadata->>'owner_id'=:owner AND status='active' "
                    "AND deleted_at IS NULL FOR UPDATE"
                ),
                dict(scope=scope, owner=str(owner)),
            )
            if found is None:
                raise MemoryPolicyError("memory_scope_not_found")

    async def settings(self, owner):
        """Inspect current settings or an inert bootstrap revision without creating implicit consent."""
        async with self.sessions() as session:
            row = await self._settings(session, owner)
        logger.info("memory_settings_inspected initialized=%s", row is not None)
        return (
            dict(row)
            if row is not None
            else dict(
                owner_id=owner,
                revision=0,
                enabled=False,
                extraction_enabled=False,
                updated_at=None,
            )
        )

    async def configure(self, owner, *, expected_revision, enabled, extraction_enabled):
        """Create or compare-and-swap settings and invalidate old consent epochs on every explicit change."""
        typed_owner(owner)
        if type(expected_revision) is not int or expected_revision < 0:
            raise MemoryPolicyError("memory_revision_invalid")
        async with self.sessions() as session, session.begin():
            current = await self._settings(session, owner, lock=True)
            if (
                current is None
                and expected_revision != 0
                or current is not None
                and current["revision"] != expected_revision
            ):
                raise MemoryPolicyError("memory_conflict")
            now = await self._now(session)
            try:
                settings = MemorySettings(
                    owner_id=owner,
                    revision=expected_revision + 1,
                    enabled=enabled,
                    extraction_enabled=extraction_enabled,
                    updated_at=now,
                )
            except ValueError:
                raise MemoryPolicyError("memory_settings_invalid") from None
            if current is None:
                row = (
                    (
                        await session.execute(
                            text(
                                "INSERT INTO assistant.memory_settings(owner_id,revision,enabled,extraction_enabled,updated_at) VALUES (:owner_id,:revision,:enabled,:extraction_enabled,:updated_at) ON CONFLICT DO NOTHING RETURNING *"
                            ),
                            settings.model_dump(),
                        )
                    )
                    .mappings()
                    .one_or_none()
                )
                if row is None:
                    raise MemoryPolicyError("memory_conflict")
            else:
                row = (
                    (
                        await session.execute(
                            text(
                                "UPDATE assistant.memory_settings SET revision=:revision,enabled=:enabled,extraction_enabled=:extraction_enabled,updated_at=:updated_at WHERE owner_id=:owner_id RETURNING *"
                            ),
                            settings.model_dump(),
                        )
                    )
                    .mappings()
                    .one()
                )
        logger.info(
            "memory_settings_configured enabled=%s extraction=%s",
            enabled,
            extraction_enabled,
        )
        return dict(row)

    async def grant(
        self,
        owner,
        *,
        kind,
        scope_id=None,
        expected_revision,
        seconds,
        allow_extraction=False,
    ):
        """Issue a new bounded receipt only under explicit current owner settings and verified session scope."""
        typed_owner(owner)
        scope_id = (
            owner
            if scope_id is None and kind in ("episodic", "preference")
            else scope_id
        )
        if type(seconds) is not int or not isinstance(scope_id, UUID):
            raise MemoryPolicyError("memory_consent_invalid")
        async with self.sessions() as session, session.begin():
            await session.execute(text("SELECT pg_advisory_xact_lock(1146310990,30)"))
            settings = await self._settings(session, owner, lock=True)
            if settings is None or not settings["enabled"]:
                raise MemoryPolicyError("memory_disabled")
            if (
                type(expected_revision) is not int
                or settings["revision"] != expected_revision
            ):
                raise MemoryPolicyError("memory_conflict")
            if allow_extraction and not settings["extraction_enabled"]:
                raise MemoryPolicyError("memory_extraction_disabled")
            counts = (
                await session.execute(
                    text(
                        "SELECT count(*),count(*) FILTER (WHERE owner_id=:owner) FROM assistant.memory_consents"
                    ),
                    dict(owner=owner),
                )
            ).one()
            if counts[0] >= 10000 or counts[1] >= 1000:
                raise MemoryPolicyError("memory_consent_limit")
            now = await self._now(session)
            try:
                consent = MemoryConsent(
                    id=uuid4(),
                    owner_id=owner,
                    kind=kind,
                    scope_id=scope_id,
                    settings_revision=settings["revision"],
                    allow_extraction=allow_extraction,
                    granted_at=now,
                    expires_at=now + timedelta(seconds=seconds),
                )
            except (ValueError, OverflowError):
                raise MemoryPolicyError("memory_consent_invalid") from None
            await self._session_scope(session, owner, kind, scope_id)
            row = (
                (
                    await session.execute(
                        text(
                            "INSERT INTO assistant.memory_consents(id,owner_id,kind,scope_id,settings_revision,policy_version,allow_extraction,granted_at,expires_at,revoked_at) VALUES (:id,:owner_id,:kind,:scope_id,:settings_revision,:policy_version,:allow_extraction,:granted_at,:expires_at,:revoked_at) RETURNING *"
                        ),
                        consent.model_dump(),
                    )
                )
                .mappings()
                .one()
            )
        logger.info(
            "memory_consent_granted kind=%s extraction=%s", kind, allow_extraction
        )
        return MemoryConsent.model_validate(dict(row))

    async def revoke(self, owner, consent_id):
        """Idempotently revoke only an owned receipt even when memory use is disabled."""
        async with self.sessions() as session, session.begin():
            if await self._settings(session, owner, lock=True) is None:
                raise MemoryPolicyError("memory_not_found")
            row = (
                (
                    await session.execute(
                        text(
                            "UPDATE assistant.memory_consents SET revoked_at=COALESCE(revoked_at,clock_timestamp()) WHERE owner_id=:owner AND id=:id RETURNING *"
                        ),
                        dict(owner=owner, id=consent_id),
                    )
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                raise MemoryPolicyError("memory_not_found")
        logger.info("memory_consent_revoked")
        return MemoryConsent.model_validate(dict(row))

    async def _receipt(self, session, owner, consent_id, settings, now):
        """Lock a current live receipt after its owner settings lock and reject inactive epochs before capture."""
        row = (
            (
                await session.execute(
                    text(
                        "SELECT * FROM assistant.memory_consents WHERE owner_id=:owner AND id=:id FOR UPDATE"
                    ),
                    dict(owner=owner, id=consent_id),
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise MemoryPolicyError("memory_not_found")
        consent = MemoryConsent.model_validate(dict(row))
        if not settings or not settings["enabled"]:
            raise MemoryPolicyError("memory_disabled")
        if (
            consent.settings_revision != settings["revision"]
            or consent.revoked_at is not None
            or not consent.granted_at <= now < consent.expires_at
        ):
            raise MemoryPolicyError("memory_consent_inactive")
        await self._session_scope(session, owner, consent.kind, consent.scope_id)
        return consent

    def _manual(self, owner, consent, value, now, *, previous=None, seconds=None):
        """Build server-authored exact manual provenance and bounded expiry without accepting caller source metadata."""
        if not isinstance(value, str) or type(seconds) not in (int, type(None)):
            raise MemoryPolicyError("memory_text_invalid")
        try:
            expiry = previous.expires_at if previous is not None else consent.expires_at
            if seconds is not None:
                expiry = now + timedelta(seconds=seconds)
                if seconds <= 0 or expiry > consent.expires_at:
                    raise ValueError("retention")
            record = MemoryRecord(
                id=previous.id if previous is not None else uuid4(),
                owner_id=owner,
                kind=consent.kind,
                scope_id=consent.scope_id,
                consent_id=consent.id,
                text=value,
                method="manual",
                model_id=None,
                provenance=dict(
                    kind="manual",
                    content_sha256=hashlib.sha256(value.encode()).hexdigest(),
                ),
                created_at=previous.created_at if previous is not None else now,
                updated_at=now,
                expires_at=expiry,
                version=previous.version + 1 if previous is not None else 1,
            )
        except (ValueError, OverflowError):
            raise MemoryPolicyError("memory_record_invalid") from None
        return record

    async def create_manual(self, owner, consent_id, value, *, seconds=None):
        """Atomically admit one bounded manual memory after global quota, owner and receipt serialization."""
        typed_owner(owner)
        async with self.sessions() as session, session.begin():
            await session.execute(text("SELECT pg_advisory_xact_lock(1146310990,30)"))
            settings = await self._settings(session, owner, lock=True)
            now = await self._now(session)
            consent = await self._receipt(session, owner, consent_id, settings, now)
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
            record = self._manual(owner, consent, value, now, seconds=seconds)
            authorize_memory(
                MemoryBundle(settings=dict(settings), consent=consent, record=record),
                owner,
                now,
                action="write",
            )
            values = record_values(record)
            await session.execute(
                text(
                    "INSERT INTO assistant.memories(id,owner_id,kind,scope_id,consent_id,text,method,model_id,provenance,content_trust,created_at,updated_at,expires_at,version) VALUES (:id,:owner_id,:kind,:scope_id,:consent_id,:text,:method,:model_id,CAST(:provenance AS jsonb),:content_trust,:created_at,:updated_at,:expires_at,:version)"
                ),
                values,
            )
        logger.info("memory_manual_created kind=%s", record.kind)
        return record

    async def inspect(self, owner, record_id):
        """Return only an owned record for explicit management independently of consent/use enablement."""
        async with self.sessions() as session:
            row = (
                (
                    await session.execute(
                        text(
                            "SELECT * FROM assistant.memories WHERE owner_id=:owner AND id=:id"
                        ),
                        dict(owner=typed_owner(owner), id=record_id),
                    )
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            raise MemoryPolicyError("memory_not_found")
        logger.info("memory_record_inspected")
        return record_from_row(row)

    async def list(self, owner, *, limit=50, after=None):
        """List bounded owned record metadata without exposing full private text/provenance in a bulk response."""
        if (
            type(limit) is not int
            or not 1 <= limit <= 100
            or after is not None
            and not isinstance(after, UUID)
        ):
            raise MemoryPolicyError("memory_list_invalid")
        async with self.sessions() as session:
            rows = (
                (
                    await session.execute(
                        text(
                            "SELECT id,kind,scope_id,method,expires_at,version FROM assistant.memories WHERE owner_id=:owner AND (CAST(:after AS uuid) IS NULL OR id>CAST(:after AS uuid)) ORDER BY id LIMIT :limit"
                        ),
                        dict(owner=typed_owner(owner), after=after, limit=limit),
                    )
                )
                .mappings()
                .all()
            )
        logger.info("memory_records_listed count=%d", len(rows))
        return [dict(row) for row in rows]

    async def edit_manual(self, owner, record_id, value, *, expected_version):
        """Replace private content with exact manual provenance under still-current consent and version fencing."""
        if type(expected_version) is not int or expected_version < 1:
            raise MemoryPolicyError("memory_revision_invalid")
        async with self.sessions() as session, session.begin():
            settings = await self._settings(session, owner, lock=True)
            row = (
                (
                    await session.execute(
                        text(
                            "SELECT * FROM assistant.memories WHERE owner_id=:owner AND id=:id FOR UPDATE"
                        ),
                        dict(owner=owner, id=record_id),
                    )
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                raise MemoryPolicyError("memory_not_found")
            previous = record_from_row(row)
            if previous.version != expected_version:
                raise MemoryPolicyError("memory_conflict")
            now = await self._now(session)
            consent = await self._receipt(
                session, owner, previous.consent_id, settings, now
            )
            authorize_memory(
                MemoryBundle(settings=dict(settings), consent=consent, record=previous),
                owner,
                now,
                action="use",
            )
            record = self._manual(owner, consent, value, now, previous=previous)
            authorize_memory(
                MemoryBundle(settings=dict(settings), consent=consent, record=record),
                owner,
                now,
                action="write",
            )
            await session.execute(
                text(
                    "UPDATE assistant.memories SET text=:text,method=:method,model_id=:model_id,provenance=CAST(:provenance AS jsonb),updated_at=:updated_at,expires_at=:expires_at,version=:version WHERE owner_id=:owner_id AND id=:id"
                ),
                record_values(record),
            )
        logger.info("memory_manual_edited")
        return record

    async def delete(self, owner, record_id, *, expected_version):
        """Hard-delete only an owned expected record version without requiring memory enabled or active consent."""
        if type(expected_version) is not int or expected_version < 1:
            raise MemoryPolicyError("memory_revision_invalid")
        async with self.sessions() as session, session.begin():
            await self._settings(session, owner, lock=True)
            row = (
                await session.execute(
                    text(
                        "SELECT version FROM assistant.memories WHERE owner_id=:owner AND id=:id FOR UPDATE"
                    ),
                    dict(owner=owner, id=record_id),
                )
            ).one_or_none()
            if row is None:
                raise MemoryPolicyError("memory_not_found")
            if row[0] != expected_version:
                raise MemoryPolicyError("memory_conflict")
            await session.execute(
                text("DELETE FROM assistant.memories WHERE owner_id=:owner AND id=:id"),
                dict(owner=owner, id=record_id),
            )
        logger.info("memory_record_deleted")

    async def purge_expired(self, owner, *, limit=100):
        """Delete a bounded owned expired batch without modifying sources, history or vector collections."""
        if type(limit) is not int or not 1 <= limit <= 100:
            raise MemoryPolicyError("memory_list_invalid")
        async with self.sessions() as session, session.begin():
            await self._settings(session, owner, lock=True)
            rows = (
                await session.execute(
                    text(
                        "DELETE FROM assistant.memories WHERE owner_id=:owner AND id IN (SELECT id FROM assistant.memories WHERE owner_id=:owner AND expires_at<=clock_timestamp() ORDER BY expires_at,id LIMIT :limit) RETURNING id"
                    ),
                    dict(owner=owner, limit=limit),
                )
            ).all()
        logger.info("memory_expired_purged count=%d", len(rows))
        return len(rows)
