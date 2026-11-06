"""Verify owned document chunk APIs, source fences and joined response lifecycle against PostgreSQL."""

import asyncio
import logging
import os
import threading
from pathlib import Path

import pytest
from test_file_http import body, counts, declaration, reserve
from test_file_http import file_client as file_client
from test_file_http import owned_service as owned_service

from apps.api.main import app
from apps.api.routes import chunks as route_module
from apps.api.services import chunks as module
from apps.api.services.files import FileService, identity_for
from src.application.services.file_storage_policy import StoragePolicyError
from src.infrastructure.local_blob_storage import BlobStorageError, LocalBlobStorage

logger = logging.getLogger(__name__)
ROOT = Path(__file__).parents[1] / "fixtures"


@pytest.mark.parametrize(
    "name",
    [
        "note.txt",
        "note.md",
        "note.csv",
        "pdf/native-pages.pdf",
        "docx/styled-table.docx",
        "xlsx/styled-formulas.xlsx",
        "ocr/clean.png",
    ],
)
def test_all_formats_repeat_provenance_private_ownership_and_immutable_source(
    file_client, name
):
    """Chunk actual accepted formats with stable IDs, private source labels and no persistence."""
    client, auth, _ = file_client
    a, b = auth["headers"]
    data = (ROOT / name).read_bytes() if "/" in name else ("e\u0301ệ😀\n" * 80).encode()
    row = reserve(client, a, data, Path(name).name)
    route = "/api/v1/files/" + row["id"]
    assert client.post(route + "/chunks", headers=a).status_code == 409
    assert client.put(route + "/content", headers=a, content=data).status_code == 200
    assert client.post(route + "/chunks").status_code == 401
    assert client.post(route + "/chunks", headers=b).status_code == 404
    response = client.post(route + "/chunks", headers=a)
    assert response.status_code == 200, response.text
    result = response.json()
    assert client.post(route + "/chunks", headers=a).json() == result
    assert (
        result["file_id"] == row["id"]
        and result["sha256"] == declaration(data)["sha256"]
    )
    assert result["content_trust"] == "untrusted"
    assert result["access"]["principal_id"] == str(auth["principals"][0])
    assert (
        result["access"]["visibility"] == "private"
        and len(result["access"]["scope"]) == 64
    )
    assert result["chunks"] and all(
        c["locator"].startswith(f"file:{row['id']}#") for c in result["chunks"]
    )
    assert response.headers["cache-control"] == "private, no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    if name.endswith("png"):
        assert result["chunks"][0]["quality"]["method"] == "tesseract"
    if name.endswith("pdf"):
        assert result["empty_sources"][0]["locator"].endswith("page=3")
    assert "image_base64" not in response.text and "namespace_id" not in response.text
    assert client.get(route + "/content", headers=a).content == data
    assert client.portal.call(
        counts, app.state.file_service, auth["principals"][0]
    ) == (len(data), 1, 0)
    assert client.delete(route, headers=a).status_code == 204
    assert client.post(route + "/chunks", headers=a).status_code == 404
    logger.info("chunks_format_http_verified format=%s", Path(name).suffix)


@pytest.mark.parametrize(
    "query",
    [
        "max_bytes=255",
        "max_bytes=8193",
        "source=invalid",
        "page=2",
        "ocr_mode=vlm",
        "source=ocr",
        "page=0",
    ],
)
def test_invalid_or_irrelevant_options_are_rejected(file_client, query):
    """Reject unsupported source projections and options instead of silently ignoring them."""
    client, auth, _ = file_client
    headers = auth["headers"][0]
    data = b"owned text"
    row = reserve(client, headers, data, "note.txt")
    route = "/api/v1/files/" + row["id"]
    assert (
        client.put(route + "/content", headers=headers, content=data).status_code == 200
    )
    assert client.post(route + "/chunks?" + query, headers=headers).status_code == (
        415 if query == "source=ocr" else 422
    )
    assert app.state.file_service._chunk_operations == 0
    assert client.delete(route, headers=headers).status_code == 204


