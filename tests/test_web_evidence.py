"""Exercise owner-bound provenance, exact dedupe, truthful cache age, signed quote integrity and joined acquisition cancellation."""

import asyncio
import hashlib
import logging
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from src.application.ports.web_evidence import EvidenceResource, ObservedSource
from src.application.ports.web_fetch import FetchedPage
from src.application.services import web_evidence
from src.application.services.web_evidence import WebEvidenceService
from src.application.services.web_evidence_policy import WebEvidenceError

logger = logging.getLogger(__name__)
URL = "https://example.org/source"


class Clock:
    """Expose independent deterministic monotonic/aware UTC clocks without changing system time."""

    def __init__(self):
        """Start a stable authored clock for TTL and source-time assertions."""
        self.value, self.wall_adjustment = 100.0, 0.0

    def tick(self):
        """Return authored monotonic time without advancing it during synchronous policy checks."""
        return self.value

    def utc(self):
        """Return an independently adjustable aware UTC clock, never a page publication date."""
        return datetime(2026, 10, 21, tzinfo=UTC) + timedelta(
            seconds=self.value - 100 + self.wall_adjustment
        )


def observation(url=URL, text="Atlas G-17. Nội dung nguồn.", ttl=300):
    """Build explicit authored static source bytes with valid original source/resource/text hashes."""
    raw = ("<p>" + text + "</p>").encode()
    digest, body_digest = (
        hashlib.sha256(text.encode()).hexdigest(),
        hashlib.sha256(raw).hexdigest(),
    )
    page = FetchedPage(
        url, url, (), "text/html", "Authored source", text, body_digest, digest, None
    )
    return ObservedSource(
        page, (), (EvidenceResource(url, "Document", 200, len(raw), body_digest),), ttl
    )


class Source:
    """Return explicit authored source evidence without claiming a real native browser, network or TLS exchange."""

    def __init__(self, *, ttl=300, text="Atlas G-17. Nội dung nguồn."):
        """Bind immutable fixture content and a metadata-only call counter."""
        self.calls, self.ttl, self.text = [], ttl, text

    async def read(self, url, mode):
        """Record an explicit source acquisition and return only the requested authored source."""
        self.calls.append((url, mode))
        return observation(url, self.text, self.ttl)


def service(source=None):
    """Create an inert service with trusted authored source and separate monotonic/UTC test clocks."""
    clock = Clock()
    source = source if source is not None else Source()
    return (
        WebEvidenceService(source, monotonic=clock.tick, utcnow=clock.utc),
        source,
        clock,
    )


@pytest.mark.asyncio
async def test_cache_hit_has_zero_source_calls_and_preserves_original_fetch_provenance():
    """Expose original fetch time, separate serving time and monotonic age rather than refreshing cached evidence dates."""
    current, source, clock = service()
    owner = uuid4()
    assert not current.cache and not source.calls and not current.operations
    first = await current.read(owner, URL)
    clock.value += 25
    second = await current.read(owner, URL)
    assert not first.cache_hit and second.cache_hit and len(source.calls) == 1
    assert (
        second.snapshot is first.snapshot
        and second.snapshot.fetched_at == first.snapshot.fetched_at
    )
    assert second.served_at > first.served_at and second.acquisition_age_seconds == 25
    assert (
        first.snapshot.date_claims == () and first.snapshot.content_trust == "untrusted"
    )
    assert (
        not first.snapshot.semantic_validation and not first.snapshot.canonical_verified
    )
    assert 0 < current.cache_bytes() <= 4194304
    await current.shutdown()
    assert not current.cache and current.proof_key == b""


