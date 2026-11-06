"""Exercise authenticated file HTTP, persistent quotas and cancellation using real DB/private roots."""

import asyncio
import hashlib
import io
import logging
import os
import threading
import time
from dataclasses import replace
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from PIL import Image
from pypdf import PdfWriter
from sqlalchemy import text
from sqlalchemy.exc import TimeoutError as PoolTimeout

from apps.api.main import app
from apps.api.routes.files import FileDownloadResponse
from apps.api.services import files as service_module
from apps.api.services.files import FileService, file_io
from apps.api.storage.files import initialize_file_service
from src.application.services.file_storage_policy import (
    DEFAULT_POLICY,
    StoragePolicyError,
)
from src.infrastructure.database.connection import (
    create_database_engine,
    create_session_factory,
)
from src.infrastructure.local_blob_storage import BlobWriter, LocalBlobStorage
from src.infrastructure.repositories.file_journal import PostgresFileJournal

logger = logging.getLogger(__name__)


async def cleanup_owners(owners):
    """Remove only test UUID journals and subtract their outstanding locked allocations."""
    engine = create_database_engine()
    sessions = create_session_factory(engine)
    try:
        async with sessions() as session, session.begin():
            await session.execute(
                text(
                    "SELECT singleton FROM assistant.file_global_usage WHERE singleton=1 FOR UPDATE"
                )
            )
            rows = (
                (
                    await session.execute(
                        text(
                            "SELECT * FROM assistant.file_owner_usage WHERE owner_id IN (:a,:b) FOR UPDATE"
                        ),
                        {"a": owners[0], "b": owners[1]},
                    )
                )
                .mappings()
                .all()
            )
            totals = {
                name: sum(row[name] for row in rows)
                for name in ("allocated_bytes", "allocated_files", "active_uploads")
            }
            await session.execute(
                text("DELETE FROM assistant.files WHERE owner_id IN (:a,:b)"),
                {"a": owners[0], "b": owners[1]},
            )
            await session.execute(
                text(
                    "DELETE FROM assistant.file_owner_usage WHERE owner_id IN (:a,:b)"
                ),
                {"a": owners[0], "b": owners[1]},
            )
            await session.execute(
                text(
                    "UPDATE assistant.file_global_usage SET allocated_bytes=allocated_bytes-:allocated_bytes,allocated_files=allocated_files-:allocated_files,active_uploads=active_uploads-:active_uploads WHERE singleton=1"
                ),
                totals,
            )
        logger.info("file_http_test_cleanup owners=2")
    finally:
        await engine.dispose()


async def counts(service, owner):
    """Read committed per-owner usage for HTTP and cancellation acceptance assertions."""
    async with service.journal.sessions() as session:
        row = (
            await session.execute(
                text(
                    "SELECT allocated_bytes,allocated_files,active_uploads FROM assistant.file_owner_usage WHERE owner_id=:owner"
                ),
                {"owner": owner},
            )
        ).one_or_none()
    return tuple(row) if row is not None else (0, 0, 0)


@pytest.fixture
def file_client(auth_settings, tmp_path, monkeypatch):
    """Enable files only for a disposable private root and real application DB tests."""
    if not os.environ.get("DATABASE_URL"):
        pytest.skip("DATABASE_URL not configured")
    monkeypatch.setenv("ASSISTANT_FILES_ENABLED", "1")
    root = tmp_path / "blobs"
    monkeypatch.setenv("ASSISTANT_FILES_ROOT", str(root))
    try:
        with TestClient(app, client=("127.0.0.1", 43000)) as client:
            yield client, auth_settings, root
    finally:
        asyncio.run(cleanup_owners(auth_settings["principals"]))


def declaration(data, filename="private.txt", key=None):
    """Build exact size/hash declarations from test bytes without exposing internal owner fields."""
    return {
        "filename": filename,
        "size_bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "request_key": key,
    }


