"""Verify grounded operation admission, source/delivery fences and joined model/client cancellation without live quality claims."""

import asyncio
import copy
import json
from contextlib import asynccontextmanager

import pytest
from test_grounded_answer import hits as hits

from apps.api.routes.retrieval import RetrievalResponse
from apps.api.services.grounded import GroundedService
from src.application.ports.inference import CompletionResult
from src.application.services.file_storage_policy import StoragePolicyError


class Retrieval:
    """Expose source lifetime independently of the grounded service for controlled authorization faults."""

    def __init__(self, hits):
        """Initialize observable retained source state and owner-scoped operation records."""
        self.hits = hits
        self.held = False
        self.closing = False
        self.changed = False
        self.validations = 0
        self.options = None

    @asynccontextmanager
    async def operation(self, owner, query, **options):
        """Keep source state open until the response-lifetime context is explicitly released."""
        self.held = True
        self.options = options
        try:
            yield dict(hits=copy.deepcopy(self.hits)), ["retained"] if self.hits else []
        finally:
            self.held = False

    async def validate(self, owner, retained):
        """Reject a source change while asserting that authorized readers remain retained."""
        assert self.held
        self.validations += 1
        if self.changed:
            raise StoragePolicyError("retrieval_source_changed", 409)


class Port:
    """Provide explicit protocol completions and cancellation barriers, never actual model-quality evidence."""

    def __init__(
        self,
        retrieval,
        *,
        blocking=False,
        change=False,
        reply=None,
        finish="stop",
        preset="fast",
    ):
        """Configure only controlled completion, source-change and cleanup faults."""
        self.retrieval = retrieval
        self.blocking = blocking
        self.change = change
        self.reply = reply
        self.finish = finish
        self.preset = preset
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        self.joined = False
        self.calls = []

    async def complete(self, **kwargs):
        """Require held readers and exact fixed inference settings while exposing joined cancellation."""
        assert self.retrieval.held
        self.calls.append(kwargs)
        self.entered.set()
        try:
            if self.blocking:
                await self.release.wait()
            self.retrieval.changed = self.change
            return CompletionResult(
                content=self.reply
                or json.dumps(
                    dict(
                        status="answered",
                        answer="7443",
                        citations=[dict(source_id="s1", quote="Cổng 7443.")],
                    )
                ),
                model_id="test-core",
                preset_selected=self.preset,
                finish_reason=self.finish,
            )
        finally:
            await asyncio.sleep(0.02)
            assert self.retrieval.held
            self.joined = True


@pytest.mark.asyncio
async def test_fixed_core_contract_reader_lifetime_and_busy(hits):
    """Use only agreed CORE/fast and retain source/model admission until complete response delivery."""
    dense = Retrieval(hits)
    port = Port(dense)
    service = GroundedService(dense, inference=port)
    async with service.operation("owner", "query", top_k=1) as (data, retained):
        assert data["status"] == "answered" and dense.held and port.joined
        assert dense.options == dict(top_k=1, file_ids=None)
        call = port.calls[0]
        assert {
            key: call[key] for key in ("profile", "preset", "temperature", "max_tokens")
        } == dict(profile="core", preset="fast", temperature=0, max_tokens=512)
        assert dense.validations == 2 and service.admission.locked()
        with pytest.raises(StoragePolicyError) as caught:
            async with service.operation("owner", "query"):
                pass
        assert caught.value.status_code == 429
        await service.validate("owner", retained)
    assert not dense.held and not service.admission.locked() and not service.operations


@pytest.mark.asyncio
async def test_no_sources_never_generates():
    """Return explicit no_sources without calling the model or creating unsupported citations."""
    dense = Retrieval([])
    port = Port(dense)
    service = GroundedService(dense, inference=port)
    async with service.operation("owner", "query") as (data, _):
        assert (
            data["status"] == "no_sources"
            and data["answer"] is None
            and data["citations"] == []
        )
        assert data["answer_trust"] == "not_generated" and port.calls == []


