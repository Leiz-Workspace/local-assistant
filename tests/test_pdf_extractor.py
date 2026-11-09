"""Test native PDF golden page mapping, resource bounds and fail-closed worker protocol."""

import io
import logging
import subprocess
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest
from process_probe import reap_survivors, watch_teardown
from pypdf import PdfReader, PdfWriter
from pypdf.generic import (
    DecodedStreamObject,
    DictionaryObject,
    NameObject,
    TextStringObject,
)

from src.application.services.file_storage_policy import StoragePolicyError
from src.infrastructure import pdf_extractor as module
from src.infrastructure.pdf_extractor import (
    EXTRACTOR_VERSION,
    extract_pdf,
    validate_pages,
)

logger = logging.getLogger(__name__)
GOLDEN = Path(__file__).parent / "fixtures/pdf/native-pages.pdf"


def run_bytes(data):
    """Supply an actual regular descriptor to the production Bubblewrap extractor."""
    with tempfile.TemporaryFile() as source:
        source.write(data)
        source.seek(0)
        return extract_pdf(source)


def test_golden_pages_unicode_and_blank():
    """Assert exact independent golden text and retain original one-based blank-page mapping."""
    assert run_bytes(GOLDEN.read_bytes()) == [
        {"page_number": 1, "text": "Page one: Alpha 123\nSecond line."},
        {"page_number": 2, "text": "Xin ệ"},
        {"page_number": 3, "text": ""},
    ]
    logger.info("pdf_golden_verified pages=3 unicode=True blank=True")


@pytest.mark.parametrize(
    "kind", ["malformed", "encrypted", "active", "pages", "page_text", "total_text"]
)
def test_actual_invalid_and_bounded_pdfs(kind):
    """Reject malformed, encrypted, active and oversized real PDF inputs inside the sandbox."""
    writer = PdfWriter()
    writer.append(PdfReader(GOLDEN))
    if kind == "encrypted":
        writer.encrypt("test-only")
    elif kind == "active":
        writer._root_object[NameObject("/OpenAction")] = DictionaryObject(
            {
                NameObject("/S"): NameObject("/JavaScript"),
                NameObject("/JS"): TextStringObject("hostile-test"),
            }
        )
    elif kind == "pages":
        for _ in range(1000):
            writer.add_blank_page(width=100, height=100)
    elif kind in ("page_text", "total_text"):
        writer = PdfWriter()
        count = 1 if kind == "page_text" else 10
        length = 131073 if kind == "page_text" else 110000
        for _ in range(count):
            page = writer.add_page(PdfReader(GOLDEN).pages[0])
            stream = DecodedStreamObject()
            stream.set_data(b"BT /F1 12 Tf (" + b"A" * length + b") Tj ET")
            page[NameObject("/Contents")] = writer._add_object(stream)
    output = io.BytesIO()
    writer.write(output)
    with pytest.raises(StoragePolicyError) as error:
        run_bytes(b"%PDF-malformed" if kind == "malformed" else output.getvalue())
    assert error.value.status_code in (413, 415)
    assert error.value.code in (
        "invalid_pdf_content",
        "extraction_limits_exceeded",
        "extraction_timeout",
    )


@pytest.mark.parametrize(
    "payload",
    [
        None,
        [],
        {},
        {"extractor": "wrong", "pages": []},
        {"extractor": EXTRACTOR_VERSION, "pages": [{"page_number": True, "text": ""}]},
        {"extractor": EXTRACTOR_VERSION, "pages": [{"page_number": 2, "text": ""}]},
        {
            "extractor": EXTRACTOR_VERSION,
            "pages": [{"page_number": 1, "text": "\ud800"}],
        },
    ],
)
def test_protocol_rejects_invalid_schema(payload):
    """Reject invalid or incomplete worker replies before constructing source provenance."""
    with pytest.raises(StoragePolicyError, match="extraction_unavailable"):
        validate_pages(payload)


