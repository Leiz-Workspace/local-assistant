"""Verify allowed formats, hostile containers and actual Bubblewrap/resource isolation."""

import io
import json
import logging
import os
import socket
import stat
import struct
import subprocess
import tempfile
import time
import warnings
import zipfile
from dataclasses import asdict, replace
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from PIL import Image
from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject, TextStringObject

from src.application.services.file_storage_policy import (
    DEFAULT_POLICY,
    StoragePolicyError,
)
from src.infrastructure import file_verifier
from src.infrastructure.file_verifier import sandbox_command, verify_file

logger = logging.getLogger(__name__)
WORD = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
SHEET = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
RELS = "http://schemas.openxmlformats.org/package/2006/relationships"
OFFICE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
TYPES = "http://schemas.openxmlformats.org/package/2006/content-types"


def office_parts(suffix):
    """Build minimal real DOCX/XLSX package parts with required types and relationships."""
    main = "word/document.xml" if suffix == "docx" else "xl/workbook.xml"
    media = "wordprocessingml.document" if suffix == "docx" else "spreadsheetml.sheet"
    parts = {
        "[Content_Types].xml": f'<Types xmlns="{TYPES}"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/{main}" ContentType="application/vnd.openxmlformats-officedocument.{media}.main+xml"/></Types>'.encode(),
        "_rels/.rels": f'<Relationships xmlns="{RELS}"><Relationship Id="rId1" Type="{OFFICE}/officeDocument" Target="{main}"/></Relationships>'.encode(),
    }
    if suffix == "docx":
        parts[main] = (
            f'<w:document xmlns:w="{WORD}"><w:body><w:p><w:r><w:t>Hello</w:t></w:r></w:p></w:body></w:document>'.encode()
        )
    else:
        parts[main] = (
            f'<workbook xmlns="{SHEET}" xmlns:r="{OFFICE}"><sheets><sheet name="Sheet1" sheetId="1" r:id="rId1"/></sheets></workbook>'.encode()
        )
        parts["xl/_rels/workbook.xml.rels"] = (
            f'<Relationships xmlns="{RELS}"><Relationship Id="rId1" Type="{OFFICE}/worksheet" Target="worksheets/sheet1.xml"/></Relationships>'.encode()
        )
        parts["xl/worksheets/sheet1.xml"] = (
            f'<worksheet xmlns="{SHEET}"><sheetData/></worksheet>'.encode()
        )
    return parts


def archive(parts, *, duplicate=None, link=None, compression=zipfile.ZIP_DEFLATED):
    """Build real package bytes including optional ambiguous or special inode entries."""
    output = io.BytesIO()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        with zipfile.ZipFile(output, "w", compression=compression) as target:
            for name, data in parts.items():
                target.writestr(name, data)
            if duplicate:
                target.writestr(duplicate, b"duplicate")
            if link:
                entry = zipfile.ZipInfo(link)
                entry.create_system = 3
                entry.external_attr = (stat.S_IFLNK | 0o777) << 16
                target.writestr(entry, b"/etc/passwd")
    return output.getvalue()


def pdf(*, encrypted=False, active=False):
    """Create genuine PDF structures for parser, encryption and active-content tests."""
    output = io.BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    if encrypted:
        writer.encrypt("test-only-password")
    if active:
        writer._root_object[NameObject("/OpenAction")] = DictionaryObject(
            {
                NameObject("/S"): NameObject("/JavaScript"),
                NameObject("/JS"): TextStringObject("hostile-test"),
            }
        )
    writer.write(output)
    return output.getvalue()


def raster(suffix):
    """Generate complete tiny raster containers with the existing Pillow dependency."""
    output = io.BytesIO()
    Image.new("RGB", (8, 8), "red").save(
        output, {"png": "PNG", "jpg": "JPEG", "jpeg": "JPEG", "webp": "WEBP"}[suffix]
    )
    return output.getvalue()


def verify_bytes(data, suffix="txt", **options):
    """Pass a real anonymous FD to the production verifier without a client pathname."""
    with tempfile.TemporaryFile() as source:
        source.write(data)
        source.flush()
        return verify_file(source, "private-label." + suffix, **options)


