"""Validate explicit public HTTPS destinations, conservative address ranges and finite fetch failures."""

import ipaddress
import logging
import re
from dataclasses import dataclass
from urllib.parse import urlsplit

logger = logging.getLogger(__name__)
ERROR_CODES = frozenset(
    {
        "web_fetch_url_invalid",
        "web_fetch_address_denied",
        "web_fetch_dns_invalid",
        "web_fetch_peer_invalid",
        "web_fetch_busy",
        "web_fetch_closed",
        "web_fetch_timeout",
        "web_fetch_tls_failed",
        "web_fetch_transport_failed",
        "web_fetch_http_invalid",
        "web_fetch_http_status",
        "web_fetch_header_limit",
        "web_fetch_body_limit",
        "web_fetch_encoding_unsupported",
        "web_fetch_media_unsupported",
        "web_fetch_redirect_invalid",
        "web_fetch_redirect_limit",
        "web_fetch_html_invalid",
        "web_fetch_text_limit",
        "web_fetch_canonical_invalid",
        "web_fetch_response_invalid",
        "web_fetch_internal",
    }
)
V4_DENIED = tuple(
    ipaddress.ip_network(value)
    for value in (
        "0.0.0.0/8",
        "10.0.0.0/8",
        "100.64.0.0/10",
        "127.0.0.0/8",
        "169.254.0.0/16",
        "172.16.0.0/12",
        "192.0.0.0/24",
        "192.0.2.0/24",
        "192.88.99.0/24",
        "192.168.0.0/16",
        "198.18.0.0/15",
        "198.51.100.0/24",
        "203.0.113.0/24",
        "224.0.0.0/4",
        "240.0.0.0/4",
    )
)
V6_GLOBAL = ipaddress.ip_network("2000::/3")
V6_DENIED = tuple(
    ipaddress.ip_network(value)
    for value in (
        "2001::/23",
        "2001:db8::/32",
        "2002::/16",
        "3ffe::/16",
        "3ff0::/13",
        "3fff::/20",
    )
)
LABEL = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\Z")
SPECIAL_SUFFIXES = (
    "localhost",
    "local",
    "internal",
    "home",
    "lan",
    "test",
    "invalid",
    "onion",
    "arpa",
    "alt",
)


class WebFetchError(Exception):
    """Expose only a finite code without raw URLs, address answers, page content or dependency errors."""

    def __init__(self, code):
        """Replace unknown error values with a safe internal identifier."""
        self.code = (
            code if type(code) is str and code in ERROR_CODES else "web_fetch_internal"
        )
        super().__init__(self.code)


@dataclass(frozen=True, slots=True, repr=False)
class PublicURL:
    """Retain explicit input separately from scheme/host/default-port/root-path URI equivalence normalization."""

    original: str
    url: str
    host: str
    target: bytes


def public_url(value):
    """Reject ambiguous, private-name or credential-bearing URLs before DNS or socket activity."""
    if (
        type(value) is not str
        or not 1 <= len(value) <= 2048
        or any(ord(char) < 33 or ord(char) > 126 for char in value)
        or "\\" in value
        or not value.startswith("https://")
    ):
        raise WebFetchError("web_fetch_url_invalid")
    try:
        parts = urlsplit(value)
        host = parts.hostname
        if (
            parts.scheme != "https"
            or not host
            or len(host) > 253
            or parts.username is not None
            or parts.password is not None
            or parts.port not in (None, 443)
            or parts.fragment
            or "#" in value
            or parts.netloc.lower() not in {host, host + ":443"}
            or "%" in parts.netloc
            or host.endswith(".")
        ):
            raise ValueError()
        labels = host.split(".")
        if (
            len(labels) < 2
            or any(LABEL.fullmatch(label) is None for label in labels)
            or all(label.isdigit() for label in labels)
            or labels[-1] in SPECIAL_SUFFIXES
        ):
            raise ValueError()
        try:
            ipaddress.ip_address(host)
        except ValueError:
            pass
        else:
            raise ValueError()
        target = (parts.path or "/") + ("?" + parts.query if "?" in value else "")
        for match in re.finditer("%", target):
            pair = target[match.start() + 1 : match.start() + 3]
            if (
                len(pair) != 2
                or re.fullmatch(r"[0-9A-Fa-f]{2}", pair) is None
                or int(pair, 16) < 32
                or int(pair, 16) == 127
            ):
                raise ValueError()
        normalized = "https://" + host + target
        logger.info("web_fetch_url_validated")
        return PublicURL(value, normalized, host, target.encode("ascii"))
    except (ValueError, UnicodeError):
        raise WebFetchError("web_fetch_url_invalid") from None


