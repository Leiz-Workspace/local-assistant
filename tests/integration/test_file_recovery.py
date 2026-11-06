"""Prove journal/FD crash recovery, fair cleanup and paired DB/blob/identity restoration."""

import asyncio
import errno
import json
import logging
import multiprocessing
import os
import stat
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError
from test_file_http import body, cleanup_owners, counts, declaration
from test_file_http import file_client as file_client
from test_file_http import owned_service as owned_service

from apps.api.main import app
from apps.api.routes.files import router as file_router
from apps.api.services.files import FileService, identity_for
from scripts.file_storage_recovery_acceptance import FileStorageRecoveryAcceptance
from scripts.postgres_recovery_acceptance import (
    PROBE_PREFIX,
    RecoveryAcceptance,
    identifier,
)
from src.infrastructure.database.connection import (
    create_database_engine,
    create_session_factory,
)
from src.infrastructure.local_blob_storage import (
    BlobStorageError,
    BlobWriter,
    LocalBlobStorage,
)
from src.infrastructure.repositories.file_journal import PostgresFileJournal

logger = logging.getLogger(__name__)


@pytest.fixture
def isolated_pair_db(tmp_path, monkeypatch):
    """Clone only schema into an exclusive same-instance probe so real user file data is never a test fixture."""
    if not os.environ.get("DATABASE_URL"):
        pytest.skip("DATABASE_URL not configured")
    operator = RecoveryAcceptance(tmp_path / "schema-operator")
    probe = PROBE_PREFIX + uuid4().hex
    created = False
    try:
        schema = operator.command(
            [
                "exec",
                "postgres",
                "pg_dump",
                "-U",
                "home-server",
                "-d",
                "local_assistant",
                "--schema-only",
            ]
        )
        operator.sql(
            "postgres", "CREATE DATABASE " + identifier(probe) + " TEMPLATE template0;"
        )
        created = True
        operator.command(
            [
                "exec",
                "-i",
                "postgres",
                "psql",
                "-X",
                "-v",
                "ON_ERROR_STOP=1",
                "-U",
                "home-server",
                "-d",
                probe,
            ],
            input_data=schema,
        )
        operator.sql(
            probe,
            "INSERT INTO assistant.alembic_version(version_num) VALUES ('0002'); INSERT INTO assistant.file_global_usage(singleton) VALUES(1);",
        )
        url = make_url(os.environ["DATABASE_URL"]).set(database=probe)
        monkeypatch.setenv("DATABASE_URL", url.render_as_string(hide_password=False))
        logger.info("paired_test_source_probe_created")
        yield probe
    finally:
        if created:
            operator.drop_probe(probe)


def crash_upload(root, owner, file_id, boundary, connection):
    """Pause a real database-backed uploader in a separate process for parent SIGKILL."""

    async def run():
        """Use app credentials and the same root identity while retaining actual writer/DB state."""
        engine = create_database_engine()
        service = FileService(
            PostgresFileJournal(create_session_factory(engine)), LocalBlobStorage(root)
        )
        original = BlobWriter.publish

        def published_then_wait(writer):
            """Pause after durable publication but before the ready database transaction."""
            original(writer)
            connection.send("published")
            connection.recv()

        async def stream():
            """Pause after a partial real write or provide the complete published payload."""
            if boundary == "partial":
                yield b"hello"
                connection.send("partial")
                await asyncio.to_thread(connection.recv)
            else:
                yield b"hello file"

        if boundary == "published":
            BlobWriter.publish = published_then_wait
        try:
            await service.upload(owner, file_id, stream())
        finally:
            await service.shutdown()
            await engine.dispose()

    try:
        asyncio.run(run())
    finally:
        connection.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("boundary", ["partial", "published"])
