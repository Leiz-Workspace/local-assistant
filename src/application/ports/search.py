"""Describe immutable untrusted search snippets and the credential-free provider port."""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True, repr=False)
class SearchHit:
    """Carry one provider snippet without treating its text or URL as authority."""

    title: str
    url: str
    snippet: str


@dataclass(frozen=True, slots=True, repr=False)
class SearchBatch:
    """Bind an immutable result tuple to the trusted adapter's configured identity."""

    provider_id: str
    hits: tuple[SearchHit, ...]


class SearchPort(Protocol):
    """Expose one explicit query without model, endpoint or credential arguments."""

    async def search(self, *, query: str, max_results: int) -> SearchBatch:
        """Return bounded raw snippets; the caller validates all returned evidence."""
        ...
