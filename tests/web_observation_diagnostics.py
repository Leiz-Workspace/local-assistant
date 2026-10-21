"""Observe finite provider/source guard metadata for frozen evaluations while forwarding unchanged bounded transport bytes and cleanup."""

import hashlib
import json
import logging
from urllib.parse import parse_qs

import httpx

from src.application.ports.search import SearchBatch, SearchHit
from src.application.services.search_pipeline import (
    bounded_text,
    unique_pairs,
    validate_batch,
)
from src.application.services.web_fetch_policy import ERROR_CODES as FETCH_CODES
from src.infrastructure.searxng_search import (
    ENDPOINT,
    ENGINES,
    MAX_BODY_BYTES,
    MAX_WIRE_RESULTS,
    SearxNGError,
    decode_response,
)

logger = logging.getLogger(__name__)


def shape_diagnosis(raw, query):
    """Explain the unchanged strict decoder's outcome using finite schema/field guard names rather than persisting provider text."""
    try:
        batch = decode_response(raw, query)
        return dict(
            strict_code=None, reason="accepted", selected_results=len(batch.hits)
        )
    except SearxNGError as error:
        code = error.code
    try:
        body = json.loads(raw.decode("utf-8"), object_pairs_hook=unique_pairs)
        if type(body) is not dict:
            return dict(strict_code=code, reason="root_not_object")
        if body.get("query") != query:
            return dict(strict_code=code, reason="query_mismatch")
        rows, failures = body.get("results"), body.get("unresponsive_engines", [])
        if type(rows) is not list or len(rows) > MAX_WIRE_RESULTS:
            return dict(strict_code=code, reason="result_list_guard")
        if type(failures) is not list or len(failures) > len(ENGINES):
            return dict(strict_code=code, reason="upstream_list_guard")
        if code == "searxng_upstream_unavailable":
            return dict(
                strict_code=code,
                reason="empty_with_declared_upstream_failure",
                wire_results=0,
                upstream_failures=len(failures),
            )
        for index, row in enumerate(rows, 1):
            if (
                type(row) is not dict
                or row.get("engine") not in ENGINES
                or type(row.get("engines")) is not list
                or not 1 <= len(row["engines"]) <= len(ENGINES)
                or any(
                    type(name) is not str or name not in ENGINES
                    for name in row["engines"]
                )
            ):
                reason = "row_engine_guard"
            elif not bounded_text(row.get("title"), 512):
                reason = "title_guard"
            elif not bounded_text(row.get("content"), 2048):
                reason = "snippet_guard"
            elif not bounded_text(row.get("url"), 2048):
                reason = "url_text_guard"
            else:
                try:
                    validate_batch(
                        SearchBatch(
                            "searxng",
                            (SearchHit(row["title"], row["url"], row["content"]),),
                        ),
                        "searxng",
                    )
                    continue
                except Exception:
                    reason = "https_url_guard"
            return dict(
                strict_code=code,
                reason=reason,
                first_bad_row=index,
                wire_results=len(rows),
                upstream_failures=len(failures),
            )
        return dict(
            strict_code=code, reason="other_strict_schema_guard", wire_results=len(rows)
        )
    except Exception:
        return dict(strict_code=code, reason="json_or_utf8_guard")


