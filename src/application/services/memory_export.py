"""Build bounded explicit owner-memory exports without authorizing model use or including source content."""

import json
import logging
from typing import Any

from pydantic import TypeAdapter

from src.application.services.memory_contract import MemoryPolicyError

logger = logging.getLogger(__name__)
MAX_EXPORT_BYTES = 12 * 1024 * 1024


def memory_export_payload(settings, consents, records, observed_at):
    """Serialize one complete bounded owner snapshot and refuse oversized inventories without truncation."""
    if len(consents) > 1000 or len(records) > 1000:
        raise MemoryPolicyError("memory_export_limit")
    payload = TypeAdapter(Any).dump_python(
        dict(
            format="local-assistant-memory-v1",
            observed_at=observed_at,
            content_trust="untrusted",
            settings=settings,
            consents=consents,
            records=records,
        ),
        mode="json",
    )
    encoded = json.dumps(
        payload, ensure_ascii=False, allow_nan=False, separators=(",", ":")
    ).encode()
    if len(encoded) > MAX_EXPORT_BYTES:
        raise MemoryPolicyError("memory_export_limit")
    logger.info(
        "memory_export_prepared consents=%d records=%d bytes=%d",
        len(consents),
        len(records),
        len(encoded),
    )
    return payload
