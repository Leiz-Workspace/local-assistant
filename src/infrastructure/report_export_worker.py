"""Create and independently reopen fixed text-only DOCX/PDF reports inside a private credential-free networkless namespace."""

import base64
import io
import json
import logging
import os
import resource
import subprocess
import sys
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)


def build_docx(payload, path):
    """Create a fixed styled document from complete escaped text blocks without importing documents or creating links/actions."""
    from datetime import datetime

    from docx import Document
    from docx.enum.style import WD_STYLE_TYPE
    from docx.shared import Inches, Pt, RGBColor

    document = Document()
    section = document.sections[0]
    section.page_width, section.page_height = Inches(8.5), Inches(11)
    section.top_margin = section.bottom_margin = section.left_margin = (
        section.right_margin
    ) = Inches(1)
    for name in ["Normal", "Title", "Heading 1", "Heading 2", "Quote", "Metadata"]:
        style = (
            document.styles[name]
            if name in document.styles
            else document.styles.add_style(name, WD_STYLE_TYPE.PARAGRAPH)
        )
        style.font.name = "Noto Sans"
        style.font.color.rgb = RGBColor(0, 0, 0)
        style.font.underline = False
        style.font.italic = False
        for border in list(style.element.xpath("./w:pPr/w:pBdr")):
            border.getparent().remove(border)
        style.font.size = Pt(
            {"Title": 22, "Heading 1": 15, "Heading 2": 12, "Metadata": 10}.get(
                name, 11
            )
        )
        style.paragraph_format.line_spacing = 1.15
        style.paragraph_format.space_after = Pt(
            2 if name in {"Normal", "Quote", "Metadata"} else 6
        )
        style.paragraph_format.widow_control = True
        style.paragraph_format.keep_together = False
        style.paragraph_format.keep_with_next = name in {
            "Title",
            "Heading 1",
            "Heading 2",
        }
        style.paragraph_format.space_before = Pt(
            14 if name == "Heading 1" else 6 if name == "Heading 2" else 0
        )
    document.styles["Quote"].paragraph_format.left_indent = Inches(0.15)
    document.styles["Quote"].paragraph_format.right_indent = Inches(0.15)
    claim_group = False
    for index, row in enumerate(payload["blocks"]):
        if row["style"] in {"Title", "Heading1", "Heading2"}:
            claim_group = row["style"] == "Heading2" and row["text"].startswith("C")
        paragraph = document.add_paragraph(
            row["text"],
            style={"Heading1": "Heading 1", "Heading2": "Heading 2"}.get(
                row["style"], row["style"]
            ),
        )
        if claim_group:
            paragraph.paragraph_format.keep_with_next = index + 1 < len(
                payload["blocks"]
            ) and payload["blocks"][index + 1]["style"] not in {
                "Title",
                "Heading1",
                "Heading2",
            }
        elif row["style"] == "Normal" and row["text"] in {
            "Title",
            "Final source URL",
            "Exact untrusted quote",
        }:
            paragraph.paragraph_format.keep_with_next = True
    properties = document.core_properties
    properties.title = "Research report"
    properties.subject = (
        "Cited claims and original source excerpts with explicit limitations"
    )
    properties.author = properties.last_modified_by = ""
    properties.comments = "Citation integrity does not establish semantic truth or verified publication freshness."
    properties.identifier = payload["source_markdown_sha256"]
    properties.keywords = payload["assessment_sha256"]
    properties.created = properties.modified = datetime.fromisoformat(
        payload["assessed_at"]
    )
    document.save(path)
    logger.info("report_docx_generated blocks=%d", len(payload["blocks"]))


def compact_text(value):
    """Compare complete native document content while ignoring layout-only whitespace and line/page wrapping."""
    return "".join(char for char in value if not char.isspace())


def verify_docx(data, payload):
    """Reopen all generated OOXML structures and original ordered paragraphs while refusing external/active Office features."""
    import xml.etree.ElementTree as ET
    import zipfile

    from docx import Document

    from src.application.services.report_export_policy import (
        MAX_DOCX,
        ReportExportError,
    )

    if not 0 < len(data) <= MAX_DOCX:
        raise ReportExportError("export_result_limit")
    with zipfile.ZipFile(io.BytesIO(data)) as package:
        if (
            len(package.infolist()) > 64
            or sum(info.file_size for info in package.infolist()) > 8 * 1024**2
            or package.testzip() is not None
        ):
            raise ReportExportError("export_native_failed")
        for name in package.namelist():
            if any(
                marker in name.lower()
                for marker in ["vbaproject", "activex", "embeddings/"]
            ):
                raise ReportExportError("export_native_failed")
            if name.endswith(".rels"):
                root = ET.fromstring(package.read(name))
                if any(
                    row.attrib.get("TargetMode", "").lower() == "external"
                    for row in root
                ):
                    raise ReportExportError("export_native_failed")
        root = ET.fromstring(package.read("word/document.xml"))
        forbidden = {
            "hyperlink",
            "fldSimple",
            "instrText",
            "object",
            "altChunk",
            "control",
        }
        if any(node.tag.rsplit("}", 1)[-1] in forbidden for node in root.iter()):
            raise ReportExportError("export_native_failed")
    reopened = Document(io.BytesIO(data))
    if any(
        reopened.styles[name].element.xpath("./w:pPr/w:pBdr")
        for name in ["Title", "Normal", "Heading 1", "Heading 2", "Quote", "Metadata"]
    ):
        raise ReportExportError("export_native_failed")
    if (
        [compact_text(row.text) for row in reopened.paragraphs]
        != [compact_text(row["text"]) for row in payload["blocks"]]
        or reopened.core_properties.identifier != payload["source_markdown_sha256"]
        or reopened.core_properties.author
    ):
        raise ReportExportError("export_native_failed")
    logger.info("report_docx_reopened_all_blocks_verified")


