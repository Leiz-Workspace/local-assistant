"""Verify response-owned admission, quotas, child cancellation joins and search shutdown without real provider calls."""

import asyncio
import logging
from uuid import uuid4

import pytest
from test_search_pipeline import FixtureCore, FixtureSearch
from test_web_search_policy import FakeClock

from apps.api.services import web_search as module
from apps.api.services.web_search import WebSearchService
from src.application.services.search_pipeline import SearchPipeline
from src.application.services.web_search_policy import WebSearchError

logger = logging.getLogger(__name__)


def service():
    """Bind the accepted pipeline to deterministic controlled ports and a private test quota window."""
    return WebSearchService(
        SearchPipeline(
            provider_id="fixture", provider=FixtureSearch(), inference=FixtureCore()
        ),
        clock=FakeClock(),
    )


@pytest.mark.asyncio
async def test_normalized_request_slot_is_owned_through_delivery_context():
    """Retain admission after generation until the response closes, denying queued work without quota charge."""
    current = service()
    owner = uuid4()
    async with current.operation(owner, "  Atlas   JSON ") as payload:
        assert payload["query"] == "Atlas JSON" and payload["normalization_applied"]
        assert current.admission.locked() and len(current.operations) == 1
        with pytest.raises(WebSearchError, match="web_search_busy"):
            async with current.operation(uuid4(), "second"):
                pytest.fail("busy operation entered")
        assert current.quota.total == 1
        assert current.pipeline.provider.calls == [
            dict(query="Atlas JSON", max_results=5)
        ]
    assert not current.admission.locked() and not current.operations
    assert current.quota.total == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("query", ["", "!bing source", "x\nsecret", "x" * 513])
async def test_precondition_rejection_has_no_quota_or_child(query):
    """Refuse invalid explicit queries before reserving rate, request or provider capacity."""
    current = service()
    with pytest.raises(WebSearchError):
        async with current.operation(uuid4(), query):
            pytest.fail("invalid operation entered")
    assert (
        current.quota.total == 0
        and not current.admission.locked()
        and not current.operations
    )
    assert current.pipeline.provider.calls == current.pipeline.inference.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "stage,expected",
    [
        ("provider", "web_search_provider_unavailable"),
        ("model", "web_search_model_unavailable"),
    ],
)
async def test_failed_attempt_is_sanitized_charged_and_joined(stage, expected, caplog):
    """Retain charged admission after a dependency error while hiding private diagnostics and releasing resources."""
    caplog.set_level(logging.INFO)
    current = service()
    dependency = (
        current.pipeline.provider if stage == "provider" else current.pipeline.inference
    )
    dependency.error = RuntimeError("private-credential-error")
    with pytest.raises(WebSearchError, match=expected):
        async with current.operation(uuid4(), "private-query-fixture"):
            pytest.fail("failed operation entered")
    assert current.quota.total == 1 and dependency.cleaned
    assert not current.admission.locked() and not current.operations
    assert (
        "private-credential-error" not in caplog.text
        and "private-query-fixture" not in caplog.text
    )


@pytest.mark.asyncio
async def test_task_creation_failure_closes_coroutine_and_retains_reservation(
    monkeypatch,
):
    """Fail safely before provider execution without orphaning a coroutine or refunding an admitted slot."""
    current = service()

    def fail_task(coroutine):
        """Inject a task-creation failure before ownership transfers from the service."""
        raise RuntimeError("controlled-task-create")

    monkeypatch.setattr(module, "create_task", fail_task)
    with pytest.raises(RuntimeError, match="controlled-task-create"):
        async with current.operation(uuid4(), "atlas"):
            pytest.fail("failed dispatch entered")
    assert (
        current.quota.total == 1
        and not current.operations
        and not current.admission.locked()
    )
    assert current.pipeline.provider.calls == current.pipeline.inference.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["provider", "model"])
