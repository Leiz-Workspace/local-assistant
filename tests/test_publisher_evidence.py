"""Verify fresh owner-bound publisher evidence, exact observed anchors, network fences and joined cancellation without public DNS or model calls."""

import asyncio
import hashlib
from dataclasses import replace
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from apps.api.services.publisher_evidence import PublisherEvidenceResolver
from src.application.ports.research import ResearchQuery, ResearchResult, ResearchSource
from src.application.ports.web_fetch import PublicResponse
from src.application.services.web_evidence import WebEvidenceService
from src.application.services.web_evidence_policy import WebEvidenceError
from src.application.services.web_fetch_policy import WebFetchError
from src.infrastructure.publisher_links import (
    PublisherCapture,
    PublisherSource,
    observed_link,
    rfc_url,
)

PARENT = "https://www.rfc-editor.org/info/rfc9112/"
CHILD = "https://www.rfc-editor.org/rfc/rfc9112.html"
BODY = b'<html><head><title>RFC landing</title></head><body>Publisher landing. <a href="/rfc/rfc9112.html">Full HTML</a></body></html>'


def discovery(owner):
    """Create an explicitly authored discovery locator, never a real search or page proof."""
    source = ResearchSource(
        "Q1:S1",
        "Authored publisher",
        PARENT,
        "Fixture only",
        hashlib.sha256(b"Fixture only").hexdigest(),
    )
    query = ResearchQuery(
        "Q1", "Authored query", "sources", True, None, datetime.now(UTC), (source,)
    )
    return ResearchResult(
        uuid4(), owner, "Authored goal", (query,), "complete", 1, 1, datetime.now(UTC)
    )


class Client:
    """Supply bounded authored responses and observable cancellation without public transport or credentials."""

    def __init__(self):
        """Prepare distinct parent and child bytes with an empty request ledger."""
        self.calls, self.hold, self.entered, self.exited = (
            [],
            False,
            asyncio.Event(),
            asyncio.Event(),
        )
        self.parent_body = BODY

    async def get(self, url):
        """Record exact destinations and return source bytes or hold one child until joined cancellation."""
        self.calls.append(url)
        if url == CHILD and self.hold:
            self.entered.set()
            try:
                await asyncio.Event().wait()
            finally:
                self.exited.set()
        body = (
            self.parent_body
            if url == PARENT
            else b"<html><body>Actual authored full text.</body></html>"
        )
        return PublicResponse(
            200, (("content-type", "text/html; charset=utf-8"),), body, "8.8.8.8"
        )


@pytest.mark.asyncio
async def test_actual_anchor_becomes_distinct_fresh_signed_child_with_owner_binding():
    """Acquire both pages once, retain complete parent hash and verify exact child citations without relabeling discovery."""
    client, owner = Client(), uuid4()
    resolver = PublisherEvidenceResolver(9112, client=client)
    value = await resolver.resolve(owner, discovery(owner), "Q1:S1")
    assert client.calls == [PARENT, CHILD]
    assert value.parent_body_sha256 == hashlib.sha256(BODY).hexdigest()
    assert value.observed_anchors[0][:2] == ("/rfc/rfc9112.html", CHILD)
    assert (
        value.child_is_search_hit is False and value.discovery_is_source_proof is False
    )
    assert not value.parent.cache_hit and not value.child.cache_hit
    assert resolver.evidence.cite(owner, value.child.snapshot, 0, 6).quote == "Actual"
    explicit = await resolver.evidence.read(
        owner, "https://example.org/explicit-source", use_cache=False
    )
    assert resolver.evidence.cite(owner, explicit.snapshot, 0, 6).quote == "Actual"
    assert client.calls == [PARENT, CHILD, "https://example.org/explicit-source"]
    with pytest.raises(Exception):
        resolver.evidence.cite(uuid4(), value.child.snapshot, 0, 6)
    await resolver.shutdown()
    with pytest.raises(Exception):
        resolver.evidence.cite(owner, value.child.snapshot, 0, 6)


