"""Enforce finite read-only browser request/media/CSP/snapshot contracts without granting page authority."""

import logging

from src.application.services.web_fetch_policy import (
    WebFetchError,
    header_map,
    public_url,
    representation,
)

logger = logging.getLogger(__name__)
ERROR_CODES = frozenset(
    {
        "browser_url_denied",
        "browser_method_denied",
        "browser_navigation_denied",
        "browser_download_denied",
        "browser_resource_denied",
        "browser_resource_failed",
        "browser_resource_limit",
        "browser_busy",
        "browser_closed",
        "browser_protocol_invalid",
        "browser_event_limit",
        "browser_text_limit",
        "browser_timeout",
        "browser_runtime_unavailable",
        "browser_cleanup_uncertain",
        "browser_source_drift",
        "browser_internal",
    }
)
ALLOWED_KINDS = frozenset({"Document", "Script", "Stylesheet", "XHR", "Fetch"})
DECORATIVE_KINDS = frozenset(
    {"Image", "Media", "Font", "Other", "Manifest", "Prefetch"}
)
MEDIA = {
    "Document": frozenset({"text/html", "text/plain"}),
    "Script": frozenset(
        {
            "text/javascript",
            "application/javascript",
            "application/ecmascript",
            "text/ecmascript",
        }
    ),
    "Stylesheet": frozenset({"text/css"}),
    "XHR": frozenset({"application/json", "text/plain", "text/html"}),
    "Fetch": frozenset({"application/json", "text/plain", "text/html"}),
}
CSP = (
    "default-src https: data:; script-src https: 'unsafe-inline' 'unsafe-eval'; "
    "style-src https: 'unsafe-inline'; connect-src https:; img-src 'none'; font-src 'none'; "
    "media-src 'none'; frame-src 'none'; child-src 'none'; worker-src 'none'; "
    "object-src 'none'; form-action 'none'; base-uri 'none'"
)


class BrowserError(Exception):
    """Expose a finite browser failure without raw page URLs, headers, stderr, content or native exception text."""

    def __init__(self, code):
        """Retain only known fixed error identifiers."""
        self.code = (
            code if type(code) is str and code in ERROR_CODES else "browser_internal"
        )
        super().__init__(self.code)


def browser_url(value):
    """Reuse accepted public HTTPS URI policy without resolving, repairing or fetching the supplied destination."""
    try:
        return public_url(value).url
    except WebFetchError:
        raise BrowserError("browser_url_denied") from None


def request_policy(params, main_frame, expected_document):
    """Admit explicit main navigation or bounded text resources only, never write methods, frames or decorative fetches."""
    if type(params) is not dict or type(params.get("request")) is not dict:
        raise BrowserError("browser_protocol_invalid")
    request, kind = params["request"], params.get("resourceType")
    if (
        type(request.get("method")) is not str
        or request["method"] != "GET"
        or request.get("postData")
        or request.get("hasPostData")
    ):
        raise BrowserError("browser_method_denied")
    if (
        type(kind) is not str
        or type(params.get("frameId")) is not str
        or params["frameId"] != main_frame
    ):
        raise BrowserError("browser_navigation_denied")
    if kind in DECORATIVE_KINDS:
        logger.info("browser_decorative_request_denied")
        return None
    if kind not in ALLOWED_KINDS:
        raise BrowserError("browser_resource_denied")
    url = browser_url(request.get("url"))
    if kind == "Document" and url != expected_document:
        raise BrowserError("browser_navigation_denied")
    logger.info("browser_request_admitted")
    return url, kind


def resource_representation(headers, kind):
    """Validate complete source headers and supported text codecs before supplying a resource to the isolated browser."""
    try:
        values = header_map(headers)
        if any(
            name.lower() == "content-disposition"
            and value.split(";", 1)[0].strip().lower() == "attachment"
            for name, value in headers
        ):
            raise BrowserError("browser_download_denied")
        original = values.get("content-type", "")
        media, separator, parameters = original.partition(";")
        media = media.strip().lower()
        if kind not in MEDIA or media not in MEDIA[kind]:
            raise BrowserError("browser_resource_denied")
        surrogate = "text/plain" + (";" + parameters if separator else "")
        adapted = tuple(
            (name, surrogate if name.lower() == "content-type" else value)
            for name, value in headers
        )
        _, encoding = representation(adapted)
        logger.info("browser_resource_representation_validated")
        return media, encoding
    except WebFetchError:
        raise BrowserError("browser_resource_denied") from None


def fulfillment_headers(headers, media, length):
    """Supply only fixed safe metadata, original stricter CSP and a local read-only CSP without cookies or transfer framing."""
    result = [
        dict(name="Content-Type", value=media + "; charset=utf-8"),
        dict(name="Content-Length", value=str(length)),
        dict(name="Cache-Control", value="no-store"),
        dict(name="X-Content-Type-Options", value="nosniff"),
        dict(name="Content-Security-Policy", value=CSP),
    ]
    for name, value in headers:
        if name.lower() in {
            "content-security-policy",
            "cross-origin-resource-policy",
            "cross-origin-opener-policy",
            "cross-origin-embedder-policy",
            "access-control-allow-origin",
            "access-control-expose-headers",
        }:
            result.append(dict(name=name, value=value))
    logger.info("browser_safe_headers_prepared")
    return result


def snapshot_text(payload, expected_url):
    """Read complete bounded native layout text/title only when the document matches its actual host-served source."""
    try:
        if (
            type(payload) is not dict
            or type(payload.get("strings")) is not list
            or type(payload.get("documents")) is not list
            or len(payload["documents"]) != 1
        ):
            raise ValueError()
        strings, document = payload["strings"], payload["documents"][0]
        if (
            any(type(value) is not str for value in strings)
            or type(document) is not dict
        ):
            raise ValueError()

        def string_at(index, *, optional=False):
            """Recognize Chromium's empty optional string sentinel without negative indexing."""
            if optional and type(index) is int and index == -1:
                return ""
            if type(index) is not int or not 0 <= index < len(strings):
                raise ValueError()
            return strings[index]

        final_url = browser_url(string_at(document["documentURL"]))
        if final_url != expected_url:
            raise BrowserError("browser_source_drift")
        title = " ".join(string_at(document["title"], optional=True).split()) or None
        layout = document["layout"]["text"]
        if type(layout) is not list or len(layout) > 32768:
            raise ValueError()
        text = " ".join(
            " ".join(string_at(index, optional=True).split()) for index in layout
        )
        text = " ".join(text.split())
        if (
            not text
            or len(text.encode()) > 131072
            or (title and len(title.encode()) > 1024)
        ):
            raise BrowserError("browser_text_limit")
        logger.info("browser_snapshot_extracted bytes=%d", len(text.encode()))
        return final_url, title, text
    except BrowserError:
        raise
    except (ValueError, TypeError, KeyError, UnicodeError):
        raise BrowserError("browser_protocol_invalid") from None
