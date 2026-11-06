"""Verify explicit private ingestion HTTP, actual background indexing and source replacement/deletion consistency."""

import asyncio
import json
import os
import time
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from test_file_http import cleanup_owners, reserve

from apps.api.main import app
from src.infrastructure.database.connection import (
    create_database_engine,
    create_session_factory,
)
from src.infrastructure.qdrant_ingestion import QdrantIngestion


@pytest.fixture
def ingest_client(auth_settings, tmp_path, monkeypatch):
    """Enable actual runtime wiring against only a fresh owned removable physical vector probe."""
    if not os.environ.get("DATABASE_URL") or not os.environ.get(
        "LOCAL_ASSISTANT_QDRANT_PROBE_KEY"
    ):
        pytest.skip("existing PostgreSQL/Qdrant acceptance credentials not configured")
    from apps.api.storage import ingestion

    key = os.environ["LOCAL_ASSISTANT_QDRANT_PROBE_KEY"]
    owner = uuid4()
    name = "la_d25_probe_" + uuid4().hex
    path = tmp_path / "ingestion.json"
    path.write_text(json.dumps(dict(owner_id=str(owner), api_key=key)))
    path.chmod(0o600)
    monkeypatch.setenv("ASSISTANT_FILES_ENABLED", "1")
    monkeypatch.setenv("ASSISTANT_FILES_ROOT", str(tmp_path / "blobs"))
    monkeypatch.setenv("ASSISTANT_INGESTION_ENABLED", "1")
    monkeypatch.setenv("ASSISTANT_INGESTION_CONFIG_FILE", str(path))
    selection = None

    def vector_probe(config, owner_id, api_key):
        """Substitute only an isolated collection name while preserving actual ownership/model/REST behavior."""
        nonlocal selection
        selection = config
        return QdrantIngestion(config, owner_id, api_key, physical_name=name)

    monkeypatch.setattr(ingestion, "QdrantIngestion", vector_probe)
    try:
        with TestClient(app, client=("127.0.0.1", 43000)) as client:
            yield client, auth_settings
    finally:

        async def cleanup():
            """Remove only this acknowledged-owned probe and these test principals' durable metadata."""
            if selection is not None:
                adapter = QdrantIngestion(selection, owner, key, physical_name=name)
                try:
                    if await adapter.owned() is not None:
                        await adapter.request("DELETE", adapter.path)
                finally:
                    await adapter.close()
            engine = create_database_engine()
            sessions = create_session_factory(engine)
            try:
                async with sessions() as session, session.begin():
                    for table in ("ingestion_heads", "ingestion_jobs"):
                        await session.execute(
                            text(
                                f"DELETE FROM assistant.{table} WHERE owner_id IN (:a,:b)"
                            ),
                            dict(
                                a=auth_settings["principals"][0],
                                b=auth_settings["principals"][1],
                            ),
                        )
            finally:
                await engine.dispose()
            await cleanup_owners(auth_settings["principals"])

        asyncio.run(cleanup())


def wait_job(client, headers, identifier, *, state="ready", seconds=30):
    """Poll actual background progress with a bounded deadline and no private source response content."""
    deadline = time.monotonic() + seconds
    last = None
    while time.monotonic() < deadline:
        response = client.get("/api/v1/ingestion/" + identifier, headers=headers)
        assert response.status_code == 200
        last = response.json()
        if last["status"] == state:
            return last
        time.sleep(0.05)
    raise AssertionError("ingestion job did not reach expected state: " + str(last))


def upload(client, headers, data, key):
    """Create an immutable verified source through the actual existing upload HTTP contract."""
    row = reserve(client, headers, data, "worker.txt", key)
    route = "/api/v1/files/" + row["id"]
    assert (
        client.put(route + "/content", content=data, headers=headers).status_code == 200
    )
    return row["id"]


def test_actual_http_admission_replay_source_replacement_and_delete(ingest_client):
    """Drive the opt-in startup/source/Qwen/vector/journal path without exposing foreign jobs or stale sources."""
    client, auth = ingest_client
    first, foreign = auth["headers"]
    source = upload(client, first, b"private-http-marker version one", "v1")
    response = client.post(f"/api/v1/files/{source}/index", headers=first)
    assert (
        response.status_code == 202
        and response.headers["cache-control"] == "private, no-store"
    )
    job = response.json()["id"]
    ready = wait_job(client, first, job)
    assert (
        ready["active"]
        and ready["chunk_count"] == 1
        and "private-http-marker" not in json.dumps(ready)
    )
    assert client.get("/api/v1/ingestion/" + job, headers=foreign).status_code == 404
    assert (
        client.post(f"/api/v1/files/{source}/index", headers=foreign).status_code == 404
    )
    assert (
        client.post(f"/api/v1/files/{source}/index", headers=first).json()["id"] == job
    )
    replacement = upload(
        client, first, b"private-http-marker changed version two", "v2"
    )
    newer = client.post(f"/api/v1/files/{replacement}/index", headers=first)
    assert newer.status_code == 202 and newer.json()["id"] != job
    assert wait_job(client, first, newer.json()["id"])["active"]
    assert client.delete("/api/v1/files/" + source, headers=first).status_code in {
        202,
        204,
    }
    assert (
        client.get("/api/v1/ingestion/" + job, headers=first).json()["active"] is False
    )
    assert wait_job(client, first, job, state="tombstone")["active"] is False
    assert client.delete("/api/v1/files/" + replacement, headers=first).status_code in {
        202,
        204,
    }
    assert (
        wait_job(client, first, newer.json()["id"], state="tombstone")["active"]
        is False
    )


def test_token_overflow_is_rejected_before_journal_or_vector_work(ingest_client):
    """Refuse a complete513-token source chunk without silent truncation or partial admission."""
    client, auth = ingest_client
    headers = auth["headers"][0]
    identifier = upload(client, headers, (" x" * 512).encode(), "overflow")
    response = client.post(
        f"/api/v1/files/{identifier}/index?max_bytes=8192", headers=headers
    )
    assert (
        response.status_code == 422
        and response.json()["detail"]["code"] == "ingestion_token_limit"
    )

    async def count():
        """Read only this principal's job count after failed token admission."""
        async with app.state.ingestion_service.journal.sessions() as session:
            return await session.scalar(
                text(
                    "SELECT count(*) FROM assistant.ingestion_jobs WHERE owner_id=:owner"
                ),
                dict(owner=auth["principals"][0]),
            )

    assert client.portal.call(count) == 0
    assert client.delete(
        "/api/v1/files/" + identifier, headers=headers
    ).status_code in {202, 204}
