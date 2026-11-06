"""Verify authenticated per-page OCR/vision source fencing, response admission and cancellation joins."""

import asyncio
import base64
import logging
import os
import threading
from pathlib import Path

import pytest
from test_file_http import body, counts, declaration, reserve
from test_file_http import file_client as file_client
from test_file_http import owned_service as owned_service

from apps.api.main import app
from apps.api.routes import ocr as route_module
from apps.api.services import files as service_module
from src.application.services.file_storage_policy import StoragePolicyError
from src.infrastructure.local_blob_storage import LocalBlobStorage

logger = logging.getLogger(__name__)
ROOT = Path(__file__).parents[1] / "fixtures/ocr"


def test_owned_scanned_pdf_page_mapping_auth_and_uncertainty(file_client):
    """Extract exact source pages while preserving owner isolation, allocation and blank-page uncertainty."""
    client, auth, _ = file_client
    a, b = auth["headers"]
    data = (ROOT / "scanned.pdf").read_bytes()
    row = reserve(client, a, data, "scan.pdf")
    route = "/api/v1/files/" + row["id"]
    assert client.post(route + "/ocr", headers=a).status_code == 409
    assert client.put(route + "/content", headers=a, content=data).status_code == 200
    assert client.post(route + "/ocr").status_code == 401
    assert client.post(route + "/ocr", headers=b).status_code == 404
    response = client.post(route + "/ocr?page=1", headers=a)
    assert response.status_code == 200, response.text
    result = response.json()
    assert (
        result["file_id"] == row["id"]
        and result["sha256"] == declaration(data)["sha256"]
    )
    assert result["locator"] == f"file:{row['id']}#page=1" and result["page_count"] == 2
    assert (
        result["method"] == "tesseract"
        and result["text"] == "LOCAL OCR GOLDEN\nInvoice 2048\nTotal 42 USD"
    )
    assert result["content_trust"] == "untrusted" and "image_base64" not in result
    assert response.headers["cache-control"] == "private, no-store"
    blank = client.post(route + "/ocr?page=2", headers=a).json()
    assert blank["locator"].endswith("#page=2") and blank["review_required"]
    assert blank["confidence_score"] is None and blank["text"] == ""
    for query in ("page=3", "page=0", "mode=unknown"):
        assert client.post(route + "/ocr?" + query, headers=a).status_code == 422
    assert client.get(route + "/content", headers=a).content == data
    assert client.portal.call(
        counts, app.state.file_service, auth["principals"][0]
    ) == (len(data), 1, 0)
    assert client.delete(route, headers=a).status_code == 204
    assert client.post(route + "/ocr", headers=a).status_code == 404
    logger.info("ocr_http_scan_page_mapping_verified")


def test_explicit_vision_keeps_confidence_unknown_and_raster_private(
    file_client, monkeypatch
):
    """Pass sanitized pixels only and retain mandatory model-review semantics in the public response."""
    client, auth, _ = file_client
    headers = auth["headers"][0]
    data = (ROOT / "table-vie.png").read_bytes()
    row = reserve(client, headers, data, "table.png")
    route = "/api/v1/files/" + row["id"]
    assert (
        client.put(route + "/content", headers=headers, content=data).status_code == 200
    )

    async def vision(image):
        """Inspect the normalized raster and return structured untrusted synthetic table data."""
        assert base64.b64decode(image).startswith(b"\x89PNG\r\n\x1a\n")
        return {
            "text": "table",
            "tables": [{"rows": [["Bút", "3"]]}],
            "uncertain_regions": [],
            "engine": "synthetic-core",
        }

    monkeypatch.setattr(service_module, "transcribe_image", vision)
    response = client.post(route + "/ocr?mode=vlm", headers=headers)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["method"] == "local_vlm" and result["engine"] == "synthetic-core"
    assert result["review_required"] and result["confidence_score"] is None
    assert result["table_structure_status"] == "unverified_vlm" and result["tables"][0][
        "rows"
    ] == [["Bút", "3"]]
    assert "image_base64" not in result and not app.state.file_service._ocr_operations
    assert client.delete(route, headers=headers).status_code == 204


@pytest.mark.parametrize("kind", ["wrong_type", "tampered", "reply_limit"])
def test_invalid_source_or_reply_budget_closes_admission(
    file_client, monkeypatch, kind
):
    """Reject unsupported/corrupt sources and overbudget provenance replies without leaking held readers."""
    client, auth, root = file_client
    headers = auth["headers"][0]
    data = b"hello text" if kind == "wrong_type" else (ROOT / "clean.png").read_bytes()
    row = reserve(
        client, headers, data, "source.txt" if kind == "wrong_type" else "source.png"
    )
    route = "/api/v1/files/" + row["id"]
    assert (
        client.put(route + "/content", headers=headers, content=data).status_code == 200
    )
    if kind == "tampered":
        next(root.rglob(row["id"] + ".blob")).write_bytes(b"!" * len(data))
    if kind == "reply_limit":
        monkeypatch.setattr(route_module, "MAX_REPLY_BYTES", 1)
    response = client.post(route + "/ocr", headers=headers)
    assert (
        response.status_code
        == {"wrong_type": 415, "tampered": 503, "reply_limit": 413}[kind]
    )
    assert app.state.file_service._ocr_operations == 0
    assert client.delete(route, headers=headers).status_code == 204


async def ready_image(service, owner):
    """Upload a real verified synthetic page using the existing file journal and sandbox verifier."""
    data = (ROOT / "clean.png").read_bytes()
    row = await service.reserve(owner, **declaration(data, "clean.png"))
    await service.upload(
        owner,
        row["id"],
        body(data),
        declared_media="image/png",
        content_length=len(data),
    )
    return row


