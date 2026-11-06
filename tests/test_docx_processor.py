"""Verify golden DOCX text/styles/tables, safe rewrites and bounded isolated processing."""

import copy
import hashlib
import io
import logging
import subprocess
import tempfile
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest
from docx import Document

from src.application.services.docx_contract import (
    DOCX_VERSION,
    validate_plan,
    validate_view,
)
from src.application.services.file_storage_policy import StoragePolicyError
from src.infrastructure import docx_processor as module
from src.infrastructure.docx_processor import process_docx

logger = logging.getLogger(__name__)
GOLDEN = Path(__file__).parent / "fixtures/docx/styled-table.docx"


def process_bytes(data, operation="read", plan=None):
    """Run the actual sandbox against an anonymous regular source FD."""
    with tempfile.TemporaryFile() as source:
        source.write(data)
        source.seek(0)
        return process_docx(source, operation, plan)


def plan_for(data, edits=None):
    """Bind golden run edits to the exact source content hash."""
    return {
        "source_sha256": hashlib.sha256(data).hexdigest(),
        "edits": edits or [{"paragraph_id": 2, "run_index": 1, "text": "Đã sửa"}],
    }


def mutate_package(data, updates):
    """Create independent hostile or boundary ZIP variants while preserving ordinary metadata."""
    output = io.BytesIO()
    with (
        zipfile.ZipFile(io.BytesIO(data)) as source,
        zipfile.ZipFile(output, "w") as target,
    ):
        for info in source.infolist():
            original = source.read(info.filename)
            if info.filename in updates:
                info = copy.copy(info)
                info.compress_type = zipfile.ZIP_STORED
            target.writestr(info, updates.pop(info.filename, original))
        for name, content in updates.items():
            target.writestr(name, content)
    return output.getvalue()


def test_golden_structured_paragraphs_tables_styles():
    """Read exact Unicode/multi-run text with native style and merged-cell provenance."""
    result = process_bytes(GOLDEN.read_bytes())
    assert result["processor"] == DOCX_VERSION
    assert result["paragraphs"][0]["text"] == "Báo cáo D19"
    paragraph = result["paragraphs"][1]
    assert paragraph["text"] == "Alpha + Beta\tXin chào\nViệt Nam"
    assert paragraph["style_id"] == "EvidenceBody" and paragraph["editable"]
    assert paragraph["runs"][0]["bold"] is True
    assert paragraph["runs"][1]["italic"] is True
    assert paragraph["runs"][2]["underline"] == "single"
    assert result["tables"][0]["style_id"] == "TableGrid"
    assert len(result["tables"][0]["cells"]) == 5
    assert result["tables"][0]["cells"][-1]["grid_span"] == 2
    pids = result["tables"][0]["cells"][0]["paragraph_ids"]
    assert result["paragraphs"][pids[0] - 1]["text"] == "Tên"
    assert any(
        style["style_id"] == "EvidenceBody" and style["based_on"] == "Normal"
        for style in result["styles"]
    )
    assert all("Header preserved" not in p["text"] for p in result["paragraphs"])
    logger.info("docx_golden_verified tables=1 merged_cells=True")


def test_rewrite_preserves_format_and_untouched_parts():
    """Reopen edited paragraphs/table cells independently and compare all untouched package bytes."""
    data = GOLDEN.read_bytes()
    edits = [
        {"paragraph_id": 2, "run_index": 1, "text": " Đã sửa\tUnicode\n "},
        {"paragraph_id": 6, "run_index": 1, "text": "99"},
    ]
    result = process_bytes(data, "rewrite", plan_for(data, edits))
    reopened = Document(io.BytesIO(result))
    assert reopened.paragraphs[1].runs[0].text == edits[0]["text"]
    assert reopened.paragraphs[1].runs[0].bold is True
    assert reopened.paragraphs[1].runs[1].text == " + Beta"
    assert reopened.paragraphs[1].runs[1].italic is True
    assert reopened.paragraphs[1].runs[2].underline is True
    assert reopened.paragraphs[1].style.style_id == "EvidenceBody"
    assert reopened.tables[0].cell(1, 1).text == "99"
    assert reopened.tables[0].style.style_id == "TableGrid"
    assert reopened.sections[0].header.paragraphs[0].text == "Header preserved"
    assert reopened.sections[0].footer.paragraphs[0].text == "Footer preserved"
    with (
        zipfile.ZipFile(io.BytesIO(data)) as before,
        zipfile.ZipFile(io.BytesIO(result)) as after,
    ):
        assert before.namelist() == after.namelist()
        for name in before.namelist():
            if name != "word/document.xml":
                assert before.read(name) == after.read(name), name
    assert process_bytes(result)["paragraphs"][1]["runs"][0]["text"] == edits[0]["text"]
    assert GOLDEN.read_bytes() == data


