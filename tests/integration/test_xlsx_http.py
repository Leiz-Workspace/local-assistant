"""Verify owned XLSX HTTP round trips, immutable sources and bounded response lifetimes."""

import asyncio
import hashlib
import io
import logging
import os
import threading
from pathlib import Path

import pytest
from openpyxl import load_workbook
from test_file_http import body, counts, declaration, reserve
from test_file_http import file_client as file_client
from test_file_http import owned_service as owned_service

from apps.api.main import app
from apps.api.routes import xlsx as route_module
from apps.api.services import files as service_module
from src.application.services.file_storage_policy import StoragePolicyError
from src.application.services.xlsx_contract import XLSX_MEDIA
from src.infrastructure.local_blob_storage import LocalBlobStorage

logger = logging.getLogger(__name__)
GOLDEN = Path(__file__).parents[1] / "fixtures/xlsx/styled-formulas.xlsx"


def edits_for(data):
    """Bind one supported literal edit to the immutable workbook source hash."""
    return {
        "source_sha256": hashlib.sha256(data).hexdigest(),
        "edits": [{"sheet_id": 1, "cell": "A2", "kind": "number", "value": "99.5"}],
    }


def test_owned_http_workbook_roundtrip_and_source_immutability(file_client):
    """Read and rewrite native cells while preserving formula/cache/styles and original allocation."""
    client, auth, root = file_client
    a, b = auth["headers"]
    data = GOLDEN.read_bytes()
    row = reserve(client, a, data, "golden.xlsx")
    route = "/api/v1/files/" + row["id"]
    assert client.post(route + "/xlsx/read", headers=a).status_code == 409
    assert client.put(route + "/content", headers=a, content=data).status_code == 200
    for operation in ("read", "rewrite"):
        kwargs = {"json": edits_for(data)} if operation == "rewrite" else {}
        assert client.post(route + "/xlsx/" + operation, **kwargs).status_code == 401
        assert (
            client.post(route + "/xlsx/" + operation, headers=b, **kwargs).status_code
            == 404
        )
    response = client.post(route + "/xlsx/read", headers=a)
    assert response.status_code == 200, response.text
    view = response.json()
    assert (
        view["file_id"] == row["id"]
        and view["sha256"] == edits_for(data)["source_sha256"]
    )
    assert view["content_trust"] == "untrusted"
    assert view["formula_cache_status"] == "preserved_not_recalculated"
    sheet = view["sheets"][0]
    assert sheet["locator"] == f"file:{row['id']}#sheet=1"
    assert sheet["cells"][0]["locator"] == f"file:{row['id']}#sheet=1&cell=A1"
    response = client.post(route + "/xlsx/rewrite", headers=a, json=edits_for(data))
    assert response.status_code == 200, response.text[:200]
    assert response.headers["content-type"] == XLSX_MEDIA
    assert response.headers["cache-control"] == "private, no-store"
    assert response.headers["x-source-file-id"] == row["id"]
    assert response.headers["x-source-sha256"] == edits_for(data)["source_sha256"]
    assert (
        response.headers["x-content-sha256"]
        == hashlib.sha256(response.content).hexdigest()
    )
    assert response.headers["x-xlsx-processor"].startswith("xlsx-literals-v1:lxml-")
    assert response.headers["x-formula-cache-status"] == "preserved_not_recalculated"
    reopened = load_workbook(io.BytesIO(response.content), data_only=False)
    assert reopened["Dữ liệu"]["A2"].value == 99.5
    assert reopened["Dữ liệu"]["A2"].number_format == "0.00"
    assert reopened["Dữ liệu"]["C2"].value == "=SUM(A2:B2)"
    assert (
        load_workbook(io.BytesIO(response.content), data_only=True)["Dữ liệu"][
            "C2"
        ].value
        == 30
    )
    assert client.get(route + "/content", headers=a).content == data
    assert len(list(root.rglob("*.blob"))) == 1
    assert client.portal.call(
        counts, app.state.file_service, auth["principals"][0]
    ) == (len(data), 1, 0)
    assert app.state.file_service._xlsx_operations == 0
    assert client.delete(route, headers=a).status_code == 204
    assert client.post(route + "/xlsx/read", headers=a).status_code == 404
    logger.info("xlsx_http_roundtrip_verified")