def reserve(client, headers, data=b"hello file", filename="private.txt", key=None):
    """Reserve a real owned file and assert successful atomic admission."""
    response = client.post(
        "/api/v1/files", json=declaration(data, filename, key), headers=headers
    )
    assert response.status_code == 201, response.text
    return response.json()


@pytest.mark.parametrize("suffix", ["txt", "png", "pdf"])
def test_http_roundtrip_provenance_replay_and_delete(file_client, suffix):
    """Persist real bytes, filter internal metadata, replay once and delete only after purge."""
    client, auth, root = file_client
    headers = auth["headers"][0]
    output = io.BytesIO()
    if suffix == "png":
        Image.new("RGB", (8, 8), "blue").save(output, "PNG")
    elif suffix == "pdf":
        writer = PdfWriter()
        writer.add_blank_page(width=100, height=100)
        writer.write(output)
    else:
        output.write("Xin chào file\n".encode())
    data = output.getvalue()
    row = reserve(client, headers, data, "tài liệu." + suffix, "once")
    identifier = row["id"]
    route = "/api/v1/files/" + identifier
    assert row["state"] == "reserved"
    assert client.get(route + "/content", headers=headers).status_code == 409
    result = client.put(
        route + "/content",
        content=data,
        headers={**headers, "Content-Type": "application/octet-stream"},
    )
    assert result.status_code == 200, result.text
    ready = result.json()
    assert ready["state"] == "ready" and ready["verified_at"]
    assert ready["sha256"] == hashlib.sha256(data).hexdigest()
    assert not {
        "owner_id",
        "storage_key",
        "lease_owner",
        "purge_token",
        "request_fingerprint",
    }.intersection(ready)
    content = client.get(route + "/content", headers=headers)
    assert content.status_code == 200 and content.content == data
    assert content.headers["x-content-type-options"] == "nosniff"
    assert content.headers["content-disposition"].startswith(
        "attachment; filename*=UTF-8''"
    )
    assert content.headers["content-length"] == str(len(data))
    assert (
        client.put(route + "/content", content=data, headers=headers).status_code == 409
    )
    assert (
        reserve(client, headers, data, "tài liệu." + suffix, "once")["id"] == identifier
    )
    assert client.portal.call(
        counts, app.state.file_service, auth["principals"][0]
    ) == (len(data), 1, 0)
    assert client.delete(route, headers=headers).status_code == 204
    assert client.delete(route, headers=headers).status_code == 204
    assert client.get(route, headers=headers).status_code == 404
    assert client.get(route + "/content", headers=headers).status_code == 404
    assert not list(root.rglob("*.blob"))
    assert client.portal.call(
        counts, app.state.file_service, auth["principals"][0]
    ) == (0, 0, 0)


def test_owner_acl_and_no_auth_or_proxy_bypass(file_client):
    """Deny foreign UUID operations, forged identity, anonymous and Origin-bearing requests."""
    client, auth, _ = file_client
    a, b = auth["headers"]
    row = reserve(client, a, key="shared")
    route = "/api/v1/files/" + row["id"]
    assert client.get("/api/v1/files").status_code == 401
    assert (
        client.get(
            "/api/v1/files", headers={**a, "Origin": "http://localhost"}
        ).status_code
        == 403
    )
    assert (
        client.get(
            "/api/v1/files", headers={**a, "X-Forwarded-For": "127.0.0.1"}
        ).status_code
        == 403
    )
    assert client.get("/api/v1/files", headers=b).json() == []
    for method, suffix in [
        ("GET", ""),
        ("GET", "/content"),
        ("PUT", "/content"),
        ("DELETE", ""),
    ]:
        response = client.request(
            method,
            route + suffix,
            headers={**b, "X-User-ID": str(auth["principals"][0])},
            content=b"hello file" if method == "PUT" else None,
        )
        assert response.status_code == 404
    assert reserve(client, b, key="shared")["id"] != row["id"]
    forged = {**declaration(b"test"), "owner_id": str(auth["principals"][0])}
    assert client.post("/api/v1/files", json=forged, headers=b).status_code == 422