def test_trusted_output_opens_in_libreoffice(tmp_path):
    """Open and render the trusted rewritten golden in an independent office application."""
    data = GOLDEN.read_bytes()
    output = tmp_path / "rewritten.docx"
    output.write_bytes(process_bytes(data, "rewrite", plan_for(data)))
    command = [
        "/usr/bin/libreoffice",
        "-env:UserInstallation=" + (tmp_path / "profile").as_uri(),
        "--headless",
        "--convert-to",
        "pdf",
        "--outdir",
        str(tmp_path),
        str(output),
    ]
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
        env={
            "PATH": "/usr/bin:/bin",
            "LANG": "C.UTF-8",
            "XDG_CACHE_HOME": str(tmp_path / "cache"),
        },
    )
    assert result.returncode == 0, result.stderr
    pdf = output.with_suffix(".pdf")
    assert pdf.is_file() and pdf.stat().st_size > 0
    from pypdf import PdfReader

    text = "\n".join(page.extract_text() for page in PdfReader(pdf).pages)
    assert "Đã sửa" in text and "Alpha" not in text
    assert "merged" in text and "42" in text
    logger.info("docx_libreoffice_open_verified pages=%d", len(PdfReader(pdf).pages))


@pytest.mark.parametrize(
    "change",
    [
        "duplicate",
        "nul",
        "surrogate",
        "carriage",
        "zero_index",
        "unknown",
        "hash",
        "missing",
        "boolean",
    ],
)
def test_edit_plan_rejects_ambiguous_or_invalid_input(change):
    """Reject duplicate targets, XML-invalid text, coercion and unknown request fields."""
    plan = plan_for(GOLDEN.read_bytes())
    if change == "duplicate":
        plan["edits"] *= 2
    elif change in ("nul", "surrogate", "carriage"):
        plan["edits"][0]["text"] = {
            "nul": "\0",
            "surrogate": "\ud800",
            "carriage": "\r",
        }[change]
    elif change == "zero_index":
        plan["edits"][0]["run_index"] = 0
    elif change == "boolean":
        plan["edits"][0]["paragraph_id"] = True
    elif change == "unknown":
        plan["owner_id"] = "forged"
    elif change == "hash":
        plan["source_sha256"] = "wrong"
    else:
        plan["edits"] = []
    with pytest.raises(StoragePolicyError, match="invalid_docx_edits"):
        validate_plan(plan)


