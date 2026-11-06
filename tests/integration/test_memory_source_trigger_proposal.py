"""Verify proposed V006 source invalidation using only connection-private PostgreSQL relations/functions before rollout."""

import importlib.util
import logging
import os
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from psycopg.types.json import Jsonb
from sqlalchemy import make_url

logger = logging.getLogger(__name__)
MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "migrations/versions/0006_memory_source_invalidation.py"
)


def migration_module():
    """Load reviewed migration code without calling Alembic or opening an application connection."""
    spec = importlib.util.spec_from_file_location("memory_source_proposal", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def temporary_sources(request):
    """Rollback every temp table/function/data change using only the existing operator probe credential."""
    raw = os.environ.get("LOCAL_ASSISTANT_MEMORY_SCHEMA_PROBE_URL")
    if not raw:
        pytest.skip("existing operator-only temporary-schema probe URL required")
    url = make_url(raw)
    with psycopg.connect(
        host=url.host,
        port=url.port,
        dbname=url.database,
        user=url.username,
        password=url.password,
        connect_timeout=5,
    ) as connection:
        revision = connection.execute(
            "SELECT version_num FROM assistant.alembic_version"
        ).fetchone()[0]
        connection.execute(
            """
            CREATE TEMP TABLE conversations(id uuid PRIMARY KEY,metadata jsonb,deleted_at timestamptz,status text DEFAULT 'active',title text);
            CREATE TEMP TABLE messages(id uuid PRIMARY KEY,conversation_id uuid REFERENCES conversations(id) ON DELETE CASCADE,content text,role text,sequence integer);
            CREATE TEMP TABLE memory_settings(owner_id uuid);
            CREATE TEMP TABLE memory_consents(id uuid PRIMARY KEY,kind text,scope_id uuid);
            CREATE TEMP TABLE memories(id uuid PRIMARY KEY,kind text,scope_id uuid,consent_id uuid REFERENCES memory_consents(id),provenance jsonb);
        """,
            prepare=False,
        )
        if getattr(request, "param", True):
            connection.execute(
                migration_module().SOURCE_INVALIDATION_DDL.replace(
                    "assistant.", "pg_temp."
                ),
                prepare=False,
            )
        try:
            yield connection
        finally:
            connection.rollback()
            assert (
                connection.execute(
                    "SELECT version_num FROM assistant.alembic_version"
                ).fetchone()[0]
                == revision
            )
            connection.rollback()
            logger.info("memory_source_trigger_private_proposal_rolled_back")


def seeded_sources(connection):
    """Seed two unrelated sources plus independent manual and session memory to test precise deletion boundaries."""
    a, b, ma, mb, receipt, session = [uuid4() for _ in range(6)]
    for conversation, message in [(a, ma), (b, mb)]:
        connection.execute(
            "INSERT INTO conversations(id,metadata) VALUES (%s,%s)",
            (conversation, Jsonb(dict(owner_id=str(uuid4())))),
        )
        connection.execute(
            "INSERT INTO messages VALUES (%s,%s,'original source','user',1)",
            (message, conversation),
        )
    connection.execute(
        "INSERT INTO memory_consents VALUES (%s,'preference',%s),(%s,'session',%s)",
        (receipt, a, session, a),
    )
    identifiers = {}
    for name, kind, scope, consent, provenance in [
        (
            "derived_a",
            "preference",
            a,
            receipt,
            dict(
                kind="conversation_message", conversation_id=str(a), message_id=str(ma)
            ),
        ),
        (
            "derived_b",
            "preference",
            b,
            receipt,
            dict(
                kind="conversation_message", conversation_id=str(b), message_id=str(mb)
            ),
        ),
        ("manual", "preference", a, receipt, dict(kind="manual")),
        ("session", "session", a, session, dict(kind="manual")),
    ]:
        identifier = uuid4()
        identifiers[name] = identifier
        connection.execute(
            "INSERT INTO memories VALUES (%s,%s,%s,%s,%s)",
            (identifier, kind, scope, consent, Jsonb(provenance)),
        )
    return dict(conversation=a, message=ma, ids=identifiers, session=session)


@pytest.mark.parametrize(
    "change",
    [
        "soft_delete",
        "hard_delete",
        "owner",
        "message_content",
        "message_role",
        "message_delete",
    ],
)
def test_proposed_source_mutation_precise_atomic_invalidation(
    temporary_sources, change
):
    """Delete only exact dependent evidence/session scope and retain unrelated source/manual memory."""
    connection = temporary_sources
    data = seeded_sources(connection)
    queries = dict(
        soft_delete="UPDATE conversations SET deleted_at=clock_timestamp() WHERE id=%s",
        hard_delete="DELETE FROM conversations WHERE id=%s",
        owner="UPDATE conversations SET metadata='{}'::jsonb WHERE id=%s",
        message_content="UPDATE messages SET content='corrected' WHERE id=%s",
        message_role="UPDATE messages SET role='assistant' WHERE id=%s",
        message_delete="DELETE FROM messages WHERE id=%s",
    )
    connection.execute(
        queries[change],
        (data["message"] if change.startswith("message") else data["conversation"],),
    )
    remaining = {row[0] for row in connection.execute("SELECT id FROM memories")}
    expected = {data["ids"]["manual"], data["ids"]["derived_b"]}
    if change.startswith("message"):
        expected.add(data["ids"]["session"])
    assert remaining == expected
    session_retained = connection.execute(
        "SELECT count(*) FROM memory_consents WHERE id=%s", (data["session"],)
    ).fetchone()[0]
    assert session_retained == int(change.startswith("message"))


@pytest.mark.parametrize(
    "query",
    [
        "UPDATE messages SET content=content WHERE id=%s",
        "UPDATE messages SET sequence=2 WHERE id=%s",
        "UPDATE conversations SET status='archived',title='new title' WHERE id=%s",
    ],
)
def test_proposed_non_source_updates_retain_memory(temporary_sources, query):
    """Avoid deleting explicit memory for a no-op, message ordering change or conversation archive alone."""
    connection = temporary_sources
    data = seeded_sources(connection)
    connection.execute(
        query, (data["message"] if "messages " in query else data["conversation"],)
    )
    assert {row[0] for row in connection.execute("SELECT id FROM memories")} == set(
        data["ids"].values()
    )


@pytest.mark.parametrize("target", ["messages", "conversations"])
def test_proposed_source_rollback_restores_evidence_together(temporary_sources, target):
    """Roll back both source and dependent-memory deletion when the surrounding transaction fails."""
    connection = temporary_sources
    data = seeded_sources(connection)
    with pytest.raises(RuntimeError, match="rollback probe"):
        with connection.transaction():
            connection.execute(
                "DELETE FROM " + target + " WHERE id=%s",
                (data["message"] if target == "messages" else data["conversation"],),
            )
            assert connection.execute("SELECT count(*) FROM memories").fetchone()[0] < 4
            raise RuntimeError("rollback probe")
    assert connection.execute("SELECT count(*) FROM memories").fetchone()[0] == 4
    assert connection.execute("SELECT count(*) FROM messages").fetchone()[0] == 2


@pytest.mark.parametrize("temporary_sources", [False], indirect=True)
@pytest.mark.parametrize(
    "populated", ["memories", "memory_consents", "memory_settings"]
)
def test_proposed_rollout_refuses_populated_memory(temporary_sources, populated):
    """Refuse unknown retained-data migration scope before creating permanent or private trigger objects."""
    connection = temporary_sources
    module = migration_module()
    if populated == "memory_settings":
        connection.execute("INSERT INTO memory_settings VALUES (%s)", (uuid4(),))
    elif populated == "memory_consents":
        connection.execute(
            "INSERT INTO memory_consents VALUES (%s,'preference',%s)",
            (uuid4(), uuid4()),
        )
    else:
        seeded_sources(connection)

    class PrivateOperator:
        """Execute only rewritten connection-private migration statements for the actual rollout guard."""

        def execute(self, statement):
            """Keep every SQL reference inside the current connection's temporary namespace."""
            connection.execute(
                str(statement).replace("assistant.", "pg_temp."), prepare=False
            )

    module.op = PrivateOperator()
    with connection.transaction():
        with pytest.raises(
            psycopg.errors.RaiseException, match="audited populated-data plan"
        ):
            with connection.transaction():
                module.upgrade()
    assert (
        connection.execute(
            "SELECT count(*) FROM pg_trigger WHERE tgname IN ('invalidate_message_memory','invalidate_conversation_memory') AND tgrelid IN ('pg_temp.messages'::regclass,'pg_temp.conversations'::regclass)"
        ).fetchone()[0]
        == 0
    )
