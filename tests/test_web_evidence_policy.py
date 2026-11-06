"""Verify explicit untrusted date semantics and every observed cache restriction without public I/O or model calls."""

import logging
from datetime import UTC, datetime

import pytest

from src.application.services.web_evidence_policy import (
    WebEvidenceError,
    cache_lifetime,
    date_claim,
)
from src.infrastructure.evidence_metadata import source_dates

logger = logging.getLogger(__name__)


@pytest.mark.parametrize(
    "headers,expected",
    [
        ((), 300),
        ((("cache-control", "public,max-age=600"),), 300),
        ((("cache-control", "max-age=120"), ("age", "10")), 110),
        ((("cache-control", "max-age=120"), ("age", "121")), 0),
        ((("age", "25"),), 275),
        ((("vary", "Accept-Encoding"),), 300),
        ((("cache-control", "max-age=60, must-revalidate"),), 60),
        ((("cache-control", "no-store"),), 0),
        ((("cache-control", "No-Cache"),), 0),
        ((("cache-control", 'private="field"'),), 0),
        ((("cache-control", "max-age=60"), ("Cache-Control", "no-store")), 0),
        ((("cache-control", "no-store,max-age=600"),), 0),
        ((("cache-control", "max-age=0"),), 0),
        ((("cache-control", "max-age=-1"),), 0),
        ((("cache-control", 'max-age="120"'),), 0),
        ((("cache-control", "max-age=120,max-age=120"),), 0),
        ((("cache-control", "max-age=NaN"),), 0),
        ((("cache-control", "max-age=99999999999"),), 0),
        ((("age", "-1"),), 0),
        ((("age", "2"), ("Age", "2")), 0),
        ((("age", "NaN"),), 0),
        ((("set-cookie", "private=discard"),), 0),
        ((("vary", "*"),), 0),
        ((("vary", "Accept-Encoding, Cookie"),), 0),
        ((("vary", "User-Agent"),), 0),
        ((("pragma", "no-cache"),), 0),
        ((("expires", "Wed, 21 Oct 2026 00:00:00 GMT"),), 0),
    ],
)
def test_complete_observed_cache_policy_never_extends_publisher_lifetime(
    headers, expected
):
    """Combine duplicate policy lines, reject unsupported negotiation and conservatively disable reuse on ambiguous freshness."""
    assert cache_lifetime(headers) == expected


@pytest.mark.parametrize(
    "raw,parsed,timezone",
    [
        ("2026-10-21", "2026-10-21", False),
        ("2026-10-21T12:34:56Z", "2026-10-21T12:34:56+00:00", True),
        ("2026-10-21T12:34:56+07:00", "2026-10-21T12:34:56+07:00", True),
        ("2026-10-21T12:34:56.123", "2026-10-21T12:34:56.123000", False),
        ("2026-02-30", None, False),
        ("2026-10-21T12:34:56+25:00", None, False),
        ("20261021", None, False),
        ("yesterday", None, False),
        (" 2026-10-21 ", None, False),
    ],
)
def test_explicit_iso_claim_does_not_invent_timezone_or_verify_date(
    raw, parsed, timezone
):
    """Preserve declaration bytes and distinguish parsed syntax from trusted publication history."""
    claim = date_claim("published", raw)
    assert (
        claim.raw_value,
        claim.parsed_iso,
        claim.timezone_present,
        claim.verified,
    ) == (raw, parsed, timezone, False)


@pytest.mark.parametrize("raw", ["", "x" * 129, "2026\n10", "\x00", "a\x7f"])
def test_date_claim_overflow_and_controls_are_rejected_without_clipping(raw):
    """Refuse malformed bounded date declarations instead of repairing or truncating their evidence."""
    with pytest.raises(WebEvidenceError, match="evidence_limit"):
        date_claim("published", raw)


