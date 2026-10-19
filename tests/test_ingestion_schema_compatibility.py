"""Verify ingestion accepts only reviewed V004/V005 schemas with unchanged immutable-column privileges."""

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from apps.api.services.ingestion import IngestionService
from src.application.services.file_storage_policy import StoragePolicyError


def service_for(row):
    """Provide observable schema/guard/vector boundaries without creating a model, pool or collection."""

    class Result:
        """Return an explicit schema/privilege tuple without bypassing the real start method."""

        def one(self):
            """Expose exactly the simulated PostgreSQL schema row."""
            return row

    @asynccontextmanager
    async def configured_sessions():
        """Provide the existing session protocol with a controlled one-row execution result."""
        yield SimpleNamespace(execute=AsyncMock(return_value=Result()))

    service = IngestionService.__new__(IngestionService)
    service.journal = SimpleNamespace(sessions=configured_sessions)
    service.guard = SimpleNamespace(open=AsyncMock(), close=AsyncMock())
    service.vectors = SimpleNamespace(ensure=AsyncMock())
    service.task = None
    return service


@pytest.mark.asyncio
@pytest.mark.parametrize("revision", ["0004", "0005"])
async def test_reviewed_schema_reaches_guard_and_vector_boundary(revision):
    """Admit only reviewed additive revisions after preserving both immutable and mutable grant checks."""
    service = service_for((revision, False, True))
    await service.start(background=False)
    service.guard.open.assert_awaited_once()
    service.vectors.ensure.assert_awaited_once()
    assert service.task is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "row",
    [
        (None, False, True),
        ("0003", False, True),
        ("0006", False, True),
        ("0005", True, True),
        ("0005", False, False),
    ],
)
async def test_unknown_schema_or_broadened_grants_fail_before_resources(row):
    """Refuse old/unknown schemas or privilege drift without opening worker locks or touching vectors."""
    service = service_for(row)
    with pytest.raises(StoragePolicyError, match="ingestion_schema_unavailable"):
        await service.start(background=False)
    service.guard.open.assert_not_awaited()
    service.vectors.ensure.assert_not_awaited()
