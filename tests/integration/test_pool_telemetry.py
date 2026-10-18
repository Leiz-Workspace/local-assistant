"""Verify real pool acquisition, saturation, invalidation and structured metric samples."""

import asyncio
import json
import logging
import os

import pytest
from sqlalchemy.exc import TimeoutError as PoolTimeout
from sqlalchemy.ext.asyncio import create_async_engine

from src.infrastructure.database.pool_telemetry import PoolTelemetry


@pytest.mark.asyncio
async def test_pool_metrics_and_periodic_export(caplog):
    """Saturate a one-slot PostgreSQL pool and observe accurate bounded operational metrics."""
    if not os.environ.get("DATABASE_URL"):
        pytest.skip("DATABASE_URL not configured")
    engine = create_async_engine(
        os.environ["DATABASE_URL"],
        pool_size=1,
        max_overflow=0,
        pool_timeout=0.05,
        hide_parameters=True,
    )
    telemetry = PoolTelemetry(engine)
    sampler = None
    try:
        with caplog.at_level(
            logging.INFO, logger="src.infrastructure.database.pool_telemetry"
        ):
            async with engine.connect() as first:
                assert telemetry.snapshot()["checked_out"] == 1
                with pytest.raises(PoolTimeout):
                    async with engine.connect():
                        pytest.fail("A saturated pool must time out")
                telemetry.note_timeout()
                await first.invalidate()
            sampler = asyncio.create_task(telemetry.sample(0.01))
            await asyncio.sleep(0.035)
            sampler.cancel()
            await asyncio.gather(sampler, return_exceptions=True)
            telemetry.close()
        values = [
            json.loads(record.message)
            for record in caplog.records
            if record.name == "src.infrastructure.database.pool_telemetry"
        ]
        assert len(values) >= 3
        assert values[-1]["checked_out"] == 0
        assert values[-1]["peak_checked_out"] == 1
        assert values[-1]["checkouts"] == 1
        assert values[-1]["invalidations"] == 1
        assert values[-1]["timeouts"] == 1
        assert all(value["event"] == "database_pool_metrics" for value in values)
        assert os.environ["DATABASE_URL"] not in caplog.text
    finally:
        if sampler is not None and not sampler.done():
            sampler.cancel()
            await asyncio.gather(sampler, return_exceptions=True)
        await engine.dispose()


@pytest.mark.asyncio
async def test_pool_reconnects_after_owned_backend_termination():
    """Recover a stale pooled connection using pre-ping after losing this test's own backend."""
    if not os.environ.get("DATABASE_URL"):
        pytest.skip("DATABASE_URL not configured")
    from sqlalchemy import text

    from src.infrastructure.database.connection import create_database_engine

    engine = create_database_engine()
    control = create_database_engine()
    observer = PoolTelemetry(engine)
    try:
        async with engine.connect() as connection:
            old_pid = await connection.scalar(text("SELECT pg_backend_pid()"))
        async with control.begin() as connection:
            assert (
                await connection.scalar(
                    text("SELECT pg_terminate_backend(:pid)"), {"pid": old_pid}
                )
                is True
            )
        async with engine.connect() as connection:
            assert await connection.scalar(text("SELECT pg_backend_pid()")) != old_pid
            assert (
                await connection.scalar(text("SELECT current_user"))
                == "local_assistant_app"
            )
        assert observer.snapshot()["invalidations"] >= 1
        assert observer.snapshot()["checked_out"] == 0
    finally:
        observer.close()
        await engine.dispose()
        await control.dispose()