class ObservedHTTPStream(httpx.AsyncByteStream):
    """Forward the exact original stream once while retaining only bounded diagnostic metadata and consumed-byte hashes."""

    def __init__(self, original, record, query):
        """Bind one original response stream and an in-memory bounded raw prefix without reading ahead."""
        self.original, self.record, self.query = original, record, query
        self.raw, self.hash = bytearray(), hashlib.sha256()

    async def __aiter__(self):
        """Yield every original chunk unchanged without retries or consuming bytes after the accepted client stops."""
        async for chunk in self.original:
            self.hash.update(chunk)
            self.record["consumed_bytes"] += len(chunk)
            if len(self.raw) + len(chunk) <= MAX_BODY_BYTES:
                self.raw.extend(chunk)
            else:
                self.record["reason"] = "body_byte_limit"
            yield chunk
        self.record["body_complete"] = True
        if self.record["reason"] is None:
            self.record.update(shape_diagnosis(bytes(self.raw), self.query))

    async def aclose(self):
        """Join original HTTP cleanup and discard all raw provider bytes before retaining the final metadata record."""
        try:
            await self.original.aclose()
        finally:
            self.record["closed"] = True
            self.record["consumed_sha256"] = self.hash.hexdigest()
            if self.record["reason"] is None:
                self.record["reason"] = "body_not_fully_consumed"
            self.raw.clear()
            self.query = ""
            logger.info("web_diagnostic_stream_closed reason=%s", self.record["reason"])


class ObservedSearxTransport(httpx.AsyncBaseTransport):
    """Observe one unchanged fixed-loopback request through the accepted adapter seam, with no fallback or raw-result persistence."""

    def __init__(self, transport=None):
        """Bind one explicit delegate or equivalent original zero-retry nonproxy HTTP transport without network activity."""
        self.transport = (
            transport
            if transport is not None
            else httpx.AsyncHTTPTransport(
                trust_env=False,
                retries=0,
                limits=httpx.Limits(max_connections=1, max_keepalive_connections=0),
            )
        )
        self.records = []

    async def handle_async_request(self, request):
        """Forward one complete original form request and wrap only its original response stream for finite observations."""
        if self.records or request.method != "POST" or str(request.url) != ENDPOINT:
            raise ValueError("diagnostic_request_guard")
        raw = request.content
        if len(raw) > 4096:
            raise ValueError("diagnostic_request_guard")
        query = parse_qs(raw.decode("ascii"), strict_parsing=True, max_num_fields=8)[
            "q"
        ][0]
        response = await self.transport.handle_async_request(request)
        record = dict(
            status=response.status_code,
            consumed_bytes=0,
            consumed_sha256=None,
            body_complete=False,
            closed=False,
            reason=None,
            strict_code=None,
        )
        media = (
            response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        )
        encoding = response.headers.get("content-encoding", "identity").lower()
        length = response.headers.get("content-length")
        record.update(
            media_is_json=media == "application/json",
            encoding_is_identity=encoding == "identity",
        )
        if response.status_code != 200:
            record["reason"] = "http_status_guard"
        elif media != "application/json" or encoding != "identity":
            record["reason"] = "media_or_encoding_guard"
        elif length is not None and (
            len(length) > 6
            or not length.isascii()
            or not length.isdecimal()
            or int(length) > MAX_BODY_BYTES
        ):
            record["reason"] = "declared_length_guard"
        self.records.append(record)
        response.stream = ObservedHTTPStream(response.stream, record, query)
        return response

    async def aclose(self):
        """Join only this observer's original transport resources without touching the owned provider container."""
        await self.transport.aclose()
        logger.info("web_diagnostic_transport_closed")


class FiniteSourceObserver:
    """Retain a source's original finite failure before outer evidence redaction without inspecting or storing page content."""

    def __init__(self, source):
        """Bind the trusted accepted source and an empty four-reference metadata trace without source I/O."""
        self.source, self.records = source, []

    async def read(self, url, mode):
        """Delegate one unchanged source acquisition and preserve only its finite original failure or successful resource count."""
        if len(self.records) >= 4:
            raise ValueError("diagnostic_source_limit")
        record = dict(status="started", underlying_code=None)
        self.records.append(record)
        try:
            value = await self.source.read(url, mode)
            record.update(status="observed", resources=len(value.resources))
            return value
        except Exception as error:
            code = getattr(error, "code", None)
            record.update(
                status="error",
                underlying_code=code
                if type(code) is str and code in FETCH_CODES
                else "other_source_failure",
            )
            raise
        finally:
            logger.info("web_diagnostic_source_finished status=%s", record["status"])