@pytest.mark.parametrize(
    "kind",
    [
        "stale",
        "unknown",
        "duplicate",
        "large",
        "json_duplicate",
        "wrong_media",
        "non_xlsx",
        "tampered",
    ],
)
def test_http_rejects_invalid_or_unsafe_xlsx_requests(file_client, kind):
    """Reject stale hashes, ambiguous bodies, foreign schemas and tampered source bytes safely."""
    client, auth, root = file_client
    a = auth["headers"][0]
    data = b"hello text" if kind == "non_xlsx" else GOLDEN.read_bytes()
    row = reserve(client, a, data, "plain.txt" if kind == "non_xlsx" else "golden.xlsx")
    route = "/api/v1/files/" + row["id"]
    assert client.put(route + "/content", headers=a, content=data).status_code == 200
    plan = edits_for(data)
    kwargs = {"json": plan}
    expected = 422
    if kind == "stale":
        plan["source_sha256"] = "0" * 64
        expected = 409
    elif kind == "unknown":
        plan["path"] = "/etc/passwd"
    elif kind == "duplicate":
        plan["edits"] *= 2
    elif kind == "large":
        plan["edits"][0]["value"] = "a" * 65536
        expected = 413
    elif kind == "json_duplicate":
        kwargs = {
            "content": b'{"edits":[],"edits":[]}',
            "headers": dict(a, **{"Content-Type": "application/json"}),
        }
    elif kind == "wrong_media":
        kwargs = {
            "content": b"{}",
            "headers": dict(a, **{"Content-Type": "text/plain"}),
        }
        expected = 415
    elif kind == "non_xlsx":
        expected = 415
    else:
        next(root.rglob(row["id"] + ".blob")).write_bytes(b"!" * len(data))
        expected = 503
    headers = kwargs.pop("headers", a)
    response = client.post(route + "/xlsx/rewrite", headers=headers, **kwargs)
    assert response.status_code == expected, response.text
    assert "Sửa HTTP" not in response.text and "/etc/passwd" not in response.text
    assert app.state.file_service._xlsx_operations == 0
    assert client.delete(route, headers=a).status_code == 204


async def ready_xlsx(service, owner):
    """Upload a real golden XLSX through journal, private storage and sandbox verification."""
    data = GOLDEN.read_bytes()
    row = await service.reserve(owner, **declaration(data, "golden.xlsx"))
    await service.upload(
        owner,
        row["id"],
        body(data),
        declared_media=XLSX_MEDIA,
        content_length=len(data),
    )
    return row


async def read_operation(service, owner, identifier):
    """Consume a service read operation and release its response slot after inspection."""
    async with service.xlsx_operation(owner, identifier) as (_, result):
        return result


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["delete", "cancel", "shutdown", "tamper"])
async def test_xlsx_operation_revalidation_and_join(owned_service, monkeypatch, action):
    """Join workers and retain source locks before reacting to deletion, shutdown or corruption."""
    service, owners = owned_service
    row = await ready_xlsx(service, owners[0])
    entered, release = threading.Event(), threading.Event()
    original = service_module.process_xlsx_reader

    def blocked(reader, operation, plan):
        """Delay a completed parser result so lifecycle actions race with final revalidation."""
        result = original(reader, operation, plan)
        entered.set()
        assert release.wait(5)
        return result

    monkeypatch.setattr(service_module, "process_xlsx_reader", blocked)
    task = asyncio.create_task(read_operation(service, owners[0], row["id"]))
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
            identity = service_module.identity_for(
                await service.journal.get(owners[0], row["id"])
            )
            reader = service.storage.open_reader(identity)
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
        assert service._xlsx_operations == 0 and not service.active
        if shutdown is None:
            assert await service.delete(owners[0], row["id"])
            assert await counts(service, owners[0]) == (0, 0, 0)
    finally:
        release.set()
        await asyncio.gather(task, return_exceptions=True)
        if shutdown is not None:
            await shutdown