@pytest.mark.asyncio
async def test_exact_text_dedupe_retains_distinct_url_title_date_and_acquisition_identity():
    """Share only exact owner-local text while preserving each actual source URL and acquisition record."""
    current, source, _ = service()
    owner = uuid4()
    first = (await current.read(owner, URL)).snapshot
    second = (await current.read(owner, URL + "?edition=2")).snapshot
    assert first.identifier != second.identifier and first.final_url != second.final_url
    assert first.text is second.text and first.content_id == second.content_id
    assert first.resources != second.resources and len(source.calls) == 2
    other = (await current.read(uuid4(), URL)).snapshot
    assert other.content_id != first.content_id and len(source.calls) == 3
    source.text = first.text + " "
    changed = (await current.read(owner, URL + "/changed")).snapshot
    assert (
        changed.content_id != first.content_id
        and changed.text_sha256 != first.text_sha256
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "elapsed,hit", [(0, True), (299.999, True), (300, False), (301, False)]
)
async def test_ttl_boundary_is_monotonic_and_expired_entries_do_not_refresh_fetch_time(
    elapsed, hit
):
    """Expire exactly at the TTL without implicit stale reads or extending publisher lifetime."""
    current, source, clock = service()
    owner = uuid4()
    first = await current.read(owner, URL)
    clock.value += elapsed
    result = await current.read(owner, URL)
    assert result.cache_hit is hit and len(source.calls) == (1 if hit else 2)
    assert (result.snapshot.identifier == first.snapshot.identifier) is hit


@pytest.mark.asyncio
async def test_no_store_result_is_never_retained_but_issued_exact_span_can_be_verified():
    """Build owner-bound references from signed returned snapshots without keeping a reusable no-store cache entry."""
    current, source, _ = service(Source(ttl=0))
    owner = uuid4()
    first = (await current.read(owner, URL)).snapshot
    second = await current.read(owner, URL)
    assert len(source.calls) == 2 and not second.cache_hit and not current.cache
    reference = current.cite(owner, first, 0, len(first.text))
    assert reference.quote == first.text and reference.quote_sha256 == first.text_sha256
    assert (
        reference.snapshot_id == first.identifier
        and reference.final_url == first.final_url
    )
    assert reference.fetched_at == first.fetched_at and reference.date_claims == ()
    assert reference.semantic_validation is False


@pytest.mark.asyncio
async def test_force_fresh_never_silently_falls_back_to_old_valid_cache(monkeypatch):
    """A failed explicit fresh acquisition remains a failure even when prior source evidence is still cached."""
    current, source, _ = service()
    owner = uuid4()
    await current.read(owner, URL)

    async def fail(url, mode):
        """Fail an authored acquisition without making any public request or returning stale evidence."""
        raise RuntimeError("PRIVATE-UPSTREAM-DETAIL")

    monkeypatch.setattr(source, "read", fail)
    with pytest.raises(WebEvidenceError, match="evidence_source_failed"):
        await current.read(owner, URL, use_cache=False)
    assert (await current.read(owner, URL)).cache_hit


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "field,value",
    [
        ("title", "Forged title"),
        ("final_url", "https://example.org/forged"),
        ("text", "Forged text"),
        ("text_sha256", "0" * 64),
        ("content_id", "0" * 64),
        ("citation_deadline", 99999999.0),
        ("proof", "0" * 64),
        ("semantic_validation", True),
        ("date_claims", ()),
    ],
)
async def test_source_snapshot_proof_detects_field_changes(field, value):
    """Reject every changed source/content/time/trust field without issuing a fabricated reference."""
    current, _, _ = service()
    owner = uuid4()
    original = (await current.read(owner, URL)).snapshot
    if field == "date_claims":
        from src.application.services.web_evidence_policy import date_claim

        value = (date_claim("published", "2026-10-20"),)
    with pytest.raises(WebEvidenceError, match="evidence_integrity"):
        current.cite(owner, replace(original, **{field: value}), 0, 5)