@pytest.mark.parametrize(
    "raw",
    [
        b"No anchor",
        b'<a href="https://127.0.0.1/rfc/rfc9112.html">x</a>',
        b'<base href="https://www.rfc-editor.org/"><a href="/rfc/rfc9112.html">x</a>',
        b'<a href="/rfc/rfc9112.html" href="/else">x</a>',
        b'<a href="/rfc/rfc9111.html">wrong RFC</a>',
        b'<a href="/rfc/rfc9112.html?key=private">query</a>',
        b'<a href="/rfc/rfc9112.html">a</a><a href="https://rfc-editor.org/rfc/rfc9112.html">b</a>',
        b"x" * 1048577,
    ],
)
def test_missing_or_ambiguous_anchor_cannot_trigger_guessed_child(raw):
    """Reject wrong number, private host, base, duplicate attributes, query and oversized body rather than synthesize a full-text URL."""
    with pytest.raises(ValueError):
        observed_link(PARENT, 9112, raw)


@pytest.mark.parametrize(
    "url",
    [
        "http://www.rfc-editor.org/info/rfc9112/",
        PARENT + "?token=x",
        PARENT + "#fragment",
        "https://www.rfc-editor.org.evil.com/info/rfc9112/",
        "https://www.rfc-editor.org/rfc/rfc9112.html",
        "https://user:pass@www.rfc-editor.org/info/rfc9112/",
    ],
)
def test_policy_rejects_parent_url_substitution(url):
    """Validate exact publisher scheme, path and credential-free scope before transport."""
    with pytest.raises(Exception):
        rfc_url(url, 9112, parent=True)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "fault", ["owner", "missing", "duplicate", "closed", "wrong_number"]
)
async def test_owner_locator_and_lifetime_denials_have_no_network_side_effects(fault):
    """Reject foreign identities, absent/ambiguous source IDs, revoked lifetime and another RFC before any fetch."""
    owner, client = uuid4(), Client()
    resolver = PublisherEvidenceResolver(9112, client=client)
    value, source_id = discovery(owner), "Q1:S1"
    if fault == "owner":
        owner = uuid4()
    elif fault == "missing":
        source_id = "Q1:S2"
    elif fault == "duplicate":
        value = replace(value, queries=value.queries * 2)
    elif fault == "closed":
        await resolver.shutdown()
    else:
        source = replace(
            value.queries[0].sources[0], url=PARENT.replace("9112", "9111")
        )
        value = replace(value, queries=(replace(value.queries[0], sources=(source,)),))
    with pytest.raises(ValueError):
        await resolver.resolve(owner, value, source_id)
    assert client.calls == []
    await resolver.shutdown()


@pytest.mark.asyncio
async def test_child_cancel_busy_and_shutdown_join_before_admission_release():
    """Keep a held child owned through cancellation and deny another request while its cleanup is pending."""
    owner, client = uuid4(), Client()
    client.hold = True
    resolver = PublisherEvidenceResolver(9112, client=client)
    task = asyncio.create_task(resolver.resolve(owner, discovery(owner), "Q1:S1"))
    await asyncio.wait_for(client.entered.wait(), 2)
    with pytest.raises(ValueError):
        await resolver.resolve(owner, discovery(owner), "Q1:S1")
    await resolver.shutdown()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert (
        client.exited.is_set()
        and not resolver.operations
        and not resolver.admission.locked()
    )


@pytest.mark.asyncio
async def test_anchor_only_issuer_is_explicit_and_default_issuer_keeps_original_gate():
    """Admit malformed-unrelated-DOM anchor metadata only through the dedicated issuer and preserve the old static extractor allowlist."""
    owner, client = uuid4(), Client()
    client.parent_body = b'<html><body><h2>Unrelated mismatch</h1><a href="/rfc/rfc9112.html">Full text</a></body></html>'
    resolver = PublisherEvidenceResolver(9112, client=client)
    value = await resolver.resolve(owner, discovery(owner), "Q1:S1")
    assert value.parent.snapshot.extractor_version == "publisher-anchors-utf8-v1"
    assert (
        value.parent.snapshot.title is None
        and value.parent.snapshot.text == "/rfc/rfc9112.html"
    )
    assert value.child.snapshot.extractor_version == "static-html-utf8-v1"
    observation = await resolver.source.read(PARENT, "static")
    default = WebEvidenceService(resolver.source)
    with pytest.raises(WebEvidenceError, match="evidence_integrity"):
        default.validate_source(observation, PARENT, "static")
    for altered in [
        replace(observation, page=replace(observation.page, title="Forged title")),
        replace(observation, cache_seconds=300),
        replace(observation, page=replace(observation.page, text="Pretend full text")),
    ]:
        with pytest.raises(WebEvidenceError, match="evidence_integrity"):
            resolver.evidence.validate_source(altered, PARENT, "static")
    await default.shutdown()
    await resolver.shutdown()