@pytest.mark.asyncio
async def test_xlsx_response_retains_admission_until_send_or_cancel(owned_service):
    """Hold both response slots through slow delivery and release them on client cancellation."""
    service, owners = owned_service
    row = await ready_xlsx(service, owners[0])
    entered = asyncio.Queue()
    release = asyncio.Event()

    async def send(message):
        """Delay response bodies while allowing independent requests to test admission."""
        if message["type"] == "http.response.body":
            await entered.put(True)
            await release.wait()

    async def receive():
        """Provide the minimal ASGI receive callable for a regular immutable response."""
        return {"type": "http.request", "body": b"", "more_body": False}

    async def serve():
        """Construct and deliver a real rewritten response within its original active task."""
        response = await route_module.xlsx_response(
            service, owners[0], row["id"], "rewrite", edits_for(GOLDEN.read_bytes())
        )
        await response({"type": "http"}, receive, send)

    tasks = [asyncio.create_task(serve()) for _ in range(2)]
    try:
        await asyncio.wait_for(entered.get(), 5)
        await asyncio.wait_for(entered.get(), 5)
        assert service._xlsx_operations == 2
        with pytest.raises(StoragePolicyError, match="xlsx_processing_busy"):
            await read_operation(service, owners[0], row["id"])
        assert not await service.delete(owners[0], row["id"])
        for task in tasks:
            task.cancel()
        results = await asyncio.gather(*tasks, return_exceptions=True)
        assert all(isinstance(result, asyncio.CancelledError) for result in results)
        assert service._xlsx_operations == 0 and not service.active
        assert await service.delete(owners[0], row["id"])
        assert await counts(service, owners[0]) == (0, 0, 0)
    finally:
        release.set()
        await asyncio.gather(*tasks, return_exceptions=True)


@pytest.mark.asyncio
async def test_xlsx_namespace_and_construction_failure_cleanup(
    owned_service, tmp_path, monkeypatch
):
    """Reject foreign roots before parsing and close an admitted operation if response construction fails."""
    service, owners = owned_service
    row = await ready_xlsx(service, owners[0])
    foreign = service_module.FileService(
        service.journal, LocalBlobStorage(tmp_path / "foreign")
    )

    def broken(*args):
        """Simulate response construction failure after the real worker has completed."""
        raise ValueError("controlled response failure")

    try:
        with pytest.raises(StoragePolicyError, match="file_not_found"):
            await read_operation(foreign, owners[0], row["id"])
        monkeypatch.setattr(route_module, "XlsxResponse", broken)
        with pytest.raises(ValueError, match="controlled response failure"):
            await route_module.xlsx_response(service, owners[0], row["id"], "read")
        assert service._xlsx_operations == 0 and not service.active
        assert await service.delete(owners[0], row["id"])
    finally:
        await foreign.shutdown()


def test_read_reply_limit_includes_provenance(file_client, monkeypatch):
    """Apply the JSON response budget after source locators are attached and release the held slot."""
    client, auth, _ = file_client
    headers = auth["headers"][0]
    data = GOLDEN.read_bytes()
    row = reserve(client, headers, data, "golden.xlsx")
    route = "/api/v1/files/" + row["id"]
    assert (
        client.put(route + "/content", headers=headers, content=data).status_code == 200
    )
    monkeypatch.setattr(route_module, "MAX_READ_BYTES", 1)
    response = client.post(route + "/xlsx/read", headers=headers)
    assert response.status_code == 413
    assert response.json()["detail"]["code"] == "xlsx_limits_exceeded"
    assert app.state.file_service._xlsx_operations == 0
    assert client.get(route + "/content", headers=headers).content == data
    assert client.delete(route, headers=headers).status_code == 204