def test_explicit_pdf_ocr_maps_selected_page_and_empty_review(file_client):
    """Use existing D21 OCR only when requested and preserve selected-page review metadata."""
    client, auth, _ = file_client
    headers = auth["headers"][0]
    data = (ROOT / "ocr/scanned.pdf").read_bytes()
    row = reserve(client, headers, data, "scan.pdf")
    route = "/api/v1/files/" + row["id"]
    assert (
        client.put(route + "/content", headers=headers, content=data).status_code == 200
    )
    native = client.post(route + "/chunks", headers=headers).json()
    assert not native["chunks"] and len(native["empty_sources"]) == 2
    response = client.post(route + "/chunks?source=ocr&page=2", headers=headers)
    assert response.status_code == 200, response.text
    empty = response.json()["empty_sources"][0]
    assert empty["locator"].endswith("#page=2") and empty["quality"]["review_required"]
    assert client.delete(route, headers=headers).status_code == 204


@pytest.mark.parametrize("kind", ["tamper", "reply", "construction", "source_limit"])
def test_errors_close_reader_and_admission(file_client, monkeypatch, kind):
    """Release every retained resource on integrity, response and lexical budget failures."""
    client, auth, root = file_client
    headers, data = auth["headers"][0], b"owned private text"
    row = reserve(client, headers, data, "note.txt")
    route = "/api/v1/files/" + row["id"]
    assert (
        client.put(route + "/content", headers=headers, content=data).status_code == 200
    )
    if kind == "tamper":
        next(root.rglob(row["id"] + ".blob")).write_bytes(b"!" * len(data))
    elif kind == "reply":
        monkeypatch.setattr(route_module, "MAX_REPLY_BYTES", 1)
    elif kind == "source_limit":
        monkeypatch.setattr(module, "MAX_SOURCE_BYTES", 1)
    else:

        def broken(*args):
            """Fail during response construction after actual chunk transformation."""
            raise ValueError("controlled chunk response failure")

        monkeypatch.setattr(route_module, "ChunkResponse", broken)
    if kind == "construction":
        with pytest.raises(ValueError, match="controlled chunk response failure"):
            client.post(route + "/chunks", headers=headers)
    else:
        assert client.post(route + "/chunks", headers=headers).status_code == (
            503 if kind == "tamper" else 413
        )
    assert (
        not app.state.file_service._chunk_operations
        and not app.state.file_service.active
    )
    assert client.delete(route, headers=headers).status_code == 204


async def ready_source(service, owner, name="note.txt"):
    """Upload a verified disposable source using the existing admission/journal pipeline."""
    data = (ROOT / name).read_bytes() if "/" in name else b"owned chunk lifecycle text"
    row = await service.reserve(owner, **declaration(data, Path(name).name))
    await service.upload(owner, row["id"], body(data), content_length=len(data))
    return row


