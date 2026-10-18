"""Own bounded authenticated chunk extraction through source verification and response lifetime."""

import logging
from contextlib import AsyncExitStack, asynccontextmanager

from apps.api.services.files import extract_reader, file_io
from src.application.services.chunk_sources import docx_units, ocr_units, xlsx_units
from src.application.services.document_chunks import (
    MAX_SOURCE_BYTES,
    ChunkSource,
    build_chunks,
    text_unit,
)
from src.application.services.docx_contract import DOCX_MEDIA
from src.application.services.file_storage_policy import StoragePolicyError
from src.application.services.xlsx_contract import XLSX_MEDIA
from src.infrastructure.pdf_extractor import EXTRACTOR_VERSION

logger = logging.getLogger(__name__)


def read_text(reader):
    """Read only the bounded exact UTF-8 projection from the retained source FD."""
    with reader.extraction_reader() as source:
        data = source.read(MAX_SOURCE_BYTES + 1)
    if len(data) > MAX_SOURCE_BYTES:
        raise StoragePolicyError("chunk_limits_exceeded", 413)
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        raise StoragePolicyError("chunk_text_invalid", 422) from None


@asynccontextmanager
async def chunk_operation(
    service,
    owner_id,
    file_id,
    *,
    max_bytes=2048,
    source="auto",
    page=1,
    ocr_mode="auto",
):
    """Retain one admission and independently verified source through joined work and delivery."""
    task = service.track()
    reader, admitted = None, False
    try:
        row = await service.journal.get(owner_id, file_id)
        if row["state"] != "ready":
            raise StoragePolicyError("file_not_ready", 409)
        media = row["detected_media_type"]
        image = media in {"image/png", "image/jpeg", "image/webp"}
        if (
            source not in {"auto", "ocr"}
            or ocr_mode not in {"auto", "ocr", "vlm"}
            or type(page) is not int
            or not 1 <= page <= 1000
            or type(max_bytes) is not int
            or not 256 <= max_bytes <= 8192
        ):
            raise StoragePolicyError("chunk_options_invalid", 422)
        if source == "auto" and (ocr_mode != "auto" or (not image and page != 1)):
            raise StoragePolicyError("chunk_options_invalid", 422)
        if source == "ocr" and media != "application/pdf" and not image:
            raise StoragePolicyError("ocr_source_required", 415)
        if service._chunk_operations:
            raise StoragePolicyError("chunk_processing_busy", 429)
        service._chunk_operations += 1
        admitted = True
        row, reader = await service.open_download(owner_id, file_id)
        async with AsyncExitStack() as stack:
            if source == "ocr" or image:
                _, view = await stack.enter_async_context(
                    service.ocr_operation(owner_id, file_id, number=page, mode=ocr_mode)
                )
                units = await file_io(ocr_units, file_id, view)
                processor = (
                    view["processor"] + ":" + view["method"] + ":" + view["engine"]
                )
            elif media == DOCX_MEDIA:
                _, view = await stack.enter_async_context(
                    service.docx_operation(owner_id, file_id)
                )
                units = await file_io(docx_units, file_id, view)
                processor = view["processor"]
            elif media == XLSX_MEDIA:
                _, view = await stack.enter_async_context(
                    service.xlsx_operation(owner_id, file_id)
                )
                units = await file_io(xlsx_units, file_id, view)
                processor = view["processor"]
            elif media == "application/pdf":
                pages = await file_io(extract_reader, reader)
                units = [
                    text_unit(
                        f"file:{file_id}#page={item['page_number']}",
                        item["text"],
                        kind="page_text",
                    )
                    for item in pages
                ]
                processor = EXTRACTOR_VERSION
            elif media in {"text/plain", "text/markdown", "text/csv"}:
                units = [
                    text_unit(f"file:{file_id}#text", await file_io(read_text, reader))
                ]
                processor = "utf8-text-v1"
            else:
                raise StoragePolicyError("chunk_source_unsupported", 415)
            identity = ChunkSource(
                owner_id,
                service.storage.namespace_id,
                file_id,
                row["actual_sha256"],
                processor,
            )
            result = await file_io(build_chunks, identity, units, max_bytes)
            await file_io(
                reader.verify_integrity, row["actual_size_bytes"], row["actual_sha256"]
            )
            current = await service.journal.get(owner_id, file_id)
            if current["state"] != "ready":
                raise StoragePolicyError("file_not_ready", 409)
            logger.info(
                "file_chunks_prepared file_id=%s chunks=%d",
                file_id,
                len(result["chunks"]),
            )
            yield row, result
    finally:
        try:
            if reader is not None:
                await file_io(reader.close)
        finally:
            if admitted:
                service._chunk_operations -= 1
            service.untrack(task)