async def test_dependency_deadline_is_sanitized_charged_and_joined(stage, monkeypatch):
    """Map the accepted pipeline deadlines without releasing admission before dependency cleanup."""
    from src.application.services import search_pipeline

    current = service()
    dependency = (
        current.pipeline.provider if stage == "provider" else current.pipeline.inference
    )
    dependency.release = asyncio.Event()
    monkeypatch.setattr(
        search_pipeline,
        "SEARCH_SECONDS" if stage == "provider" else "CORE_SECONDS",
        0.01,
    )
    with pytest.raises(WebSearchError, match="web_search_timeout") as observed:
        async with current.operation(uuid4(), "atlas"):
            pytest.fail("timed-out operation entered")
    assert observed.value.status_code == 504
    assert dependency.cleaned and current.quota.total == 1
    assert not current.operations and not current.admission.locked()


@pytest.mark.asyncio
async def test_invalid_completion_is_rejected_without_exposing_generated_content():
    """Map a malformed generated answer to a finite gateway error with charged quota and joined work."""
    current = service()
    current.pipeline.inference = FixtureCore("private-invalid-generated-answer")
    with pytest.raises(WebSearchError, match="web_search_pipeline_invalid") as observed:
        async with current.operation(uuid4(), "atlas"):
            pytest.fail("invalid completion entered")
    assert observed.value.status_code == 502
    assert (
        current.quota.total == 1
        and not current.operations
        and not current.admission.locked()
    )


class SlowCleanupPipeline:
    """Hold owned cancellation cleanup so repeated caller cancellation can be observed without an external dependency."""

    def __init__(self):
        """Create deterministic action and cleanup barriers without starting any task."""
        self.started, self.cleaning, self.release = (
            asyncio.Event(),
            asyncio.Event(),
            asyncio.Event(),
        )
        self.cleaned = False

    async def run(self, query):
        """Wait for cancellation and then hold cleanup until the test explicitly releases it."""
        self.started.set()
        try:
            await asyncio.Event().wait()
        finally:
            self.cleaning.set()
            await self.release.wait()
            self.cleaned = True


@pytest.mark.asyncio
async def test_repeated_caller_cancellation_joins_child_before_releasing_slot():
    """Prevent a second cancellation from interrupting child cleanup or admitting a replacement request early."""
    pipeline = SlowCleanupPipeline()
    current = WebSearchService(pipeline, clock=FakeClock())

    async def request():
        """Enter an operation that remains pending inside its owned pipeline child."""
        async with current.operation(uuid4(), "atlas"):
            pytest.fail("pending operation yielded")

    caller = asyncio.create_task(request())
    await pipeline.started.wait()
    try:
        caller.cancel()
        await pipeline.cleaning.wait()
        caller.cancel()
        await asyncio.sleep(0)
        assert not caller.done() and current.admission.locked() and not pipeline.cleaned
        with pytest.raises(WebSearchError, match="web_search_busy"):
            async with current.operation(uuid4(), "second"):
                pytest.fail("cleanup released admission")
        pipeline.release.set()
        with pytest.raises(asyncio.CancelledError):
            await caller
        assert (
            pipeline.cleaned
            and not current.operations
            and not current.admission.locked()
        )
        assert current.quota.total == 1
    finally:
        pipeline.release.set()
        if not caller.done():
            caller.cancel()
        await asyncio.gather(caller, return_exceptions=True)


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["provider", "model"])
async def test_shutdown_cancels_owned_request_and_closes_before_rejecting_new_work(
    stage,
):
    """Join actual controlled dependency cleanup while preserving charged quota and rejecting subsequent operations."""
    current = service()
    dependency = (
        current.pipeline.provider if stage == "provider" else current.pipeline.inference
    )
    dependency.release = asyncio.Event()

    async def request():
        """Own the pending request that shutdown must cancel and join."""
        async with current.operation(uuid4(), "atlas"):
            pytest.fail("pending request entered")

    caller = asyncio.create_task(request())
    await dependency.started.wait()
    await current.shutdown()
    assert caller.done() and caller.cancelled() and dependency.cleaned
    assert (
        not current.admission.locked()
        and not current.operations
        and current.quota.total == 1
    )
    with pytest.raises(WebSearchError, match="web_search_unavailable"):
        async with current.operation(uuid4(), "another"):
            pytest.fail("closed service admitted work")
    await current.shutdown()
