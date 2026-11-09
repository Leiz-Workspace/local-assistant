"""Validate real native/raster OCR, per-page mapping, uncertainty and kernel-bounded parser behavior."""

import base64
import io
import logging
import subprocess
import tempfile
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from PIL import Image
from process_probe import reap_survivors, watch_teardown

from src.application.services.file_storage_policy import StoragePolicyError
from src.application.services.ocr_contract import validate_page, validate_vision
from src.infrastructure import page_ocr as module
from src.infrastructure.page_ocr import prepare_page

logger = logging.getLogger(__name__)
ROOT = Path(__file__).parent / "fixtures/ocr"
CLEAN_TEXT = "LOCAL OCR GOLDEN\nInvoice 2048\nTotal 42 USD"


def recognize_file(name="clean.png", page=1, mode="auto"):
    """Exercise the actual namespace worker using a trusted fixture's retained read-only FD."""
    with (ROOT / name).open("rb") as source:
        return prepare_page(source, name.rsplit(".", 1)[1], page, mode)


def edit_distance(expected, actual):
    """Measure exact Levenshtein edits on characters or word sequences for golden evaluation."""
    previous = list(range(len(actual) + 1))
    for index, left in enumerate(expected, 1):
        current = [index]
        for column, right in enumerate(actual, 1):
            current.append(
                min(
                    current[-1] + 1,
                    previous[column] + 1,
                    previous[column - 1] + (left != right),
                )
            )
        previous = current
    return previous[-1]


@pytest.mark.parametrize("name,page", [("clean.png", 1), ("scanned.pdf", 1)])
def test_golden_ocr_quality_and_pixel_mapping(name, page):
    """Require measured clean/scan transcription quality and bounded real engine pixel boxes."""
    result = recognize_file(name, page)
    assert result["method"] == "tesseract"
    assert edit_distance(CLEAN_TEXT, result["text"]) / len(CLEAN_TEXT) <= 0.02
    assert edit_distance(CLEAN_TEXT.split(), result["text"].split()) == 0
    assert result["page_number"] == page
    assert result["page_count"] == (2 if name.endswith("pdf") else 1)
    assert result["engine"].startswith("tesseract 5.5.0:eng")
    assert 85 <= result["confidence_score"] <= 100 and not result["review_required"]
    assert (
        result["confidence_basis"] == "character_weighted_engine_score_not_probability"
    )
    assert "english_only" in result["uncertainties"]
    assert result["table_structure_status"] == "not_inferred"
    assert result["coordinate_space"] == "rendered_pixels"
    assert result["words"]
    for word in result["words"]:
        assert word["left"] + word["width"] <= result["width"]
        assert word["top"] + word["height"] <= result["height"]
    logger.info(
        "ocr_golden_quality_verified fixture=%s character_errors=%d",
        name,
        edit_distance(CLEAN_TEXT, result["text"]),
    )


@pytest.mark.parametrize(
    "name,page", [("blank.png", 1), ("unclear.png", 1), ("scanned.pdf", 2)]
)
def test_blank_or_unclear_is_not_confident(name, page):
    """Expose absent text and uncertainty rather than inventing confident output for unreadable pages."""
    result = recognize_file(name, page)
    assert result["text"] == "" and result["confidence_score"] is None
    assert result["review_required"]
    assert "no_text_detected_not_proof_of_blank" in result["uncertainties"]


def test_native_pdf_fallback_and_page_errors():
    """Prefer native text while retaining source page numbers and rejecting nonexistent pages."""
    path = ROOT.parent / "pdf/native-pages.pdf"
    with path.open("rb") as source:
        result = prepare_page(source, "pdf", 1, "auto")
    assert result["method"] == "native_pdf" and result["page_count"] == 3
    assert result["text"] == "Page one: Alpha 123\nSecond line."
    assert result["confidence_score"] is None and result["words"] == []
    for filename, page in [("clean.png", 2), ("scanned.pdf", 3)]:
        with pytest.raises(StoragePolicyError, match="ocr_page_not_found"):
            recognize_file(filename, page)


