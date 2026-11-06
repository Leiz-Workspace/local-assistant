"""Verify exception-context diagnostics exclude raw messages/locals and preserve original source failure ownership without network calls."""

import json

import pytest
from web_source_forensics import ForensicSourceObserver, exception_metadata

from src.application.services.web_fetch_policy import WebFetchError


def test_exception_context_preserves_finite_types_and_drops_messages_and_unknown_codes():
    """Observe a suppressed underlying type while keeping every private exception message/code out of diagnostic metadata."""
    error = WebFetchError("web_fetch_internal")
    inner = ValueError("PRIVATE-SOURCE-URL-AND-DIAGNOSTIC")
    inner.code = "PRIVATE-CODE"
    error.__context__ = inner
    value = exception_metadata(error)
    assert [row["type"] for row in value] == ["WebFetchError", "ValueError"]
    assert value[0]["code"] == "web_fetch_internal" and value[1]["code"] is None
    assert "PRIVATE" not in json.dumps(value)


def test_exception_context_cycles_and_depth_are_bounded():
    """Refuse unbounded traceback-context traversal without changing the original exception graph."""
    error = ValueError("PRIVATE")
    error.__context__ = error
    assert len(exception_metadata(error)) == 1
    for _ in range(20):
        outer = RuntimeError("PRIVATE")
        outer.__context__ = error
        error = outer
    assert len(exception_metadata(error)) == 8


@pytest.mark.asyncio
async def test_source_wrapper_rethrows_exact_original_error_with_bounded_context():
    """Retain the exact original finite failure and avoid source substitutions or diagnostic retries."""
    error = WebFetchError("web_fetch_internal")
    error.__context__ = TypeError("PRIVATE")

    class Source:
        """Provide one authored finite failure without model or public/private HTTP activity."""

        async def read(self, url, mode):
            """Raise the controlled original exception once rather than replacing the accepted failure."""
            raise error

    observer = ForensicSourceObserver(Source())
    with pytest.raises(WebFetchError) as caught:
        await observer.read("https://example.org/source", "static")
    assert caught.value is error and len(observer.records) == 1
    assert [row["type"] for row in observer.records[0]["exception_chain"]] == [
        "WebFetchError",
        "TypeError",
    ]
