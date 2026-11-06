"""Inspect untrusted text, image, PDF and OOXML bytes inside the isolated verifier only."""

import codecs
import logging
import os
import posixpath
import re
import stat
import struct
import warnings
import zipfile
from pathlib import PurePosixPath
from typing import BinaryIO

from defusedxml import ElementTree
from PIL import Image
from pypdf import PdfReader

from src.application.services.file_storage_policy import (
    MEDIA_BY_EXTENSION,
    StoragePolicy,
    StoragePolicyError,
    validate_archive_bounds,
)
from src.infrastructure.file_verifier import (
    MAX_IMAGE_PIXELS,
    MAX_PDF_PAGES,
    MAX_XML_BYTES,
)

logger = logging.getLogger(__name__)
REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
TYPE_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
WORD_TYPE = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"
)
SHEET_TYPE = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"
)


def reject() -> None:
    """Reject unsafe or malformed structures without returning document-controlled text."""
    raise StoragePolicyError("invalid_file_content", 415)


def verify_text(source: BinaryIO, policy: StoragePolicy) -> str:
    """Validate incremental UTF-8 text and reject binary/control/active-markup disguises."""
    decoder = codecs.getincrementaldecoder("utf-8-sig")("strict")
    prefix = ""
    while chunk := source.read(policy.chunk_bytes):
        decoded = decoder.decode(chunk)
        if len(prefix) < 256:
            prefix = (prefix + decoded).lstrip().lower()[:256]
            if re.match(
                r"(?:#!|%pdf-|<\?xml|<!doctype\s+html|<html\b|<svg\b|<script\b)", prefix
            ):
                reject()
        if any(ord(char) < 32 and char not in "\n\r\t" for char in decoded):
            reject()
    decoder.decode(b"", final=True)
    return "text/plain"


def verify_image(source: BinaryIO, suffix: str) -> str:
    """Verify the complete permitted raster container with bounded decoded pixel count."""
    expected = {"png": "PNG", "jpg": "JPEG", "jpeg": "JPEG", "webp": "WEBP"}[suffix]
    Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        with Image.open(source) as image:
            if (
                image.format != expected
                or image.width * image.height > MAX_IMAGE_PIXELS
            ):
                reject()
            if getattr(image, "n_frames", 1) != 1:
                reject()
            image.verify()
        source.seek(0)
        with Image.open(source) as image:
            image.load()
    return next(iter(MEDIA_BY_EXTENSION[suffix]))


def verify_pdf(source: BinaryIO, policy: StoragePolicy) -> str:
    """Parse PDF structure and bound pages/decoded streams while rejecting active features."""
    if not source.read(8).startswith(b"%PDF-"):
        reject()
    size = os.fstat(source.fileno()).st_size
    source.seek(max(0, size - 1024))
    if b"%%EOF" not in source.read(1024):
        reject()
    source.seek(0)
    reader = PdfReader(source, strict=True)
    if reader.is_encrypted or not 1 <= len(reader.pages) <= MAX_PDF_PAGES:
        reject()
    forbidden = {
        "/OpenAction",
        "/AA",
        "/JavaScript",
        "/JS",
        "/Launch",
        "/EmbeddedFiles",
        "/RichMedia",
        "/XFA",
    }
    seen = set()
    expanded = 0

    def inspect(value, depth=0):
        """Traverse bounded indirect objects and force capped stream decoding in isolation."""
        nonlocal expanded
        if depth > 64 or len(seen) >= 100_000:
            raise StoragePolicyError("archive_limits_exceeded", 413)
        if hasattr(value, "get_object"):
            value = value.get_object()
        identity = id(value)
        if identity in seen:
            return
        seen.add(identity)
        if isinstance(value, dict):
            if forbidden.intersection(value):
                reject()
            if hasattr(value, "get_data"):
                expanded += len(value.get_data())
                if expanded > policy.max_archive_bytes:
                    raise StoragePolicyError("archive_limits_exceeded", 413)
            for item in value.values():
                inspect(item, depth + 1)
        elif isinstance(value, (list, tuple)):
            for item in value:
                inspect(item, depth + 1)

    inspect(reader.trailer)
    return "application/pdf"