@pytest.mark.asyncio
async def test_owner_cross_service_expired_or_closed_reference_authority_is_denied():
    """Prevent another owner/service or expired proof from manufacturing source access while preserving copied immutable references."""
    current, _, clock = service()
    owner = uuid4()
    snapshot = (await current.read(owner, URL)).snapshot
    with pytest.raises(WebEvidenceError, match="evidence_integrity"):
        current.cite(uuid4(), snapshot, 0, 5)
    other, _, _ = service()
    with pytest.raises(WebEvidenceError, match="evidence_integrity"):
        other.cite(owner, snapshot, 0, 5)
    clock.value += 300
    with pytest.raises(WebEvidenceError, match="evidence_expired"):
        current.cite(owner, snapshot, 0, 5)
    await current.shutdown()
    with pytest.raises(WebEvidenceError, match="evidence_closed"):
        current.cite(owner, snapshot, 0, 5)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "start,end",
    [(-1, 5), (0, 0), (3, 2), (0, 1000), (True, 5), (0, False), ("0", 5), (0.0, 5)],
)
async def test_exact_quote_indices_are_codepoints_and_cannot_use_python_negative_or_bool_indexing(
    start, end
):
    """Reject invalid exact-span requests rather than silently clipping or repairing their evidence."""
    current, _, _ = service()
    owner = uuid4()
    snapshot = (await current.read(owner, URL)).snapshot
    with pytest.raises(WebEvidenceError, match="evidence_invalid"):
        current.cite(owner, snapshot, start, end)


@pytest.mark.asyncio
async def test_unicode_span_bytes_and_quote_budget_are_exact():
    """Copy Vietnamese Unicode code-point spans without whitespace normalization and enforce4096UTF-8-byte quote bounds."""
    current, _, _ = service(Source(text="Nguồn Việt Nam " + "x" * 4097))
    owner = uuid4()
    snapshot = (await current.read(owner, URL)).snapshot
    reference = current.cite(owner, snapshot, 0, len("Nguồn Việt Nam"))
    assert reference.quote == "Nguồn Việt Nam"
    with pytest.raises(WebEvidenceError, match="evidence_limit"):
        current.cite(owner, snapshot, 0, len(snapshot.text))


@pytest.mark.asyncio
async def test_owner_and_global_lru_entry_and_byte_bounds_remain_finite():
    """Apply four-per-owner/sixteen-global retention while keeping all exact prior returned snapshots independently verifiable."""
    current, source, _ = service(Source(text="x" * 120000))
    owner = uuid4()
    first = (await current.read(owner, URL)).snapshot
    for index in range(5):
        await current.read(owner, URL + f"?page={index}")
    assert len(current.cache) == 4 and (owner, "static", URL) not in current.cache
    assert current.cite(owner, first, 0, 5).quote == "xxxxx"
    for index in range(20):
        await current.read(uuid4(), URL + f"?owner-page={index}")
    assert len(current.cache) == 16 and current.cache_bytes() <= 4194304
    assert len(source.calls) == 26


@pytest.mark.asyncio
@pytest.mark.parametrize("value", [-1, float("nan"), float("inf"), True, "100"])
async def test_invalid_monotonic_clock_fails_before_source_io_and_closes_admission(
    value,
):
    """Refuse invalid clock inputs rather than granting unlimited cache lifetime or accepting false age evidence."""
    current, source, clock = service()
    clock.value = value
    with pytest.raises(WebEvidenceError, match="evidence_clock_invalid"):
        await current.read(uuid4(), URL)
    assert not source.calls and current.closing


