"""Inspect bounded original HTML meta declarations without executing scripts or promoting source dates to verified facts."""

import logging

from lxml import etree

from src.application.services.web_evidence_policy import WebEvidenceError, date_claim
from src.infrastructure.static_web_text import DenyExternalResources

logger = logging.getLogger(__name__)


def source_dates(raw, media, encoding="utf-8"):
    """Read bounded explicit main-document meta dates without fetching canonical links, executing scripts or inferring prose dates."""
    if media != "text/html":
        return ()
    if type(raw) is not bytes or len(raw) > 1048576:
        raise WebEvidenceError("evidence_limit")
    parser = etree.HTMLPullParser(
        events=("start",),
        encoding="utf-8",
        no_network=True,
        recover=False,
        huge_tree=False,
    )
    parser.resolvers.add(DenyExternalResources())
    try:
        raw.decode(encoding, errors="strict")
        count = 0
        for offset in range(0, len(raw), 8192):
            parser.feed(raw[offset : offset + 8192])
            for _, _element in parser.read_events():
                count += 1
                if count > 32768:
                    raise WebEvidenceError("evidence_limit")
        root = parser.close()
        if root is None:
            raise WebEvidenceError("evidence_invalid")
        result = []
        for node in root.xpath("//head/meta"):
            value = node.get("property", "").lower()
            if value == "article:published_time":
                kind = "published"
            elif value == "article:modified_time":
                kind = "modified"
            elif node.get("name", "").lower() == "date":
                kind = "unspecified"
            else:
                continue
            claim = date_claim(kind, node.get("content", ""))
            if claim not in result:
                result.append(claim)
            if len(result) > 4:
                raise WebEvidenceError("evidence_limit")
        logger.info("web_evidence_source_dates_observed count=%d", len(result))
        return tuple(result)
    except (UnicodeError, etree.XMLSyntaxError, ValueError):
        raise WebEvidenceError("evidence_invalid") from None