@pytest.mark.parametrize(
    "metadata",
    [
        b"{}",
        b'{"filename":"a.txt","filename":"b.txt"}',
        b"\xff",
        b"[]",
        b'{"filename":"../escape.txt","size_bytes":1,"sha256":"' + b"0" * 64 + b'"}',
        b'{"filename":"a.txt","size_bytes":true,"sha256":"' + b"0" * 64 + b'"}',
    ],
)
def test_invalid_metadata_never_creates_payload(file_client, metadata):
    """Reject malformed, duplicate, unknown or traversal declarations before blob admission."""
    client, auth, root = file_client
    response = client.post(
        "/api/v1/files",
        content=metadata,
        headers={**auth["headers"][0], "Content-Type": "application/json"},
    )
    assert response.status_code == 422
    assert not list(root.rglob("*.part"))


def test_metadata_envelope_is_bounded_for_chunked_and_sized_bodies(file_client):
    """Check actual bytes before JSON parsing rather than trusting Content-Length."""
    client, auth, _ = file_client
    headers = {**auth["headers"][0], "Content-Type": "application/json"}
    for body in (b"x" * 8193, iter([b"x" * 4096, b"x" * 4097])):
        assert (
            client.post("/api/v1/files", content=body, headers=headers).status_code
            == 413
        )


@pytest.mark.parametrize(
    "failure", ["short", "overflow", "hash", "mime", "declared_mime"]
)
def test_invalid_raw_streams_are_hidden_and_release_after_cleanup(file_client, failure):
    """Reject observed body/hash/type violations and verify no terminal payload/quota remains."""
    client, auth, root = file_client
    headers = auth["headers"][0]
    payload = {
        "short": b"hello",
        "overflow": b"hello file extra",
        "hash": b"HELLO FILE",
        "mime": b"\x00" * 10,
        "declared_mime": b"hello file",
    }[failure]
    row = reserve(client, headers, payload if failure == "mime" else b"hello file")
    media = "image/png" if failure == "declared_mime" else "application/octet-stream"
    result = client.put(
        "/api/v1/files/" + row["id"] + "/content",
        content=iter([payload]),
        headers={**headers, "Content-Type": media},
    )
    assert (
        result.status_code
        == {
            "short": 422,
            "overflow": 413,
            "hash": 422,
            "mime": 415,
            "declared_mime": 415,
        }[failure]
    ), result.text
    assert client.get("/api/v1/files/" + row["id"], headers=headers).status_code == 404
    assert client.portal.call(
        counts, app.state.file_service, auth["principals"][0]
    ) == (0, 0, 0)
    assert not list(root.rglob("*.part")) and not list(root.rglob("*.blob"))


def test_held_reader_returns_pending_delete_without_releasing_allocation(file_client):
    """Return 202 while a real shared reader FD holds bytes, then 204 after it closes."""
    client, auth, _ = file_client
    headers = auth["headers"][0]
    row = reserve(client, headers)
    route = "/api/v1/files/" + row["id"]
    assert (
        client.put(
            route + "/content", content=b"hello file", headers=headers
        ).status_code
        == 200
    )
    service = app.state.file_service
    _, reader = client.portal.call(
        service.open_download, auth["principals"][0], UUID(row["id"])
    )
    try:
        deleted = client.delete(route, headers=headers)
        assert deleted.status_code == 202 and deleted.json()["state"] == "purging"
        assert client.get(route, headers=headers).status_code == 404
        assert client.get(route + "/content", headers=headers).status_code == 404
        assert client.portal.call(counts, service, auth["principals"][0]) == (10, 1, 0)
    finally:
        client.portal.call(file_io, reader.close)
    assert client.delete(route, headers=headers).status_code == 204
    assert client.portal.call(counts, service, auth["principals"][0]) == (0, 0, 0)