@pytest.mark.asyncio
async def test_backward_monotonic_and_naive_host_wall_clock_are_denied():
    """Distinguish trusted host clock failures from untrusted publication dates without changing system clocks."""
    current, _, clock = service()
    owner = uuid4()
    await current.read(owner, URL)
    clock.value -= 1
    with pytest.raises(WebEvidenceError, match="evidence_clock_invalid"):
        await current.read(owner, URL)
    other, source, _ = service()
    other.utcnow = lambda: datetime(2026, 10, 21)
    with pytest.raises(WebEvidenceError, match="evidence_clock_invalid"):
        await other.read(owner, URL)
    assert not source.calls


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "owner,url,mode,use_cache",
    [
        ("owner", URL, "static", True),
        (None, URL, "static", True),
        (uuid4(), "http://127.0.0.1/", "static", True),
        (uuid4(), URL, "auto", True),
        (uuid4(), URL, [], True),
        (uuid4(), URL, "static", 1),
    ],
)
async def test_invalid_owner_url_mode_and_cache_flags_do_not_start_acquisition(
    owner, url, mode, use_cache
):
    """Reject nonexplicit identity/mode/cache authority before consulting a source port."""
    current, source, _ = service()
    with pytest.raises(WebEvidenceError, match="evidence_invalid"):
        await current.read(owner, url, mode, use_cache=use_cache)
    assert not source.calls and not current.cache and not current.operations


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mutation",
    [
        "text_hash",
        "requested_url",
        "verified",
        "body_hash",
        "no_resources",
        "ttl_bool",
        "ttl_high",
        "text_overflow",
    ],
)
async def test_invalid_source_result_never_becomes_signed_or_cached(mutation):
    """Reject complete trusted-port provenance drift and overbudget values before issuing reusable source evidence."""
    current, source, _ = service()

    async def invalid(url, mode):
        """Return one authored malformed source result without any public requests."""
        result = observation(url)
        if mutation == "text_hash":
            return replace(result, page=replace(result.page, text_sha256="0" * 64))
        if mutation == "requested_url":
            return replace(
                result, page=replace(result.page, requested_url=URL + "/other")
            )
        if mutation == "verified":
            return replace(result, page=replace(result.page, canonical_verified=True))
        if mutation == "body_hash":
            return replace(result, page=replace(result.page, body_sha256="0" * 64))
        if mutation == "no_resources":
            return replace(result, resources=())
        if mutation == "text_overflow":
            return observation(url, text="x" * 131073)
        return replace(result, cache_seconds=True if mutation == "ttl_bool" else 301)

    source.read = invalid
    with pytest.raises(WebEvidenceError):
        await current.read(uuid4(), URL)
    assert (
        not current.cache and not current.operations and not current.admission.locked()
    )


@pytest.mark.asyncio
async def test_repeated_cancel_retains_busy_fence_until_source_cleanup_and_never_caches():
    """Join a cancellation-resistant owned cleanup before releasing admission or allowing another source acquisition."""
    entered, cleanup, release = asyncio.Event(), asyncio.Event(), asyncio.Event()
    current, source, _ = service()

    async def held(url, mode):
        """Model source cancellation cleanup that cannot finish until its explicit acknowledgment is released."""
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            cleanup.set()
            await release.wait()

    source.read = held
    task = asyncio.create_task(current.read(uuid4(), URL))
    await entered.wait()
    task.cancel()
    await cleanup.wait()
    task.cancel()
    with pytest.raises(WebEvidenceError, match="evidence_busy"):
        await current.read(uuid4(), URL)
    assert not task.done() and not current.cache
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert (
        not current.operations and not current.cache and not current.admission.locked()
    )


@pytest.mark.asyncio
async def test_cleanup_uncertainty_closes_cancelled_adapter_and_shutdown_only_joins_owned_callers():
    """Propagate uncertainty into admission state without cancelling an unrelated task or retaining partial evidence."""
    from src.application.services.browser_policy import BrowserError

    current, source, _ = service()
    entered = asyncio.Event()

    async def uncertain(url, mode):
        """Fail native cleanup after cancellation without returning a source page."""
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            raise BrowserError("browser_cleanup_uncertain")

    source.read = uncertain
    task = asyncio.create_task(current.read(uuid4(), URL))
    unrelated = asyncio.create_task(asyncio.Event().wait())
    await entered.wait()
    await current.shutdown()
    assert task.cancelled() and not unrelated.done() and current.closing
    assert not current.operations and not current.cache
    unrelated.cancel()
    with pytest.raises(asyncio.CancelledError):
        await unrelated


