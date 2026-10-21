"""Exercise fixed research budgets, whole-plan admission, truthful partial outcomes, quota accounting and joined cancellation without live inference."""

import asyncio
import hashlib
import json
import logging
from dataclasses import FrozenInstanceError, replace
from uuid import uuid4

import pytest

from src.application.ports.inference import CompletionResult
from src.application.ports.search import SearchBatch, SearchHit
from src.application.services import research as module
from src.application.services.research import ResearchService
from src.application.services.research_policy import ResearchError

logger = logging.getLogger(__name__)


class Core:
    """Return an explicitly authored plan while observing the exact host-selected options and optional ownership boundary."""

    def __init__(self, queries=None):
        """Prepare a controlled completion and empty port calls without a real model or network request."""
        self.calls = []
        self.result = CompletionResult(
            json.dumps(
                dict(
                    queries=queries
                    if queries is not None
                    else ["SearXNG JSON API", "RFC9111 cache"]
                )
            ),
            "fixture-core",
            "fast",
            "stop",
        )

    async def complete(self, **options):
        """Record one fixed host-selected inference call and return the unchanged authored response."""
        self.calls.append(options)
        return self.result


class Provider:
    """Supply only authored immutable batches without fetching source URLs or invoking an external provider."""

    def __init__(self):
        """Bind a complete synthetic source and empty attempt trace."""
        self.calls = []
        self.hit = SearchHit(
            "Original source",
            "https://example.org/source",
            "Original untrusted snippet G-17.",
        )

    async def search(self, **options):
        """Return a complete trusted-port fixture without interpreting its text or changing a source URL."""
        self.calls.append(options)
        return SearchBatch("fixture", (self.hit,))


def configured(core=None, provider=None):
    """Create inert controlled dependencies and the same finite runtime policy used by the internal service."""
    core = core if core is not None else Core()
    provider = provider if provider is not None else Provider()
    return (
        ResearchService(
            provider_id="fixture",
            provider=provider,
            inference=core,
            expected_model="fixture-core",
        ),
        core,
        provider,
    )


@pytest.mark.asyncio
async def test_fixed_model_and_sequential_complete_sources_preserve_identity_hash_and_unknown_states(
    caplog,
):
    """Bind every query/source to the original bytes while exposing attempts without generating a researched answer/date."""
    caplog.set_level(logging.INFO)
    service, core, provider = configured()
    owner = uuid4()
    assert not core.calls and not provider.calls and not service.operations
    result = await service.research(owner, "  Explicit   PRIVATE-GOAL-CANARY ")
    assert (
        result.goal == "Explicit PRIVATE-GOAL-CANARY"
        and result.owner_id == owner
        and result.status == "complete"
    )
    assert (
        result.model_attempts == 1
        and result.provider_attempts == 2
        and service.quota.total == 3
    )
    assert {k: v for k, v in core.calls[0].items() if k != "messages"} == dict(
        profile="core", preset="fast", temperature=0, max_tokens=512
    )
    assert str(owner) not in json.dumps(core.calls) and [
        row.query_id for row in result.queries
    ] == ["Q1", "Q2"]
    assert provider.calls == [
        dict(query="SearXNG JSON API", max_results=5),
        dict(query="RFC9111 cache", max_results=5),
    ]
    for row in result.queries:
        source = row.sources[0]
        assert (
            source.source_id == row.query_id + ":S1"
            and source.url == provider.hit.url
            and source.snippet == provider.hit.snippet
        )
        assert (
            source.snippet_sha256
            == hashlib.sha256(provider.hit.snippet.encode()).hexdigest()
        )
        assert row.attempted and row.received_at.tzinfo is not None
    assert (
        result.content_trust == "untrusted"
        and result.evidence_kind == "provider_snippet_not_fetched"
    )
    assert result.semantic_validation is False and result.verified_freshness is None
    assert (
        "PRIVATE-GOAL-CANARY" not in caplog.text
        and provider.hit.snippet not in caplog.text
        and str(owner) not in caplog.text
    )
    assert "PRIVATE-GOAL-CANARY" not in repr(result)
    with pytest.raises(FrozenInstanceError):
        result.status = "forged"
    await service.shutdown()


@pytest.mark.asyncio
async def test_invalid_tail_plan_is_fully_rejected_before_first_provider_and_charges_model_only():
    """Validate every proposed query before dispatch instead of running the good prefix and discarding unauthorized tail data."""
    service, core, provider = configured(Core(["valid query", "!brave override"]))
    with pytest.raises(ResearchError, match="research_plan_invalid"):
        await service.research(uuid4(), "Explicit public goal")
    assert len(core.calls) == 1 and not provider.calls and service.quota.total == 1
    assert not service.operations and not service.admission.locked()