async def test_expired_live_process_keeps_quota_then_kill_recovers(
    owned_service, tmp_path, boundary
):
    """Keep charged bytes while the expired process owns locks and release only after SIGKILL."""
    service, owners = owned_service
    row = await service.reserve(owners[0], **declaration(b"hello file"))
    context = multiprocessing.get_context("spawn")
    parent, child = context.Pipe()
    process = context.Process(
        target=crash_upload,
        args=(tmp_path / "blobs", owners[0], row["id"], boundary, child),
    )
    process.start()
    child.close()
    try:
        assert await asyncio.to_thread(parent.poll, 10)
        assert parent.recv() == boundary
        async with service.journal.sessions() as session, session.begin():
            await session.execute(
                text(
                    "UPDATE assistant.files SET lease_expires_at=clock_timestamp()-interval '1 second' WHERE id=:id"
                ),
                {"id": row["id"]},
            )
        pending = await service.recover_once()
        assert pending["pending"] == 1 and await counts(service, owners[0]) == (
            10,
            1,
            1,
        )
        process.kill()
        await asyncio.to_thread(process.join, 5)
        assert not process.is_alive()
        assert (await service.recover_once())["completed"] == 1
        assert await counts(service, owners[0]) == (0, 0, 0)
        assert service.storage.inventory() == {}
        assert (await service.recover_once())["completed"] == 0
    finally:
        if process.is_alive():
            process.kill()
        await asyncio.to_thread(process.join, 5)
        parent.close()


@pytest.mark.asyncio
async def test_busy_cleanup_does_not_starve_another_expired_resource(owned_service):
    """Rotate a held reader behind older pending work under a one-resource batch limit."""
    service, owners = owned_service
    first = await service.reserve(owners[0], **declaration(b"hello file"))
    await service.upload(owners[0], first["id"], body())
    _, reader = await service.open_download(owners[0], first["id"])
    try:
        await service.journal.begin_purge(owners[0], first["id"], uuid4())
        second = await service.reserve(owners[1], **declaration(b"hello file"))
        async with service.journal.sessions() as session, session.begin():
            await session.execute(
                text(
                    "UPDATE assistant.files SET reservation_expires_at=clock_timestamp()-interval '1 second' WHERE id=:id"
                ),
                {"id": second["id"]},
            )
        assert (await service.recover_once(limit=1))["pending"] == 1
        assert (await service.recover_once(limit=1))["completed"] == 1
        assert await counts(service, owners[0]) == (10, 1, 0)
        assert await counts(service, owners[1]) == (0, 0, 0)
    finally:
        reader.close()
    assert (await service.recover_once(limit=1))["completed"] == 1


@pytest.mark.asyncio
async def test_ready_redundant_link_removed_without_releasing_ready_quota(
    owned_service, tmp_path
):
    """Reconcile only a proven same-inode stage link while retaining ready metadata and allocation."""
    service, owners = owned_service
    row = await service.reserve(owners[0], **declaration(b"hello file"))
    await service.upload(owners[0], row["id"], body())
    ready = await service.journal.get(owners[0], row["id"])
    identity = identity_for(ready)
    root = tmp_path / "blobs"
    os.link(
        root.joinpath(*identity.object_parts), root.joinpath(*identity.staging_parts)
    )
    await service.recover_once()
    assert not root.joinpath(*identity.staging_parts).exists()
    assert await counts(service, owners[0]) == (10, 1, 0)
    _, reader = await service.open_download(owners[0], row["id"])
    with reader:
        assert reader.read() == b"hello file"


def create_ready_files(root, auth, monkeypatch):
    """Drain a real authenticated API after creating nonempty owner-scoped source payloads."""
    monkeypatch.setenv("ASSISTANT_FILES_ENABLED", "1")
    monkeypatch.setenv("ASSISTANT_FILES_ROOT", str(root))
    identifiers = []
    with TestClient(app, client=("127.0.0.1", 43000)) as client:
        for index, headers in enumerate(auth["headers"]):
            data = f"paired-owner-{index}\n".encode()
            response = client.post(
                "/api/v1/files", json=declaration(data), headers=headers
            )
            assert response.status_code == 201, response.text
            identifier = response.json()["id"]
            assert (
                client.put(
                    "/api/v1/files/" + identifier + "/content",
                    content=data,
                    headers=headers,
                ).status_code
                == 200
            )
            identifiers.append((identifier, data))
    return identifiers


