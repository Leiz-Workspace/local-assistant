"""Verify diagnostic observers preserve strict provider/source acceptance, original bytes, bounded reading and joined cleanup without raw-data logs."""

import hashlib
import json
import logging

import httpx
import pytest
from web_observation_diagnostics import (
    FiniteSourceObserver,
    ObservedSearxTransport,
    shape_diagnosis,
)

from src.application.services.web_fetch_policy import WebFetchError
from src.infrastructure.searxng_search import (
    MAX_BODY_BYTES,
    SearxNGError,
    SearxNGSearchAdapter,
)


def body():
    """Build one explicitly authored strict-wire result with a private-text canary that must never enter logs/metadata."""
    return dict(
        query="Public goal",
        results=[
            dict(
                engine="brave",
                engines=["brave"],
                title="PRIVATE-TITLE-CANARY",
                content="PRIVATE-SNIPPET-CANARY",
                url="https://example.org/source",
            )
        ],
    )


@pytest.mark.parametrize(
    "mutation,reason",
    [
        ("valid", "accepted"),
        ("http_url", "https_url_guard"),
        ("title", "title_guard"),
        ("snippet", "snippet_guard"),
        ("url", "url_text_guard"),
        ("engine", "row_engine_guard"),
        ("query", "query_mismatch"),
        ("count", "result_list_guard"),
        ("root", "root_not_object"),
        ("upstream", "empty_with_declared_upstream_failure"),
        ("json", "json_or_utf8_guard"),
    ],
)
@pytest.mark.asyncio
async def test_diagnostic_reason_does_not_change_original_whole_response_acceptance(
    mutation, reason, caplog
):
    """Retain finite guard names while unchanged strict adapter accepts only the original fully valid response."""
    v = body()
    if mutation == "http_url":
        v["results"][0]["url"] = "http://example.org/source"
    elif mutation == "title":
        v["results"][0]["title"] = "x" * 513
    elif mutation == "snippet":
        v["results"][0]["content"] = "x" * 2049
    elif mutation == "url":
        v["results"][0]["url"] = ""
    elif mutation == "engine":
        v["results"][0]["engine"] = "other"
    elif mutation == "query":
        v["query"] = "different"
    elif mutation == "count":
        v["results"] *= 51
    elif mutation == "root":
        v = []
    elif mutation == "upstream":
        v.update(
            results=[], unresponsive_engines=[["brave", "PRIVATE-UPSTREAM-CANARY"]]
        )
    raw = (
        b'{"duplicate":1,"duplicate":2}'
        if mutation == "json"
        else json.dumps(v).encode()
    )
    caplog.set_level(logging.INFO)
    calls = []

    def response(request):
        """Observe the original fixed form bytes and supply an authored complete response without external HTTP."""
        calls.append(request.content)
        return httpx.Response(
            200,
            headers={"content-type": "application/json"},
            stream=httpx.ByteStream(raw),
        )

    observer = ObservedSearxTransport(httpx.MockTransport(response))
    adapter = SearxNGSearchAdapter(instance_reviewed=True, transport=observer)
    if mutation == "valid":
        result = await adapter.search(query="Public goal", max_results=5)
        assert result.hits[0].snippet == "PRIVATE-SNIPPET-CANARY"
    else:
        with pytest.raises(SearxNGError):
            await adapter.search(query="Public goal", max_results=5)
    assert len(calls) == 1
    record = observer.records[0]
    assert record["reason"] == reason and record["body_complete"] and record["closed"]
    assert (
        record["consumed_bytes"] == len(raw)
        and record["consumed_sha256"] == hashlib.sha256(raw).hexdigest()
    )
    assert "PRIVATE-" not in json.dumps(record) and "PRIVATE-" not in caplog.text


@pytest.mark.parametrize(
    "fault,reason",
    [
        ("status", "http_status_guard"),
        ("media", "media_or_encoding_guard"),
        ("length", "declared_length_guard"),
    ],
)
@pytest.mark.asyncio
async def test_header_guard_does_not_read_a_rejected_body(fault, reason):
    """Observe rejection metadata without forcing the original adapter to consume bytes after a header/status guard."""
    headers = {"content-type": "application/json"}
    status = 503 if fault == "status" else 200
    if fault == "media":
        headers["content-type"] = "text/html"
    if fault == "length":
        headers["content-length"] = str(MAX_BODY_BYTES + 1)

    def response(request):
        """Return an authored body that must remain entirely unread after the selected original header guard."""
        return httpx.Response(
            status, headers=headers, stream=httpx.ByteStream(b"PRIVATE-UNREAD-CANARY")
        )

    observer = ObservedSearxTransport(httpx.MockTransport(response))
    with pytest.raises(SearxNGError):
        await SearxNGSearchAdapter(instance_reviewed=True, transport=observer).search(
            query="Public goal", max_results=5
        )
    record = observer.records[0]
    assert (
        record["reason"] == reason
        and record["closed"]
        and record["consumed_bytes"] == 0
        and not record["body_complete"]
    )


@pytest.mark.asyncio
async def test_source_failure_reason_is_finite_and_original_error_is_preserved(caplog):
    """Observe an original accepted failure before evidence redaction without logging raw backend diagnostics or changing exception identity."""
    error = WebFetchError("web_fetch_encoding_unsupported")

    class Source:
        """Expose an authored source failure with no public or private network access."""

        async def read(self, url, mode):
            """Raise the exact original finite source guard and leave outer redaction unchanged."""
            raise error

    caplog.set_level(logging.INFO)
    source = FiniteSourceObserver(Source())
    with pytest.raises(WebFetchError) as caught:
        await source.read("https://example.org/source", "static")
    assert caught.value is error
    assert source.records == [
        dict(status="error", underlying_code="web_fetch_encoding_unsupported")
    ]
    assert "https://" not in caplog.text


def test_malformed_utf8_metadata_is_finite():
    """Reject malformed provider bytes without attempting codec fallback or echoing raw content."""
    assert shape_diagnosis(b"\xffPRIVATE-CANARY", "Public goal") == dict(
        strict_code="searxng_response_invalid", reason="json_or_utf8_guard"
    )