def verify_pdf(data, payload):
    """Reopen every generated PDF page and complete source text while refusing interactive actions, attachments or annotations."""
    from pypdf import PdfReader

    from src.application.services.report_export_policy import MAX_PDF, ReportExportError

    if not 0 < len(data) <= MAX_PDF:
        raise ReportExportError("export_result_limit")
    reader = PdfReader(io.BytesIO(data), strict=True)
    if reader.is_encrypted or not 1 <= len(reader.pages) <= 32:
        raise ReportExportError("export_result_limit")
    root = reader.trailer["/Root"]
    if any(key in root for key in ["/OpenAction", "/AA", "/AcroForm", "/Collection"]):
        raise ReportExportError("export_native_failed")
    names = root.get("/Names")
    if names is not None and any(
        key in names.get_object() for key in ["/EmbeddedFiles", "/JavaScript"]
    ):
        raise ReportExportError("export_native_failed")
    text = []
    for page in reader.pages:
        if page.get("/AA") or page.get("/Annots"):
            raise ReportExportError("export_native_failed")
        text.append(page.extract_text() or "")
    if compact_text("\n".join(text)) != compact_text(
        "\n".join(row["text"] for row in payload["blocks"])
    ):
        raise ReportExportError("export_native_failed")
    logger.info(
        "report_pdf_all_pages_complete_text_verified pages=%d", len(reader.pages)
    )
    return len(reader.pages)


def convert_pdf(root, docx_path):
    """Convert only the newly generated trusted DOCX with fixed options and a namespace-private Office profile/cache."""
    from src.application.services.report_export_policy import ReportExportError

    options = {
        name: dict(type="boolean", value=value)
        for name, value in {
            "ExportFormFields": False,
            "ExportBookmarks": False,
            "ExportNotes": False,
            "UseTaggedPDF": True,
        }.items()
    }
    command = [
        "/usr/bin/libreoffice",
        "-env:UserInstallation=" + (root / "profile").as_uri(),
        "--headless",
        "--nologo",
        "--nodefault",
        "--nofirststartwizard",
        "--norestore",
        "--unaccept=all",
        "--convert-to",
        "pdf:writer_pdf_Export:" + json.dumps(options, separators=(",", ":")),
        "--outdir",
        str(root),
        str(docx_path),
    ]
    with (
        tempfile.TemporaryFile(dir=root) as stdout,
        tempfile.TemporaryFile(dir=root) as stderr,
    ):
        try:
            result = subprocess.run(
                command,
                stdin=subprocess.DEVNULL,
                stdout=stdout,
                stderr=stderr,
                timeout=15,
                check=False,
                close_fds=True,
            )
        except subprocess.TimeoutExpired:
            raise ReportExportError("export_timeout") from None
        for stream in [stdout, stderr]:
            stream.seek(0)
            if len(stream.read(65537)) > 65536:
                raise ReportExportError("export_result_limit")
        if result.returncode != 0:
            raise ReportExportError("export_native_failed")
    logger.info("report_private_office_conversion_joined")
    return docx_path.with_suffix(".pdf")


def main():
    """Apply native budgets before imports, validate the whole request and publish only complete independently reopened artifact bytes."""
    resource.setrlimit(resource.RLIMIT_AS, (2 * 1024**3, 2 * 1024**3))
    resource.setrlimit(resource.RLIMIT_CPU, (20, 21))
    resource.setrlimit(resource.RLIMIT_FSIZE, (8 * 1024**2, 8 * 1024**2))
    resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    os.umask(0o077)
    logging.basicConfig(level=logging.INFO)
    from src.application.services.report_export_policy import (
        MAX_INPUT,
        ReportExportError,
        parse_payload,
    )

    try:
        raw = sys.stdin.buffer.read(MAX_INPUT + 1)
        payload = parse_payload(raw)
        with tempfile.TemporaryDirectory(
            prefix="report-export-", dir="/tmp"
        ) as directory:
            root = Path(directory)
            docx_path = root / "report.docx"
            build_docx(payload, docx_path)
            docx = docx_path.read_bytes()
            verify_docx(docx, payload)
            pdf_path = convert_pdf(root, docx_path)
            pdf = pdf_path.read_bytes()
            pages = verify_pdf(pdf, payload)
            status = Path("/proc/self/status").read_text()
            capabilities = next(
                line.split()[1]
                for line in status.splitlines()
                if line.startswith("CapEff:")
            )
            routes = len(Path("/proc/net/route").read_text().splitlines()) - 1
            result = dict(
                source_markdown_sha256=payload["source_markdown_sha256"],
                docx=base64.b64encode(docx).decode(),
                pdf=base64.b64encode(pdf).decode(),
                pdf_pages=pages,
                uid=os.getuid(),
                gid=os.getgid(),
                pid_namespace=os.readlink("/proc/self/ns/pid"),
                net_namespace=os.readlink("/proc/self/ns/net"),
                effective_capabilities=capabilities,
                network_routes=routes,
            )
        logger.info(
            "report_export_worker_complete pages=%d docx_bytes=%d pdf_bytes=%d",
            pages,
            len(docx),
            len(pdf),
        )
    except ReportExportError as error:
        result = dict(error=error.code)
    except MemoryError:
        result = dict(error="export_result_limit")
    except Exception as error:
        logger.warning(
            "report_export_worker_rejected error_type=%s", type(error).__name__
        )
        result = dict(error="export_native_failed")
    sys.stdout.buffer.write(
        json.dumps(result, separators=(",", ":"), allow_nan=False).encode()
    )
    sys.stdout.buffer.flush()


if __name__ == "__main__":
    main()
