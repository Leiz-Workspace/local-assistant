"""Verify real owner-scoped PDF extraction, immutable provenance and FD lifecycle races."""

import asyncio
import logging
import os
import threading
from pathlib import Path

import pytest
from test_file_http import (
    body,
    counts,
    declaration,
    reserve,
)
from test_file_http import file_client as file_client
from test_file_http import owned_service as owned_service

from apps.api.main import app
from apps.api.services import files as service_module
from src.application.services.file_storage_policy import StoragePolicyError

logger = logging.getLogger(__name__)
GOLDEN = Path(__file__).parents[1] / "fixtures/pdf/native-pages.pdf"


def test_authenticated_native_pdf_provenance(file_client):
    """Extract exact golden text with owner-only locators, no caching and unchanged source quota."""
    client, auth, _ = file_client
    a, b = auth["headers"]
    data = GOLDEN.read_bytes()
    row = reserve(client, a, data, "golden.pdf")
    route = "/api/v1/files/" + row["id"]
    assert client.post(route + "/extract", headers=a).status_code == 409
    assert client.put(route + "/content", headers=a, content=data).status_code == 200
    assert client.post(route + "/extract").status_code == 401
    assert client.post(route + "/extract", headers=b).status_code == 404
    response = client.post(route + "/extract", headers=a)
    assert response.status_code == 200, response.text
    result = response.json()
    assert (
        result["file_id"] == row["id"]
        and result["sha256"] == declaration(data)["sha256"]
    )
    assert result["content_trust"] == "untrusted"
    assert result["extractor"].startswith("native-pdf-v1:pypdf-")
    assert [page["text"] for page in result["pages"]] == [
        "Page one: Alpha 123\nSecond line.",
        "Xin ệ",
        "",
    ]
    assert [page["status"] for page in result["pages"]] == [
        "native_text",
        "native_text",
        "no_native_text",
    ]
    for number, page in enumerate(result["pages"], 1):
        assert page["page_number"] == number
        assert page["locator"] == f"file:{row['id']}#page={number}"
    assert response.headers["cache-control"] == "private, no-store"
    assert client.portal.call(
        counts, app.state.file_service, auth["principals"][0]
    ) == (len(data), 1, 0)
    assert client.get(route + "/content", headers=a).content == data
    assert client.post(route + "/extract", headers=a).json() == result
    assert client.delete(route, headers=a).status_code == 204
    assert client.post(route + "/extract", headers=a).status_code == 404
    logger.info("pdf_http_provenance_verified pages=3")


def test_non_pdf_and_corrupt_ready_source(file_client):
    """Reject non-PDF and detect on-disk tampering before a parser returns text."""
    client, auth, root = file_client
    headers = auth["headers"][0]
    for filename, data in [("text.txt", b"hello"), ("golden.pdf", GOLDEN.read_bytes())]:
        row = reserve(client, headers, data, filename)
        route = "/api/v1/files/" + row["id"]
        assert (
            client.put(route + "/content", headers=headers, content=data).status_code
            == 200
        )
        if filename.endswith(".pdf"):
            paths = list(root.rglob(row["id"] + ".blob"))
            paths[0].write_bytes(b"!" * len(data))
        response = client.post(route + "/extract", headers=headers)
        assert response.status_code == (503 if filename.endswith(".pdf") else 415)
        assert "hello" not in response.text and "Page one" not in response.text
        assert client.delete(route, headers=headers).status_code == 204