async def operation(service, owner, identifier):
    """Consume the actual chunk operation through its retained source context."""
    async with module.chunk_operation(service, owner, identifier) as (_, result):
        return result


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["delete", "cancel", "shutdown", "tamper"])
async def test_transform_join_and_final_source_fences(
    owned_service, monkeypatch, action
):
    """Join CPU work and refuse stale/deleted sources before exposing computed chunks."""
    service, owners = owned_service
    row = await ready_source(service, owners[0])
    entered, release = threading.Event(), threading.Event()
    original = module.build_chunks

    def blocked(*args):
        """Hold actual completed chunks while cancellation and source changes race."""
        result = original(*args)
        entered.set()
        assert release.wait(5)
        return result

    monkeypatch.setattr(module, "build_chunks", blocked)
    task = asyncio.create_task(operation(service, owners[0], row["id"]))
    shutdown = None
    try:
        assert await asyncio.to_thread(entered.wait, 3)
        if action == "delete":
            assert not await service.delete(owners[0], row["id"])
        elif action == "cancel":
            task.cancel()
            await asyncio.sleep(0)
            assert not task.done() and service._chunk_operations == 1
            assert not await service.delete(owners[0], row["id"])
        elif action == "shutdown":
            shutdown = asyncio.create_task(service.shutdown())
            await asyncio.sleep(0.02)
            assert not shutdown.done()
        else:
            reader = service.storage.open_reader(
                identity_for(await service.journal.get(owners[0], row["id"]))
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
            (StoragePolicyError, asyncio.CancelledError, BlobStorageError)
        ):
            await task
        assert (
            service._chunk_operations == 0
            and not service.active
            and not service._active_depth
        )
        if shutdown is None:
            assert await service.delete(owners[0], row["id"])
            assert await counts(service, owners[0]) == (0, 0, 0)
    finally:
        release.set()
        await asyncio.gather(task, return_exceptions=True)
        if shutdown is not None:
            await shutdown


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "name",
    [
        "note.txt",
        "docx/styled-table.docx",
        "xlsx/styled-formulas.xlsx",
        "ocr/clean.png",
    ],
)
async def test_slow_response_nested_tracking_busy_delete_cancel(owned_service, name):
    """Retain nested parser tracking and the outer source lock through a cancelled slow response."""
    service, owners = owned_service
    row = await ready_source(service, owners[0], name)
    entered, release = asyncio.Event(), asyncio.Event()

    async def send(message):
        """Hold response body delivery while a second request and deletion race."""
        if message["type"] == "http.response.body":
            entered.set()
            await release.wait()

    async def receive():
        """Provide a minimal regular HTTP request receiver."""
        return {"type": "http.request", "body": b"", "more_body": False}

    async def serve():
        """Construct and deliver the response within the owning active task."""
        response = await route_module.chunk_response(service, owners[0], row["id"])
        await response({"type": "http"}, receive, send)

    task = asyncio.create_task(serve())
    try:
        await asyncio.wait_for(entered.wait(), 5)
        assert task in service.active
        assert service._active_depth[task] == (1 if name == "note.txt" else 2)
        with pytest.raises(StoragePolicyError, match="chunk_processing_busy"):
            await operation(service, owners[0], row["id"])
        with pytest.raises(StoragePolicyError, match="file_not_found"):
            await operation(service, owners[1], row["id"])
        assert not await service.delete(owners[0], row["id"])
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert (
            not service.active
            and not service._active_depth
            and service._chunk_operations == 0
        )
        assert await service.delete(owners[0], row["id"])
    finally:
        release.set()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_wrong_namespace_and_nested_tracking_survives_inner_close(
    owned_service, tmp_path
):
    """Hide foreign storage and retain outer tracked work after nested context teardown."""
    service, owners = owned_service
    row = await ready_source(service, owners[0])
    foreign = FileService(service.journal, LocalBlobStorage(tmp_path / "foreign"))
    try:
        with pytest.raises(StoragePolicyError, match="file_not_found"):
            await operation(foreign, owners[0], row["id"])
        outer, inner = service.track(), service.track()
        assert outer is inner and service._active_depth[outer] == 2
        service.untrack(inner)
        assert outer in service.active and service._active_depth[outer] == 1
        service.untrack(outer)
        assert not service.active and not service._active_depth
        assert await service.delete(owners[0], row["id"])
    finally:
        await foreign.shutdown()


def test_explicit_vlm_propagates_table_uncertainty_through_api(
    file_client, monkeypatch
):
    """Reuse explicit D21 vision admission and retain review flags on narrative and table chunks."""
    from apps.api.services import files as file_module

    client, auth, _ = file_client
    headers = auth["headers"][0]
    data = (ROOT / "ocr/table-vie.png").read_bytes()
    row = reserve(client, headers, data, "table.png")
    route = "/api/v1/files/" + row["id"]
    assert (
        client.put(route + "/content", headers=headers, content=data).status_code == 200
    )

    async def vision(image):
        """Return controlled unverified model data after the real sanitized raster pipeline."""
        assert image
        return dict(
            text="Bút 3",
            tables=[dict(rows=[["Bút", "3"]])],
            uncertain_regions=["uncertain cell"],
            engine="synthetic-core",
        )

    monkeypatch.setattr(file_module, "transcribe_image", vision)
    response = client.post(route + "/chunks?source=ocr&ocr_mode=vlm", headers=headers)
    assert response.status_code == 200, response.text
    chunks = response.json()["chunks"]
    assert len(chunks) == 2
    assert chunks[1]["structure"]["rows"][0]["cells"] == ["Bút", "3"]
    for chunk in chunks:
        assert (
            chunk["quality"]["method"] == "local_vlm"
            and chunk["quality"]["review_required"]
        )
        assert chunk["quality"]["confidence_score"] is None
        assert "uncertain cell" in chunk["quality"]["uncertainties"]
    assert (
        not app.state.file_service.active and not app.state.file_service._active_depth
    )
    assert client.delete(route, headers=headers).status_code == 204
