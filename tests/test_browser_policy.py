"""Verify read-only browser URI/request/media/CSP/native-snapshot boundaries without starting a browser or network client."""

import logging

import pytest

from src.application.services.browser_policy import (
    BrowserError,
    browser_url,
    fulfillment_headers,
    request_policy,
    resource_representation,
    snapshot_text,
)

logger = logging.getLogger(__name__)
URL = "https://example.org/page"


def request(**changes):
    """Create one explicit main-frame GET with optional adversarial CDP field mutations."""
    return dict(
        frameId="frame",
        resourceType="Document",
        request=dict(url=URL, method="GET"),
        **changes,
    )


def snapshot(text="Dynamic G-17.", **changes):
    """Create native-like layout evidence with a separate document URL/title string table."""
    document = dict(documentURL=0, title=1, layout=dict(text=[2]), **changes)
    return dict(strings=[URL, "Atlas", text], documents=[document])


def test_explicit_navigation_and_script_get_do_not_accept_browser_authority():
    """Admit only source-matching main navigation and finite same-frame text resource classes."""
    assert request_policy(request(), "frame", URL) == (URL, "Document")
    value = request()
    value["resourceType"] = "Script"
    value["request"]["url"] = "https://cdn.example.org/app.js"
    value["request"]["headers"] = {
        "Authorization": "private-token-fixture",
        "Cookie": "private-cookie",
    }
    assert request_policy(value, "frame", URL) == (
        "https://cdn.example.org/app.js",
        "Script",
    )


@pytest.mark.parametrize(
    "method", ["POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS", "get", None]
)
def test_write_or_unsupported_methods_are_denied_before_host_fetch(method):
    """Reject every method beyond the fixed GET broker without translating a request into another method."""
    value = request()
    value["request"]["method"] = method
    with pytest.raises(BrowserError, match="browser_method_denied"):
        request_policy(value, "frame", URL)


@pytest.mark.parametrize(
    "mutation,code",
    [
        (dict(frameId="iframe"), "browser_navigation_denied"),
        (dict(resourceType="WebSocket"), "browser_resource_denied"),
        (dict(resourceType=[]), "browser_navigation_denied"),
        (
            dict(request=dict(url="https://127.0.0.1/", method="GET")),
            "browser_url_denied",
        ),
        (
            dict(request=dict(url="http://example.org/", method="GET")),
            "browser_url_denied",
        ),
        (
            dict(request=dict(url="https://example.org/other", method="GET")),
            "browser_navigation_denied",
        ),
        (
            dict(request=dict(url=URL, method="GET", postData="private-body")),
            "browser_method_denied",
        ),
    ],
)
def test_frames_new_documents_schemes_and_body_authority_are_denied(mutation, code):
    """Deny iframe/source drift/private destinations and hidden request bodies before a host resource call."""
    value = request()
    value.update(mutation)
    with pytest.raises(BrowserError, match=code):
        request_policy(value, "frame", URL)


@pytest.mark.parametrize(
    "kind", ["Image", "Font", "Media", "Other", "Manifest", "Prefetch"]
)
def test_decorative_classes_are_denied_without_host_lookup(kind):
    """Return only a no-fetch decision for unsupported nontext resources."""
    value = request()
    value["resourceType"] = kind
    assert request_policy(value, "frame", URL) is None


@pytest.mark.parametrize(
    "value",
    [
        "https://127.0.0.1/",
        "file:///etc/passwd",
        "http://example.org/",
        "https://user:password@example.org/",
        None,
    ],
)
def test_browser_uri_reuses_accepted_public_policy(value):
    """Reject unsupported browser destinations without loading a profile, credential or resolver."""
    with pytest.raises(BrowserError, match="browser_url_denied"):
        browser_url(value)


@pytest.mark.parametrize(
    "kind,media",
    [
        ("Document", "text/html"),
        ("Script", "application/javascript"),
        ("Stylesheet", "text/css"),
        ("XHR", "application/json"),
        ("Fetch", "text/plain"),
    ],
)
def test_media_allowlist_preserves_type_and_supported_codec(kind, media):
    """Recognize the finite text resource types while retaining original bytes and UTF-8 codec policy."""
    assert resource_representation(
        (("content-type", media + "; charset=utf-8"),), kind
    ) == (media, "utf-8")


