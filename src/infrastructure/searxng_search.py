"""Prepare an inactive fixed-loopback SearXNG search adapter without deploying or selecting a provider."""

import asyncio
import json
import logging

import httpx

from src.application.ports.search import SearchBatch, SearchHit
from src.application.services.search_pipeline import (
    SearchPipelineError,
    bounded_text,
    unique_pairs,
    validate_batch,
    validate_query,
)

logger = logging.getLogger(__name__)
ENDPOINT = "http://127.0.0.1:8889/search"
ENGINES = ("brave",)
MAX_BODY_BYTES = 131072
MAX_WIRE_RESULTS = 50
REQUEST_SECONDS = 10


class SearxNGError(Exception):
    """Report finite adapter outcomes without provider bodies, queries or diagnostic text."""

    def __init__(self, code):
        """Retain only known review, request, HTTP, upstream and transport failure codes."""
        if type(code) is not str or code not in {
            "searxng_instance_unreviewed",
            "searxng_options_invalid",
            "searxng_access_denied",
            "searxng_quota",
            "searxng_http",
            "searxng_response_invalid",
            "searxng_upstream_unavailable",
            "searxng_timeout",
            "searxng_transport",
        }:
            code = "searxng_transport"
        super().__init__(code)
        self.code = code


def decode_response(raw, query):
    """Validate every bounded raw row and explicitly project the first five without treating engine answers as authority."""
    try:
        body = json.loads(raw.decode("utf-8"), object_pairs_hook=unique_pairs)
        if type(body) is not dict or body.get("query") != query:
            raise ValueError()
        rows = body["results"]
        failures = body.get("unresponsive_engines", [])
        if (
            type(rows) is not list
            or len(rows) > MAX_WIRE_RESULTS
            or type(failures) is not list
            or len(failures) > len(ENGINES)
        ):
            raise ValueError()
        for failure in failures:
            if (
                type(failure) is not list
                or len(failure) != 2
                or type(failure[0]) is not str
                or failure[0] not in ENGINES
                or not bounded_text(failure[1], 256)
            ):
                raise ValueError()
        hits = []
        for row in rows:
            if (
                type(row) is not dict
                or type(row.get("engine")) is not str
                or row["engine"] not in ENGINES
                or type(row.get("engines")) is not list
                or not 1 <= len(row["engines"]) <= len(ENGINES)
                or any(
                    type(name) is not str or name not in ENGINES
                    for name in row["engines"]
                )
            ):
                raise ValueError()
            hit = SearchHit(row["title"], row["url"], row["content"])
            validate_batch(SearchBatch("searxng", (hit,)), "searxng")
            hits.append(hit)
        if not hits and failures:
            raise SearxNGError("searxng_upstream_unavailable")
        selected = tuple(hits[:5])
        logger.info(
            "search_searxng_window received=%d selected=%d omitted=%d upstream_failures=%d",
            len(hits),
            len(selected),
            max(0, len(hits) - 5),
            len(failures),
        )
        return SearchBatch("searxng", selected)
    except (
        UnicodeError,
        ValueError,
        TypeError,
        KeyError,
        RecursionError,
        SearchPipelineError,
    ):
        raise SearxNGError("searxng_response_invalid") from None


class SearxNGSearchAdapter:
    """Bind an explicitly reviewed owned instance without credentials, endpoint overrides or automatic startup."""

    def __init__(self, *, instance_reviewed=False, transport=None):
        """Retain trusted configuration without reading environment/Vault or contacting the instance."""
        self._instance_reviewed = instance_reviewed is True
        self._transport = transport
        logger.info("search_searxng_constructed reviewed=%s", self._instance_reviewed)

    async def search(self, *, query, max_results):
        """Make one bounded fixed-loopback form POST and await HTTP cleanup on every terminal path."""
        if not self._instance_reviewed:
            raise SearxNGError("searxng_instance_unreviewed")
        try:
            validate_query(query)
        except SearchPipelineError:
            raise SearxNGError("searxng_options_invalid") from None
        if type(max_results) is not int or max_results != 5:
            raise SearxNGError("searxng_options_invalid")
        logger.info("search_searxng_started")
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
                            "Accept": "application/json",
                            "Accept-Encoding": "identity",
                        },
                        data=dict(
                            q=query,
                            format="json",
                            pageno="1",
                            language="auto",
                            engines=",".join(ENGINES),
                            safesearch="1",
                        ),
                    ) as response:
                        if response.status_code in (401, 403):
                            raise SearxNGError("searxng_access_denied")
                        if response.status_code == 429:
                            raise SearxNGError("searxng_quota")
                        if response.status_code != 200:
                            raise SearxNGError("searxng_http")
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
                            raise SearxNGError("searxng_response_invalid")
                        length = response.headers.get("content-length")
                        if length is not None and (
                            len(length) > 6
                            or not length.isascii()
                            or not length.isdecimal()
                            or int(length) > MAX_BODY_BYTES
                        ):
                            raise SearxNGError("searxng_response_invalid")
                        raw = bytearray()
                        async for chunk in response.aiter_raw(chunk_size=8192):
                            if len(raw) + len(chunk) > MAX_BODY_BYTES:
                                raise SearxNGError("searxng_response_invalid")
                            raw.extend(chunk)
                        result = decode_response(bytes(raw), query)
            logger.info("search_searxng_completed count=%d", len(result.hits))
            return result
        except asyncio.CancelledError:
            logger.info("search_searxng_cancelled")
            raise
        except (TimeoutError, httpx.TimeoutException):
            logger.info("search_searxng_timeout")
            raise SearxNGError("searxng_timeout") from None
        except SearxNGError:
            logger.info("search_searxng_rejected")
            raise
        except Exception:
            logger.info("search_searxng_transport_failed")
            raise SearxNGError("searxng_transport") from None
