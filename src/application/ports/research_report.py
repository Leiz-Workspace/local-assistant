"""Describe reproducible cited Markdown and expiring owner-bound integrity receipts without granting semantic truth or action authority."""

from dataclasses import dataclass
from uuid import UUID

from src.application.ports.claim_validation import ClaimValidation


@dataclass(frozen=True, slots=True, repr=False)
class ResearchReport:
    """Bind complete original assessment and deterministic Markdown to one owner and one process-scoped expiring receipt."""

    owner_id: UUID
    assessment: ClaimValidation
    markdown: str
    markdown_sha256: str
    assessment_sha256: str
    citation_deadline: float
    proof: str
    schema_version: str = "research-markdown-v1"
    content_trust: str = "untrusted"
    semantic_validation: bool = False
    verified_freshness: None = None
