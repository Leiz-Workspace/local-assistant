"""Initialize explicitly enabled ingestion from approved selection and private operator-delivered credentials."""

import asyncio
import hashlib
import json
import logging
import os
import stat
from pathlib import Path
from uuid import UUID

from apps.api.services.files import file_io
from apps.api.services.ingestion import IngestionService
from src.application.services.ingestion_contract import validate_model_contract
from src.infrastructure.qdrant_ingestion import QdrantIngestion

logger = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parents[3]


def read_configuration(path):
    """Read bounded owner-only regular credential material and verify the approved selected-file hash."""
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        info = os.fstat(descriptor)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_mode & 0o077
            or info.st_uid != os.getuid()
            or info.st_nlink != 1
            or not 1 <= info.st_size <= 16384
        ):
            raise ValueError("ingestion_private_configuration_required")
        data = os.read(descriptor, 16385)
        if len(data) > 16384:
            raise ValueError("ingestion_private_configuration_required")
    finally:
        os.close(descriptor)
    credentials = json.loads(data)
    if not isinstance(credentials, dict) or set(credentials) != {"owner_id", "api_key"}:
        raise ValueError("ingestion_private_configuration_invalid")
    owner = UUID(credentials["owner_id"])
    key = credentials["api_key"]
    if (
        not isinstance(key, str)
        or not 32 <= len(key) <= 512
        or any(character.isspace() for character in key)
    ):
        raise ValueError("ingestion_private_configuration_invalid")
    selected_bytes = (ROOT / "configs/embedding-selected.json").read_bytes()
    selection = json.loads(selected_bytes)
    approval_path = (ROOT / selection["approval_record"]).resolve()
    if not approval_path.is_relative_to(ROOT):
        raise ValueError("ingestion_model_approval_invalid")
    approval = json.loads(approval_path.read_text())
    if (
        approval["approval_status"] != "OWNER_APPROVED_SELECTION_APPLIED"
        or hashlib.sha256(selected_bytes).hexdigest()
        != approval["selected_configuration_sha256"]
    ):
        raise ValueError("ingestion_model_approval_invalid")
    logger.info("ingestion_operator_configuration_validated")
    return selection, owner, key


async def initialize_ingestion_service(files):
    """Keep ingestion disabled by default and start only verified approved namespace/model resources."""
    if os.environ.get("ASSISTANT_INGESTION_ENABLED", "0") != "1":
        logger.info("ingestion_disabled")
        return None
    if files is None or files.closing:
        raise RuntimeError("Ingestion requires enabled file storage")
    path = os.environ.get("ASSISTANT_INGESTION_CONFIG_FILE")
    if not path:
        raise RuntimeError("Ingestion requires private operator configuration")
    service = None
    try:
        selection, owner, key = await file_io(read_configuration, Path(path))
        validate_model_contract(selection)
        logger.info("ingestion_model_contract_validated")
        vectors = QdrantIngestion(selection, owner, key)
        service = IngestionService(files, selection, vectors)
        await service.start()
        return service
    except BaseException as error:
        if service is not None:
            await service.shutdown()
        logger.warning("ingestion_startup_failed_safely")
        if isinstance(error, asyncio.CancelledError):
            raise
        raise RuntimeError("Ingestion configuration or resources unavailable") from None