@pytest.mark.parametrize("fault", ["missing", "corrupt"])
def test_ready_blob_fault_never_serves_bad_bytes(file_client, fault):
    """Fail before response headers and retain charged metadata when ready storage is damaged."""
    client, auth, root = file_client
    headers = auth["headers"][0]
    row = reserve(client, headers)
    route = "/api/v1/files/" + row["id"]
    assert (
        client.put(
            route + "/content", content=b"hello file", headers=headers
        ).status_code
        == 200
    )
    blob = next(root.rglob("*.blob"))
    blob.unlink() if fault == "missing" else blob.write_bytes(b"CORRUPTION")
    result = client.get(route + "/content", headers=headers)
    assert result.status_code == 503 and b"CORRUPTION" not in result.content
    assert client.portal.call(
        counts, app.state.file_service, auth["principals"][0]
    ) == (10, 1, 0)
    assert client.delete(route, headers=headers).status_code == 204


def test_pool_errors_do_not_return_driver_text(file_client, monkeypatch):
    """Sanitize database capacity errors without logging or returning private driver messages."""
    client, auth, _ = file_client

    async def unavailable(*args, **kwargs):
        """Inject only a pool failure at the repository boundary."""
        raise PoolTimeout("private-credential-marker")

    monkeypatch.setattr(app.state.file_service.journal, "reserve", unavailable)
    result = client.post(
        "/api/v1/files", json=declaration(b"test"), headers=auth["headers"][0]
    )
    assert (
        result.status_code == 503 and result.json()["detail"]["code"] == "pool_timeout"
    )
    assert "private-credential-marker" not in result.text


@pytest.mark.parametrize("fault", ["write", "published"])
def test_io_failure_keeps_journal_honest_and_cleans_known_bytes(
    file_client, monkeypatch, fault
):
    """Handle disk errors and publish-before-DB failure with actual hidden metadata cleanup."""
    client, auth, root = file_client
    headers = auth["headers"][0]
    row = reserve(client, headers)
    original = BlobWriter.publish

    def fail_operation(writer, *args):
        """Fail either before writing or after durable publication without fabricating ready."""
        if fault == "published":
            original(writer)
        raise OSError("private-filesystem-path")

    monkeypatch.setattr(
        BlobWriter, "write" if fault == "write" else "publish", fail_operation
    )
    result = client.put(
        "/api/v1/files/" + row["id"] + "/content",
        content=b"hello file",
        headers=headers,
    )
    assert result.status_code == 503 and "private-filesystem-path" not in result.text
    assert client.portal.call(
        counts, app.state.file_service, auth["principals"][0]
    ) == (0, 0, 0)
    assert not list(root.rglob("*.blob")) and not list(root.rglob("*.part"))


def test_feature_disabled_does_not_create_blob_root(
    auth_settings, tmp_path, monkeypatch
):
    """Keep existing deployments inert until explicit file feature enablement."""
    monkeypatch.setenv("ASSISTANT_FILES_ENABLED", "0")
    root = tmp_path / "must-not-exist"
    monkeypatch.setenv("ASSISTANT_FILES_ROOT", str(root))
    with TestClient(app, client=("127.0.0.1", 43000)) as client:
        result = client.get("/api/v1/files", headers=auth_settings["headers"][0])
        assert result.status_code == 503
    assert not root.exists()


@pytest_asyncio.fixture
async def owned_service(tmp_path):
    """Create a directly testable async service sharing one loop, pool and private root."""
    if not os.environ.get("DATABASE_URL"):
        pytest.skip("DATABASE_URL not configured")
    engine = create_database_engine()
    sessions = create_session_factory(engine)
    owners = [uuid4(), uuid4()]
    service = FileService(
        PostgresFileJournal(sessions), LocalBlobStorage(tmp_path / "blobs")
    )
    try:
        yield service, owners
    finally:
        await service.shutdown()
        await engine.dispose()
        await cleanup_owners(owners)


async def body(data=b"hello file"):
    """Produce one raw ASGI-sized body chunk without multipart or external I/O."""
    yield data


