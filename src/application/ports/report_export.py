"""Describe bounded owner-bound DOCX/PDF bytes and observed native namespace metadata for authenticated report export."""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True, slots=True, repr=False)
class ExportArtifact:
    """Bind one complete fixed-format artifact to exact bytes/hash and the original report Markdown identity."""

    format: str
    media_type: str
    filename: str
    content: bytes
    sha256: str
    source_markdown_sha256: str


@dataclass(frozen=True, slots=True, repr=False)
class NativeReportExport:
    """Retain complete native artifact bytes and actual bounded namespace observations without raw logs or private report payloads."""

    artifacts: tuple[ExportArtifact, ...]
    pdf_pages: int
    uid: int
    gid: int
    pid_namespace: str
    net_namespace: str
    effective_capabilities: str
    network_routes: int
    stderr_bytes: int
    stderr_sha256: str


@dataclass(frozen=True, slots=True, repr=False)
class ReportExport:
    """Return both complete artifacts only after issuer-bound source proofs and native cleanup remain valid."""

    owner_id: UUID
    source_markdown_sha256: str
    artifacts: tuple[ExportArtifact, ...]
    pdf_pages: int
    completed_at: datetime
    content_trust: str = "untrusted"
    semantic_validation: bool = False
    verified_freshness: None = None


class ReportExportPort(Protocol):
    """Expose one fixed both-format native batch without caller-selected commands, paths, templates or network requests."""

    async def render(self, payload: bytes) -> NativeReportExport:
        """Return complete bounded artifact bytes only after owned native namespace/process/pipes cleanup is joined."""
        ...