@pytest.mark.parametrize(
    "mode",
    [
        "timeout",
        "os_error",
        "crash",
        "json",
        "large",
        "unknown_error",
        "unhashable_error",
    ],
)
def test_worker_failures_sanitized_and_source_reset(monkeypatch, mode):
    """Bound output and hide process errors while rewinding the retained source FD."""

    def worker(command, **kwargs):
        """Emulate worker boundary failures without leaking parser text or credentials."""
        assert kwargs["env"] == {} and kwargs["close_fds"]
        kwargs["stdin"].read(3)
        if mode == "timeout":
            raise subprocess.TimeoutExpired(command, 10)
        if mode == "os_error":
            raise OSError("private-parser-detail")
        payload = {
            "unknown_error": b'{"error":"private-parser-detail"}',
            "unhashable_error": b'{"error":[]}',
            "json": b"broken",
            "large": b"x" * (module.MAX_EXTRACTION_OUTPUT_BYTES + 1),
        }.get(mode, b"{}")
        kwargs["stdout"].write(payload)
        return SimpleNamespace(returncode=1 if mode == "crash" else 0)

    monkeypatch.setattr(module, "run_sandbox", worker)
    with tempfile.TemporaryFile() as source:
        source.write(b"abcdef")
        with pytest.raises(StoragePolicyError) as error:
            extract_pdf(source)
        assert error.value.code in ("extraction_unavailable", "extraction_timeout")
        assert source.tell() == 0


def test_parent_rejects_text_overflow():
    """Enforce the document text budget independently of the isolated worker."""
    payload = {
        "extractor": EXTRACTOR_VERSION,
        "pages": [
            {"page_number": number, "text": "a" * 120000} for number in range(1, 11)
        ],
    }
    with pytest.raises(StoragePolicyError, match="extraction_limits_exceeded"):
        validate_pages(payload)


def test_worker_kernel_limits():
    """Inspect real kernel limits at the production extractor's parser entrypoint."""
    probe = '''
"""Audit worker resource limits without reading private host state."""
import resource
from src.infrastructure import file_content_verifier, pdf_extractor_worker
from src.infrastructure.file_verifier import VERIFIER_MEMORY_BYTES, VERIFIER_CPU_SECONDS
original = file_content_verifier.verify_pdf
def inspect_limits(*args):
    """Check limits before permitting the actual golden parser invocation."""
    assert resource.getrlimit(resource.RLIMIT_AS) == (VERIFIER_MEMORY_BYTES, VERIFIER_MEMORY_BYTES)
    assert resource.getrlimit(resource.RLIMIT_CPU) == (VERIFIER_CPU_SECONDS, VERIFIER_CPU_SECONDS + 1)
    assert resource.getrlimit(resource.RLIMIT_FSIZE) == (8*1024*1024,8*1024*1024)
    assert resource.getrlimit(resource.RLIMIT_NOFILE) == (32,32)
    assert resource.getrlimit(resource.RLIMIT_CORE) == (0,0)
    return original(*args)
file_content_verifier.verify_pdf = inspect_limits
raise SystemExit(pdf_extractor_worker.main())
'''
    with GOLDEN.open("rb") as source:
        result = subprocess.run(
            module.sandbox_command(["/venv/bin/python", "-c", probe]),
            stdin=source,
            capture_output=True,
            timeout=10,
            check=False,
        )
    assert result.returncode == 0
    import json

    assert len(validate_pages(json.loads(result.stdout))) == 3


def test_real_timeout_reaps_worker(monkeypatch):
    """Kill a real stalled sandbox and verify no process keeps its borrowed source descriptor."""
    from uuid import uuid4

    marker = "pdf-extraction-timeout-" + uuid4().hex
    sandbox = module.sandbox_command

    def stalled(arguments):
        """Keep production namespace isolation while replacing the worker with a stalled probe."""
        return sandbox(
            ["/venv/bin/python", "-c", "import time; time.sleep(30)", marker]
        )

    monkeypatch.setattr(module, "sandbox_command", stalled)
    monkeypatch.setattr(module, "EXTRACTION_WALL_SECONDS", 2.5)
    try:
        # The namespace processes are seen alive before the timeout fires and must all
        # have exited at the moment the call returns.
        report = watch_teardown(lambda: run_bytes(GOLDEN.read_bytes()), marker, 2)
        assert isinstance(report.error, StoragePolicyError)
        assert report.error.code == "extraction_timeout"
        assert report.held == 2 and report.exited_at_return is True
    finally:
        reap_survivors(marker, timeout=0)


def test_extraction_logs_keep_page_content_private(caplog):
    """Audit counts and versions without recording source text or parser diagnostics."""
    with caplog.at_level(logging.INFO):
        run_bytes(GOLDEN.read_bytes())
    assert "pdf_extraction_completed" in caplog.text
    assert "Alpha 123" not in caplog.text and "Xin ệ" not in caplog.text