def test_sanitized_vision_raster_and_orientation():
    """Strip source metadata, apply orientation and expose only a bounded re-encoded PNG to vision."""
    image = Image.new("RGB", (400, 200), "white")
    exif = Image.Exif()
    exif[274] = 6
    exif[270] = "private-metadata-marker"
    output = io.BytesIO()
    image.save(output, "JPEG", exif=exif, icc_profile=b"private-icc-marker")
    with tempfile.TemporaryFile() as source:
        source.write(output.getvalue())
        source.seek(0)
        result = prepare_page(source, "jpg", 1, "vlm")
    assert (result["width"], result["height"]) == (200, 400)
    data = base64.b64decode(result["image_base64"])
    assert b"private-metadata-marker" not in data
    with Image.open(io.BytesIO(data)) as normalized:
        assert not normalized.getexif() and normalized.format == "PNG"
        assert "icc_profile" not in normalized.info
    assert result["review_required"] and result["confidence_score"] is None


@pytest.mark.parametrize(
    "kind", ["box", "nan", "page", "low_confidence", "untrusted_image", "text"]
)
def test_parent_page_protocol_rejects_invalid_data(kind):
    """Reject forged provenance, pixel bounds, nonfinite scores and missing uncertainty requirements."""
    result = recognize_file()
    if kind == "box":
        result["words"][0]["left"] = 99999
    elif kind == "nan":
        result["confidence_score"] = float("nan")
    elif kind == "page":
        result["page_number"] = 3
    elif kind == "low_confidence":
        result.update(confidence_score=20.0, review_required=False)
    elif kind == "untrusted_image":
        result["image_base64"] = "not-an-image"
    else:
        result["text"] = "x" * 65537
    with pytest.raises(StoragePolicyError, match="ocr_processing_unavailable"):
        validate_page(result)


@pytest.mark.parametrize(
    "kind", ["extra", "confidence", "wide_table", "large_text", "invalid_type"]
)
def test_vision_schema_rejects_actions_or_unbounded_payloads(kind):
    """Accept transcription data only and forbid model-reported certainty or arbitrary actions."""
    payload = {"text": "sample", "tables": [], "uncertain_regions": []}
    if kind == "extra":
        payload["tool_call"] = "execute"
    elif kind == "confidence":
        payload["confidence"] = 0.99
    elif kind == "wide_table":
        payload["tables"] = [{"rows": [["x"] * 21]}]
    elif kind == "large_text":
        payload["text"] = "x" * 65537
    else:
        payload["tables"] = None
    with pytest.raises(StoragePolicyError, match="vision_invalid_result"):
        validate_vision(payload)


@pytest.mark.parametrize(
    "mode", ["timeout", "os_error", "crash", "json", "oversized", "error_type"]
)
def test_parent_worker_failures_sanitized(monkeypatch, mode):
    """Bound malformed worker replies, keep credentials out and rewind the caller's source FD."""

    def failed(command, **kwargs):
        """Inject controlled parser boundary failures without revealing source or exception diagnostics."""
        assert kwargs["env"] == {} and kwargs["close_fds"]
        if mode == "timeout":
            raise subprocess.TimeoutExpired(command, 25)
        if mode == "os_error":
            raise OSError("private-detail")
        kwargs["stdout"].write(
            b"x" * (module.MAX_WORKER_BYTES + 1)
            if mode == "oversized"
            else b'{"error":[]}'
            if mode == "error_type"
            else b"broken"
        )
        return SimpleNamespace(returncode=1 if mode == "crash" else 0)

    monkeypatch.setattr(module, "run_sandbox", failed)
    with pytest.raises(StoragePolicyError) as error:
        recognize_file()
    assert error.value.code in ("ocr_processing_unavailable", "ocr_processing_timeout")