@pytest.mark.parametrize(
    "suffix", ["txt", "md", "csv", "png", "jpg", "jpeg", "webp", "pdf", "docx", "xlsx"]
)
def test_complete_allowed_formats_in_real_sandbox(suffix):
    """Accept valid structures through the actual isolated process for every allowed suffix."""
    if suffix in {"txt", "md", "csv"}:
        payload = "Xin chào, dữ liệu\n".encode()
    elif suffix in {"docx", "xlsx"}:
        payload = archive(office_parts(suffix))
    elif suffix == "pdf":
        payload = pdf()
    else:
        payload = raster(suffix)
    media = verify_bytes(payload, suffix)
    assert media.startswith(("text/", "image/", "application/"))


@pytest.mark.parametrize(
    "payload",
    [
        b"",
        b"\x00text",
        b"\xff\xfe",
        b"<html>hostile</html>",
        b'<?xml version="1.0"?><svg/>',
        b"#!/bin/sh\necho bad",
        b"%PDF-1.4\n%%EOF",
        b" " * 70000 + b"<script>bad</script>",
        b"\x01control",
    ],
)
def test_binary_or_active_disguises_rejected_as_text(payload):
    """Reject invalid UTF-8, controls and leading active markup despite a text filename."""
    with pytest.raises(StoragePolicyError):
        verify_bytes(payload)


@pytest.mark.parametrize("suffix", ["png", "jpg", "webp", "pdf", "docx", "xlsx"])
def test_headers_and_extensions_do_not_prove_content(suffix):
    """Require a complete parser-verified structure instead of a plausible magic prefix."""
    magic = {
        "png": b"\x89PNG\r\n\x1a\n",
        "jpg": b"\xff\xd8",
        "webp": b"RIFF0000WEBP",
        "pdf": b"%PDF-1.4\n%%EOF",
        "docx": b"PK\x03\x04",
        "xlsx": b"PK\x03\x04",
    }
    with pytest.raises(StoragePolicyError):
        verify_bytes(magic[suffix], suffix)


@pytest.mark.parametrize(
    "kind",
    [
        "macro",
        "traversal",
        "absolute",
        "backslash",
        "symlink",
        "duplicate",
        "nested",
        "entity",
        "external",
        "wrong_type",
        "missing_main",
        "missing_rel",
        "encrypted",
        "empty_workbook",
    ],
)
def test_hostile_ooxml_rejected(kind):
    """Reject dangerous ZIP/XML/package constructs before any extraction or model use."""
    suffix = "xlsx" if kind == "empty_workbook" else "docx"
    parts = office_parts(suffix)
    options = {}
    if kind == "macro":
        parts["word/vbaProject.bin"] = b"hostile"
    elif kind in {"traversal", "absolute", "backslash"}:
        name = {
            "traversal": "../escape.txt",
            "absolute": "/escape.txt",
            "backslash": "word\\escape.txt",
        }[kind]
        parts[name] = b"hostile"
    elif kind == "symlink":
        options["link"] = "word/link"
    elif kind == "duplicate":
        options["duplicate"] = "word/document.xml"
    elif kind == "nested":
        parts["word/nested.bin"] = archive({"payload.txt": b"embedded"})
    elif kind == "entity":
        parts["word/document.xml"] = (
            f'<!DOCTYPE x [<!ENTITY e SYSTEM "file:///etc/passwd">]><w:document xmlns:w="{WORD}">&e;</w:document>'.encode()
        )
    elif kind == "external":
        parts["_rels/.rels"] = (
            f'<Relationships xmlns="{RELS}"><Relationship Id="rId1" Type="{OFFICE}/officeDocument" TargetMode="External" Target="https://example.invalid/private"/></Relationships>'.encode()
        )
    elif kind == "wrong_type":
        parts["[Content_Types].xml"] = parts["[Content_Types].xml"].replace(
            b"wordprocessingml.document", b"spreadsheetml.sheet"
        )
    elif kind == "missing_main":
        del parts["word/document.xml"]
    elif kind == "missing_rel":
        del parts["_rels/.rels"]
    elif kind == "empty_workbook":
        parts["xl/workbook.xml"] = f'<workbook xmlns="{SHEET}"/>'.encode()
    payload = archive(parts, **options)
    if kind == "encrypted":
        mutated = bytearray(payload)
        struct.pack_into("<H", mutated, 6, 1)
        offset = mutated.find(b"PK\x01\x02")
        struct.pack_into("<H", mutated, offset + 8, 1)
        payload = bytes(mutated)
    with pytest.raises(StoragePolicyError):
        verify_bytes(payload, suffix)


