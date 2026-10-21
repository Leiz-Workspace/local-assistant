"""Describe immutable bounded research plans and untrusted per-query outcomes without implying page fetch, answer or verified freshness."""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True, slots=True, repr=False)
class ResearchSource:
    """Bind a server-issued query/source identifier to complete original provider text and URL/hash."""

    source_id: str
    title: str
    url: str
    snippet: str
    snippet_sha256: str


@dataclass(frozen=True, slots=True, repr=False)
class ResearchQuery:
    """Retain an explicit canonical query, actual attempt state and untrusted source outcomes without silent missing work."""

    query_id: str
    query: str
    status: str
    attempted: bool
    error_code: str | None
    received_at: datetime | None
    sources: tuple[ResearchSource, ...]


@dataclass(frozen=True, slots=True, repr=False)
class ResearchResult:
    """Expose one fixed-budget run with partial/missing states, never a fabricated researched answer or publication date."""

    run_id: UUID
    owner_id: UUID
    goal: str
    queries: tuple[ResearchQuery, ...]
    status: str
    model_attempts: int
    provider_attempts: int
    completed_at: datetime
    content_trust: str = "untrusted"
    evidence_kind: str = "provider_snippet_not_fetched"
    semantic_validation: bool = False
    verified_freshness: None = None


class ResearchPort(Protocol):
    """Expose only an explicit trusted-owner goal, without caller-selected model/provider/action/budget or private context arguments."""

    async def research(self, owner: UUID, goal: str) -> ResearchResult:
        """Return a bounded plan/query-state run after joined backend cleanup without generating an evidence-backed answer."""
        ...