def test_worker_kernel_limits_and_private_namespace(monkeypatch):
    """Inspect actual resource limits and read-only private-path isolation at the production entrypoint."""
    sandbox = module.sandbox_command
    probe = '''
"""Inspect the production page worker before any source parsing."""
import os,resource
from src.infrastructure import ocr_worker
original=ocr_worker.process
def inspect(*args):
    """Assert kernel budgets and cleared host state then call the actual OCR parser."""
    assert resource.getrlimit(resource.RLIMIT_AS)==(512*1024**2,512*1024**2)
    assert resource.getrlimit(resource.RLIMIT_CPU)==(8,9)
    assert resource.getrlimit(resource.RLIMIT_FSIZE)==(8*1024**2,8*1024**2)
    assert resource.getrlimit(resource.RLIMIT_NOFILE)==(32,32)
    assert resource.getrlimit(resource.RLIMIT_CORE)==(0,0)
    assert not os.path.exists('/app/data') and not os.path.exists('/home/korosaki-ryukai')
    assert not any('DATABASE' in key or 'VAULT' in key for key in os.environ)
    try: fd=os.open('/tmp/probe',os.O_CREAT|os.O_WRONLY,0o600)
    except OSError: pass
    else:
        os.close(fd)
        raise AssertionError('writable parser tmp')
    return original(*args)
ocr_worker.process=inspect
raise SystemExit(ocr_worker.main())
'''

    def command(arguments):
        """Retain production mounts while replacing the entrypoint with a kernel-inspection wrapper."""
        return sandbox(["/venv/bin/python", "-c", probe, "png", "1", "ocr"])

    monkeypatch.setattr(module, "sandbox_command", command)
    assert recognize_file()["text"] == CLEAN_TEXT


def test_timeout_reaps_worker_and_descendant(monkeypatch):
    """Kill a real stalled namespace and verify neither it nor a nested parser retains source descriptors."""
    marker = "page-ocr-timeout-" + uuid4().hex
    sandbox = module.sandbox_command

    def stalled(arguments):
        """Create a real nested stalled parser under the same production PID namespace."""
        code = 'import subprocess,sys,time; subprocess.Popen([sys.executable,"-c","import time; time.sleep(30)",sys.argv[1]]); time.sleep(30)'
        return sandbox(["/venv/bin/python", "-c", code, marker])

    monkeypatch.setattr(module, "sandbox_command", stalled)
    monkeypatch.setattr(module, "OCR_WALL_SECONDS", 2.5)
    try:
        # The namespace processes are seen alive before the timeout fires and must all
        # have exited at the moment the call returns.
        report = watch_teardown(lambda: recognize_file(), marker, 3)
        assert isinstance(report.error, StoragePolicyError)
        assert report.error.code == "ocr_processing_timeout"
        assert report.held == 3 and report.exited_at_return is True
    finally:
        reap_survivors(marker, timeout=0)


def test_ocr_logs_keep_source_text_private(caplog):
    """Audit method/page identifiers while keeping recognized words out of runtime logs."""
    with caplog.at_level(logging.INFO):
        recognize_file()
    assert "ocr_page_prepared" in caplog.text and "Invoice 2048" not in caplog.text


def test_ocr_text_budget_includes_line_separators(monkeypatch):
    """Reject OCR output whose joined transcription exceeds the combined text/word budget."""
    from src.application.services import ocr_contract
    from src.infrastructure import ocr_worker

    def output(command, **kwargs):
        """Provide a small valid TSV where the join separator crosses the total text limit."""
        if "--version" in command:
            return b"tesseract synthetic\n"
        return b"level\tblock_num\tpar_num\tline_num\tleft\ttop\twidth\theight\tconf\ttext\n5\t1\t1\t1\t0\t0\t1\t1\t90\tab\n5\t1\t1\t1\t1\t0\t1\t1\t90\txyz\n"

    monkeypatch.setattr(ocr_worker, "child_output", output)
    monkeypatch.setattr(ocr_contract, "MAX_TEXT_BYTES", 10)
    with pytest.raises(StoragePolicyError, match="ocr_limits_exceeded"):
        ocr_worker.recognize(b"not-decoded-in-this-boundary-test", {})