@pytest.mark.asyncio
async def test_provider_failure_and_empty_results_are_preserved_without_retry_or_fabricated_claim(
    monkeypatch,
):
    """Return partial source state and original errors while every planned query is attempted at mostonce."""
    service, _, provider = configured(Core(["first", "second", "third"]))

    async def respond(**options):
        """Produce one source, one failure and one empty outcome with an exact observable call count."""
        provider.calls.append(options)
        if len(provider.calls) == 2:
            raise RuntimeError("PRIVATE-PROVIDER-ERROR")
        return SearchBatch(
            "fixture", (provider.hit,) if len(provider.calls) == 1 else ()
        )

    monkeypatch.setattr(provider, "search", respond)
    result = await service.research(uuid4(), "Explicit public goal")
    assert result.status == "partial" and [row.status for row in result.queries] == [
        "sources",
        "error",
        "empty",
    ]
    assert (
        result.queries[1].error_code == "research_provider_failed"
        and result.provider_attempts == 3
    )
    assert len(provider.calls) == 3 and service.quota.total == 4


@pytest.mark.asyncio
async def test_quota_is_charged_per_attempt_without_refund_and_stops_remaining_queries_before_dispatch():
    """Keep four-owner/sixteen-global counters finite and expose quota-not-run queries rather than silently dropping them."""
    service, core, provider = configured()
    owner = uuid4()
    await service.research(owner, "Explicit goal")
    second = await service.research(owner, "Explicit goal")
    assert second.status == "no_sources" and all(
        row.status == "not_run_quota" and not row.attempted for row in second.queries
    )
    assert second.provider_attempts == 0 and service.quota.total == 4
    with pytest.raises(ResearchError, match="research_rate_limited"):
        await service.research(owner, "Explicit goal")
    assert len(core.calls) == 2 and len(provider.calls) == 2


@pytest.mark.asyncio
async def test_global_attempt_quota_does_not_grow_unbounded_owner_counters():
    """Cap four full three-query owners at16 charged attempts and reject a fifth before inference."""
    service, core, provider = configured(Core(["first", "second", "third"]))
    for _ in range(4):
        await service.research(uuid4(), "Explicit goal")
    with pytest.raises(ResearchError, match="research_rate_limited"):
        await service.research(uuid4(), "Explicit goal")
    assert (
        service.quota.total == 16
        and len(service.quota.owners) == 4
        and len(core.calls) == 4
        and len(provider.calls) == 12
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["model", "provider"])
async def test_stage_deadline_joins_owned_cleanup_before_releasing_admission(
    stage, monkeypatch
):
    """Bound model/provider waiting without an automatic retry or publishing a result before cleanup acknowledgment."""
    service, core, provider = configured(Core(["one"]))
    cleaned = asyncio.Event()

    async def held(**options):
        """Hold a controlled backend until its owning deadline cancels and completes finite cleanup."""
        try:
            await asyncio.Event().wait()
        finally:
            cleaned.set()

    monkeypatch.setattr(
        core if stage == "model" else provider,
        "complete" if stage == "model" else "search",
        held,
    )
    monkeypatch.setattr(
        module, "MODEL_SECONDS" if stage == "model" else "PROVIDER_SECONDS", 0.01
    )
    if stage == "model":
        with pytest.raises(ResearchError, match="research_model_timeout"):
            await service.research(uuid4(), "Explicit goal")
        assert not provider.calls
    else:
        result = await service.research(uuid4(), "Explicit goal")
        assert (
            result.status == "no_sources"
            and result.queries[0].error_code == "research_provider_timeout"
        )
    assert (
        cleaned.is_set() and not service.operations and not service.admission.locked()
    )


