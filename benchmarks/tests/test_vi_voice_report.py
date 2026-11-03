"""Check local listening artifacts preserve native audio and exclude capture, uploads and external resources."""

import base64
from html.parser import HTMLParser

import pytest

from benchmarks.scripts.vi_voice_report import render_review


class ReviewParser(HTMLParser):
    """Collect actual audio elements and executable or external capabilities from the rendered document."""

    def __init__(self):
        """Initialize observed media and forbidden tag collections."""
        super().__init__()
        self.audio, self.forbidden = [], []

    def handle_starttag(self, tag, attrs):
        """Record media attributes and reject script/upload/embed controls."""
        values = dict(attrs)
        if tag == "audio":
            self.audio.append(values)
        if tag in {"script", "iframe", "form", "input", "object", "embed"}:
            self.forbidden.append(tag)


def items():
    """Create24 harmless independent binary media fixtures with hostile display text."""
    return [
        dict(
            id=f"clip-{i}",
            text="<script>private()</script>",
            voice='"quoted"',
            sample_rate=48000,
            sha256="a" * 64,
            wav=b"fixture" + bytes([i]),
        )
        for i in range(24)
    ]


def test_review_contains_exact_unmodified_audio_and_no_remote_capabilities():
    """Ensure every embedded payload decodes to original bytes while hostile text remains inert."""
    data = items()
    page = render_review(data)
    parser = ReviewParser()
    parser.feed(page)
    assert len(parser.audio) == 24 and not parser.forbidden
    assert "<script>private()" not in page
    assert "https://" not in page and "http://" not in page
    assert "media-src data:" in page and "form-action 'none'" in page
    for observed, original in zip(parser.audio, data, strict=True):
        assert observed["preload"] == "none" and "autoplay" not in observed
        assert base64.b64decode(observed["src"].split(",", 1)[1]) == original["wav"]


@pytest.mark.parametrize("count", [0, 23, 25])
def test_review_rejects_missing_or_extra_clips(count):
    """Refuse incomplete or expanded panels instead of presenting them as a complete24-item review."""
    data = items()
    if count == 25:
        data.append(data[0] | dict(id="extra"))
    else:
        data = data[:count]
    with pytest.raises(ValueError, match="coverage"):
        render_review(data)


def test_review_rejects_duplicate_clip_ids():
    """Keep stable clip identity unique across the entire listening panel."""
    data = items()
    data[-1] = data[0]
    with pytest.raises(ValueError):
        render_review(data)
