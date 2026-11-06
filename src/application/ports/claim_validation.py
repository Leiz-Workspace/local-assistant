"""Describe host-bound authentic source quotes and explicitly unverified model support assessments for complete claim batches."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from src.application.ports.web_evidence import EvidenceReference


@dataclass(frozen=True, slots=True, repr=False)
class ClaimEvidence:
    """Bind one host-assigned excerpt ID to its original owner-authenticated exact quote provenance."""

    evidence_id: str
    reference: EvidenceReference


@dataclass(frozen=True, slots=True, repr=False)
class ClaimAssessment:
    """Retain original claim text and unverified model status/reason with only known source excerpt IDs."""

    claim_id: str
    text: str
    status: str
    evidence_ids: tuple[str, ...]
    reason: str
    assessment_trust: str = "model_unverified"


@dataclass(frozen=True, slots=True, repr=False)
class ClaimValidation:
    """Return complete citation-integrity evidence without promoting a model classification to semantic verification."""

    owner_id: UUID
    goal: str
    evidence: tuple[ClaimEvidence, ...]
    claims: tuple[ClaimAssessment, ...]
    completed_at: datetime
    model_attempts: int = 1
    citation_integrity: str = "owner_signed_exact_span"
    status: str = "assessed_unverified"
    content_trust: str = "untrusted"
    semantic_validation: bool = False
    verified_freshness: None = None