@pytest.mark.asyncio
async def test_idle_timeout_cleans_stream_and_counter(owned_service):
    """Expire an idle claimed stream using real short policy deadlines and database leases."""
    service, owners = owned_service
    policy = replace(
        DEFAULT_POLICY,
        idle_seconds=1,
        heartbeat_seconds=1,
        lease_seconds=2,
        upload_seconds=4,
    )
    service.policy = service.journal.policy = policy
    row = await service.reserve(owners[0], **declaration(b"hello file"))

    async def stalled_body():
        """Leave a body idle beyond the one-second test deadline."""
        await asyncio.sleep(2)
        yield b"hello file"

    with pytest.raises(TimeoutError):
        await service.upload(owners[0], row["id"], stalled_body())
    assert await counts(service, owners[0]) == (0, 0, 0)


@pytest.mark.asyncio
async def test_cancellation_joins_verifier_before_closing_payload(
    owned_service, monkeypatch
):
    """Keep borrowed FDs locked until an in-flight thread ends, then clean without leaked quota."""
    service, owners = owned_service
    row = await service.reserve(owners[0], **declaration(b"hello file"))
    started, release = threading.Event(), threading.Event()

    def held_verifier(writer, policy, declared_media):
        """Hold the actual borrowed descriptor until the cancellation test explicitly releases it."""
        with writer.verification_reader() as source:
            assert source.read() == b"hello file"
            started.set()
            assert release.wait(3)
        return "text/plain"

    monkeypatch.setattr(service_module, "verify_writer", held_verifier)
    task = asyncio.create_task(service.upload(owners[0], row["id"], body()))
    try:
        assert await asyncio.to_thread(started.wait, 2)
        task.cancel()
        await asyncio.sleep(0.02)
        assert not task.done()
        assert await counts(service, owners[0]) == (10, 1, 1)
    finally:
        release.set()
        result = await asyncio.gather(task, return_exceptions=True)
    assert isinstance(result[0], asyncio.CancelledError)
    assert await counts(service, owners[0]) == (0, 0, 0)


@pytest.mark.asyncio
async def test_cancel_before_response_generator_entry_closes_reader(owned_service):
    """Close a response FD even if response-start send fails before its iterator is entered."""
    service, owners = owned_service
    row = await service.reserve(owners[0], **declaration(b"hello file"))
    await service.upload(owners[0], row["id"], body())
    row, reader = await service.open_download(owners[0], row["id"])
    response = FileDownloadResponse(service, row, reader)

    async def disconnect():
        """Provide a disconnected ASGI receive channel for response cancellation."""
        return {"type": "http.disconnect"}

    async def cancelled_send(message):
        """Cancel before any response body byte can be iterated."""
        raise asyncio.CancelledError()

    with pytest.raises(asyncio.CancelledError):
        await response(
            {"type": "http", "asgi": {"spec_version": "2.4"}},
            disconnect,
            cancelled_send,
        )
    assert await service.delete(owners[0], row["id"]) is True
    assert not service.active


@pytest.mark.asyncio
async def test_shutdown_joins_active_upload_before_pool_disposal(owned_service):
    """Cancel and clean an idle request while its journal pool remains available."""
    service, owners = owned_service
    row = await service.reserve(owners[0], **declaration(b"hello file"))
    started = asyncio.Event()

    async def waiting_body():
        """Signal a claimed live writer and wait until shutdown cancels its request."""
        started.set()
        await asyncio.Event().wait()
        yield b"unreachable"

    task = asyncio.create_task(service.upload(owners[0], row["id"], waiting_body()))
    await asyncio.wait_for(started.wait(), 2)
    await asyncio.wait_for(service.shutdown(), 3)
    assert task.cancelled() and not service.active
    assert await counts(service, owners[0]) == (0, 0, 0)


