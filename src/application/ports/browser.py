"""Describe immutable untrusted dynamic-page text and host-verified browser resource evidence."""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True, repr=False)
class BrowserHTTPResponse:
    """Carry one complete host-verified HTTPS GET response without credential, browser or model authority."""

    url: str
    status: int
    headers: tuple[tuple[str, str], ...]
    body: bytes
    pinned_address: str


@dataclass(frozen=True, slots=True, repr=False)
class BrowserResource:
    """Bind one permitted browser resource to its actual host-fetched URL, bytes and TLS peer."""

    url: str
    kind: str
    status: int
    media_type: str
    body_bytes: int
    body_sha256: str
    pinned_address: str


@dataclass(frozen=True, slots=True, repr=False)
class BrowserPage:
    """Return complete bounded rendered text while keeping page content and resource claims untrusted."""

    requested_url: str
    final_url: str
    title: str | None
    text: str
    text_sha256: str
    resources: tuple[BrowserResource, ...]
    blocked_decorative_requests: int
    content_trust: str = "untrusted"
    evidence_kind: str = "isolated_browser_layout_text"
    semantic_validation: bool = False
    browser_direct_network: bool = False


class BrowserPort(Protocol):
    """Expose explicit navigation/text only, without arbitrary CDP, JavaScript, interaction, header or model arguments."""

    async def navigate(self, url: str) -> BrowserPage:
        """Observe one permitted dynamic page after bounded host GET fulfillment and joined browser cleanup."""
        ...
