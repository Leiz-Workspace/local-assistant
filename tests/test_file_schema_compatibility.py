"""Verify file startup accepts reviewed additive migrations and refuses unknown schema before root I/O."""

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from apps.api.storage import files


class RootBoundary(Exception):
    """Mark the first root-opening call without creating storage or bypassing revision validation."""


def sessions_for(revision):
    """Provide one readonly revision result through the actual startup session protocol."""

    @asynccontextmanager
    async def sessions():
        """Yield only the schema query surface used before root initialization."""
        yield SimpleNamespace(scalar=AsyncMock(return_value=revision))

    return sessions


@pytest.mark.asyncio
@pytest.mark.parametrize("revision", ["0002", "0003", "0004"])
async def test_reviewed_additive_revision_reaches_root_boundary(monkeypatch, revision):
    """Preserve V002 file behavior while admitting reviewed additive ingestion schemas."""
    monkeypatch.setenv("ASSISTANT_FILES_ENABLED", "1")

    async def root_boundary(function, *args, **kwargs):
        """Stop before any filesystem creation after the real revision guard accepted the schema."""
        assert function is files.LocalBlobStorage and kwargs["close_result"] is True
        raise RootBoundary()

    monkeypatch.setattr(files, "file_io", root_boundary)
    with pytest.raises(RootBoundary):
        await files.initialize_file_service(sessions_for(revision))


@pytest.mark.asyncio
@pytest.mark.parametrize("revision", [None, "0001", "0005", "unreviewed"])
async def test_unknown_revision_fails_before_root_side_effect(monkeypatch, revision):
    """Reject unreviewed schemas without reading auth or opening a source storage root."""
    monkeypatch.setenv("ASSISTANT_FILES_ENABLED", "1")
    action = AsyncMock(side_effect=AssertionError("root must remain unopened"))
    monkeypatch.setattr(files, "file_io", action)
    with pytest.raises(RuntimeError, match="reviewed V002-compatible"):
        await files.initialize_file_service(sessions_for(revision))
    action.assert_not_called()


@pytest.mark.asyncio
async def test_disabled_files_do_not_access_schema_or_root(monkeypatch):
    """Keep the existing opt-in feature disabled without creating new database/filesystem work."""
    monkeypatch.setenv("ASSISTANT_FILES_ENABLED", "0")
    action = AsyncMock(side_effect=AssertionError("root must remain unopened"))
    monkeypatch.setattr(files, "file_io", action)
    assert await files.initialize_file_service(None) is None
    action.assert_not_called()
