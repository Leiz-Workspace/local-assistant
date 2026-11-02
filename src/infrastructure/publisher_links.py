"""Extract one actually observed RFC full-text anchor through unchanged bounded HTTPS transport, never guessed URLs or browser/page instructions."""

import asyncio
import hashlib
import logging
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

from src.application.services.web_fetch_policy import (
    WebFetchError,
    public_url,
    representation,
)
from src.infrastructure.web_evidence_source import ObservedWebSource
from src.application.ports.web_fetch import FetchedPage, PublicResponse
from src.application.ports.web_evidence import EvidenceResource, ObservedSource
from src.application.services.web_fetch_policy import header_map, public_address

logger = logging.getLogger(__name__)


def rfc_url(url, number, *, parent):
    """Accept only the configured RFC's exact HTTPS publisher landing or full-text path without credentials, query or fragment."""
    if type(number) is not int or not 1 <= number <= 99999:
        raise ValueError("publisher_scope")
    parsed = urlsplit(public_url(url).url)
    paths = (
        {f"/info/rfc{number}", f"/info/rfc{number}/"}
        if parent
        else {f"/rfc/rfc{number}.html"}
    )
    if (
        parsed.hostname not in {"www.rfc-editor.org", "rfc-editor.org"}
        or parsed.path not in paths
        or parsed.query
        or parsed.fragment
        or parsed.port not in (None, 443)
    ):
        raise ValueError("publisher_scope")
    return parsed.geturl()


class RFCLinkParser(HTMLParser):
    """Keep bounded literal anchors and reject base-URL or duplicate-attribute ambiguity before admitting a child."""

    def __init__(self, parent, number):
        """Bind an explicit publisher/number and initialize an empty bounded observation ledger."""
        super().__init__(convert_charrefs=True)
        self.parent, self.number = rfc_url(parent, number, parent=True), number
        self.links, self.elements = [], 0

    def handle_starttag(self, tag, attrs):
        """Record only present allowed hrefs and finite positions without executing or interpreting source instructions."""
        self.elements += 1
        if self.elements > 32768 or tag == "base":
            raise ValueError("publisher_html_ambiguity")
        if tag != "a":
            return
        hrefs = [value for key, value in attrs if key == "href"]
        if len(hrefs) > 1:
            raise ValueError("publisher_duplicate_href")
        if (
            not hrefs
            or type(hrefs[0]) is not str
            or not 0 < len(hrefs[0]) <= 2048
            or hrefs[0] != hrefs[0].strip()
        ):
            return
        try:
            child = rfc_url(urljoin(self.parent, hrefs[0]), self.number, parent=False)
        except (ValueError, WebFetchError):
            return
        if len(self.links) >= 32:
            raise ValueError("publisher_link_limit")
        self.links.append((hrefs[0], child, *self.getpos()))


def observed_link(parent, number, raw):
    """Bind a single unambiguous full-text target to complete original HTML bytes and actual anchor positions."""
    if type(raw) is not bytes or not 0 < len(raw) <= 1048576:
        raise ValueError("publisher_body_limit")
    parser = RFCLinkParser(parent, number)
    parser.feed(raw.decode("utf-8"))
    parser.close()
    children = {row[1] for row in parser.links}
    if len(children) != 1:
        raise ValueError("publisher_link_missing_or_ambiguous")
    logger.info("publisher_observed_anchor_verified anchors=%d", len(parser.links))
    return next(iter(children)), hashlib.sha256(raw).hexdigest(), tuple(parser.links)


