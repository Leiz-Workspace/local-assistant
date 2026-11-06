"""Exercise public HTTPS URL/address/header boundaries without opening a network connection."""

import logging

import pytest

from src.application.services.web_fetch_policy import (
    WebFetchError,
    header_map,
    public_address,
    public_answers,
    public_url,
    representation,
)

logger = logging.getLogger(__name__)


@pytest.mark.parametrize(
    "value,normalized,target",
    [
        ("https://docs.searxng.org", "https://docs.searxng.org/", b"/"),
        (
            "https://DOCS.searxng.org:443/dev?q=%2F",
            "https://docs.searxng.org/dev?q=%2F",
            b"/dev?q=%2F",
        ),
        ("https://example.org/path?", "https://example.org/path?", b"/path?"),
        (
            "https://example.org/%E1%BA%BF?x=1&x=2",
            "https://example.org/%E1%BA%BF?x=1&x=2",
            b"/%E1%BA%BF?x=1&x=2",
        ),
    ],
)
def test_explicit_uri_semantics_and_visible_normalization(value, normalized, target):
    """Preserve complete path/query bytes and explicit input while normalizing only URI-equivalent authority/root spelling."""
    parsed = public_url(value)
    assert (
        parsed.original == value
        and parsed.url == normalized
        and parsed.target == target
    )


@pytest.mark.parametrize(
    "value",
    [
        None,
        1,
        True,
        [],
        "",
        "http://example.org",
        "HTTPS://example.org",
        "file:///etc/passwd",
        "https://user:password@example.org/",
        "https://user@example.org",
        "https://example.org:80/",
        "https://example.org:0/",
        "https://example.org:444/",
        "https://example.org:443evil/",
        "https://127.0.0.1/",
        "https://[::1]/",
        "https://[2606:4700::1111]/",
        "https://2130706433/",
        "https://localhost/",
        "https://app.localhost/",
        "https://app.local/",
        "https://app.internal/",
        "https://app.test/",
        "https://app.onion/",
        "https://example.org./",
        "https://-bad.example.org",
        "https://bad_.example.org",
        "https://exámple.org/",
        "https://%65xample.org/",
        "https://example.org\\@127.0.0.1",
        "https://example.org/#fragment",
        "https://example.org/#",
        "https://example.org/\nsecret",
        " https://example.org/",
        "https://example.org/%00",
        "https://example.org/%0d%0a",
        "https://example.org/%7f",
        "https://example.org/%xy",
        "https://example.org/%",
        "https://example.org/" + "x" * 2048,
    ],
)
def test_ambiguous_or_private_uri_is_denied_before_lookup(value):
    """Deny unsupported URI authority/control/credential/length inputs without silently repairing them."""
    with pytest.raises(WebFetchError, match="web_fetch_url_invalid"):
        public_url(value)


@pytest.mark.parametrize(
    "value",
    [
        "8.8.8.8",
        "1.1.1.1",
        "104.21.1.2",
        "2606:4700:4700::1111",
        "2001:4860:4860::8888",
    ],
)
def test_canonical_public_addresses_are_eligible(value):
    """Allow ordinary public unicast addresses without treating DNS order as a retry list."""
    assert public_address(value) == value


@pytest.mark.parametrize(
    "value",
    [
        None,
        1,
        "",
        "localhost",
        "127.1",
        "0177.0.0.1",
        "0x7f000001",
        "0.0.0.0",
        "10.0.0.1",
        "100.64.0.1",
        "127.0.0.1",
        "169.254.169.254",
        "172.16.0.1",
        "192.168.1.1",
        "192.0.0.9",
        "192.0.2.1",
        "192.88.99.1",
        "198.18.0.1",
        "198.51.100.1",
        "203.0.113.1",
        "224.0.0.1",
        "255.255.255.255",
        "::",
        "::1",
        "::ffff:8.8.8.8",
        "::ffff:127.0.0.1",
        "64:ff9b::808:808",
        "64:ff9b:1::1",
        "fe80::1%eth0",
        "fe80::1",
        "fc00::1",
        "ff02::1",
        "2001::1",
        "2001:20::1",
        "2001:db8::1",
        "2002:7f00:1::1",
        "3ffe::1",
        "3fff::1",
        "5f00::1",
    ],
)
def test_special_mapped_tunnel_and_old_python_misclassified_addresses_are_denied(value):
    """Block internal/metadata/special families even when the installed old ipaddress flags call them global."""
    with pytest.raises(WebFetchError, match="web_fetch_address_denied"):
        public_address(value)