async def operation(service, owner, identifier, mode="auto"):
    """Consume one fully tracked page operation and release its source lock after inspection."""
    async with service.ocr_operation(owner, identifier, mode=mode) as (_, page):
        return page


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["delete", "cancel", "shutdown", "tamper"])
async def test_cpu_completion_is_joined_and_fenced_before_vision(
    owned_service, monkeypatch, action
):
    """Retain worker/source ownership and refuse any model disclosure after deletion or corruption."""
    service, owners = owned_service
    row = await ready_image(service, owners[0])
    entered, release = threading.Event(), threading.Event()
    original = service_module.prepare_ocr_reader

    def blocked(reader, suffix, number, mode):
        """Hold a real completed sanitized raster while lifecycle actions race with source revalidation."""
        page = original(reader, suffix, number, mode)
        entered.set()
        assert release.wait(5)
        return page

    async def forbidden(image):
        """Fail if a fenced source can reach the local model."""
        pytest.fail("fenced source disclosed to model")

    monkeypatch.setattr(service_module, "prepare_ocr_reader", blocked)
    monkeypatch.setattr(service_module, "transcribe_image", forbidden)
    task = asyncio.create_task(operation(service, owners[0], row["id"], "vlm"))
    shutdown = None
    try:
        assert await asyncio.to_thread(entered.wait, 3)
        if action == "delete":
            assert not await service.delete(owners[0], row["id"])
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
            reader = service.storage.open_reader(
                service_module.identity_for(
                    await service.journal.get(owners[0], row["id"])
                )
            )
            try:
                descriptor = os.open("/proc/self/fd/" + str(reader._fd), os.O_WRONLY)
                try:
                    os.pwrite(descriptor, b"!", 0)
                finally:
                    os.close(descriptor)
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
        assert service._ocr_operations == 0 and not service.active
        if shutdown is None:
            assert await service.delete(owners[0], row["id"])
    finally:
        release.set()
        await asyncio.gather(task, return_exceptions=True)
        if shutdown is not None:
            await shutdown


@pytest.mark.asyncio
async def test_cancelled_vision_joins_before_releasing_source_and_slot(
    owned_service, monkeypatch
):
    """Keep model admission until its bounded request completes even if the original client cancels."""
    service, owners = owned_service
    row = await ready_image(service, owners[0])
    entered, release = asyncio.Event(), asyncio.Event()

    async def vision(image):
        """Emulate an already admitted local model request with explicit completion ownership."""
        entered.set()
        await release.wait()
        return {
            "text": "synthetic",
            "tables": [],
            "uncertain_regions": [],
            "engine": "synthetic-core",
        }

    monkeypatch.setattr(service_module, "transcribe_image", vision)
    task = asyncio.create_task(operation(service, owners[0], row["id"], "vlm"))
    try:
        await asyncio.wait_for(entered.wait(), 3)
        task.cancel()
        await asyncio.sleep(0.02)
        assert not task.done() and service._ocr_operations == 1
        with pytest.raises(StoragePolicyError, match="ocr_processing_busy"):
            await operation(service, owners[0], row["id"])
        assert not await service.delete(owners[0], row["id"])
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert not service.active and service._ocr_operations == 0
        assert await service.delete(owners[0], row["id"])
        assert await counts(service, owners[0]) == (0, 0, 0)
    finally:
        release.set()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_slow_response_holds_single_slot_and_lock(owned_service):
    """Bound response retention and close source admission on a disconnected slow client."""
    service, owners = owned_service
    row = await ready_image(service, owners[0])
    entered, release = asyncio.Event(), asyncio.Event()

    async def send(message):
        """Delay the body while a second operation and deletion attempt to acquire admission."""
        if message["type"] == "http.response.body":
            entered.set()
            await release.wait()

    async def receive():
        """Provide a minimal regular response receive callable."""
        return {"type": "http.request", "body": b"", "more_body": False}

    async def serve():
        """Construct and send a real OCR reply within its original active task."""
        response = await route_module.ocr_response(service, owners[0], row["id"])
        await response({"type": "http"}, receive, send)

    task = asyncio.create_task(serve())
    try:
        await asyncio.wait_for(entered.wait(), 5)
        with pytest.raises(StoragePolicyError, match="ocr_processing_busy"):
            await operation(service, owners[0], row["id"])
        assert not await service.delete(owners[0], row["id"])
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert service._ocr_operations == 0 and not service.active
        assert await service.delete(owners[0], row["id"])
    finally:
        release.set()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_wrong_namespace_and_response_construction_cleanup(
    owned_service, tmp_path, monkeypatch
):
    """Hide foreign namespace sources and close an admitted reader when response creation fails."""
    service, owners = owned_service
    row = await ready_image(service, owners[0])
    foreign = service_module.FileService(
        service.journal, LocalBlobStorage(tmp_path / "foreign")
    )

    def broken(*args):
        """Fail after actual OCR to exercise response ownership transfer cleanup."""
        raise ValueError("controlled response failure")

    try:
        with pytest.raises(StoragePolicyError, match="file_not_found"):
            await operation(foreign, owners[0], row["id"])
        monkeypatch.setattr(route_module, "OcrResponse", broken)
        with pytest.raises(ValueError, match="controlled response failure"):
            await route_module.ocr_response(service, owners[0], row["id"])
        assert service._ocr_operations == 0 and not service.active
        assert await service.delete(owners[0], row["id"])
    finally:
        await foreign.shutdown()
