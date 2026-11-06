"""Describe caller-designated primary lookup, signed excerpt selections and unverified cross-source comparison groups."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from src.application.ports.web_evidence import EvidenceReference, EvidenceSnapshot


@dataclass(frozen=True, slots=True, repr=False)
class PrimaryCandidate:
    """Preserve an original URI and explicit navigation/eligibility/attempt result without inventing publisher authority."""

    original_url: str
    navigation_url: str
    fragment_removed: bool
    status: str
    attempted: bool
    snapshot_id: UUID | None
    error_code: str | None


@dataclass(frozen=True, slots=True, repr=False)
class PrimaryLookup:
    """Return at mostfour complete signed source snapshots and all candidate states under caller-supplied host policy."""

    owner_id: UUID
    candidates: tuple[PrimaryCandidate, ...]
    snapshots: tuple[EvidenceSnapshot, ...]
    attempts: int
    status: str
    completed_at: datetime
    primary_designation: str = "caller_designated_unverified"
    content_trust: str = "untrusted"
    verified_freshness: None = None


@dataclass(frozen=True, slots=True, repr=False)
class SourceSpan:
    """Bind a caller-selected complete code-point span to one issued owner-signed snapshot."""

    snapshot: EvidenceSnapshot
    start: int
    end: int


@dataclass(frozen=True, slots=True, repr=False)
class EvidenceGroup:
    """Describe an unverified model comparison topic and only existing host-issued excerpt identifiers."""

    topic: str
    evidence_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True, repr=False)
class SourceComparison:
    """Surface agreements/conflicts/unresolved questions with original quote provenance and no source winner/truth promotion."""

    owner_id: UUID
    goal: str
    evidence: tuple[EvidenceReference, ...]
    agreements: tuple[EvidenceGroup, ...]
    conflicts: tuple[EvidenceGroup, ...]
    unresolved: tuple[EvidenceGroup, ...]
    completed_at: datetime
    model_attempts: int = 1
    content_trust: str = "untrusted"
    semantic_validation: bool = False
    verified_freshness: None = None
