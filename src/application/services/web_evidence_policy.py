"""Enforce bounded source-date claims, publisher cache directives and immutable snapshot serialization without content logging."""

import json
import logging
import math
import re
from dataclasses import asdict
from datetime import UTC, date, datetime
from email.utils import parsedate_to_datetime
from uuid import UUID

from src.application.ports.web_evidence import SourceDateClaim
from src.application.services.web_fetch_policy import header_map

logger = logging.getLogger(__name__)
ERRORS = frozenset(
    {
        "evidence_invalid",
        "evidence_busy",
        "evidence_closed",
        "evidence_clock_invalid",
        "evidence_source_failed",
        "evidence_integrity",
        "evidence_expired",
        "evidence_limit",
        "evidence_internal",
    }
)


class WebEvidenceError(Exception):
    """Expose only a finite failure without source URLs, queries, dates, raw upstream errors or page text."""

    def __init__(self, code):
        """Retain only the fixed local evidence failure vocabulary."""
        self.code = (
            code if type(code) is str and code in ERRORS else "evidence_internal"
        )
        super().__init__(self.code)


def serializable(value):
    """Convert immutable dataclass metadata into bounded deterministic JSON values for integrity and accounting."""
    if type(value) in {UUID, datetime}:
        return value.isoformat() if type(value) is datetime else str(value)
    raise TypeError("unsupported_evidence_value")


def snapshot_bytes(snapshot, *, proof=True, text=True):
    """Serialize every snapshot field deterministically without normalizing source text or logging private payload bytes."""
    value = asdict(snapshot)
    if not proof:
        value["proof"] = ""
    if not text:
        value.pop("text")
    raw = json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
        default=serializable,
    ).encode()
    if len(raw) > 262144:
        raise WebEvidenceError("evidence_limit")
    return raw


def cache_lifetime(headers, *, now=None):
    """Return at most300seconds of local reuse after all observed publisher restrictions and source Age are considered."""
    header_map(headers)
    directives, ages, dates = [], [], []
    for name, value in headers:
        key = name.lower()
        if key == "set-cookie":
            return 0
        if key == "pragma" and "no-cache" in {
            part.strip().lower() for part in value.split(",")
        }:
            return 0
        if key == "vary" and any(
            part.strip().lower() != "accept-encoding" for part in value.split(",")
        ):
            return 0
        if key == "cache-control":
            directives.extend(part.strip().lower() for part in value.split(","))
        if key == "age":
            ages.append(value)
        if key == "date":
            dates.append(value)
        if key == "expires":
            return 0
    if any(
        part.partition("=")[0].strip() in {"no-store", "no-cache", "private"}
        for part in directives
    ):
        return 0
    maxima = [
        part.partition("=")[2].strip()
        for part in directives
        if part.partition("=")[0].strip() == "max-age"
    ]
    if len(maxima) > 1 or len(ages) > 1 or len(dates) > 1:
        return 0
    if any(not re.fullmatch(r"[0-9]{1,10}", value) for value in maxima + ages):
        return 0
    ttl = int(maxima[0]) if maxima else 300
    age = int(ages[0]) if ages else 0
    if dates:
        current = now if now is not None else datetime.now(UTC)
        if (
            type(current) is not datetime
            or current.tzinfo is None
            or current.utcoffset() is None
        ):
            raise WebEvidenceError("evidence_clock_invalid")
        try:
            declared = parsedate_to_datetime(dates[0])
            if declared.tzinfo is None or declared.utcoffset() is None:
                return 0
            age = max(age, max(0, math.ceil((current - declared).total_seconds())))
        except (ValueError, TypeError, OverflowError):
            return 0
    logger.info("web_evidence_cache_policy_observed")
    return max(0, min(300, ttl - age))


def date_claim(kind, raw):
    """Parse only bounded explicit ISO declarations without inventing a timezone or verifying their truth."""
    if (
        not raw
        or len(raw.encode()) > 128
        or any(ord(char) < 32 or ord(char) == 127 for char in raw)
    ):
        raise WebEvidenceError("evidence_limit")
    parsed, timezone = None, False
    try:
        if re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", raw):
            parsed = date.fromisoformat(raw).isoformat()
        elif re.fullmatch(
            r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,6})?(?:Z|[+-][0-9]{2}:[0-9]{2})?",
            raw,
        ):
            value = datetime.fromisoformat(raw)
            parsed, timezone = value.isoformat(), value.tzinfo is not None
    except ValueError:
        logger.info("web_evidence_unparseable_date_claim")
    return SourceDateClaim(kind, raw, parsed, timezone)
