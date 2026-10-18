"""Build deterministic private chunks from exact bounded document projections."""

import hashlib
import json
import logging
from dataclasses import dataclass
from uuid import UUID

from src.application.services.file_storage_policy import StoragePolicyError

logger = logging.getLogger(__name__)
CHUNK_VERSION = "structured-chunks-v1"
MAX_SOURCE_BYTES = 1024 * 1024
MAX_REPLY_BYTES = 8 * 1024 * 1024
MAX_CHUNKS = 1000


def canonical(value):
    """Serialize identity and row content without changing source Unicode."""
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


@dataclass(frozen=True)
class ChunkSource:
    """Bind parsed content to server-authorized immutable source identity."""

    owner_id: UUID
    namespace_id: UUID
    file_id: UUID
    sha256: str
    processor: str

    def identity(self):
        """Return private identity fields used only inside cryptographic digests."""
        return dict(
            owner=str(self.owner_id),
            namespace=str(self.namespace_id),
            file=str(self.file_id),
        )


def text_unit(locator, text, *, section=None, quality=None, kind="text"):
    """Describe one exact extracted field with optional section and quality context."""
    return dict(
        kind=kind,
        locator=locator,
        text=text,
        section=section or [],
        quality=quality or {},
    )


def row_unit(locator, rows, *, spans, section=None, quality=None, structure=None):
    """Describe atomic table rows with their original field-level source spans."""
    return dict(
        kind="rows",
        locator=locator,
        rows=rows,
        spans=spans,
        section=section or [],
        quality=quality or {},
        structure=structure or {},
    )


def source_span(locator, field, text):
    """Map an entire lexical field using Unicode code-point offsets."""
    return dict(locator=locator, field=field, start=0, end=len(text))


def build_chunks(source, units, max_bytes=2048):
    """Preserve boundaries and exact spans while deriving source/access-bound chunk IDs."""
    if type(max_bytes) is not int or not 256 <= max_bytes <= 8192:
        raise StoragePolicyError("chunk_size_invalid", 422)
    chunks, empty = [], []
    source_bytes = 0
    reply_bytes = 0
    identity = dict(
        source.identity(),
        sha256=source.sha256,
        processor=source.processor,
        chunker=CHUNK_VERSION,
        max_bytes=max_bytes,
    )

    def append(unit, text, spans, structure):
        """Bound final chunk count and hash every public content-bearing field."""
        nonlocal reply_bytes
        if len(chunks) + len(empty) >= MAX_CHUNKS:
            raise StoragePolicyError("chunk_limits_exceeded", 413)
        chunk = dict(
            kind=unit["kind"],
            locator=unit["locator"],
            text=text,
            spans=spans,
            structure=structure,
            section_path=unit["section"],
            quality=unit["quality"],
        )
        chunk["id"] = (
            "chk_"
            + hashlib.sha256(
                canonical(dict(identity=identity, chunk=chunk)).encode()
            ).hexdigest()
        )
        reply_bytes += len(canonical(chunk).encode()) + 1
        if reply_bytes > MAX_REPLY_BYTES:
            raise StoragePolicyError("chunk_limits_exceeded", 413)
        chunks.append(chunk)

    for unit in units:
        if unit["kind"] == "rows":
            text = canonical(unit["rows"])
            source_bytes += len(text.encode())
            if len(text.encode()) > max_bytes:
                raise StoragePolicyError("chunk_row_too_large", 413)
            append(
                unit, text, unit["spans"], dict(unit["structure"], rows=unit["rows"])
            )
        else:
            text = unit["text"]
            source_bytes += len(text.encode())
            if not text:
                if len(chunks) + len(empty) >= MAX_CHUNKS:
                    raise StoragePolicyError("chunk_limits_exceeded", 413)
                empty.append(
                    dict(
                        locator=unit["locator"],
                        status="empty_extracted_field",
                        section_path=unit["section"],
                        quality=unit["quality"],
                    )
                )
                reply_bytes += len(canonical(empty[-1]).encode()) + 1
                if reply_bytes > MAX_REPLY_BYTES:
                    raise StoragePolicyError("chunk_limits_exceeded", 413)
            if source_bytes > MAX_SOURCE_BYTES:
                raise StoragePolicyError("chunk_limits_exceeded", 413)
            start = size = 0
            for index, char in enumerate(text):
                length = len(char.encode())
                if size + length > max_bytes:
                    append(
                        unit,
                        text[start:index],
                        [
                            dict(
                                locator=unit["locator"],
                                field="text",
                                start=start,
                                end=index,
                            )
                        ],
                        {},
                    )
                    start, size = index, 0
                size += length
            if start < len(text):
                append(
                    unit,
                    text[start:],
                    [
                        dict(
                            locator=unit["locator"],
                            field="text",
                            start=start,
                            end=len(text),
                        )
                    ],
                    {},
                )
        if source_bytes > MAX_SOURCE_BYTES:
            raise StoragePolicyError("chunk_limits_exceeded", 413)
    scope = hashlib.sha256(canonical(source.identity()).encode()).hexdigest()
    payload = dict(
        file_id=str(source.file_id),
        sha256=source.sha256,
        processor=source.processor,
        chunker=CHUNK_VERSION,
        max_bytes=max_bytes,
        span_unit="unicode_code_points",
        content_trust="untrusted",
        access=dict(
            visibility="private", principal_id=str(source.owner_id), scope=scope
        ),
        chunks=chunks,
        empty_sources=empty,
    )
    if len(canonical(payload).encode()) > MAX_REPLY_BYTES:
        raise StoragePolicyError("chunk_limits_exceeded", 413)
    logger.info(
        "document_chunks_built file_id=%s chunks=%d empty=%d",
        source.file_id,
        len(chunks),
        len(empty),
    )
    return payload
