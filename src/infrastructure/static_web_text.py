"""Extract bounded static UTF-8 web text without executing or retrieving page-controlled resources."""

import logging
from urllib.parse import urljoin

from lxml import etree

from src.application.services.web_fetch_policy import (
    WebFetchError,
    public_url,
    representation,
)

logger = logging.getLogger(__name__)
OMITTED = frozenset(
    {
        "script",
        "style",
        "noscript",
        "template",
        "iframe",
        "frame",
        "frameset",
        "object",
        "embed",
        "svg",
        "canvas",
        "form",
        "nav",
        "header",
        "footer",
    }
)


class DenyExternalResources(etree.Resolver):
    """Reject any parser attempt to resolve a local file, external entity or network resource."""

    def resolve(self, url, public_id, context):
        """Stop resource resolution without exposing the supplied location in diagnostics."""
        logger.info("web_fetch_external_parser_resource_denied")
        raise WebFetchError("web_fetch_html_invalid")


def bounded_text(value, maximum):
    """Retain complete normalized static text within its encoded budget, never returning a clipped prefix."""
    text = " ".join(value.split())
    if not text or len(text.encode("utf-8")) > maximum:
        raise WebFetchError("web_fetch_text_limit")
    return text


def canonical_claim(root, final_url):
    """Recognize at most one unverified canonical claim without fetching it or replacing actual source identity."""
    rows = root.xpath("//link[@href]")
    candidates = []
    for node in rows:
        if "canonical" not in node.get("rel", "").lower().split():
            continue
        value = node.get("href")
        if (
            not value
            or len(value.encode("utf-8")) > 2048
            or any(ord(char) < 33 or ord(char) > 126 for char in value)
            or "#" in value
        ):
            raise WebFetchError("web_fetch_canonical_invalid")
        if root.xpath("//base[@href]") and not value.startswith("https://"):
            raise WebFetchError("web_fetch_canonical_invalid")
        try:
            candidate = public_url(urljoin(final_url, value)).url
        except (WebFetchError, ValueError):
            raise WebFetchError("web_fetch_canonical_invalid") from None
        candidates.append(candidate)
        if len(candidates) > 1:
            raise WebFetchError("web_fetch_canonical_invalid")
    logger.info("web_fetch_canonical_metadata_checked present=%s", bool(candidates))
    return candidates[0] if candidates else None


def extract_static(raw, media, encoding, final_url):
    """Return title/text/unverified canonical metadata from complete bounded static bytes without browser semantics."""
    if type(raw) is not bytes or not 1 <= len(raw) <= 1048576:
        raise WebFetchError("web_fetch_body_limit")
    try:
        decoded = raw.decode(encoding, errors="strict")
        if "\x00" in decoded:
            raise WebFetchError("web_fetch_html_invalid")
        if media == "text/plain":
            text = bounded_text(decoded, 131072)
            logger.info("web_fetch_plain_text_extracted bytes=%d", len(text.encode()))
            return None, text, None
        if media != "text/html":
            raise WebFetchError("web_fetch_media_unsupported")
        parser = etree.HTMLPullParser(
            events=("start",),
            encoding="utf-8",
            no_network=True,
            recover=False,
            huge_tree=False,
            remove_comments=True,
            remove_pis=True,
        )
        parser.resolvers.add(DenyExternalResources())
        nodes = 0
        for offset in range(0, len(raw), 8192):
            parser.feed(raw[offset : offset + 8192])
            for _, _element in parser.read_events():
                nodes += 1
                if nodes > 32768:
                    raise WebFetchError("web_fetch_html_invalid")
        root = parser.close()
        if root is None:
            raise WebFetchError("web_fetch_html_invalid")
        for meta in root.xpath("//meta"):
            charset = meta.get("charset")
            if meta.get("http-equiv", "").lower() == "content-type":
                representation((("content-type", meta.get("content", "")),))
            if charset is not None and charset.lower() not in {
                "utf-8",
                "utf8",
                "ascii",
                "us-ascii",
            }:
                raise WebFetchError("web_fetch_encoding_unsupported")
        canonical = canonical_claim(root, final_url)
        titles = root.xpath("//head/title")
        title = bounded_text(" ".join(titles[0].itertext()), 1024) if titles else None
        for node in reversed(list(root.iter())):
            if not isinstance(node.tag, str):
                continue
            if (
                node.tag.lower() in OMITTED
                or "hidden" in node.attrib
                or node.get("aria-hidden", "").lower() == "true"
            ):
                parent = node.getparent()
                if parent is not None:
                    tail = node.tail or ""
                    previous = node.getprevious()
                    if previous is not None:
                        previous.tail = (previous.tail or "") + tail
                    else:
                        parent.text = (parent.text or "") + tail
                    parent.remove(node)
        bodies = root.xpath("//body")
        if len(bodies) != 1:
            raise WebFetchError("web_fetch_html_invalid")
        text = bounded_text(" ".join(bodies[0].itertext()), 131072)
        logger.info(
            "web_fetch_html_text_extracted nodes=%d bytes=%d", nodes, len(text.encode())
        )
        return title, text, canonical
    except (UnicodeError, etree.XMLSyntaxError, ValueError):
        raise WebFetchError("web_fetch_html_invalid") from None