def archive_preflight(source: BinaryIO, policy: StoragePolicy) -> None:
    """Bound ordinary ZIP directory declarations before ZipFile allocates entry objects."""
    size = os.fstat(source.fileno()).st_size
    source.seek(max(0, size - 65557))
    tail = source.read(65557)
    marker = tail.rfind(b"PK\x05\x06")
    if marker < 0 or len(tail) - marker < 22:
        reject()
    (
        _,
        disk,
        directory_disk,
        on_disk,
        total,
        directory_size,
        directory_offset,
        comment,
    ) = struct.unpack_from("<4s4H2LH", tail, marker)
    if disk or directory_disk or on_disk != total or total == 65535:
        reject()
    if (
        marker + 22 + comment != len(tail)
        or directory_offset + directory_size != size - len(tail) + marker
    ):
        reject()
    validate_archive_bounds(
        entries=total, compressed_bytes=size, expanded_bytes=0, policy=policy
    )
    source.seek(0)


def safe_member(name: str) -> bool:
    """Accept only unambiguous relative ZIP paths without traversal or URI syntax."""
    return bool(name) and not (
        name.startswith("/")
        or "\\" in name
        or ":" in name
        or "%" in name
        or any(part in {"", ".", ".."} for part in name.rstrip("/").split("/"))
        or any(ord(character) < 32 for character in name)
    )