def test_actual_paired_restore_and_reopened_api_identity(
    auth_settings, tmp_path, monkeypatch, isolated_pair_db
):
    """Restore a real DB probe plus independent blobs/auth bindings and serve the restored bytes."""
    if not os.environ.get("DATABASE_URL"):
        pytest.skip("DATABASE_URL not configured")
    root = tmp_path / "source"
    try:
        identifiers = create_ready_files(root, auth_settings, monkeypatch)
        backup = tmp_path / "paired"
        manifest = FileStorageRecoveryAcceptance(
            backup, root, auth_settings["path"]
        ).run()
        assert (
            manifest["paired_restore_verified"]
            and manifest["database_security_verified"]
        )
        assert manifest["files"] == 2 and manifest["identity_verified"]
        for path in backup.rglob("*"):
            assert stat.S_IMODE(path.stat().st_mode) == (
                0o700 if path.is_dir() else 0o600
            )
        saved = json.loads((backup / "manifest.json").read_text())
        assert saved["namespace_id"] == manifest["namespace_id"]
        monkeypatch.setenv("ASSISTANT_FILES_ROOT", str(backup / "restored-blobs"))
        monkeypatch.setenv("ASSISTANT_AUTH_FILE", str(backup / "principals.json"))
        with TestClient(app, client=("127.0.0.1", 43000)) as client:
            for index, (identifier, data) in enumerate(identifiers):
                response = client.get(
                    "/api/v1/files/" + identifier + "/content",
                    headers=auth_settings["headers"][index],
                )
                assert response.status_code == 200 and response.content == data
                assert (
                    client.get(
                        "/api/v1/files/" + identifier + "/content",
                        headers=auth_settings["headers"][1 - index],
                    ).status_code
                    == 404
                )
    finally:
        asyncio.run(cleanup_owners(auth_settings["principals"]))


@pytest.mark.parametrize(
    "fault", ["unknown_blob", "corrupt_blob", "active_reservation"]
)
def test_paired_backup_refuses_unresolved_or_inconsistent_source(
    auth_settings, tmp_path, monkeypatch, fault, isolated_pair_db
):
    """Reject ambiguous data without deleting source bytes or certifying a partial backup."""
    if not os.environ.get("DATABASE_URL"):
        pytest.skip("DATABASE_URL not configured")
    root = tmp_path / "source"
    try:
        create_ready_files(root, auth_settings, monkeypatch)
        if fault == "unknown_blob":
            path = root / "unknown"
            path.write_bytes(b"untracked")
            path.chmod(0o600)
        elif fault == "corrupt_blob":
            path = next(root.rglob("*.blob"))
            path.write_bytes(b"X" * path.stat().st_size)
        else:
            with TestClient(app, client=("127.0.0.1", 43000)) as client:
                assert (
                    client.post(
                        "/api/v1/files",
                        json=declaration(b"pending"),
                        headers=auth_settings["headers"][0],
                    ).status_code
                    == 201
                )
        backup = tmp_path / "rejected-backup"
        expected = {
            "unknown_blob": (RuntimeError, "inventory differs"),
            "corrupt_blob": (BlobStorageError, "blob_integrity_mismatch"),
            "active_reservation": (RuntimeError, "Resolve active file journals"),
        }[fault]
        with pytest.raises(expected[0], match=expected[1]):
            FileStorageRecoveryAcceptance(backup, root, auth_settings["path"]).run()
        assert not (backup / "manifest.json").exists()
        assert len(list(root.rglob("*.blob"))) == 2
    finally:
        asyncio.run(cleanup_owners(auth_settings["principals"]))