@pytest.mark.parametrize("values", [[], (), None, "8.8.8.8", ["8.8.8.8"] * 65])
def test_dns_answer_shape_and_complete_count_are_bounded(values):
    """Reject empty, wrong-shaped and oversized whole DNS answers rather than choosing a convenient prefix."""
    with pytest.raises(WebFetchError, match="web_fetch_dns_invalid"):
        public_answers(values)


@pytest.mark.parametrize(
    "values",
    [
        ["127.0.0.1", "8.8.8.8"],
        ["8.8.8.8", "127.0.0.1"],
        ["8.8.8.8"] * 63 + ["3fff::1"],
    ],
)
def test_unsafe_dns_tail_denies_the_entire_resolution(values):
    """Never skip an unsafe answer or connect before validating the whole returned set."""
    with pytest.raises(WebFetchError, match="web_fetch_address_denied"):
        public_answers(values)


def test_duplicate_public_answers_preserve_first_order_without_address_failover():
    """Deduplicate only after every raw answer has passed eligibility validation."""
    assert public_answers(["8.8.8.8", "1.1.1.1", "8.8.8.8"]) == ("8.8.8.8", "1.1.1.1")


@pytest.mark.parametrize(
    "headers,code",
    [
        ([], "web_fetch_header_limit"),
        ((("x", "a"),) * 129, "web_fetch_header_limit"),
        ((("x", "a" * 16384),), "web_fetch_header_limit"),
        (
            (("Content-Type", "text/html"), ("content-type", "text/plain")),
            "web_fetch_http_invalid",
        ),
        ((("content-length", "2"), ("Content-Length", "2")), "web_fetch_http_invalid"),
        ((("x", "private\nline"),), "web_fetch_http_invalid"),
        ((("x", "é"),), "web_fetch_http_invalid"),
    ],
)
def test_complete_header_limits_duplicates_and_control_values(headers, code):
    """Refuse complete-field overflow and ambiguous framing/representation headers without logging their text."""
    with pytest.raises(WebFetchError, match=code):
        header_map(headers)


@pytest.mark.parametrize(
    "media,encoding",
    [
        ("text/html", "utf-8"),
        ("text/plain; charset=us-ascii", "ascii"),
        ('text/html; charset="UTF-8"', "utf-8"),
    ],
)
def test_static_representation_has_explicit_supported_codec(media, encoding):
    """Choose only the advertised supported static type/codec without decompression or character guessing."""
    assert representation((("content-type", media),)) == (media.split(";")[0], encoding)


@pytest.mark.parametrize(
    "headers,code",
    [
        ((), "web_fetch_media_unsupported"),
        ((("content-type", "application/pdf"),), "web_fetch_media_unsupported"),
        (
            (("content-type", "text/html"), ("content-encoding", "gzip")),
            "web_fetch_encoding_unsupported",
        ),
        (
            (("content-type", "text/html; charset=latin1"),),
            "web_fetch_encoding_unsupported",
        ),
        (
            (("content-type", "text/html; charset=utf-8; charset=utf-8"),),
            "web_fetch_encoding_unsupported",
        ),
        ((("content-type", "text/html; charset"),), "web_fetch_encoding_unsupported"),
        (
            (("content-type", 'text/html; charset="utf-8'),),
            "web_fetch_encoding_unsupported",
        ),
        (
            (("content-type", "text/html"), ("content-length", "1048577")),
            "web_fetch_body_limit",
        ),
        (
            (("content-type", "text/html"), ("content-length", "-1")),
            "web_fetch_http_invalid",
        ),
        (
            (
                ("content-type", "text/html"),
                ("content-length", "2"),
                ("transfer-encoding", "chunked"),
            ),
            "web_fetch_http_invalid",
        ),
    ],
)
def test_unsupported_or_ambiguous_representation_fails(headers, code):
    """Refuse compressed, binary, oversized, ambiguous and unknown representations before body extraction."""
    with pytest.raises(WebFetchError, match=code):
        representation(headers)


def test_private_url_and_unknown_failure_values_are_not_logged(caplog):
    """Retain only finite validation metadata while exceptions hide unknown private values."""
    caplog.set_level(logging.DEBUG)
    value = "https://example.org/private-query-fixture?token=credential-fixture"
    public_url(value)
    assert str(WebFetchError(value)) == "web_fetch_internal"
    assert value not in caplog.text and "credential-fixture" not in caplog.text