def verify_ooxml(source: BinaryIO, suffix: str, policy: StoragePolicy) -> str:
    """Validate bounded actual ZIP expansion, XML, package types and local relationships."""
    archive_preflight(source, policy)
    documents = {}
    members = set()
    actual_members = set()
    main = "word/document.xml" if suffix == "docx" else "xl/workbook.xml"
    expected_type = WORD_TYPE if suffix == "docx" else SHEET_TYPE
    expanded = compressed = 0
    with zipfile.ZipFile(source) as package:
        entries = package.infolist()
        validate_archive_bounds(
            entries=len(entries),
            compressed_bytes=os.fstat(source.fileno()).st_size,
            expanded_bytes=0,
            policy=policy,
        )
        for item in entries:
            name = item.filename
            key = name.casefold()
            mode = stat.S_IFMT(item.external_attr >> 16)
            if (
                not safe_member(name)
                or key in members
                or item.flag_bits & 1
                or mode not in {0, stat.S_IFREG, stat.S_IFDIR}
                or item.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}
                or any(
                    word in key
                    for word in ("vbaproject", "macrosheet", "activex", "embeddings/")
                )
            ):
                reject()
            members.add(key)
            actual_members.add(name)
            compressed += item.compress_size
            validate_archive_bounds(
                entries=len(entries),
                compressed_bytes=max(item.compress_size, 1),
                expanded_bytes=item.file_size,
                policy=policy,
            )
            observed = 0
            xml = bytearray()
            with package.open(item) as member:
                prefix = b""
                while chunk := member.read(policy.chunk_bytes):
                    observed += len(chunk)
                    expanded += len(chunk)
                    validate_archive_bounds(
                        entries=len(entries),
                        compressed_bytes=max(compressed, 1),
                        expanded_bytes=expanded,
                        policy=policy,
                    )
                    prefix = (prefix + chunk)[:8]
                    if prefix.startswith((b"PK\x03\x04", b"\xd0\xcf\x11\xe0")):
                        reject()
                    if name.lower().endswith((".xml", ".rels")):
                        xml.extend(chunk)
                        if len(xml) > MAX_XML_BYTES:
                            raise StoragePolicyError("archive_limits_exceeded", 413)
            if observed != item.file_size:
                reject()
            if name.lower().endswith((".xml", ".rels")):
                documents[name] = ElementTree.fromstring(
                    bytes(xml),
                    forbid_dtd=True,
                    forbid_entities=True,
                    forbid_external=True,
                )
        validate_archive_bounds(
            entries=len(entries),
            compressed_bytes=max(compressed, 1),
            expanded_bytes=expanded,
            policy=policy,
        )
    types = documents.get("[Content_Types].xml")
    relationships = documents.get("_rels/.rels")
    if types is None or relationships is None or main not in documents:
        reject()
    if (
        types.tag != f"{{{TYPE_NS}}}Types"
        or relationships.tag != f"{{{REL_NS}}}Relationships"
    ):
        reject()
    main_types = [
        part.attrib.get("ContentType")
        for part in types
        if part.attrib.get("PartName") == "/" + main
    ]
    if main_types != [expected_type]:
        reject()
    for part in types:
        content_type = part.attrib.get("ContentType", "").lower()
        if any(
            word in content_type
            for word in ("macroenabled", "vba", "oleobject", "activex")
        ):
            reject()
    main_rel = 0
    for name, root in documents.items():
        if not name.lower().endswith(".rels"):
            continue
        if root.tag != f"{{{REL_NS}}}Relationships":
            reject()
        ids = set()
        for relationship in root:
            target = relationship.attrib.get("Target", "")
            identifier = relationship.attrib.get("Id", "")
            if (
                not identifier
                or identifier in ids
                or relationship.attrib.get("TargetMode", "Internal") != "Internal"
            ):
                reject()
            ids.add(identifier)
            base = (
                "" if name == "_rels/.rels" else str(PurePosixPath(name).parent.parent)
            )
            if (
                not target
                or target.startswith("/")
                or "\\" in target
                or ":" in target
                or "%" in target
            ):
                reject()
            resolved = posixpath.normpath(posixpath.join(base, target))
            if resolved.startswith("../") or resolved not in actual_members:
                reject()
            if name == "_rels/.rels" and relationship.attrib.get("Type", "").endswith(
                "/officeDocument"
            ):
                if resolved != main:
                    reject()
                main_rel += 1
    expected_root = (
        "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}document"
        if suffix == "docx"
        else "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}workbook"
    )
    if main_rel != 1 or documents[main].tag != expected_root:
        reject()
    if suffix == "xlsx":
        namespace = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
        relationships_ns = (
            "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
        )
        book_rels = documents.get("xl/_rels/workbook.xml.rels")
        sheets = documents[main].findall(f"{{{namespace}}}sheets/{{{namespace}}}sheet")
        if book_rels is None or not sheets:
            reject()
        for sheet in sheets:
            matches = [
                rel
                for rel in book_rels
                if rel.attrib.get("Id") == sheet.attrib.get(f"{{{relationships_ns}}}id")
                and rel.attrib.get("Type", "").endswith("/worksheet")
            ]
            if len(matches) != 1:
                reject()
            target = posixpath.normpath(
                posixpath.join("xl", matches[0].attrib["Target"])
            )
            worksheet = documents.get(target)
            if (
                worksheet is None
                or worksheet.tag != f"{{{namespace}}}worksheet"
                or worksheet.find(f"{{{namespace}}}sheetData") is None
            ):
                reject()
    return next(iter(MEDIA_BY_EXTENSION[suffix]))


def detect_content(source: BinaryIO, suffix: str, policy: StoragePolicy) -> str:
    """Dispatch only policy-approved formats after verifying actual FD size bounds."""
    info = os.fstat(source.fileno())
    if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= policy.max_file_bytes:
        reject()
    source.seek(0)
    if suffix in {"txt", "md", "csv"}:
        media = verify_text(source, policy)
    elif suffix in {"png", "jpg", "jpeg", "webp"}:
        media = verify_image(source, suffix)
    elif suffix == "pdf":
        media = verify_pdf(source, policy)
    elif suffix in {"docx", "xlsx"}:
        media = verify_ooxml(source, suffix, policy)
    else:
        reject()
    logger.info("file_structure_checked media_type=%s", media)
    return media