def test_actual_http_reservation_races_charge_once_and_enforce_capacity(file_client):
    """Prove idempotency and quota contention through concurrent real HTTP adapters and DB sessions."""
    client, auth, _ = file_client
    headers = auth["headers"][0]

    def send(shared):
        """Submit one authenticated reservation from a separate HTTP caller thread."""
        return client.post(
            "/api/v1/files",
            json=declaration(b"hello file", key="race" if shared else None),
            headers=headers,
        )

    with ThreadPoolExecutor(max_workers=4) as pool:
        responses = list(pool.map(send, [True] * 4))
        assert all(response.status_code == 201 for response in responses)
        assert len({response.json()["id"] for response in responses}) == 1
        responses = list(pool.map(send, [False] * 4))
    assert [response.status_code for response in responses].count(201) == 1
    assert [response.status_code for response in responses].count(429) == 3
    assert client.portal.call(
        counts, app.state.file_service, auth["principals"][0]
    ) == (20, 2, 2)


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["database_release", "purge_sync"])
async def test_cleanup_failure_retains_charge_and_recovers_once(
    owned_service, tmp_path, monkeypatch, failure
):
    """Keep purging allocation after real unlink or rolled-back counter updates, then retry safely."""
    service, owners = owned_service
    row = await service.reserve(owners[0], **declaration(b"hello file"))
    await service.upload(owners[0], row["id"], body())
    blob = next((tmp_path / "blobs").rglob("*.blob"))
    parent_inode = blob.parent.stat().st_ino
    original_sync = os.fsync
    original_adjust = service.journal._adjust

    async def fail_counter_commit(session, owner_id, **values):
        """Execute real counter updates before forcing rollback of the same release transaction."""
        await original_adjust(session, owner_id, **values)
        if values.get("files") == -1:
            raise SQLAlchemyError("controlled-release-failure")

    def fail_purge_sync(descriptor):
        """Fail the actual object-parent fsync only after its final payload name was unlinked."""
        if not blob.exists() and os.fstat(descriptor).st_ino == parent_inode:
            raise OSError(errno.EIO, "controlled-sync-failure")
        original_sync(descriptor)

    with monkeypatch.context() as fault:
        if failure == "database_release":
            fault.setattr(service.journal, "_adjust", fail_counter_commit)
            with pytest.raises(SQLAlchemyError, match="controlled-release-failure"):
                await service.delete(owners[0], row["id"])
        else:
            fault.setattr(os, "fsync", fail_purge_sync)
            assert await service.delete(owners[0], row["id"]) is False
    assert not blob.exists()
    assert await counts(service, owners[0]) == (10, 1, 0)
    assert (await service.recover_once())["completed"] == 1
    assert await counts(service, owners[0]) == (0, 0, 0)
    assert (await service.recover_once())["completed"] == 0


@pytest.mark.asyncio
async def test_concurrent_http_delete_fences_a_receiving_upload(
    owned_service, auth_settings
):
    """Hide a receiving file immediately and prevent ready publication while its request finishes."""
    service, owners = owned_service
    principals = json.loads(auth_settings["path"].read_text())
    for entry, owner in zip(principals["principals"], owners):
        entry["id"] = str(owner)
    auth_settings["path"].write_text(json.dumps(principals))
    application = FastAPI()
    application.include_router(file_router, prefix="/api/v1")
    application.state.file_service = service
    application.state.pool_telemetry = None
    transport = httpx.ASGITransport(app=application, client=("127.0.0.1", 43000))
    entered, release = asyncio.Event(), asyncio.Event()

    async def slow_stream():
        """Keep a real HTTP body receiving after the first chunk has been written."""
        yield b"hello"
        entered.set()
        await release.wait()
        yield b" file"

    async with httpx.AsyncClient(
        transport=transport, base_url="http://localhost"
    ) as client:
        headers = auth_settings["headers"][0]
        reserved = await client.post(
            "/api/v1/files", json=declaration(b"hello file"), headers=headers
        )
        assert reserved.status_code == 201
        route = "/api/v1/files/" + reserved.json()["id"]
        upload = asyncio.create_task(
            client.put(route + "/content", content=slow_stream(), headers=headers)
        )
        try:
            await asyncio.wait_for(entered.wait(), 2)
            assert (await client.delete(route, headers=headers)).status_code == 202
            assert (await client.get(route, headers=headers)).status_code == 404
            assert await counts(service, owners[0]) == (10, 1, 1)
        finally:
            release.set()
            result = await asyncio.gather(upload, return_exceptions=True)
        assert isinstance(result[0], httpx.Response) and result[0].status_code == 409
        assert await counts(service, owners[0]) == (0, 0, 0)
        assert (await client.delete(route, headers=headers)).status_code == 204