async def parent_observation(client, requested, number):
    """Read only exact publisher hops and issue explicitly anchor-only parent evidence without relaxing generic full-text parsing."""
    target = rfc_url(requested, number, parent=True)
    resources, redirects, seen = [], [], set()
    try:
        async with asyncio.timeout(15):
            while True:
                if target in seen:
                    raise ValueError("publisher_redirect_cycle")
                seen.add(target)
                response = await client.get(target)
                if (
                    type(response) is not PublicResponse
                    or type(response.status) is not int
                    or type(response.body) is not bytes
                    or len(response.body) > 1048576
                ):
                    raise ValueError("publisher_response_invalid")
                public_address(response.pinned_address)
                headers = header_map(response.headers)
                resources.append(
                    EvidenceResource(
                        target,
                        "Document",
                        response.status,
                        len(response.body),
                        hashlib.sha256(response.body).hexdigest(),
                    )
                )
                if response.status in {301, 302, 303, 307, 308}:
                    if len(redirects) >= 3:
                        raise ValueError("publisher_redirect_limit")
                    location = headers.get("location")
                    if (
                        type(location) is not str
                        or not 0 < len(location) <= 2048
                        or location != location.strip()
                    ):
                        raise ValueError("publisher_redirect_invalid")
                    destination = rfc_url(
                        urljoin(target, location), number, parent=True
                    )
                    redirects.append((target, destination))
                    target = destination
                    continue
                if response.status != 200:
                    raise ValueError("publisher_http_status")
                media, encoding = representation(response.headers)
                if media != "text/html" or encoding not in {"utf-8", "utf8", "ascii"}:
                    raise ValueError("publisher_parent_representation")
                response.body.decode(encoding, errors="strict")
                if b"\x00" in response.body:
                    raise ValueError("publisher_parent_binary_data")
                child, sha, anchors = observed_link(target, number, response.body)
                text = "\n".join(row[0] for row in anchors)
                page = FetchedPage(
                    requested,
                    target,
                    tuple(redirects),
                    media,
                    None,
                    text,
                    sha,
                    hashlib.sha256(text.encode()).hexdigest(),
                    None,
                    extractor_version="publisher-anchors-utf8-v1",
                )
                logger.info(
                    "publisher_parent_anchor_only_evidence_complete resources=%d",
                    len(resources),
                )
                return ObservedSource(page, (), tuple(resources), 0), (
                    target,
                    child,
                    sha,
                    anchors,
                )
    except Exception as error:
        logger.warning(
            "publisher_parent_rejected kind=%s code=%s",
            type(error).__name__,
            getattr(error, "code", "publisher_parent_invalid"),
        )
        raise


class PublisherSource:
    """Delegate explicit sources unchanged and capture only configured RFC pages with strict publisher hop restrictions."""

    def __init__(self, number, client):
        """Bind a trusted RFC number and accepted public client without I/O or raw HTML persistence."""
        rfc_url(f"https://www.rfc-editor.org/info/rfc{number}/", number, parent=True)
        self.number, self.client, self.parent_binding = number, client, None
        logger.info("publisher_source_initialized")

    async def read(self, url, mode):
        """Read one explicit parent/child through unchanged evidence extraction and bind only its original parent response."""
        if mode != "static":
            raise ValueError("publisher_static_only")
        parsed = urlsplit(url)
        configured = parsed.hostname in {
            "www.rfc-editor.org",
            "rfc-editor.org",
        } and parsed.path in {
            f"/info/rfc{self.number}",
            f"/info/rfc{self.number}/",
            f"/rfc/rfc{self.number}.html",
        }
        if not configured:
            logger.info("publisher_explicit_source_delegated")
            return await ObservedWebSource(static_client=self.client).read(url, mode)
        parent = urlsplit(url).path.startswith("/info/")
        rfc_url(url, self.number, parent=parent)
        if parent:
            observation, binding = await parent_observation(
                self.client, url, self.number
            )
            self.parent_binding = binding
            return observation
        capture = PublisherCapture(self.client, self.number, parent)
        observation = await ObservedWebSource(static_client=capture).read(url, mode)
        if parent:
            if (
                capture.final != observation.page.final_url
                or hashlib.sha256(capture.raw or b"").hexdigest()
                != observation.page.body_sha256
            ):
                raise ValueError("publisher_parent_binding_changed")
            child, sha, anchors = observed_link(capture.final, self.number, capture.raw)
            self.parent_binding = (observation.page.final_url, child, sha, anchors)
        logger.info("publisher_original_source_read parent=%s", parent)
        return observation


class PublisherCapture:
    """Restrict every delegated redirect hop and temporarily retain only the single bounded parent body."""

    def __init__(self, client, number, parent):
        """Initialize one per-read capture without a shared response or cross-owner mutable body."""
        self.client, self.number, self.parent = client, number, parent
        self.raw, self.final = None, None

    async def get(self, url):
        """Validate publisher/path before the accepted transport performs DNS/TLS/body checks and retain the final parent only."""
        rfc_url(url, self.number, parent=self.parent)
        response = await self.client.get(url)
        if self.parent and response.status == 200:
            media, encoding = representation(response.headers)
            if media != "text/html" or encoding not in {"utf-8", "utf8"}:
                raise ValueError("publisher_parent_media_invalid")
            self.raw, self.final = response.body, url
        return response