def test_only_explicit_head_dates_are_retained_without_guessing_or_following_links():
    """Ignore prose, HTTP-equivalent date, body timestamps and JSON-LD while retaining distinct declared date kinds."""
    raw = b"""<html><head><title>Evidence</title>
<meta property="article:published_time" content="2026-10-20T10:00:00Z">
<meta property="article:modified_time" content="2026-10-21">
<meta name="date" content="unknown source date">
<meta http-equiv="date" content="2026-10-19">
<script type="application/ld+json">{"datePublished":"2026-10-18"}</script>
<link rel="canonical" href="https://127.0.0.1/private"></head><body><time datetime="2026-10-17">Yesterday</time></body></html>"""
    claims = source_dates(raw, "text/html")
    assert len(claims) == 3 and [row.kind for row in claims] == [
        "published",
        "modified",
        "unspecified",
    ]
    assert claims[2].parsed_iso is None and not any(row.verified for row in claims)
    assert source_dates(b"Published2026-10-21", "text/plain") == ()
    assert source_dates(b"<title>No date</title><p>2026-10-21</p>", "text/html") == ()
    logger.info("web_evidence_explicit_unknown_date_contract_verified")


def test_conflicting_date_claims_remain_separate_unverified_declarations():
    """Retain conflicting publisher values without selecting a convenient answer or treating duplicates as independent evidence."""
    raw = b'<head><meta property="article:published_time" content="2026-10-20"><meta property="article:published_time" content="2026-10-21"><meta property="article:published_time" content="2026-10-21"></head><body>x</body>'
    claims = source_dates(raw, "text/html")
    assert [row.raw_value for row in claims] == ["2026-10-20", "2026-10-21"]


@pytest.mark.parametrize(
    "raw",
    [
        b"x" * 1048577,
        b"<head>"
        + b'<meta name="date" content="2026-10-21">' * 32769
        + b"</head><body>x</body>",
        b"<head>"
        + b"".join(
            b'<meta name="date" content="2026-10-' + str(day).encode() + b'">'
            for day in range(10, 15)
        )
        + b"</head><body>x</body>",
    ],
)
def test_metadata_body_node_and_claim_limits_fail_without_partial_dates(raw):
    """Reject complete overbudget metadata instead of dropping overflow dates or returning a partial useful result."""
    with pytest.raises(WebEvidenceError, match="evidence_limit"):
        source_dates(raw, "text/html")


@pytest.mark.parametrize(
    "headers,expected",
    [
        ((("cache-control", "max-age=600"), ("age", "500")), 100),
        (
            (
                ("cache-control", "max-age=600"),
                ("date", "Wed, 21 Oct 2026 00:00:00 GMT"),
            ),
            0,
        ),
        (
            (
                ("cache-control", "max-age=600"),
                ("date", "Wed, 21 Oct 2026 00:09:00 GMT"),
            ),
            300,
        ),
        (
            (
                ("cache-control", "max-age=600"),
                ("date", "Wed, 21 Oct 2026 00:00:01 GMT"),
            ),
            1,
        ),
        (
            (
                ("cache-control", "max-age=120"),
                ("date", "Wed, 21 Oct 2026 00:09:00 GMT"),
                ("age", "80"),
            ),
            40,
        ),
        (
            (
                ("cache-control", "max-age=120"),
                ("date", "Wed, 21 Oct 2026 00:09:00 GMT"),
            ),
            60,
        ),
        ((("date", "malformed"),), 0),
        ((("date", "Wed, 21 Oct 2026 00:09:00"),), 0),
        (
            (
                ("date", "Wed, 21 Oct 2026 00:09:00 GMT"),
                ("Date", "Wed, 21 Oct 2026 00:09:00 GMT"),
            ),
            0,
        ),
    ],
)
def test_apparent_http_date_and_age_shorten_reuse_without_becoming_publication_claims(
    headers, expected
):
    """Account the greater actual source age before applying the local maximum rather than refreshing an already stale response."""
    assert (
        cache_lifetime(headers, now=datetime(2026, 10, 21, 0, 10, tzinfo=UTC))
        == expected
    )


def test_metadata_node_budget_is_independent_from_body_byte_budget():
    """Reject too many small meta nodes while complete original HTML remains below the oneMiB body cap."""
    raw = b"<html><head>" + b"<meta>" * 32769 + b"</head><body>x</body></html>"
    assert len(raw) < 1048576
    with pytest.raises(WebEvidenceError, match="evidence_limit"):
        source_dates(raw, "text/html")
