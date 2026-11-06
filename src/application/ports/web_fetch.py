"""Describe immutable fetched web evidence without granting page, canonical-link or model authority."""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True, repr=False)
class PublicResponse:
    """Carry one bounded HTTPS hop's complete body and headers from a trusted network adapter."""

    status: int
    headers: tuple[tuple[str, str], ...]
    body: bytes
    pinned_address: str


@dataclass(frozen=True, slots=True, repr=False)
class FetchedPage:
    """Bind static untrusted text to actual fetched bytes and URLs, keeping canonical metadata unverified."""

    requested_url: str
    final_url: str
    redirects: tuple[tuple[str, str], ...]
    media_type: str
    title: str | None
    text: str
    body_sha256: str
    text_sha256: str
    advertised_canonical_url: str | None
    canonical_verified: bool = False
    content_trust: str = "untrusted"
    extractor_version: str = "static-html-utf8-v1"


class WebFetchPort(Protocol):
    """Expose only one explicit URL without headers, credentials, model, resolver or policy overrides."""

    async def fetch(self, url: str) -> FetchedPage:
        """Return complete bounded static evidence without following page instructions or fetching subresources."""
        ...
