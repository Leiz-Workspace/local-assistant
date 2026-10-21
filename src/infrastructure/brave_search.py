"""Provide an unwired fixed-endpoint Brave search adapter with bounded unpersisted responses."""

import asyncio
import json
import logging

import httpx

from src.application.ports.search import SearchBatch, SearchHit
from src.application.services.search_pipeline import (
    SearchPipelineError,
    unique_pairs,
    validate_batch,
    validate_query,
)

logger = logging.getLogger(__name__)
ENDPOINT = "https://api.search.brave.com/res/v1/web/search"
MAX_BODY_BYTES = 65536
REQUEST_SECONDS = 10


class SearchProviderError(Exception):
    """Report a finite adapter outcome without exposing secret-bearing HTTP diagnostics."""

    def __init__(self, code):
        """Restrict public errors to known credential, account, HTTP and transport outcomes."""
        if type(code) is not str or code not in {
            "search_account_unreviewed",
            "search_credential_missing",
            "search_options_invalid",
            "search_provider_auth",
            "search_provider_quota",
            "search_provider_http",
            "search_provider_response",
            "search_provider_timeout",
            "search_provider_transport",
        }:
            code = "search_provider_transport"
        super().__init__(code)
        self.code = code


def decode_response(raw):
    """Extract all bounded web rows without trusting summaries, callbacks or provider-generated answers."""
    try:
        body = json.loads(raw.decode("utf-8"), object_pairs_hook=unique_pairs)
        if type(body) is not dict or body.get("type") != "search":
            raise ValueError()
        web = body.get("web")
        if web is None:
            rows = []
        elif type(web) is dict and type(web.get("results")) is list:
            rows = web["results"]
        else:
            raise ValueError()
        if len(rows) > 5 or any(type(row) is not dict for row in rows):
            raise ValueError()
        batch = SearchBatch(
            "brave",
            tuple(
                SearchHit(row["title"], row["url"], row["description"]) for row in rows
            ),
        )
        validate_batch(batch, "brave")
        return batch
    except (
        UnicodeError,
        ValueError,
        KeyError,
        TypeError,
        RecursionError,
        SearchPipelineError,
    ):
        raise SearchProviderError("search_provider_response") from None


class BraveSearchAdapter:
    """Own a caller-supplied key without Vault/environment discovery or implicit account activation."""

    def __init__(self, api_key=None, *, account_reviewed=False, transport=None):
        """Bind trusted configuration and optional test transport without creating a client or request."""
        self._api_key = api_key
        self._account_reviewed = account_reviewed is True
        self._transport = transport
        logger.info("search_brave_constructed reviewed=%s", self._account_reviewed)

    async def search(self, *, query, max_results):
        """Perform exactly one reviewed fixed HTTPS POST and close the client before returning or failing."""
        if not self._account_reviewed:
            raise SearchProviderError("search_account_unreviewed")
        key = self._api_key
        if (
            type(key) is not str
            or not 1 <= len(key) <= 512
            or any(ord(char) < 33 or ord(char) > 126 for char in key)
        ):
            raise SearchProviderError("search_credential_missing")
        try:
            validate_query(query)
        except SearchPipelineError:
            raise SearchProviderError("search_options_invalid") from None
        if type(max_results) is not int or max_results != 5 or len(query.split()) > 75:
            raise SearchProviderError("search_options_invalid")
        logger.info("search_brave_started")
        try:
            async with asyncio.timeout(REQUEST_SECONDS):
                async with httpx.AsyncClient(
                    trust_env=False,
                    follow_redirects=False,
                    timeout=httpx.Timeout(10, connect=3),
                    limits=httpx.Limits(max_connections=1, max_keepalive_connections=0),
                    transport=self._transport,
                ) as client:
                    async with client.stream(
                        "POST",
                        ENDPOINT,
                        headers={
                            "X-Subscription-Token": key,
                            "Accept": "application/json",
                            "Accept-Encoding": "identity",
                        },
                        json=dict(
                            q=query,
                            count=5,
                            result_filter=["web"],
                            spellcheck=False,
                            text_decorations=False,
                            extra_snippets=False,
                            summary=False,
                            enable_rich_callback=False,
                            country="US",
                            search_lang="en",
                        ),
                    ) as response:
                        if response.status_code in (401, 403):
                            raise SearchProviderError("search_provider_auth")
                        if response.status_code in (429, 402):
                            raise SearchProviderError("search_provider_quota")
                        if response.status_code != 200:
                            raise SearchProviderError("search_provider_http")
                        if (
                            response.headers.get("content-type", "")
                            .split(";", 1)[0]
                            .strip()
                            .lower()
                            != "application/json"
                            or response.headers.get(
                                "content-encoding", "identity"
                            ).lower()
                            != "identity"
                        ):
                            raise SearchProviderError("search_provider_response")
                        length = response.headers.get("content-length")
                        if length is not None and (
                            not length.isascii()
                            or not length.isdecimal()
                            or int(length) > MAX_BODY_BYTES
                        ):
                            raise SearchProviderError("search_provider_response")
                        raw = bytearray()
                        async for chunk in response.aiter_raw(chunk_size=8192):
                            if len(raw) + len(chunk) > MAX_BODY_BYTES:
                                raise SearchProviderError("search_provider_response")
                            raw.extend(chunk)
                        result = decode_response(bytes(raw))
            logger.info("search_brave_completed count=%d", len(result.hits))
            return result
        except asyncio.CancelledError:
            logger.info("search_brave_cancelled")
            raise
        except (TimeoutError, httpx.TimeoutException):
            logger.info("search_brave_timeout")
            raise SearchProviderError("search_provider_timeout") from None
        except SearchProviderError:
            logger.info("search_brave_rejected")
            raise
        except Exception:
            logger.info("search_brave_transport_failed")
            raise SearchProviderError("search_provider_transport") from None
