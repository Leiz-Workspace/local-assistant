from __future__ import annotations

import os

from alembic import context
from sqlalchemy import create_engine, pool


config = context.config

SCHEMA = "assistant"
VERSION_TABLE = "alembic_version"

# V001 uses explicit Alembic operations.
# ORM metadata integration can be added later.
target_metadata = None


def get_database_url() -> str:
    database_url = os.environ.get("DATABASE_URL")

    if not database_url:
        raise RuntimeError(
            "DATABASE_URL is required to run migrations. "
            "Do not commit database credentials to source code."
        )

    if not database_url.startswith(
        "postgresql+psycopg://"
    ):
        raise RuntimeError(
            "Migrations require PostgreSQL with psycopg 3."
        )

    return database_url


def run_migrations_offline() -> None:
    context.configure(
        url=get_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_schemas=True,
        version_table=VERSION_TABLE,
        version_table_schema=SCHEMA,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(
        get_database_url(),
        poolclass=pool.NullPool,
        connect_args={
            "connect_timeout": 10,
            "options": "-c search_path=assistant,public",
        },
    )

    try:
        with engine.connect() as connection:
            context.configure(
                connection=connection,
                target_metadata=target_metadata,
                include_schemas=True,
                version_table=VERSION_TABLE,
                version_table_schema=SCHEMA,
                transactional_ddl=True,
            )

            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