def public_address(value):
    """Recognize public unicast only, excluding special and embedded/tunnel ranges independently of old Python flags."""
    try:
        if type(value) is not str or "%" in value:
            raise ValueError()
        address = ipaddress.ip_address(value)
        if not address.is_global:
            raise ValueError()
        if address.version == 4:
            valid = not any(address in block for block in V4_DENIED)
        else:
            valid = address in V6_GLOBAL and not any(
                address in block for block in V6_DENIED
            )
        if not valid:
            raise ValueError()
        return str(address)
    except ValueError:
        raise WebFetchError("web_fetch_address_denied") from None


def public_answers(values):
    """Validate every answer before choosing one, without skipping unsafe or overbudget tail entries."""
    if type(values) not in (tuple, list) or not 1 <= len(values) <= 64:
        raise WebFetchError("web_fetch_dns_invalid")
    addresses = tuple(dict.fromkeys(public_address(value) for value in values))
    logger.info("web_fetch_dns_validated count=%d", len(addresses))
    return addresses


def header_map(headers):
    """Validate complete bounded header/trailer metadata without silently merging security-sensitive duplicates."""
    if type(headers) is not tuple or len(headers) > 128:
        raise WebFetchError("web_fetch_header_limit")
    result, size = {}, 0
    for row in headers:
        if (
            type(row) is not tuple
            or len(row) != 2
            or any(type(item) is not str for item in row)
        ):
            raise WebFetchError("web_fetch_http_invalid")
        key, value = row
        if (
            not key
            or any(ord(c) < 33 or ord(c) > 126 for c in key)
            or any(ord(c) < 32 or ord(c) > 126 for c in value)
        ):
            raise WebFetchError("web_fetch_http_invalid")
        size += len(key) + len(value) + 4
        if size > 16384:
            raise WebFetchError("web_fetch_header_limit")
        key = key.lower()
        if (
            key
            in {
                "content-type",
                "content-encoding",
                "content-length",
                "transfer-encoding",
                "location",
            }
            and key in result
        ):
            raise WebFetchError("web_fetch_http_invalid")
        result.setdefault(key, value)
    logger.info("web_fetch_headers_validated count=%d", len(headers))
    return result


def representation(headers):
    """Require one static identity-encoded UTF-8/ASCII representation without guessing another codec or media type."""
    values = header_map(headers)
    if values.get("content-encoding", "identity").lower() != "identity":
        raise WebFetchError("web_fetch_encoding_unsupported")
    if "transfer-encoding" in values and "content-length" in values:
        raise WebFetchError("web_fetch_http_invalid")
    length = values.get("content-length")
    if length is not None:
        if not length.isascii() or not length.isdigit() or len(length) > 10:
            raise WebFetchError("web_fetch_http_invalid")
        if int(length) > 1048576:
            raise WebFetchError("web_fetch_body_limit")
    fields = values.get("content-type", "").split(";")
    media = fields[0].strip().lower()
    if media not in {"text/html", "text/plain"}:
        raise WebFetchError("web_fetch_media_unsupported")
    charsets = []
    for field in fields[1:]:
        key, separator, value = field.strip().partition("=")
        if not separator:
            raise WebFetchError("web_fetch_encoding_unsupported")
        if key.lower() == "charset":
            value = value.strip()
            if value.startswith('"') or value.endswith('"'):
                if (
                    len(value) < 2
                    or not (value.startswith('"') and value.endswith('"'))
                    or '"' in value[1:-1]
                ):
                    raise WebFetchError("web_fetch_encoding_unsupported")
                value = value[1:-1]
            charsets.append(value.lower())
    if len(charsets) > 1 or any(
        value not in {"utf-8", "utf8", "us-ascii", "ascii"} for value in charsets
    ):
        raise WebFetchError("web_fetch_encoding_unsupported")
    logger.info("web_fetch_representation_validated")
    return media, "ascii" if charsets and charsets[0] in {
        "ascii",
        "us-ascii",
    } else "utf-8"