async def ready_pdf(service, owner):
    """Upload a golden PDF through the real journal, private FS and sandbox verifier."""
    data = GOLDEN.read_bytes()
    row = await service.reserve(owner, **declaration(data, "golden.pdf"))
    await service.upload(
        owner,
        row["id"],
        body(data),
        declared_media="application/pdf",
        content_length=len(data),
    )
    return row


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["delete", "cancel", "shutdown", "tamper"])
async def test_extraction_join_and_revalidation(owned_service, monkeypatch, action):
    """Keep locks through thread completion and reject sources hidden or changed during parsing."""
    service, owners = owned_service
    row = await ready_pdf(service, owners[0])
    entered, release = threading.Event(), threading.Event()
    original = service_module.extract_reader

    def blocked(reader):
        """Hold the production locked reader until an independent lifecycle action completes."""
        result = original(reader)
        entered.set()
        assert release.wait(5)
        return result

    monkeypatch.setattr(service_module, "extract_reader", blocked)
    task = asyncio.create_task(service.extract(owners[0], row["id"]))
    assert await asyncio.to_thread(entered.wait, 3)
    shutdown = None
    try:
        if action == "delete":
            assert not await service.delete(owners[0], row["id"])
            assert await counts(service, owners[0]) == (len(GOLDEN.read_bytes()), 1, 0)
        elif action == "cancel":
            task.cancel()
            await asyncio.sleep(0)
            assert not task.done()
            assert not await service.delete(owners[0], row["id"])
        elif action == "shutdown":
            shutdown = asyncio.create_task(service.shutdown())
            await asyncio.sleep(0.02)
            assert not shutdown.done()
        else:
            # Mutate the exact test inode through its retained descriptor to simulate operator corruption.
            identity = service_module.identity_for(
                await service.journal.get(owners[0], row["id"])
            )
            reader = service.storage.open_reader(identity)
            try:
                writable = os.open("/proc/self/fd/" + str(reader._fd), os.O_WRONLY)
                try:
                    os.pwrite(writable, b"!", 0)
                finally:
                    os.close(writable)
            finally:
                reader.close()
        release.set()
        with pytest.raises(
            (
                StoragePolicyError,
                asyncio.CancelledError,
                service_module.BlobStorageError,
            )
        ):
            await task
        assert service._extractions == 0 and not service.active
        if shutdown is not None:
            await shutdown
        else:
            assert await service.delete(owners[0], row["id"])
            assert await counts(service, owners[0]) == (0, 0, 0)
    finally:
        release.set()
        await asyncio.gather(task, return_exceptions=True)
        if shutdown is not None:
            await shutdown


@pytest.mark.asyncio
async def test_bounded_extraction_admission(owned_service, monkeypatch):
    """Admit two parsers only, reject queued work and release slots after completion."""
    service, owners = owned_service
    row = await ready_pdf(service, owners[0])
    release = threading.Event()
    entered = threading.Barrier(3)
    original = service_module.extract_reader

    def blocked(reader):
        """Hold both parser slots while a third request attempts admission."""
        entered.wait(timeout=3)
        assert release.wait(5)
        return original(reader)

    monkeypatch.setattr(service_module, "extract_reader", blocked)
    tasks = [
        asyncio.create_task(service.extract(owners[0], row["id"])) for _ in range(2)
    ]
    try:
        await asyncio.to_thread(entered.wait, 3)
        with pytest.raises(StoragePolicyError, match="extraction_busy"):
            await service.extract(owners[0], row["id"])
        release.set()
        results = await asyncio.gather(*tasks)
        assert results[0] == results[1]
        assert service._extractions == 0 and not service.active
    finally:
        release.set()
        await asyncio.gather(*tasks, return_exceptions=True)
        await service.delete(owners[0], row["id"])


@pytest.mark.asyncio
async def test_namespace_isolation_before_extraction(
    owned_service, tmp_path, monkeypatch
):
    """Hide a ready source from a different storage namespace before scheduling a parser."""
    from src.infrastructure.local_blob_storage import LocalBlobStorage

    service, owners = owned_service
    row = await ready_pdf(service, owners[0])
    foreign = service_module.FileService(
        service.journal, LocalBlobStorage(tmp_path / "foreign")
    )

    def forbidden(reader):
        """Fail the test if a foreign namespace reaches the extraction worker."""
        pytest.fail("foreign namespace scheduled parser")

    monkeypatch.setattr(service_module, "extract_reader", forbidden)
    try:
        with pytest.raises(StoragePolicyError, match="file_not_found"):
            await foreign.extract(owners[0], row["id"])
        assert foreign._extractions == 0 and not foreign.active
    finally:
        await foreign.shutdown()
        await service.delete(owners[0], row["id"])
