"""Verify paired local review coverage, escaping, unchanged media bytes and explicit missing results."""

import base64
from html.parser import HTMLParser

import pytest

from benchmarks.scripts.vi_speech_quality import packet_rows
from benchmarks.scripts.vi_speech_review import render_page


class MediaParser(HTMLParser):
    """Collect media and forbidden capabilities from actual rendered markup."""

    def __init__(self):
        """Initialize observed local media and forbidden element lists."""
        super().__init__()
        self.media, self.forbidden = [], []

    def handle_starttag(self, tag, attrs):
        """Record players and reject executable, upload or remote embedding elements."""
        if tag == "audio":
            self.media.append(dict(attrs))
        if tag in {"script", "iframe", "form", "input", "object", "embed"}:
            self.forbidden.append(tag)


def test_full_paired_page_embeds_exact_bytes_and_no_capture_or_remote_code():
    """Retain all48 supplied native payloads without autoplay, script execution or remote dependencies."""
    rows = packet_rows()
    rows[0]["render"]["source_text"] = "<script>bad()</script>"
    audio = {row["id"]: b"fixture:" + row["id"].encode() for row in rows}
    page = render_page(rows, audio)
    parser = MediaParser()
    parser.feed(page)
    assert len(parser.media) == 48 and parser.forbidden == []
    assert "<script>bad()" not in page and "https://" not in page
    decoded = {base64.b64decode(item["src"].split(",", 1)[1]) for item in parser.media}
    assert decoded == set(audio.values())
    assert all(
        "autoplay" not in item and item["preload"] == "none" for item in parser.media
    )


def test_partial_page_preserves_missing_slots_without_inventing_audio():
    """Display unattempted outcomes rather than dropping them from the panel denominator."""
    rows = packet_rows()
    page = render_page(rows, {rows[0]["id"]: b"first"})
    parser = MediaParser()
    parser.feed(page)
    assert (
        len(parser.media) == 1
        and page.count("Chưa có clip hoàn chỉnh: UNATTEMPTED") == 47
    )


def test_paired_page_rejects_bad_coverage():
    """Reject missing, duplicate or unexpected variant identities."""
    rows = packet_rows()
    with pytest.raises(ValueError):
        render_page(rows[:-1], {})
    rows[-1] = rows[0]
    with pytest.raises(ValueError):
        render_page(rows, {})
