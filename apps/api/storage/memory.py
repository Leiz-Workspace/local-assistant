"""Initialize optional memory management only with reviewed schema and least-privilege runtime sessions."""

import logging
import os

from sqlalchemy import text

from apps.api.services.memory import MemoryService
from apps.api.services.memory_extraction import MemoryExtractor
from apps.api.services.memory_retention import MemoryRetention
from src.infrastructure.repositories.message_memory_journal import (
    PostgresMessageMemoryJournal,
)

logger = logging.getLogger(__name__)


async def initialize_memory_service(sessions):
    """Keep startup inert by default and refuse unknown schema or broadened grants before serving memory."""
    if os.environ.get("ASSISTANT_MEMORY_ENABLED", "0") != "1":
        logger.info("memory_management_disabled")
        return None
    if sessions is None:
        raise RuntimeError("Memory management requires existing app sessions")
    async with sessions() as session:
        row = (
            await session.execute(
                text(
                    "SELECT (SELECT version_num FROM assistant.alembic_version),has_column_privilege(current_user,'assistant.memories','owner_id','UPDATE'),has_column_privilege(current_user,'assistant.memories','text','UPDATE'),has_column_privilege(current_user,'assistant.memory_consents','settings_revision','UPDATE'),has_column_privilege(current_user,'assistant.memory_consents','revoked_at','UPDATE'),has_table_privilege(current_user,'assistant.memories','TRUNCATE')"
                )
            )
        ).one()
        if tuple(row) != ("0006", False, True, False, True, False):
            raise RuntimeError(
                "Memory management requires reviewed V006 source privacy and least-privilege grants"
            )
    logger.info("memory_management_initialized")
    journal = PostgresMessageMemoryJournal(sessions)
    retention = MemoryRetention(journal)
    service = MemoryService(
        journal, extractor=MemoryExtractor(journal), retention=retention
    )
    retention.start()
    return service
