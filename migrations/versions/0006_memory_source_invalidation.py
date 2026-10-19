"""Invalidate only dependent message/session memory atomically with source mutation without rewriting existing data."""

import logging

from alembic import op
from sqlalchemy import text

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None
logger = logging.getLogger(__name__)

SOURCE_INVALIDATION_DDL = """
CREATE INDEX ix_memories_source_conversation ON assistant.memories
    ((provenance->>'conversation_id')) WHERE provenance->>'kind'='conversation_message';
CREATE INDEX ix_memories_source_message ON assistant.memories
    ((provenance->>'message_id')) WHERE provenance->>'kind'='conversation_message';

CREATE FUNCTION assistant.invalidate_conversation_memory() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog,assistant AS $$
DECLARE removed integer;
BEGIN
    IF TG_OP='UPDATE' THEN
        IF NOT (NEW.deleted_at IS NOT NULL AND OLD.deleted_at IS NULL)
            AND NEW.metadata->>'owner_id' IS NOT DISTINCT FROM OLD.metadata->>'owner_id'
            AND NEW.id IS NOT DISTINCT FROM OLD.id THEN
            RETURN NEW;
        END IF;
    END IF;
    DELETE FROM assistant.memories
    WHERE (provenance->>'kind'='conversation_message' AND provenance->>'conversation_id'=OLD.id::text)
       OR (kind='session' AND scope_id=OLD.id);
    GET DIAGNOSTICS removed = ROW_COUNT;
    DELETE FROM assistant.memory_consents c
    WHERE c.kind='session' AND c.scope_id=OLD.id
      AND NOT EXISTS (SELECT 1 FROM assistant.memories m WHERE m.consent_id=c.id);
    IF removed>0 THEN
        RAISE LOG 'memory_source_invalidated kind=conversation records=%',removed;
    END IF;
    IF TG_OP='DELETE' THEN RETURN OLD; END IF;
    RETURN NEW;
END;
$$;
COMMENT ON FUNCTION assistant.invalidate_conversation_memory() IS
    'Remove only exact conversation-derived and session-scoped memory in the source transaction.';
REVOKE ALL ON FUNCTION assistant.invalidate_conversation_memory() FROM PUBLIC;
CREATE TRIGGER invalidate_conversation_memory BEFORE UPDATE OR DELETE ON assistant.conversations
    FOR EACH ROW EXECUTE FUNCTION assistant.invalidate_conversation_memory();

CREATE FUNCTION assistant.invalidate_message_memory() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog,assistant AS $$
DECLARE removed integer;
BEGIN
    IF TG_OP='UPDATE' THEN
        IF NEW.content IS NOT DISTINCT FROM OLD.content
            AND NEW.role IS NOT DISTINCT FROM OLD.role
            AND NEW.conversation_id IS NOT DISTINCT FROM OLD.conversation_id
            AND NEW.id IS NOT DISTINCT FROM OLD.id THEN
            RETURN NEW;
        END IF;
    END IF;
    DELETE FROM assistant.memories
    WHERE provenance->>'kind'='conversation_message'
      AND provenance->>'message_id'=OLD.id::text
      AND provenance->>'conversation_id'=OLD.conversation_id::text;
    GET DIAGNOSTICS removed = ROW_COUNT;
    IF removed>0 THEN
        RAISE LOG 'memory_source_invalidated kind=message records=%',removed;
    END IF;
    IF TG_OP='DELETE' THEN RETURN OLD; END IF;
    RETURN NEW;
END;
$$;
COMMENT ON FUNCTION assistant.invalidate_message_memory() IS
    'Remove only exact previous message-provenance memory atomically with source deletion or meaningful mutation.';
REVOKE ALL ON FUNCTION assistant.invalidate_message_memory() FROM PUBLIC;
CREATE TRIGGER invalidate_message_memory BEFORE UPDATE OR DELETE ON assistant.messages
    FOR EACH ROW EXECUTE FUNCTION assistant.invalidate_message_memory();
"""


def upgrade():
    """Require an empty local memory inventory before enabling reviewed transactional source privacy fences."""
    op.execute(text("SET LOCAL lock_timeout='5s'"))
    op.execute(text("SET LOCAL statement_timeout='30s'"))
    op.execute(
        text(
            "LOCK TABLE assistant.memories,assistant.memory_consents,assistant.memory_settings IN ACCESS EXCLUSIVE MODE"
        )
    )
    op.execute(
        text(
            "DO $$ BEGIN IF EXISTS (SELECT 1 FROM assistant.memories) OR EXISTS (SELECT 1 FROM assistant.memory_consents) OR EXISTS (SELECT 1 FROM assistant.memory_settings) THEN RAISE EXCEPTION 'Memory privacy rollout requires an audited populated-data plan'; END IF; END $$"
        )
    )
    op.execute(text(SOURCE_INVALIDATION_DDL))
    logger.info("memory_source_invalidation_migration_applied revision=0006")


def downgrade():
    """Remove only source-fence objects after operator drain without resurrecting deleted private memories."""
    op.execute(text("SET LOCAL lock_timeout='5s'"))
    op.execute(text("SET LOCAL statement_timeout='30s'"))
    op.execute(text("DROP TRIGGER invalidate_message_memory ON assistant.messages"))
    op.execute(
        text("DROP TRIGGER invalidate_conversation_memory ON assistant.conversations")
    )
    op.execute(text("DROP FUNCTION assistant.invalidate_message_memory()"))
    op.execute(text("DROP FUNCTION assistant.invalidate_conversation_memory()"))
    op.execute(text("DROP INDEX assistant.ix_memories_source_message"))
    op.execute(text("DROP INDEX assistant.ix_memories_source_conversation"))
    logger.info("memory_source_invalidation_migration_removed revision=0005")