@pytest.mark.parametrize("kind", ["ratio", "entries", "xml", "actual_expansion"])
def test_archive_expansion_limits_are_enforced(kind):
    """Exercise real ZIP decompression against versioned ratio/count/XML/byte bounds."""
    parts = office_parts("docx")
    policy = DEFAULT_POLICY
    if kind == "ratio":
        parts["word/large.bin"] = b"A" * 200_000
    elif kind == "entries":
        policy = replace(policy, max_archive_entries=2)
    elif kind == "xml":
        parts["word/large.xml"] = b"<x>" + b" " * (2 * 1024**2) + b"</x>"
    else:
        policy = replace(policy, max_archive_bytes=1024)
        parts["word/large.bin"] = os.urandom(2048)
    with pytest.raises(StoragePolicyError) as failure:
        verify_bytes(
            archive(
                parts,
                compression=zipfile.ZIP_STORED
                if kind == "xml"
                else zipfile.ZIP_DEFLATED,
            ),
            "docx",
            policy=policy,
        )
    assert failure.value.code == "archive_limits_exceeded"


@pytest.mark.parametrize("kind", ["encrypted", "active", "truncated"])
def test_unsafe_pdf_rejected(kind):
    """Reject encrypted, active or structurally incomplete PDFs despite correct headers."""
    payload = pdf(encrypted=kind == "encrypted", active=kind == "active")
    if kind == "truncated":
        payload = payload[:-20]
    with pytest.raises(StoragePolicyError):
        verify_bytes(payload, "pdf")


def test_declared_mime_must_agree_with_verified_content():
    """Reject a false HTTP media declaration after verification of the actual bytes."""
    with pytest.raises(StoragePolicyError, match="file_type_mismatch"):
        verify_bytes(b"plain text", declared_media="image/png")


def test_namespace_blocks_host_secrets_network_and_writes(tmp_path, monkeypatch):
    """Prove actual mount/network isolation and environment clearing in the sandbox."""
    secret = tmp_path / "never-mounted"
    secret.write_text("private-test-only")
    monkeypatch.setenv("VAULT_TOKEN", "must-not-enter-worker")
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        port = listener.getsockname()[1]
        probe = f'''
"""Probe sandbox boundaries without using production credentials."""
import json, os, socket
assert not os.path.exists({str(secret)!r})
assert not os.path.exists('/home')
assert 'VAULT_TOKEN' not in os.environ and 'DATABASE_URL' not in os.environ
try:
    open('/tmp/write-probe', 'w')
except OSError:
    pass
else:
    raise AssertionError('Sandbox temp mount is writable')
client=socket.socket()
client.settimeout(0.2)
try:
    client.connect(('127.0.0.1',{port}))
except OSError:
    pass
else:
    raise AssertionError('Host network reachable')
print(json.dumps({{'isolated':True}}))
'''
        result = subprocess.run(
            sandbox_command(["/venv/bin/python", "-c", probe]),
            capture_output=True,
            timeout=5,
        )
    assert result.returncode == 0, result.stderr.decode()
    assert json.loads(result.stdout) == {"isolated": True}


@pytest.mark.parametrize(
    "failure",
    [
        "timeout",
        "missing",
        "invalid_json",
        "unknown_error",
        "oversize_output",
        "nonzero",
    ],
)
def test_failed_worker_never_falls_back_to_inprocess_parsing(monkeypatch, failure):
    """Fail closed for timeouts, missing sandbox, crashes and malformed worker verdicts."""

    def broken_run(command, **parameters):
        """Inject only the parent/worker boundary failure, without bypassing its validator."""
        if failure == "timeout":
            raise subprocess.TimeoutExpired(command, 10)
        if failure == "missing":
            raise FileNotFoundError("sensitive host path")
        output = {
            "invalid_json": b"not-json",
            "unknown_error": b'{"error":"hostile-text"}',
            "oversize_output": b"x" * 5000,
            "nonzero": b"",
        }[failure]
        parameters["stdout"].write(output)
        return SimpleNamespace(returncode=1 if failure == "nonzero" else 0)

    monkeypatch.setattr(subprocess, "run", broken_run)
    with pytest.raises(StoragePolicyError) as error:
        verify_bytes(b"plain text")
    assert error.value.code in {"verification_timeout", "verification_unavailable"}