@pytest.mark.asyncio
async def test_cancelled_guard_acquisition_closes_unreturned_resource(owned_service):
    """Close a guard returned by a thread even when its awaiting caller was cancelled first."""
    service, owners = owned_service
    from src.infrastructure.local_blob_storage import BlobIdentity

    identity = BlobIdentity(owners[0], uuid4(), uuid4())
    started, release = threading.Event(), threading.Event()

    def acquire_then_wait():
        """Acquire a real stable directory lock before delaying its return to the caller."""
        guard = service.storage.lock_resource(identity)
        started.set()
        assert release.wait(3)
        return guard

    task = asyncio.create_task(file_io(acquire_then_wait, close_result=True))
    try:
        assert await asyncio.to_thread(started.wait, 2)
        task.cancel()
        await asyncio.sleep(0.02)
        assert not task.done()
        assert service.storage.purge(identity) is False
    finally:
        release.set()
        result = await asyncio.gather(task, return_exceptions=True)
    assert isinstance(result[0], asyncio.CancelledError)
    assert service.storage.purge(identity) is True


@pytest.mark.asyncio
async def test_stream_wall_deadline_cannot_be_extended_by_progress(owned_service):
    """Stop a slowly progressing body at its absolute deadline despite live heartbeat renewals."""
    service, owners = owned_service
    policy = replace(
        DEFAULT_POLICY,
        idle_seconds=1,
        heartbeat_seconds=1,
        lease_seconds=2,
        upload_seconds=3,
    )
    service.policy = service.journal.policy = policy
    row = await service.reserve(owners[0], **declaration(b"x" * 10))

    async def slow_body():
        """Make byte progress within the idle window while exceeding the whole-stream budget."""
        for _ in range(10):
            await asyncio.sleep(0.4)
            yield b"x"

    start = time.monotonic()
    with pytest.raises(TimeoutError):
        await service.upload(owners[0], row["id"], slow_body())
    assert 2.5 < time.monotonic() - start < 6
    assert await counts(service, owners[0]) == (0, 0, 0)


@pytest.mark.asyncio
async def test_wrong_root_cannot_recover_or_release_another_namespace(
    owned_service, tmp_path
):
    """Reject DB/FS cleanup on a different empty root rather than treating foreign bytes as absent."""
    service, owners = owned_service
    row = await service.reserve(
        owners[0], **declaration(b"hello file", key="namespace")
    )
    other = FileService(
        PostgresFileJournal(service.journal.sessions),
        LocalBlobStorage(tmp_path / "wrong-root"),
    )
    try:
        assert await other.cleanup(row) is False
        assert await counts(service, owners[0]) == (10, 1, 1)
        assert await other.journal.list(owners[0]) == []
        with pytest.raises(StoragePolicyError, match="file_not_found"):
            await other.delete(owners[0], row["id"])
        with pytest.raises(StoragePolicyError, match="file_storage_namespace_mismatch"):
            await other.reserve(
                owners[0], **declaration(b"hello file", key="namespace")
            )
        async with service.journal.sessions() as session, session.begin():
            await session.execute(
                text(
                    "UPDATE assistant.files SET reservation_expires_at=clock_timestamp()-interval '1 second' WHERE id=:id"
                ),
                {"id": row["id"]},
            )
        assert not await other.journal.recovery_candidates()
        assert row["id"] in {
            record["id"] for record in await service.journal.recovery_candidates()
        }
    finally:
        await other.shutdown()


def test_startup_rejects_wrong_root_for_current_principals(
    file_client, tmp_path, monkeypatch
):
    """Catch root misconfiguration before file admission when bound owners have outstanding data."""
    client, auth, _ = file_client
    row = reserve(client, auth["headers"][0])
    service = app.state.file_service
    with monkeypatch.context() as settings:
        settings.setenv("ASSISTANT_FILES_ROOT", str(tmp_path / "wrong-root"))
        with pytest.raises(RuntimeError, match="does not match"):
            client.portal.call(initialize_file_service, service.journal.sessions)
    assert (
        client.get("/api/v1/files/" + row["id"], headers=auth["headers"][0]).status_code
        == 200
    )
