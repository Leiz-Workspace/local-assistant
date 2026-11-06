"""Normalize explicit bounded search queries and maintain finite process-local principal quotas."""

import logging
import math
import unicodedata
from time import monotonic
from uuid import UUID

from src.application.services.search_pipeline import SearchPipelineError, validate_query

logger = logging.getLogger(__name__)
ERROR_STATUS = {
    "web_search_query_invalid": 422,
    "web_search_selector_forbidden": 422,
    "web_search_owner_invalid": 403,
    "web_search_rate_limited": 429,
    "web_search_busy": 429,
    "web_search_unavailable": 503,
    "web_search_provider_unavailable": 503,
    "web_search_model_unavailable": 503,
    "web_search_pipeline_invalid": 502,
    "web_search_timeout": 504,
    "web_search_response_limit": 413,
    "web_search_request_limit": 413,
    "web_search_json_invalid": 422,
    "web_search_request_invalid": 422,
    "web_search_media_type": 415,
}


class WebSearchError(Exception):
    """Expose finite status/code/retry metadata without private queries or dependency diagnostics."""

    def __init__(self, code, *, retry_after=None):
        """Bind only known error codes and bounded optional retry seconds."""
        if type(code) is not str or code not in ERROR_STATUS:
            code = "web_search_unavailable"
        super().__init__(code)
        self.code = code
        self.status_code = ERROR_STATUS[code]
        self.retry_after = (
            retry_after if type(retry_after) is int and 1 <= retry_after <= 60 else None
        )


def normalize_query(query):
    """Apply visible NFC/whitespace normalization after original byte checks, rejecting engine/redirect selectors."""
    try:
        validate_query(query)
        normalized = " ".join(unicodedata.normalize("NFC", query).split())
        validate_query(normalized)
    except (SearchPipelineError, UnicodeError):
        raise WebSearchError("web_search_query_invalid") from None
    if any(token.startswith(("!", ":")) for token in normalized.split(" ")):
        raise WebSearchError("web_search_selector_forbidden")
    logger.info("web_search_query_normalized changed=%s", normalized != query)
    return normalized


class WebSearchQuota:
    """Bound global/principal admission counters inside one lazy monotonic60second window."""

    def __init__(self, *, clock=monotonic):
        """Initialize server-owned counters without accepting client quota or clock configuration."""
        self.clock = clock
        self.started = self.now()
        self.total = 0
        self.owners = {}
        logger.info("web_search_quota_initialized")

    def now(self):
        """Reject invalid trusted clock observations rather than bypassing a quota window."""
        value = self.clock()
        if type(value) not in (int, float) or not math.isfinite(value):
            raise WebSearchError("web_search_unavailable")
        return value

    def charge(self, owner):
        """Charge an admitted attempt once without refunds, bounding counters to16 principals/global and4 per owner."""
        if not isinstance(owner, UUID):
            raise WebSearchError("web_search_owner_invalid")
        now = self.now()
        if now >= self.started + 60:
            self.started, self.total, self.owners = now, 0, {}
            logger.info("web_search_quota_window_reset")
        count = self.owners.get(owner, 0)
        if (
            self.total >= 16
            or count >= 4
            or (owner not in self.owners and len(self.owners) >= 16)
        ):
            retry = max(1, min(60, math.ceil(self.started + 60 - now)))
            logger.info("web_search_quota_rejected")
            raise WebSearchError("web_search_rate_limited", retry_after=retry)
        self.total += 1
        self.owners[owner] = count + 1
        logger.info(
            "web_search_quota_charged total=%d owners=%d", self.total, len(self.owners)
        )
