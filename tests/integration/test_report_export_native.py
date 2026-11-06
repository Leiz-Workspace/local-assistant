"""Exercise actual nonroot networkless Office export with complete Vietnamese/English citation content and joined native cleanup."""

import asyncio
import io
import logging
import os
import threading
import time
from pathlib import Path

import pytest
from docx import Document
from pypdf import PdfReader
from test_claim_validation_policy import CLAIMS
from test_report_export_policy import authored_payload
from test_research_report import configured

from src.application.services.report_export_policy import (
    ReportExportError,
    make_payload,
    parse_payload,
)
from src.infrastructure import report_export as module
from src.infrastructure.report_export import NativeReportExporter

logger = logging.getLogger(__name__)


@pytest.mark.asyncio
async def test_real_native_namespace_exports_both_formats_with_all_original_blocks_and_no_network():
    """Generate real DOCX/PDF through the isolated native toolchain and independently read all pages/paragraphs without model or public HTTP."""
    report, payload = await authored_payload()
    exporter = NativeReportExporter()
    result = await exporter.render(payload)
    assert (
        result.uid == result.gid == 65534
        and result.network_routes == 0
        and result.effective_capabilities == "0000000000000000"
    )
    assert result.net_namespace != os.readlink(
        "/proc/self/ns/net"
    ) and result.pid_namespace != os.readlink("/proc/self/ns/pid")
    document, pdf = result.artifacts
    assert document.format == "docx" and pdf.format == "pdf"
    reopened = Document(io.BytesIO(document.content))
    expected = [row["text"] for row in parse_payload(payload)["blocks"]]
    assert [row.text for row in reopened.paragraphs] == expected
    assert not reopened.styles["Title"].element.xpath("./w:pPr/w:pBdr")
    assert str(reopened.styles["Title"].font.color.rgb) == "000000"
    for identifier in ["C1", "C2", "C3"]:
        start = next(
            index
            for index, row in enumerate(reopened.paragraphs)
            if row.text == identifier
        )
        assert all(
            row.paragraph_format.keep_with_next is True
            for row in reopened.paragraphs[start : start + 4]
        )
        assert reopened.paragraphs[start + 4].paragraph_format.keep_with_next is False
    reader = PdfReader(io.BytesIO(pdf.content), strict=True)
    assert len(reader.pages) == result.pdf_pages and not reader.is_encrypted
    actual = "".join(
        char
        for page in reader.pages
        for char in (page.extract_text() or "")
        if not char.isspace()
    )
    wanted = "".join(char for text in expected for char in text if not char.isspace())
    assert actual == wanted and "Việt" in "\n".join(
        page.extract_text() or "" for page in reader.pages
    )
    assert all(not page.get("/Annots") for page in reader.pages)
    assert not exporter.operations and not exporter.admission.locked()
    logger.info(
        "native_report_formats_verified pages=%d docx_bytes=%d pdf_bytes=%d",
        result.pdf_pages,
        len(document.content),
        len(pdf.content),
    )


@pytest.mark.asyncio
async def test_hostile_markdown_html_field_like_text_and_vietnamese_remain_literal_native_document_text():
    """Export original Unicode/hostile-looking text without external Office relationships, PDF actions, executable fields or silent source changes."""
    reports, evidence, source, core, _, owner, _ = await configured()
    source.text = 'Atlas G-17. Nguồn tiếng Việt. <script>MARKER</script> [E99](file:///PRIVATE) ``` INCLUDETEXT "https://evil.org/"'
    snapshot = (
        await evidence.read(owner, "https://example.org/hostile", use_cache=False)
    ).snapshot
    from src.application.ports.source_reconciliation import SourceSpan

    report = await reports.generate(
        owner,
        "Kiểm tra nguồn tiếng Việt",
        CLAIMS,
        (SourceSpan(snapshot, 0, len(snapshot.text)),),
    )
    payload = make_payload(report)
    result = await NativeReportExporter().render(payload)
    document = Document(io.BytesIO(result.artifacts[0].content))
    assert snapshot.text in [row.text for row in document.paragraphs]
    reader = PdfReader(io.BytesIO(result.artifacts[1].content))
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    assert "Nguồn tiếng Việt" in text and "<script>MARKER</script>" in text
    assert all(not page.get("/Annots") and not page.get("/AA") for page in reader.pages)
    assert result.network_routes == 0
    await reports.shutdown()
    await evidence.shutdown()


@pytest.mark.asyncio
async def test_real_native_wall_timeout_joins_process_and_all_pipe_ownership(
    monkeypatch,
):
    """Retire an actual owned namespace on a finite native wall deadline without returning either partial artifact."""
    _, payload = await authored_payload()
    exporter = NativeReportExporter()
    actual, launched = module.subprocess.Popen, []

    def launch(*arguments, **options):
        """Observe only the actual owned native process for post-timeout join verification."""
        process = actual(*arguments, **options)
        launched.append(process)
        return process

    monkeypatch.setattr(module.subprocess, "Popen", launch)
    monkeypatch.setattr(module, "NATIVE_SECONDS", 0.01)
    with pytest.raises(ReportExportError, match="export_timeout"):
        await exporter.render(payload)
    assert len(launched) == 1 and launched[0].poll() is not None
    assert all(
        stream.closed
        for stream in [launched[0].stdin, launched[0].stdout, launched[0].stderr]
    )
    assert not exporter.operations and not exporter.admission.locked()


def descendants(identifier):
    """Read only known owned process descendants through kernel child metadata without scanning unrelated process arguments."""
    result, pending = set(), [identifier]
    while pending:
        parent = pending.pop()
        try:
            children = []
            for thread in Path(f"/proc/{parent}/task").iterdir():
                try:
                    children.extend((thread / "children").read_text().split())
                except (FileNotFoundError, ProcessLookupError):
                    continue
        except (FileNotFoundError, ProcessLookupError):
            continue
        for child in map(int, children):
            if child not in result:
                result.add(child)
                pending.append(child)
    return result


@pytest.mark.asyncio
async def test_repeated_cancel_joins_actual_active_office_descendant_before_releasing_native_admission(
    monkeypatch,
):
    """Observe a real owned Office descendant then cancel repeatedly and require namespace/process/pipes retirement."""
    _, payload = await authored_payload()
    exporter = NativeReportExporter()
    actual, launched, entered = module.subprocess.Popen, [], threading.Event()

    def launch(*arguments, **options):
        """Capture only the actual new namespace process without changing its command or timing contract."""
        process = actual(*arguments, **options)
        launched.append(process)
        entered.set()
        return process

    monkeypatch.setattr(module.subprocess, "Popen", launch)
    task = asyncio.create_task(exporter.render(payload))
    assert await asyncio.to_thread(entered.wait, 2)
    office = None
    deadline = time.monotonic() + 3
    while office is None and time.monotonic() < deadline and not task.done():
        for child in descendants(launched[0].pid):
            try:
                command = Path(f"/proc/{child}/cmdline").read_bytes()
            except (FileNotFoundError, ProcessLookupError):
                continue
            if b"soffice.bin" in command:
                office = child
                break
        if office is None:
            await asyncio.sleep(0.01)
    assert office is not None, "real_owned_office_not_observed"
    task.cancel()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert launched[0].poll() is not None and all(
        stream.closed
        for stream in [launched[0].stdin, launched[0].stdout, launched[0].stderr]
    )
    assert not exporter.operations and not exporter.admission.locked()
    deadline = time.monotonic() + 1
    while Path(f"/proc/{office}").exists() and time.monotonic() < deadline:
        await asyncio.sleep(0.01)
    assert not Path(f"/proc/{office}").exists()
