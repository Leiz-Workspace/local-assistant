"""Verify visible Unicode normalization and finite principal/global search quotas without network calls."""

import logging
from uuid import uuid4

import pytest

from src.application.services.web_search_policy import (
    WebSearchError,
    WebSearchQuota,
    normalize_query,
)

logger = logging.getLogger(__name__)


class FakeClock:
    """Expose deterministic monotonic observations without sleeping or modifying a runtime clock."""

    def __init__(self, value=0.0):
        """Bind one explicit test time value."""
        self.value = value

    def __call__(self):
        """Return the current controlled time without side effects."""
        return self.value


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("  SearXNG   JSON  ", "SearXNG JSON"),
        ("Tiếng\u00a0 Việt", "Tiếng Việt"),
        ("Cafe\u0301 search", "Café search"),
        ('site:docs.searxng.org "JSON format"', 'site:docs.searxng.org "JSON format"'),
        ("https://example.org/a?b=1", "https://example.org/a?b=1"),
        ("Xin chào!", "Xin chào!"),
    ],
)
def test_only_visible_nfc_whitespace_transforms(raw, expected, caplog):
    """Preserve case, operators and punctuation while omitting query text from audit logs."""
    caplog.set_level(logging.INFO)
    assert normalize_query(raw) == expected
    assert raw not in caplog.text and expected not in caplog.text


@pytest.mark.parametrize(
    "raw",
    [
        None,
        1,
        True,
        "",
        "  ",
        "a\nvalue",
        "a\tvalue",
        "\ud800",
        "x" * 513,
        "ế" * 171,
        " " * 513 + "a",
    ],
)
def test_original_query_budgets_cannot_be_bypassed_by_normalization(raw):
    """Reject invalid original bytes before whitespace collapse could turn an excessive request into an admitted query."""
    with pytest.raises(WebSearchError, match="web_search_query_invalid"):
        normalize_query(raw)


@pytest.mark.parametrize(
    "query",
    [
        "!bing search",
        "search !images",
        "!!wiki search",
        "search !!",
        ":en search",
        "search :fr",
        " \u00a0!brave search",
    ],
)
def test_engine_language_and_external_redirect_tokens_are_not_query_authority(query):
    """Reject SearXNG selector tokens before any provider request can override fixed server policy."""
    with pytest.raises(WebSearchError, match="web_search_selector_forbidden"):
        normalize_query(query)


def test_principal_quota_does_not_charge_denials_or_block_another_owner():
    """Keep four admitted attempts per principal with no denied-attempt increment or cross-owner result state."""
    quota = WebSearchQuota(clock=FakeClock())
    first, second = uuid4(), uuid4()
    for _ in range(4):
        quota.charge(first)
    with pytest.raises(WebSearchError) as captured:
        quota.charge(first)
    assert (
        captured.value.code == "web_search_rate_limited"
        and captured.value.retry_after == 60
    )
    assert quota.total == 4 and quota.owners[first] == 4
    quota.charge(second)
    assert quota.total == 5 and quota.owners[second] == 1


def test_global_capacity_bounds_owner_map_and_known_window_reset():
    """Bound all counters to16 identities and reset only on an observed monotonic window boundary."""
    clock = FakeClock()
    quota = WebSearchQuota(clock=clock)
    for _ in range(16):
        quota.charge(uuid4())
    with pytest.raises(WebSearchError):
        quota.charge(uuid4())
    assert quota.total == len(quota.owners) == 16
    clock.value = 59.99
    with pytest.raises(WebSearchError) as captured:
        quota.charge(uuid4())
    assert captured.value.retry_after == 1
    clock.value = 60
    owner = uuid4()
    quota.charge(owner)
    assert quota.total == 1 and quota.owners == {owner: 1}


def test_clock_regression_cannot_refund_an_admitted_attempt():
    """Keep charged quota when a trusted clock unexpectedly moves backwards instead of resetting counters."""
    clock = FakeClock(10)
    quota = WebSearchQuota(clock=clock)
    owner = uuid4()
    for _ in range(4):
        quota.charge(owner)
    clock.value = -1
    with pytest.raises(WebSearchError) as captured:
        quota.charge(owner)
    assert captured.value.retry_after == 60 and quota.total == 4


@pytest.mark.parametrize("value", [float("nan"), float("inf"), True, "0"])
def test_invalid_trusted_clock_fails_closed(value):
    """Deny invalid clock values rather than disabling or widening quota enforcement."""
    with pytest.raises(WebSearchError, match="web_search_unavailable"):
        WebSearchQuota(clock=FakeClock(value))


@pytest.mark.parametrize("owner", [None, "forged-owner", 1])
def test_only_trusted_principal_uuid_can_be_charged(owner):
    """Refuse body-like owner identifiers without allocating a counter entry."""
    quota = WebSearchQuota(clock=FakeClock())
    with pytest.raises(WebSearchError, match="web_search_owner_invalid"):
        quota.charge(owner)
    assert quota.total == 0 and quota.owners == {}