@pytest.mark.parametrize(
    "headers,kind,code",
    [
        (
            (("content-type", "application/octet-stream"),),
            "Document",
            "browser_resource_denied",
        ),
        (
            (
                ("content-type", "text/html"),
                ("content-disposition", "attachment; filename=private.zip"),
            ),
            "Document",
            "browser_download_denied",
        ),
        (
            (("content-type", "text/javascript"), ("content-encoding", "gzip")),
            "Script",
            "browser_resource_denied",
        ),
        (
            (("content-type", "text/javascript; charset=latin1"),),
            "Script",
            "browser_resource_denied",
        ),
        (
            (("content-type", "text/css"), ("content-length", "1048577")),
            "Stylesheet",
            "browser_resource_denied",
        ),
        (
            (("content-type", "text/html"), ("content-type", "text/plain")),
            "Document",
            "browser_resource_denied",
        ),
    ],
)
def test_download_binary_encoding_and_overbudget_headers_are_not_fulfilled(
    headers, kind, code
):
    """Fail closed before a resource body becomes a browser response or a file download."""
    with pytest.raises(BrowserError, match=code):
        resource_representation(headers, kind)


def test_fulfillment_drops_cookie_auth_framing_and_keeps_stricter_csp():
    """Supply fixed complete response metadata and layered CSP without ambient secret-bearing headers."""
    rows = fulfillment_headers(
        (
            ("Set-Cookie", "private-cookie"),
            ("Authorization", "private-token"),
            ("Transfer-Encoding", "chunked"),
            ("Content-Security-Policy", "script-src 'none'"),
        ),
        "text/html",
        32,
    )
    assert all(
        row["name"].lower() not in {"set-cookie", "authorization", "transfer-encoding"}
        for row in rows
    )
    policies = [
        row["value"] for row in rows if row["name"] == "Content-Security-Policy"
    ]
    assert len(policies) == 2 and policies[-1] == "script-src 'none'"
    assert all(
        term in policies[0]
        for term in [
            "worker-src 'none'",
            "frame-src 'none'",
            "form-action 'none'",
            "connect-src https:",
        ]
    )


def test_native_layout_observation_binds_source_without_page_script_evaluation():
    """Extract native title/layout text from matching actual source metadata without arbitrary JavaScript."""
    assert snapshot_text(snapshot(), URL) == (URL, "Atlas", "Dynamic G-17.")


@pytest.mark.parametrize(
    "payload",
    [
        {},
        dict(strings=[], documents=[]),
        dict(strings=[URL, "Atlas", 1], documents=[dict()]),
        dict(
            strings=[URL, "Atlas", "x"],
            documents=[dict(documentURL=-1, title=1, layout=dict(text=[2]))],
        ),
        dict(
            strings=[URL, "Atlas", "x"],
            documents=[dict(documentURL=True, title=1, layout=dict(text=[2]))],
        ),
        dict(
            strings=[URL, "Atlas", "x"],
            documents=[dict(documentURL=0, title=1, layout=dict(text=[-2]))],
        ),
    ],
)
def test_malformed_native_snapshot_indices_and_shapes_are_denied(payload):
    """Reject malformed or negative/bool indices rather than selecting a convenient Python list element."""
    with pytest.raises(BrowserError, match="browser_protocol_invalid"):
        snapshot_text(payload, URL)


def test_optional_native_empty_string_sentinel_never_selects_last_string():
    """Accept native empty text/title sentinels while retaining required document provenance."""
    payload = snapshot()
    payload["strings"].append("Never select this last table entry.")
    payload["documents"][0]["title"] = -1
    payload["documents"][0]["layout"]["text"] = [-1, 2, -1]
    assert snapshot_text(payload, URL) == (URL, None, "Dynamic G-17.")


@pytest.mark.parametrize("text", ["", "x" * 131073])
def test_complete_rendered_text_is_not_clipped(text):
    """Refuse empty or overbudget native layout text without returning a partial useful page."""
    with pytest.raises(BrowserError, match="browser_text_limit"):
        snapshot_text(snapshot(text), URL)


def test_history_url_changes_do_not_impersonate_fetched_source(caplog):
    """Reject source drift and keep private URLs/error diagnostics out of metadata logs."""
    caplog.set_level(logging.DEBUG)
    value = snapshot()
    value["strings"][0] = "https://example.org/private?token=fixture"
    with pytest.raises(BrowserError, match="browser_source_drift"):
        snapshot_text(value, URL)
    assert (
        "private?token" not in caplog.text
        and str(BrowserError("private-secret")) == "browser_internal"
    )
