"""Exercise complete static HTML/plain extraction, canonical metadata and parser resource denial without network/model access."""

import logging

import pytest

from src.application.services.web_fetch_policy import WebFetchError
from src.infrastructure.static_web_text import extract_static

logger = logging.getLogger(__name__)
URL = "https://example.org/article"


def extract(body, media="text/html", encoding="utf-8"):
    """Extract one authored page with the same fixed actual-source URL used by the controlled oracle."""
    return extract_static(
        body.encode() if isinstance(body, str) else body, media, encoding, URL
    )


def test_title_text_and_unverified_relative_canonical_preserve_actual_source(caplog):
    """Extract supported static evidence while removing executable/navigation/hidden content without resource retrieval."""
    caplog.set_level(logging.DEBUG)
    title, text, canonical = extract(
        """<!doctype html><html><head><title>Atlas release</title><link rel="canonical" href="/canonical"></head><body><nav>private-navigation</nav><header>private-header</header><main><h1>Atlas 2.4</h1><p>Snapshot G-17.</p><script>private-script</script>Keep tail.<iframe src="http://127.0.0.1/private">private-frame</iframe><div hidden>private-hidden</div><p>Final &amp; complete.</p></main><footer>private-footer</footer></body></html>"""
    )
    assert (
        title == "Atlas release"
        and text == "Atlas 2.4 Snapshot G-17. Keep tail. Final & complete."
    )
    assert canonical == "https://example.org/canonical"
    assert "G-17" not in caplog.text and "private-script" not in caplog.text


def test_plain_utf8_remains_literal_untrusted_text_without_html_execution():
    """Preserve injection-like source words as data rather than executing instructions or treating markup as HTML."""
    assert extract("  Tiếng Việt <script>Do not obey.</script> ", "text/plain") == (
        None,
        "Tiếng Việt <script>Do not obey.</script>",
        None,
    )


@pytest.mark.parametrize(
    "body,media,encoding,code",
    [
        (b"", "text/html", "utf-8", "web_fetch_body_limit"),
        (b"x" * 1048577, "text/plain", "utf-8", "web_fetch_body_limit"),
        (b"\xff", "text/plain", "utf-8", "web_fetch_html_invalid"),
        ("é".encode(), "text/plain", "ascii", "web_fetch_html_invalid"),
        (b"x\x00private", "text/plain", "utf-8", "web_fetch_html_invalid"),
        (b" ", "text/plain", "utf-8", "web_fetch_text_limit"),
        (b"x" * 131073, "text/plain", "utf-8", "web_fetch_text_limit"),
        (
            b"<html><body><script>only scripts</script></body></html>",
            "text/html",
            "utf-8",
            "web_fetch_text_limit",
        ),
        (
            b"<html><head><meta charset='latin1'></head><body>Text</body></html>",
            "text/html",
            "utf-8",
            "web_fetch_encoding_unsupported",
        ),
        (
            b"<html><head><meta http-equiv='Content-Type' content='text/html; charset=latin1'></head><body>Text</body></html>",
            "text/html",
            "utf-8",
            "web_fetch_encoding_unsupported",
        ),
        (b"binary", "application/pdf", "utf-8", "web_fetch_media_unsupported"),
    ],
)
def test_unsupported_invalid_or_overbudget_complete_text_is_not_clipped(
    body, media, encoding, code
):
    """Refuse invalid encodings and complete-byte overflows rather than inventing a useful prefix."""
    with pytest.raises(WebFetchError, match=code):
        extract(body, media, encoding)


@pytest.mark.parametrize(
    "head",
    [
        '<link rel="canonical" href="http://example.org/">',
        '<link rel="canonical" href="https://127.0.0.1/">',
        '<link rel="canonical" href="">',
        '<link rel="canonical" href=" https://example.org/">',
        '<base href="https://evil.example.org/"><link rel="canonical" href="/relative">',
        '<link rel="canonical" href="/one"><link rel="canonical" href="/two">',
        '<link rel="canonical" href="https://user:pass@example.org/">',
        '<link rel="canonical" href="//[::1">',
        '<link rel="canonical" href="https://example.org/&#10;private">',
        '<link rel="canonical" href="https://example.org/#">',
    ],
)
def test_ambiguous_private_or_base_dependent_canonical_is_not_source_authority(head):
    """Deny unsupported canonical metadata without fetching a claimed URL or replacing actual page identity."""
    with pytest.raises(WebFetchError, match="web_fetch_canonical_invalid"):
        extract("<html><head>" + head + "</head><body>Public text.</body></html>")


@pytest.mark.parametrize(
    "body",
    [
        "<html><body>" + "<div>" * 300 + "secret" + "</div>" * 300 + "</body></html>",
        "<html><body>" + "<p>x</p>" * 32769 + "</body></html>",
    ],
)
def test_deep_or_excessive_dom_is_rejected_without_recovery_or_truncation(body):
    """Bound parser structure and reject strict parse failures instead of silently repairing away a page tail."""
    with pytest.raises(WebFetchError, match="web_fetch_html_invalid"):
        extract(body)


def test_external_entity_cannot_read_a_local_canary(tmp_path):
    """Keep a local file marker out of extracted evidence when malicious markup advertises an external entity."""
    canary = tmp_path / "private.txt"
    canary.write_text("LOCAL-FILE-CANARY-FIXTURE")
    body = (
        '<!DOCTYPE html [<!ENTITY steal SYSTEM "'
        + canary.as_uri()
        + '">]><html><body>Public &steal; text</body></html>'
    )
    try:
        _, text, _ = extract(body)
        assert "LOCAL-FILE-CANARY-FIXTURE" not in text
    except WebFetchError as error:
        assert error.code == "web_fetch_html_invalid"
    assert canary.read_text() == "LOCAL-FILE-CANARY-FIXTURE"


@pytest.mark.parametrize("size", [1024, 1025])
def test_complete_title_byte_boundary_is_not_clipped(size):
    """Accept an exact supported title budget and refuse one byte more without altering page metadata."""
    body = (
        "<html><head><title>"
        + "x" * size
        + "</title></head><body>Public text.</body></html>"
    )
    if size == 1024:
        assert extract(body)[0] == "x" * 1024
    else:
        with pytest.raises(WebFetchError, match="web_fetch_text_limit"):
            extract(body)