@pytest.mark.asyncio
async def test_total_deadline_marks_inflight_and_unattempted_queries_truthfully(
    monkeypatch,
):
    """Stop dispatch at the run deadline while preserving prior source success and distinguishing attempted timeout from unrun work."""
    service, _, provider = configured(Core(["one", "two", "three"]))

    async def respond(**options):
        """Return the first source then block the second until the outer run budget cancels it."""
        provider.calls.append(options)
        if len(provider.calls) == 1:
            return SearchBatch("fixture", (provider.hit,))
        await asyncio.Event().wait()

    monkeypatch.setattr(provider, "search", respond)
    monkeypatch.setattr(module, "TOTAL_SECONDS", 0.02)
    result = await service.research(uuid4(), "Explicit goal")
    assert (
        result.status == "partial"
        and result.provider_attempts == 2
        and len(provider.calls) == 2
    )
    assert [row.status for row in result.queries] == [
        "sources",
        "error",
        "not_run_budget",
    ]
    assert [row.attempted for row in result.queries] == [True, True, False]


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["model", "provider"])
async def test_repeated_cancellation_holds_busy_until_backend_cleanup_and_shutdown_owns_only_its_callers(
    stage, monkeypatch
):
    """Keep admission pinned under repeated cancellation without cancelling unrelated work or exposing a late result."""
    service, core, provider = configured(Core(["one"]))
    entered, cleanup, release = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def held(**options):
        """Model backend resources whose cleanup cannot finish until its explicit acknowledgment is released."""
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            cleanup.set()
            await release.wait()

    monkeypatch.setattr(
        core if stage == "model" else provider,
        "complete" if stage == "model" else "search",
        held,
    )
    task = asyncio.create_task(service.research(uuid4(), "Explicit goal"))
    await entered.wait()
    task.cancel()
    await cleanup.wait()
    task.cancel()
    with pytest.raises(ResearchError, match="research_busy"):
        await service.research(uuid4(), "Another goal")
    assert not task.done() and service.admission.locked()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    unrelated = asyncio.create_task(asyncio.Event().wait())
    await service.shutdown()
    assert not unrelated.done()
    unrelated.cancel()
    with pytest.raises(asyncio.CancelledError):
        await unrelated
    assert not service.operations and not service.admission.locked()


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["model", "provider"])
async def test_swallowed_dependency_cancellation_cannot_start_more_queries_or_publish(
    stage, monkeypatch
):
    """Reject late successful port data when its owning run was already cancelled instead of publishing it or continuing execution."""
    service, core, provider = configured(Core(["one", "two"]))
    entered = asyncio.Event()

    async def suppress(**options):
        """Return a controlled valid result after swallowing cancellation to challenge the host ownership fence."""
        entered.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            return (
                core.result
                if stage == "model"
                else SearchBatch("fixture", (provider.hit,))
            )

    monkeypatch.setattr(
        core if stage == "model" else provider,
        "complete" if stage == "model" else "search",
        suppress,
    )
    task = asyncio.create_task(service.research(uuid4(), "Explicit goal"))
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert (
        not provider.calls and not service.operations and not service.admission.locked()
    )


@pytest.mark.asyncio
async def test_operation_dispatch_failure_closes_coroutine_and_retains_charged_attempt(
    monkeypatch,
):
    """Close an unadmitted task and release the busy fence without refunding an already admitted attempt."""
    import inspect

    pending = []

    def unavailable(coroutine):
        """Inject dispatch failure after closing the unstarted owned run coroutine."""
        pending.append(coroutine)
        coroutine.close()
        raise RuntimeError("PRIVATE-DISPATCH")

    service, core, provider = configured()
    monkeypatch.setattr(module, "spawn_owned", unavailable)
    with pytest.raises(ResearchError, match="research_internal"):
        await service.research(uuid4(), "Explicit goal")
    assert inspect.getcoroutinestate(pending[0]) == inspect.CORO_CLOSED
    assert (
        service.quota.total == 1
        and not core.calls
        and not provider.calls
        and not service.operations
        and not service.admission.locked()
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mutation", ["wrong_provider", "invalid_tail", "oversized_escaped_result"]
)
async def test_whole_batch_identity_and_complete_result_limits_do_not_clip_or_publish_invalid_sources(
    mutation, monkeypatch
):
    """Reject malformed complete batches per query and complete oversized runs without dropping an inconvenient source tail."""
    service, _, provider = configured(Core(["one", "two", "three"]))

    async def malformed(**options):
        """Return an authored wrong-identity/bad-tail/overescaped batch with no external provider call."""
        provider.calls.append(options)
        if mutation == "wrong_provider":
            return SearchBatch("foreign", (provider.hit,))
        if mutation == "invalid_tail":
            return SearchBatch(
                "fixture", (provider.hit, replace(provider.hit, url="http://private/"))
            )
        return SearchBatch(
            "fixture",
            tuple(replace(provider.hit, snippet="\x01" * 2048) for _ in range(5)),
        )

    monkeypatch.setattr(provider, "search", malformed)
    if mutation == "oversized_escaped_result":
        with pytest.raises(ResearchError, match="research_result_limit"):
            await service.research(uuid4(), "Explicit goal")
    else:
        result = await service.research(uuid4(), "Explicit goal")
        assert result.status == "no_sources" and all(
            row.status == "error" and not row.sources for row in result.queries
        )
    assert (
        len(provider.calls) == 3
        and not service.operations
        and not service.admission.locked()
    )