@pytest.mark.asyncio
async def test_post_model_source_change_blocks_yield(hits):
    """Reject stale source context immediately after generation even when quoted output is otherwise valid."""
    dense = Retrieval(hits)
    port = Port(dense, change=True)
    service = GroundedService(dense, inference=port)
    with pytest.raises(StoragePolicyError) as caught:
        async with service.operation("owner", "query"):
            pytest.fail("must not yield stale answer")
    assert caught.value.status_code == 409 and port.joined
    assert not dense.held and not service.admission.locked()


@pytest.mark.parametrize("fault", ["length", "preset", "malformed"])
@pytest.mark.asyncio
async def test_unverified_completion_rejected(hits, fault):
    """Refuse incomplete, wrong-preset or malformed model output without fallback or private raw data."""
    dense = Retrieval(hits)
    port = Port(
        dense,
        finish="length" if fault == "length" else "stop",
        preset="deep" if fault == "preset" else "fast",
        reply="PRIVATE-MODEL-MARKER" if fault == "malformed" else None,
    )
    service = GroundedService(dense, inference=port)
    with pytest.raises(StoragePolicyError):
        async with service.operation("owner", "query"):
            pytest.fail("must reject")
    assert not dense.held and not service.operations and port.joined


@pytest.mark.parametrize("mode", ["cancel", "repeated_cancel", "shutdown", "timeout"])
@pytest.mark.asyncio
async def test_owned_model_task_join_before_reader_release(hits, mode):
    """Join delayed model-client cleanup before closing readers under every interruption path."""
    dense = Retrieval(hits)
    port = Port(dense, blocking=True)
    service = GroundedService(
        dense, inference=port, model_timeout=0.01 if mode == "timeout" else 60
    )

    async def consume():
        """Hold the complete source operation while controlled inference is blocked."""
        async with service.operation("owner", "query"):
            await asyncio.sleep(30)

    task = asyncio.create_task(consume())
    await port.entered.wait()
    if mode == "shutdown":
        await service.shutdown()
    elif mode != "timeout":
        task.cancel()
        if mode == "repeated_cancel":
            asyncio.get_running_loop().call_later(0.005, task.cancel)
    with pytest.raises((asyncio.CancelledError, StoragePolicyError)) as caught:
        await task
    if mode == "timeout":
        assert caught.value.status_code == 504
    assert (
        port.joined
        and not dense.held
        and not service.admission.locked()
        and not service.operations
    )
    await service.shutdown()
    with pytest.raises(StoragePolicyError):
        async with service.operation("owner", "query"):
            pass


@pytest.mark.parametrize("fault", ["changed", "send_failure"])
@pytest.mark.asyncio
async def test_final_response_fence_and_send_cleanup(hits, fault):
    """Retain the original response lifecycle for final authorization and failed actual ASGI delivery."""
    dense = Retrieval(hits)
    service = GroundedService(dense, inference=Port(dense))
    context = service.operation("owner", "query")
    data, retained = await context.__aenter__()
    response = RetrievalResponse(context, service, "owner", data, retained)
    messages = []

    async def send(message):
        """Capture only delivered ASGI data or raise a controlled transport error."""
        if fault == "send_failure":
            raise OSError("controlled transport failure")
        messages.append(message)

    if fault == "changed":
        dense.changed = True
        await response({"type": "http"}, None, send)
        assert messages[0]["status"] == 409 and b"7443" not in b"".join(
            row.get("body", b"") for row in messages
        )
    else:
        with pytest.raises(OSError):
            await response({"type": "http"}, None, send)
    assert not dense.held and not service.admission.locked() and not service.operations


@pytest.mark.parametrize("timeout", [0, -1, 61, True, float("nan")])
def test_invalid_timeout(timeout):
    """Reject invalid model deadlines before constructing resources or making any request."""
    with pytest.raises(ValueError):
        GroundedService(None, model_timeout=timeout)