def test_small_chunks_do_not_hide_active_text_prefix():
    """Detect markup prefixes split across tiny policy-bounded stream chunks."""
    policy = replace(DEFAULT_POLICY, chunk_bytes=1)
    with pytest.raises(StoragePolicyError):
        verify_bytes(b"   <html>bad</html>", policy=policy)


def test_worker_applies_real_resource_limits():
    """Exercise the real worker entrypoint and inspect limits from its parser callback."""
    probe = '''
"""Inspect the production resource-limit entrypoint in an isolated process."""
import json, resource, sys
from src.infrastructure import file_content_verifier, file_verifier_worker
from src.infrastructure.file_verifier import VERIFIER_MEMORY_BYTES, VERIFIER_CPU_SECONDS
def inspect_limits(*args):
    """Assert kernel-enforced bounds at the exact parser invocation boundary."""
    assert resource.getrlimit(resource.RLIMIT_AS) == (VERIFIER_MEMORY_BYTES, VERIFIER_MEMORY_BYTES)
    assert resource.getrlimit(resource.RLIMIT_CPU)[0] == VERIFIER_CPU_SECONDS
    assert resource.getrlimit(resource.RLIMIT_FSIZE) == (4096,4096)
    assert resource.getrlimit(resource.RLIMIT_NOFILE) == (32,32)
    return 'text/plain'
file_content_verifier.detect_content = inspect_limits
sys.argv=['worker','txt',sys.argv[1]]
raise SystemExit(file_verifier_worker.main())
'''
    with tempfile.TemporaryFile() as source:
        source.write(b"test")
        source.seek(0)
        result = subprocess.run(
            sandbox_command(
                ["/venv/bin/python", "-c", probe, json.dumps(asdict(DEFAULT_POLICY))]
            ),
            stdin=source,
            capture_output=True,
            timeout=10,
        )
    assert result.returncode == 0, result.stderr.decode()
    assert json.loads(result.stdout) == {"media_type": "text/plain"}


def test_verification_logs_do_not_expose_original_filename_or_content(caplog):
    """Audit canonical media verdicts while keeping document data and labels out of logs."""
    with caplog.at_level(logging.INFO):
        assert verify_bytes(b"sensitive-body-marker") == "text/plain"
    assert "file_content_verified" in caplog.text
    assert (
        "private-label" not in caplog.text
        and "sensitive-body-marker" not in caplog.text
    )


@pytest.mark.parametrize(
    "verdict", [b'{"error":[]}', b'{"media_type":null}', b"[]", b"null"]
)
def test_worker_verdict_types_fail_closed(monkeypatch, verdict):
    """Reject malformed JSON value types without leaking a raw parent TypeError."""

    def malformed_worker(command, **parameters):
        """Write one invalid typed verdict through the same bounded stdout channel."""
        parameters["stdout"].write(verdict)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(subprocess, "run", malformed_worker)
    with pytest.raises(StoragePolicyError, match="verification_unavailable"):
        verify_bytes(b"text")


def test_real_timeout_leaves_no_worker_or_namespace_supervisor(monkeypatch):
    """Kill a real stalled sandbox and confirm it cannot retain the caller's payload FD."""
    marker = "verifier-timeout-" + uuid4().hex

    def stalled_command(arguments):
        """Replace only the worker program with a real stalled process in the same sandbox."""
        return sandbox_command(
            ["/venv/bin/python", "-c", "import time; time.sleep(30)", marker]
        )

    monkeypatch.setattr(file_verifier, "sandbox_command", stalled_command)
    monkeypatch.setattr(file_verifier, "VERIFIER_WALL_SECONDS", 0.2)
    with pytest.raises(StoragePolicyError, match="verification_timeout"):
        verify_bytes(b"text")
    deadline = time.monotonic() + 2
    while True:
        remaining = []
        for process in Path("/proc").iterdir():
            if not process.name.isdecimal():
                continue
            try:
                if marker.encode() in (process / "cmdline").read_bytes():
                    remaining.append(process.name)
            except OSError:
                continue
        if not remaining or time.monotonic() >= deadline:
            break
        time.sleep(0.02)
    assert not remaining
