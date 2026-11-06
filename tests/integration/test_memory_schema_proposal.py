"""Exercise D29 proposed relational constraints only in connection-private PostgreSQL temporary tables."""

import hashlib
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from psycopg.types.json import Jsonb
from sqlalchemy import make_url

logger = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parents[2]
PROPOSAL = ROOT / "docs/proposals/d29-memory-schema.sql"


@pytest.fixture
def temporary_memory():
    """Use the existing operator probe credential and roll back private temporary DDL/data after each test."""
    raw = os.environ.get("LOCAL_ASSISTANT_MEMORY_SCHEMA_PROBE_URL")
    if not raw:
        pytest.skip("explicit existing migrator temporary-schema probe URL required")
    url = make_url(raw)
    assert url.drivername == "postgresql+psycopg"
    ddl = PROPOSAL.read_text().replace(
        "CREATE TABLE assistant.", "CREATE TEMPORARY TABLE "
    )
    ddl = ddl.replace("assistant.memory_", "memory_").replace(
        "assistant.memories", "memories"
    )
    ddl = ddl.replace("\n);", "\n) ON COMMIT DROP;")
    with psycopg.connect(
        host=url.host,
        port=url.port,
        dbname=url.database,
        user=url.username,
        password=url.password,
        connect_timeout=5,
    ) as connection:
        before = connection.execute(
            "SELECT version_num FROM assistant.alembic_version"
        ).fetchone()[0]
        connection.execute(ddl, prepare=False)
        assert (
            connection.execute(
                "SELECT count(*) FROM pg_class WHERE relname IN ('memory_settings','memory_consents','memories') AND relnamespace = pg_my_temp_schema()"
            ).fetchone()[0]
            == 3
        )
        try:
            yield connection
            assert (
                connection.execute(
                    "SELECT version_num FROM assistant.alembic_version"
                ).fetchone()[0]
                == before
            )
        finally:
            connection.rollback()
            logger.info("memory_proposal_temporary_transaction_rolled_back")


def insert_record(connection, data):
    """Insert only synthetic memory content into the private temporary record table."""
    row = dict(data)
    row["provenance"] = Jsonb(row["provenance"])
    columns = list(row)
    query = (
        "INSERT INTO memories ("
        + ",".join(columns)
        + ") VALUES ("
        + ",".join("%s" for _ in columns)
        + ")"
    )
    connection.execute(query, [row[name] for name in columns])


def seed(connection, *, kind="preference", extracted=False):
    """Create matching synthetic settings/receipt rows for relational fault tests without runtime source claims."""
    now = datetime(2026, 10, 19, 9, tzinfo=timezone.utc)
    owner, receipt = uuid4(), uuid4()
    scope = owner if kind in ("episodic", "preference") else uuid4()
    text = "SQL-owned preference."
    provenance = dict(
        kind="manual", content_sha256=hashlib.sha256(text.encode()).hexdigest()
    )
    if extracted:
        provenance = dict(
            kind="conversation_message",
            conversation_id=str(scope if kind == "session" else uuid4()),
            message_id=str(uuid4()),
            role="user",
            content_sha256=hashlib.sha256(text.encode()).hexdigest(),
            quote="SQL",
            start=0,
            end=3,
        )
    data = dict(
        settings=dict(
            owner_id=owner,
            revision=1,
            enabled=True,
            extraction_enabled=extracted,
            updated_at=now,
        ),
        consent=dict(
            id=receipt,
            owner_id=owner,
            kind=kind,
            scope_id=scope,
            settings_revision=1,
            allow_extraction=extracted,
            granted_at=now,
            expires_at=now + timedelta(hours=1),
        ),
        record=dict(
            id=uuid4(),
            owner_id=owner,
            kind=kind,
            scope_id=scope,
            consent_id=receipt,
            text=text,
            method="extracted" if extracted else "manual",
            model_id="existing-core-fixture" if extracted else None,
            provenance=provenance,
            created_at=now,
            updated_at=now,
            expires_at=now + timedelta(minutes=30),
        ),
    )
    for table, row in (
        ("memory_settings", data["settings"]),
        ("memory_consents", data["consent"]),
    ):
        columns = list(row)
        query = (
            "INSERT INTO "
            + table
            + " ("
            + ",".join(columns)
            + ") VALUES ("
            + ",".join("%s" for _ in columns)
            + ")"
        )
        connection.execute(query, [row[name] for name in columns])
    return data["record"]


@pytest.mark.parametrize("kind", ["session", "episodic", "preference", "project"])
def test_actual_temporary_schema_accepts_four_bound_classes(temporary_memory, kind):
    """Verify SQL parses and records all four classes with actual nonnullable receipt bindings."""
    connection = temporary_memory
    record = seed(connection, kind=kind)
    insert_record(connection, record)
    observed = connection.execute(
        "SELECT kind,content_trust,provenance->>'kind' FROM memories"
    ).fetchone()
    assert observed == (kind, "untrusted", "manual")
    assert (
        connection.execute("SELECT count(*) FROM assistant.alembic_version").fetchone()[
            0
        ]
        == 1
    )
    logger.info("memory_proposal_class_verified kind=%s", kind)


@pytest.mark.parametrize(
    "fault",
    [
        "owner",
        "receipt",
        "scope",
        "kind",
        "bytes",
        "trust",
        "provenance",
        "null_provenance_kind",
        "producer",
        "version",
        "retention",
    ],
)
def test_actual_temporary_schema_rejects_invalid_records(temporary_memory, fault):
    """Reject cross-receipt/owner/scope and bounded content failures at the actual PostgreSQL boundary."""
    connection = temporary_memory
    record = seed(connection, kind="project")
    if fault in ("owner", "receipt", "scope"):
        record[
            {"owner": "owner_id", "receipt": "consent_id", "scope": "scope_id"}[fault]
        ] = uuid4()
    elif fault == "kind":
        record["kind"] = "session"
    elif fault == "bytes":
        record["text"] = "ệ" * 1366
    elif fault == "trust":
        record["content_trust"] = "system"
    elif fault == "provenance":
        record["provenance"] = {}
    elif fault == "null_provenance_kind":
        record["provenance"] = {"kind": None}
    elif fault == "producer":
        record["model_id"] = "unexpected-producer"
    elif fault == "version":
        record["version"] = 0
    else:
        record["expires_at"] = record["created_at"] + timedelta(days=366)
    with pytest.raises(psycopg.IntegrityError):
        with connection.transaction():
            insert_record(connection, record)
    assert connection.execute("SELECT count(*) FROM memories").fetchone()[0] == 0


def test_extraction_and_default_settings_sql_contract(temporary_memory):
    """Keep SQL defaults disabled and require a producer with nonmanual extracted provenance."""
    connection = temporary_memory
    owner = uuid4()
    connection.execute(
        "INSERT INTO memory_settings(owner_id,revision,updated_at) VALUES (%s,1,clock_timestamp())",
        (owner,),
    )
    assert connection.execute(
        "SELECT enabled,extraction_enabled FROM memory_settings WHERE owner_id=%s",
        (owner,),
    ).fetchone() == (False, False)
    record = seed(connection, extracted=True)
    insert_record(connection, record)
    assert connection.execute(
        "SELECT method,model_id,provenance->>'kind' FROM memories"
    ).fetchone() == ("extracted", "existing-core-fixture", "conversation_message")
    with pytest.raises(psycopg.errors.CheckViolation):
        with connection.transaction():
            connection.execute(
                "UPDATE memory_settings SET extraction_enabled=true WHERE owner_id=%s",
                (owner,),
            )
