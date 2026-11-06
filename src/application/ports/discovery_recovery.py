"""Describe explicit archived search provenance and bounded recovery plans without live source authorization or fabricated provider text."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True, slots=True, repr=False)
class ArchivedDiscoveryHit:
    """Preserve one actually observed result rank, original URL and unavailable-text fingerprints."""

    rank: int
    url: str
    title_sha256: str
    snippet_sha256: str


@dataclass(frozen=True, slots=True, repr=False)
class ArchivedDiscoveryQuery:
    """Bind the original public query to its complete observed outcome and UTC acquisition time."""

    query_id: str
    query: str
    topic: str
    language: str
    observed_at: datetime
    status: str
    error_code: str | None
    error_type: str | None
    hits: tuple[ArchivedDiscoveryHit, ...]


@dataclass(frozen=True, slots=True, repr=False)
class DiscoveryCheckpoint:
    """Retain pinned complete metadata bytes and derived owner-bound records without old source text or proof keys."""

    owner_id: UUID
    archive_sha256: str
    corpus_sha256: str
    archive_bytes: bytes
    corpus_bytes: bytes
    queries: tuple[ArchivedDiscoveryQuery, ...]
    imported_at: datetime
    expires_at: datetime
    provider_id: str = "searxng"
    provider_engine: str = "brave"
    verified_freshness: None = None
    content_trust: str = "untrusted"


@dataclass(frozen=True, slots=True, repr=False)
class RecoveredDiscoverySource:
    """Identify a selected archived pointer whose content still requires a fresh policy-admitted acquisition."""

    family: str
    query_id: str
    rank: int
    url: str
    observed_at: datetime
    title_sha256: str
    snippet_sha256: str


@dataclass(frozen=True, slots=True, repr=False)
class DiscoveryRecoveryPlan:
    """Expose a complete query selection and historical provenance while explicitly counting zero current provider requests."""

    owner_id: UUID
    goal: str
    query_ids: tuple[str, ...]
    sources: tuple[RecoveredDiscoverySource, ...]
    archive_sha256: str
    corpus_sha256: str
    planned_at: datetime
    model_attempts: int = 1
    provider_requests: int = 0
    verified_freshness: None = None
    content_trust: str = "untrusted"
