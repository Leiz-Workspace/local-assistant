"""Initialize optional file resources only after explicit operator enablement and schema validation."""

import logging
import os
from pathlib import Path

from sqlalchemy import text

from apps.api.core.conversation_auth import load_principals
from apps.api.services.files import FileService, file_io
from src.infrastructure.local_blob_storage import LocalBlobStorage
from src.infrastructure.repositories.file_journal import PostgresFileJournal

logger = logging.getLogger(__name__)


async def initialize_file_service(session_factory):
    """Validate V002 and create a dedicated root only when ASSISTANT_FILES_ENABLED=1."""
    if os.environ.get("ASSISTANT_FILES_ENABLED", "0") != "1":
        logger.info("file_storage_disabled")
        return None
    async with session_factory() as session:
        revision = await session.scalar(
            text("SELECT version_num FROM assistant.alembic_version")
        )
        if revision != "0002":
            raise RuntimeError("File storage requires reviewed V002 schema")
    root = Path(
        os.environ.get(
            "ASSISTANT_FILES_ROOT",
            str(Path(__file__).resolve().parents[3] / "data/files"),
        )
    )
    storage = await file_io(LocalBlobStorage, root, close_result=True)
    try:
        auth_path = os.environ.get("ASSISTANT_AUTH_FILE")
        if not auth_path:
            raise RuntimeError("File storage requires principal bindings")
        bindings = await file_io(load_principals, Path(auth_path))
        owners = list(set(bindings.values()))
        async with session_factory() as session:
            incompatible = await session.scalar(
                text(
                    "SELECT count(*) FROM assistant.files WHERE owner_id=ANY(:owners) "
                    "AND quota_released_at IS NULL AND policy_snapshot->>'_storage_namespace' IS DISTINCT FROM :namespace"
                ),
                {"owners": owners, "namespace": str(storage.namespace_id)},
            )
            if incompatible:
                logger.error("file_storage_root_namespace_mismatch")
                raise RuntimeError(
                    "File storage root does not match existing allocations"
                )
    except BaseException:
        await file_io(storage.close)
        raise
    service = FileService(PostgresFileJournal(session_factory), storage)
    try:
        await service.start()
    except BaseException:
        await service.shutdown()
        raise
    logger.info("file_storage_initialized")
    return service