@pytest.mark.parametrize(
    "kind",
    [
        "malformed",
        "external",
        "dtd",
        "macro",
        "nested",
        "xml_limit",
        "paragraphs",
        "run_limit",
        "text_limit",
        "field",
        "signed",
        "missing_run",
        "stale",
    ],
)
def test_real_hostile_and_unsupported_variants(kind):
    """Exercise actual sandbox rejection for unsafe packages, unsupported edits and resource budgets."""
    data = GOLDEN.read_bytes()
    with zipfile.ZipFile(io.BytesIO(data)) as package:
        main = package.read("word/document.xml")
        rels = package.read("_rels/.rels")
    operation = "read"
    if kind == "malformed":
        data = b"not-a-docx"
    elif kind == "external":
        data = mutate_package(
            data,
            {
                "_rels/.rels": rels.replace(
                    b'Target="word/document.xml"',
                    b'Target="https://example.invalid/a" TargetMode="External"',
                )
            },
        )
    elif kind == "dtd":
        data = mutate_package(
            data,
            {
                "word/document.xml": main.replace(
                    b"<w:document",
                    b'<!DOCTYPE document [<!ENTITY x "hostile">]><w:document',
                    1,
                )
            },
        )
    elif kind == "macro":
        data = mutate_package(data, {"word/vbaProject.bin": b"hostile"})
    elif kind == "nested":
        data = mutate_package(data, {"word/nested.bin": b"PK\x03\x04hostile"})
    elif kind == "xml_limit":
        data = mutate_package(
            data,
            {"word/document.xml": main.replace(b"Alpha", b"A" * (2 * 1024 * 1024))},
        )
    elif kind == "paragraphs":
        data = mutate_package(
            data,
            {
                "word/document.xml": main.replace(
                    b"<w:body>", b"<w:body>" + b"<w:p/>" * 10001
                )
            },
        )
    elif kind == "run_limit":
        data = mutate_package(
            data, {"word/document.xml": main.replace(b"Alpha", b"A" * 65537)}
        )
    elif kind == "text_limit":
        data = mutate_package(
            data,
            {
                "word/document.xml": main.replace(
                    b"<w:body>",
                    b"<w:body>"
                    + (b"<w:p><w:r><w:t>" + b"A" * 60000 + b"</w:t></w:r></w:p>") * 18,
                )
            },
        )
    elif kind == "field":
        operation = "rewrite"
        data = mutate_package(
            data,
            {
                "word/document.xml": main.replace(
                    b"<w:t>Alpha</w:t>",
                    b'<w:fldChar w:fldCharType="begin"/><w:t>Alpha</w:t>',
                )
            },
        )
    elif kind == "signed":
        operation = "rewrite"
        data = mutate_package(data, {"_xmlsignatures/test.xml": b"<signature/>"})
    else:
        operation = "rewrite"
    plan = plan_for(data)
    if kind == "missing_run":
        plan["edits"][0]["run_index"] = 999
    elif kind == "stale":
        plan["source_sha256"] = "0" * 64
    with pytest.raises(StoragePolicyError) as error:
        process_bytes(data, operation, plan)
    expected = {
        "xml_limit": ("docx_limits_exceeded", 413),
        "paragraphs": ("docx_limits_exceeded", 413),
        "run_limit": ("docx_limits_exceeded", 413),
        "text_limit": ("docx_limits_exceeded", 413),
        "field": ("unsupported_docx_edit", 422),
        "signed": ("unsupported_docx_edit", 422),
        "missing_run": ("docx_edit_not_found", 422),
        "stale": ("docx_source_changed", 409),
    }.get(kind, ("invalid_docx_content", 415))
    assert (error.value.code, error.value.status_code) == expected


@pytest.mark.parametrize(
    "mode",
    ["timeout", "os_error", "crash", "json", "large", "unknown_error", "array_error"],
)
def test_parent_failure_protocol_is_sanitized(monkeypatch, mode):
    """Reject malformed replies without leaking text and ensure metadata stays out of argv/env."""

    def worker(command, **kwargs):
        """Emulate a broken isolated worker while checking its parent-side descriptor contract."""
        assert "Đã sửa" not in " ".join(command)
        assert kwargs["env"] == {} and kwargs["pass_fds"]
        assert "--ro-bind-data" in command
        if mode == "timeout":
            raise subprocess.TimeoutExpired(command, 10)
        if mode == "os_error":
            raise OSError("private-detail")
        payload = {
            "json": b"broken",
            "large": b"x" * (module.MAX_OUTPUT_BYTES + 1),
            "unknown_error": b'{"error":"private-detail"}',
            "array_error": b'{"error":[]}',
        }.get(mode, b"{}")
        kwargs["stdout"].write(payload)
        return SimpleNamespace(returncode=1 if mode == "crash" else 0)

    monkeypatch.setattr(module.subprocess, "run", worker)
    with pytest.raises(StoragePolicyError) as error:
        process_bytes(GOLDEN.read_bytes())
    assert error.value.code in (
        "docx_processing_unavailable",
        "docx_processing_timeout",
    )


def test_view_protocol_and_log_privacy(caplog):
    """Validate numbering/references independently while keeping source text out of audit logs."""
    with caplog.at_level(logging.INFO):
        result = process_bytes(GOLDEN.read_bytes())
    assert "docx_read_completed" in caplog.text and "Alpha" not in caplog.text
    result["tables"][0]["cells"][0]["paragraph_ids"] = [99999]
    with pytest.raises(StoragePolicyError, match="docx_processing_unavailable"):
        validate_view(result)


