"""Describe immutable owner-bound source observations, signed acquisition snapshots and exact untrusted text references."""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from src.application.ports.browser import BrowserPage
from src.application.ports.web_fetch import FetchedPage


@dataclass(frozen=True, slots=True, repr=False)
class SourceDateClaim:
    """Retain an explicit page date declaration without treating it as verified publication history."""

    kind: str
    raw_value: str
    parsed_iso: str | None
    timezone_present: bool
    verified: bool = False


@dataclass(frozen=True, slots=True, repr=False)
class EvidenceResource:
    """Bind an actually received source resource to its URL, status, kind and complete body hash."""

    url: str
    kind: str
    status: int
    body_bytes: int
    body_sha256: str


@dataclass(frozen=True, slots=True, repr=False)
class ObservedSource:
    """Carry accepted static/browser evidence and bounded original-response date/cache metadata from a trusted port."""

    page: FetchedPage | BrowserPage
    dates: tuple[SourceDateClaim, ...]
    resources: tuple[EvidenceResource, ...]
    cache_seconds: int


@dataclass(frozen=True, slots=True, repr=False)
class EvidenceSnapshot:
    """Bind complete untrusted text and original acquisition provenance to one owner and an ephemeral integrity proof."""

    identifier: UUID
    owner_id: UUID
    requested_url: str
    final_url: str
    title: str | None
    source_mode: str
    extractor_version: str
    fetch_started_at: datetime
    fetched_at: datetime
    date_claims: tuple[SourceDateClaim, ...]
    text: str
    text_sha256: str
    content_id: str
    resources: tuple[EvidenceResource, ...]
    advertised_canonical_url: str | None
    citation_deadline: float
    proof: str
    canonical_verified: bool = False
    content_trust: str = "untrusted"
    semantic_validation: bool = False


@dataclass(frozen=True, slots=True, repr=False)
class EvidenceRead:
    """Expose cache reuse separately from the original source acquisition time and publication claims."""

    snapshot: EvidenceSnapshot
    cache_hit: bool
    served_at: datetime
    acquisition_age_seconds: float


@dataclass(frozen=True, slots=True, repr=False)
class EvidenceReference:
    """Map an exact code-point quote to one issued source snapshot without claiming semantic entailment."""

    snapshot_id: UUID
    content_id: str
    start: int
    end: int
    quote: str
    quote_sha256: str
    final_url: str
    title: str | None
    fetched_at: datetime
    date_claims: tuple[SourceDateClaim, ...]
    content_trust: str = "untrusted"
    semantic_validation: bool = False


class WebEvidenceSourcePort(Protocol):
    """Expose only explicit static/dynamic acquisition through previously accepted source boundaries."""

    async def read(self, url: str, mode: str) -> ObservedSource:
        """Return original source metadata only after owned fetch/browser/resource cleanup has completed."""
        ...
