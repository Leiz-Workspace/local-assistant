"""Construct bounded, credential-safe PostgreSQL engines and transactional sessions."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


def create_database_engine(
    database_url: str | None = None,
) -> AsyncEngine:
    """Create a bounded PostgreSQL pool without exposing credential parameters."""
    url = database_url or os.environ.get("DATABASE_URL")

    if not url:
        raise RuntimeError(
            "DATABASE_URL is required. "
            "Supply it securely at runtime; do not hardcode secrets."
        )

    if not url.startswith("postgresql+psycopg://"):
        raise ValueError("Expected DATABASE_URL with postgresql+psycopg://")

    return create_async_engine(
        url,
        pool_size=5,
        pool_timeout=10,
        hide_parameters=True,
        max_overflow=5,
        pool_pre_ping=True,
        pool_recycle=1800,
        connect_args={
            "connect_timeout": 10,
            "options": "-c search_path=assistant,public",
        },
    )


def create_session_factory(
    engine: AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    """Build non-expiring async sessions for committed domain entities."""
    return async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )


@asynccontextmanager
async def transactional_session(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    """Commit successful operations and roll back failures within a managed session."""
    async with session_factory() as session:
        async with session.begin():
            yield session


async def check_database_connection(
    engine: AsyncEngine,
) -> dict[str, str]:
    """Verify the live database, runtime user and schema identity."""
    async with engine.connect() as connection:
        result = await connection.execute(
            text(
                "SELECT "
                "current_database() AS database_name, "
                "current_user AS database_user, "
                "current_schema() AS schema_name"
            )
        )

        row = result.mappings().one()

        return {
            "database": row["database_name"],
            "user": row["database_user"],
            "schema": row["schema_name"],
        }