@pytest.mark.asyncio
async def test_dispatch_failure_closes_unadmitted_source_and_releases_admission(
    monkeypatch,
):
    """Avoid unawaited source coroutines or stuck busy state if the operation task cannot be created."""
    import inspect

    pending = []

    def unavailable(coroutine):
        """Close the unadmitted coroutine and inject a deterministic task-dispatch failure."""
        pending.append(coroutine)
        coroutine.close()
        raise RuntimeError("PRIVATE-DISPATCH-DETAIL")

    monkeypatch.setattr(web_evidence, "spawn_owned", unavailable)
    current, source, _ = service()
    with pytest.raises(WebEvidenceError, match="evidence_source_failed"):
        await current.read(uuid4(), URL)
    assert inspect.getcoroutinestate(pending[0]) == inspect.CORO_CLOSED
    assert (
        not source.calls and not current.operations and not current.admission.locked()
    )


@pytest.mark.asyncio
async def test_snapshots_references_and_logs_do_not_echo_private_source_payload(caplog):
    """Keep ordinary repr and audit logs free of URL queries, page text, titles and ephemeral proof values."""
    caplog.set_level(logging.INFO)
    current, _, _ = service(Source(text="PRIVATE-CONTENT-CANARY"))
    owner = uuid4()
    result = await current.read(owner, URL + "?q=PRIVATE-QUERY-CANARY")
    ref = current.cite(owner, result.snapshot, 0, 5)
    for value in [
        "PRIVATE-CONTENT-CANARY",
        "PRIVATE-QUERY-CANARY",
        result.snapshot.proof,
        str(owner),
    ]:
        assert value not in caplog.text
        assert (
            value not in repr(result)
            and value not in repr(result.snapshot)
            and value not in repr(ref)
        )
    logger.info("web_evidence_private_provenance_redaction_verified")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mutation",
    [
        "extra_script",
        "missing_redirect",
        "wrong_chain",
        "canonical_private",
        "resource_status",
        "resource_body_size",
        "resource_hash",
        "date_verified",
    ],
)
async def test_resource_chain_and_unverified_date_contract_cannot_drift(mutation):
    """Refuse source/resource/redirect/date inconsistencies before signing an acquisition record."""
    from src.application.services.web_evidence_policy import date_claim

    current, source, _ = service()

    async def invalid(url, mode):
        """Return one authored inconsistent acquisition without changing accepted fetch/browser primitives."""
        result = observation(url)
        resource = result.resources[0]
        if mutation == "extra_script":
            return replace(
                result, resources=result.resources + (replace(resource, kind="Script"),)
            )
        if mutation == "missing_redirect":
            return replace(
                result, page=replace(result.page, redirects=((url, url + "/final"),))
            )
        if mutation == "wrong_chain":
            return replace(
                result,
                page=replace(result.page, redirects=((url + "/wrong", url),)),
                resources=(replace(resource, status=302), resource),
            )
        if mutation == "canonical_private":
            return replace(
                result,
                page=replace(
                    result.page, advertised_canonical_url="https://127.0.0.1/private"
                ),
            )
        if mutation == "date_verified":
            return replace(
                result,
                dates=(replace(date_claim("published", "2026-10-20"), verified=True),),
            )
        changes = {
            "resource_status": dict(status=True),
            "resource_body_size": dict(body_bytes=1048577),
            "resource_hash": dict(body_sha256="not-a-hash"),
        }
        return replace(result, resources=(replace(resource, **changes[mutation]),))

    source.read = invalid
    with pytest.raises(WebEvidenceError):
        await current.read(uuid4(), URL)
    assert not current.cache


@pytest.mark.asyncio
async def test_acquisition_duration_is_subtracted_from_short_upstream_lifetime():
    """Do not restart max-age after source rendering/cleanup has already consumed its advertised freshness budget."""
    current, source, clock = service(Source(ttl=10))

    async def slow(url, mode):
        """Consume the entire authored source freshness lifetime before returning complete evidence."""
        clock.value += 10
        return observation(url, ttl=10)

    source.read = slow
    result = await current.read(uuid4(), URL)
    assert not result.cache_hit and not current.cache