class RedirectingClient(Client):
    """Answer the child URL with one redirect to an authored location."""

    def __init__(self, location):
        """Keep the authored redirect target beside the base client's ledger."""
        super().__init__()
        self.location = location

    async def get(self, url):
        """Redirect the child once and serve every other URL like the base client."""
        if url != CHILD:
            return await super().get(url)
        self.calls.append(url)
        return PublicResponse(301, (("location", self.location),), b"", "8.8.8.8")


@pytest.mark.asyncio
async def test_source_reads_parent_as_anchor_only_binding_without_capture():
    """A configured parent is fetched once through the anchor-only path and binds the observed child."""
    client = Client()
    source = PublisherSource(9112, client)
    observation = await source.read(PARENT, "static")
    assert client.calls == [PARENT]
    assert observation.page.extractor_version == "publisher-anchors-utf8-v1"
    final, child, sha, anchors = source.parent_binding
    assert (final, child, sha) == (PARENT, CHILD, hashlib.sha256(BODY).hexdigest())
    assert anchors[0][:2] == ("/rfc/rfc9112.html", CHILD)


@pytest.mark.asyncio
async def test_source_reads_child_without_touching_the_parent_binding(caplog):
    """A configured child goes through the capture, keeps the binding unset and logs the same event."""
    client = Client()
    source = PublisherSource(9112, client)
    with caplog.at_level("INFO", logger="src.infrastructure.publisher_links"):
        observation = await source.read(CHILD, "static")
    assert client.calls == [CHILD]
    assert observation.page.final_url == CHILD
    assert observation.page.extractor_version == "static-html-utf8-v1"
    assert source.parent_binding is None
    assert "publisher_original_source_read parent=False" in caplog.messages


@pytest.mark.asyncio
async def test_child_redirect_to_the_other_publisher_host_is_followed():
    """Both configured publisher hosts are valid child hops."""
    other = "https://rfc-editor.org/rfc/rfc9112.html"
    client = RedirectingClient(other)
    source = PublisherSource(9112, client)
    observation = await source.read(CHILD, "static")
    assert client.calls == [CHILD, other]
    assert observation.page.final_url == other
    assert source.parent_binding is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "location",
    [
        PARENT,
        "/info/rfc9112",
        "https://www.rfc-editor.org/rfc/rfc9111.html",
        "https://example.org/rfc/rfc9112.html",
        CHILD + "?token=x",
    ],
)
async def test_child_redirect_outside_the_full_text_path_never_reaches_transport(
    location,
):
    """The capture refuses a parent, another RFC, another host or a query before any request."""
    client = RedirectingClient(location)
    source = PublisherSource(9112, client)
    with pytest.raises(WebFetchError):
        await source.read(CHILD, "static")
    assert client.calls == [CHILD]
    assert source.parent_binding is None


@pytest.mark.asyncio
async def test_capture_checks_scope_first_and_keeps_no_body():
    """The capture validates before delegating and returns the response without retaining it."""
    client = Client()
    capture = PublisherCapture(client, 9112)
    with pytest.raises(ValueError, match="publisher_scope"):
        await capture.get(PARENT)
    assert client.calls == []
    response = await capture.get(CHILD)
    assert response.status == 200 and client.calls == [CHILD]
    assert vars(capture) == dict(client=client, number=9112)


@pytest.mark.asyncio
async def test_cancelled_child_read_joins_the_held_transport():
    """Cancelling a child read propagates and the held transport call exits."""
    client = Client()
    client.hold = True
    source = PublisherSource(9112, client)
    task = asyncio.create_task(source.read(CHILD, "static"))
    await asyncio.wait_for(client.entered.wait(), 2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert client.exited.is_set() and source.parent_binding is None
