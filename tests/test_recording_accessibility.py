"""Verify the optional recorder's documented accessible semantics without changing audio lifecycle or API security contracts."""

from html.parser import HTMLParser
from pathlib import Path


class Elements(HTMLParser):
    """Collect declared element attributes without executing scripts or accepting untrusted markup."""

    def __init__(self):
        """Create an isolated HTML attribute inventory for the committed static page."""
        super().__init__()
        self.elements = []

    def handle_starttag(self, tag, attrs):
        """Retain only exact static tag/attribute pairs for landmark and accessible-name assertions."""
        self.elements.append((tag, dict(attrs)))


def test_landmarks_controls_live_state_and_preview_have_explicit_accessible_names():
    """Keep keyboard-native controls, stable descriptive references and named ephemeral audio without hidden upload forms."""
    parsed = Elements()
    parsed.feed(Path("apps/voice/static/index.html").read_text())
    ids = {attrs["id"]: (tag, attrs) for tag, attrs in parsed.elements if "id" in attrs}
    main = next(attrs for tag, attrs in parsed.elements if tag == "main")
    assert main["aria-labelledby"] == "page-title" and ids["page-title"][0] == "h1"
    assert (
        ids["status"][1]["aria-live"] == "polite"
        and ids["status"][1]["aria-atomic"] == "true"
    )
    assert ids["preview"][1]["aria-label"] == "Bản ghi âm vừa tạo"
    for identifier in ("start", "stop", "cancel"):
        tag, attrs = ids[identifier]
        assert (
            tag == "button"
            and attrs["type"] == "button"
            and attrs["aria-describedby"] in ids
        )
    assert all(tag not in {"form", "input", "iframe"} for tag, _ in parsed.elements)