@pytest.mark.asyncio
async def test_invalid_closed_and_unavailable_inputs_have_zero_backend_or_quota_effect():
    """Keep rejected input/default-off/closed work inert before admission without reading keys or creating external tasks."""
    service, core, provider = configured()
    with pytest.raises(ResearchError, match="research_invalid"):
        await service.research("forged-owner", "Explicit goal")
    with pytest.raises(ResearchError, match="research_invalid"):
        await service.research(uuid4(), "!brave goal")
    service.provider = None
    with pytest.raises(ResearchError, match="research_unavailable"):
        await service.research(uuid4(), "Explicit goal")
    await service.shutdown()
    with pytest.raises(ResearchError, match="research_closed"):
        await service.research(uuid4(), "Explicit goal")
    assert not core.calls and not provider.calls and service.quota.total == 0
    logger.info("research_controlled_budget_ownership_and_inertness_verified")


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["model", "provider"])
async def test_suppressed_stage_timeout_is_not_a_successful_late_plan_or_source(
    stage, monkeypatch
):
    """Reject late valid data even when a dependency consumes the stage timeout and its context clears cancellation count."""
    service, core, provider = configured(Core(["one"]))

    async def suppress(**options):
        """Return authored valid data only after the stage deadline's cancellation has been swallowed."""
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            return (
                core.result
                if stage == "model"
                else SearchBatch("fixture", (provider.hit,))
            )

    monkeypatch.setattr(
        core if stage == "model" else provider,
        "complete" if stage == "model" else "search",
        suppress,
    )
    monkeypatch.setattr(
        module, "MODEL_SECONDS" if stage == "model" else "PROVIDER_SECONDS", 0.01
    )
    if stage == "model":
        with pytest.raises(ResearchError, match="research_model_timeout"):
            await service.research(uuid4(), "Explicit goal")
        assert not provider.calls
    else:
        result = await service.research(uuid4(), "Explicit goal")
        assert (
            result.queries[0].status == "error"
            and result.queries[0].error_code == "research_provider_timeout"
        )
        assert not result.queries[0].sources


@pytest.mark.asyncio
async def test_active_shutdown_waits_for_owned_cleanup_and_preserves_unrelated_task(
    monkeypatch,
):
    """Close new admission and join an active backend's cancellation cleanup without touching another service task."""
    service, core, provider = configured()
    entered, cleanup, release = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def held(**options):
        """Hold an actual owning caller until shutdown cancellation cleanup is explicitly acknowledged."""
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            cleanup.set()
            await release.wait()

    monkeypatch.setattr(core, "complete", held)
    active = asyncio.create_task(service.research(uuid4(), "Explicit goal"))
    unrelated = asyncio.create_task(asyncio.Event().wait())
    await entered.wait()
    closing = asyncio.create_task(service.shutdown())
    await cleanup.wait()
    assert service.closing and not closing.done() and not unrelated.done()
    with pytest.raises(ResearchError, match="research_closed"):
        await service.research(uuid4(), "Another goal")
    release.set()
    await closing
    assert (
        active.cancelled()
        and not provider.calls
        and not service.operations
        and not service.admission.locked()
    )
    unrelated.cancel()
    with pytest.raises(asyncio.CancelledError):
        await unrelated


@pytest.mark.asyncio
async def test_total_budget_exhausted_before_a_plan_never_dispatches_provider(
    monkeypatch,
):
    """Report a total planning deadline without fabricating an empty/partial plan when no valid model result exists."""
    service, core, provider = configured()

    async def held(**options):
        """Await cancellation from the enclosing run budget without returning a plan."""
        await asyncio.Event().wait()

    monkeypatch.setattr(core, "complete", held)
    monkeypatch.setattr(module, "TOTAL_SECONDS", 0.01)
    with pytest.raises(ResearchError, match="research_timeout"):
        await service.research(uuid4(), "Explicit goal")
    assert (
        not provider.calls
        and service.quota.total == 1
        and not service.operations
        and not service.admission.locked()
    )


@pytest.mark.parametrize(
    "provider_id,expected_model",
    [("Bad/provider", "fixture-core"), ("fixture", ""), ("fixture", None)],
)
def test_untrusted_construction_metadata_cannot_select_an_unbounded_port_identity(
    provider_id, expected_model
):
    """Reject invalid trusted-composition identities before any source/model/quota side effect is created."""
    with pytest.raises(ResearchError, match="research_invalid"):
        ResearchService(
            provider_id=provider_id,
            provider=None,
            inference=None,
            expected_model=expected_model,
        )