def test_worker_kernel_limits_and_readonly_plan(monkeypatch):
    """Inspect real kernel budgets and private metadata mounts at the parser entrypoint."""
    sandbox = module.sandbox_command
    probe = '''
"""Inspect the production DOCX worker boundary without exposing host secrets."""
import os, resource
from src.infrastructure import file_content_verifier, docx_worker
from src.infrastructure.file_verifier import VERIFIER_MEMORY_BYTES, VERIFIER_CPU_SECONDS
original = file_content_verifier.verify_ooxml
def inspect_limits(*args):
    """Verify limits, private mounts and cleared environment before actual parsing."""
    assert resource.getrlimit(resource.RLIMIT_AS) == (VERIFIER_MEMORY_BYTES, VERIFIER_MEMORY_BYTES)
    assert resource.getrlimit(resource.RLIMIT_CPU) == (VERIFIER_CPU_SECONDS, VERIFIER_CPU_SECONDS+1)
    assert resource.getrlimit(resource.RLIMIT_FSIZE) == (25*1024*1024,25*1024*1024)
    assert resource.getrlimit(resource.RLIMIT_NOFILE) == (32,32)
    assert resource.getrlimit(resource.RLIMIT_CORE) == (0,0)
    assert not any('VAULT' in key or 'DATABASE' in key for key in os.environ)
    assert not os.path.exists('/app/data') and not os.path.exists('/home/korosaki-ryukai')
    try:
        descriptor = os.open('/request.json', os.O_WRONLY)
    except OSError:
        pass
    else:
        os.close(descriptor)
        raise AssertionError('editable plan mount')
    return original(*args)
file_content_verifier.verify_ooxml = inspect_limits
raise SystemExit(docx_worker.main())
'''

    def command(arguments):
        """Replace only the trusted worker entrypoint and retain production mount construction."""
        return sandbox(["/venv/bin/python", "-c", probe, "read"])

    monkeypatch.setattr(module, "sandbox_command", command)
    assert process_bytes(GOLDEN.read_bytes())["processor"] == DOCX_VERSION


def test_real_timeout_does_not_leave_workers(monkeypatch):
    """Reap a real stalled sandbox so source descriptors and metadata mounts cannot outlive it."""
    from uuid import uuid4

    marker = "docx-timeout-" + uuid4().hex
    sandbox = module.sandbox_command

    def stalled(arguments):
        """Replace parsing with a stalled process inside the same isolated namespaces."""
        return sandbox(
            ["/venv/bin/python", "-c", "import time; time.sleep(30)", marker]
        )

    monkeypatch.setattr(module, "sandbox_command", stalled)
    monkeypatch.setattr(module, "DOCX_WALL_SECONDS", 0.2)
    with pytest.raises(StoragePolicyError, match="docx_processing_timeout"):
        process_bytes(GOLDEN.read_bytes())
    for process in Path("/proc").iterdir():
        if process.name.isdecimal():
            try:
                assert marker.encode() not in (process / "cmdline").read_bytes()
            except (FileNotFoundError, ProcessLookupError, PermissionError):
                pass


def test_multiple_runs_empty_text_and_noop_roundtrip():
    """Edit multiple differently styled runs, clear text and preserve unchanged semantic content."""
    data = GOLDEN.read_bytes()
    plan = plan_for(
        data,
        [
            {"paragraph_id": 2, "run_index": 1, "text": "Alpha"},
            {"paragraph_id": 2, "run_index": 2, "text": ""},
        ],
    )
    result = process_bytes(data, "rewrite", plan)
    reopened = Document(io.BytesIO(result))
    assert reopened.paragraphs[1].runs[0].text == "Alpha"
    assert reopened.paragraphs[1].runs[1].text == ""
    assert reopened.paragraphs[1].runs[1].italic is True
    assert reopened.paragraphs[1].runs[2].text == "\tXin chào\nViệt Nam"


def test_plan_size_bound_before_worker(monkeypatch):
    """Reject oversized serialized edit metadata before opening an isolated parser process."""

    def forbidden(*args, **kwargs):
        """Fail if a plan exceeding the envelope budget schedules a worker."""
        pytest.fail("oversized plan scheduled worker")

    monkeypatch.setattr(module.subprocess, "run", forbidden)
    data = GOLDEN.read_bytes()
    plan = plan_for(data, [{"paragraph_id": 2, "run_index": 1, "text": "a" * 65536}])
    with pytest.raises(StoragePolicyError, match="docx_edits_too_large"):
        process_bytes(data, "rewrite", plan)
