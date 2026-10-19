"""Verify explicit memory source/model/delivery lifetimes and bounded retention with controlled ports."""

import asyncio
import json
from types import SimpleNamespace
from uuid import uuid4

import pytest
from test_memory_selection import source

from apps.api.routes.memory import ExtractionInput, MemorySelectionResponse
from apps.api.services.memory_extraction import MemoryExtractor
from apps.api.services.memory_retention import MemoryRetention
from src.application.ports.inference import CompletionResult
from src.application.services.memory_contract import MemoryPolicyError


class Journal:
    """Expose observable controlled storage decisions without claiming PostgreSQL source authentication."""

    def __init__(self):
        """Initialize an immutable synthetic snapshot and capture/fence audit fields."""
        self.source = source()
        self.captures = []
        self.changed = False
        self.validations = 0
        self.denied = False

    async def preflight_selection(self, *args):
        """Return a declared synthetic source unless preflight permission is deliberately denied."""
        if self.denied:
            raise MemoryPolicyError("memory_extraction_disabled")
        return SimpleNamespace(kind="preference"), self.source

    async def capture_selection(self, owner, receipt, snapshot, quote, model):
        """Record only explicit model-selected parameters after the controlled current-source fence."""
        if self.changed:
            raise MemoryPolicyError("memory_source_changed")
        self.captures.append((quote, model))
        return dict(id="controlled-record", text=quote)

    async def validate_selection(self, *args):
        """Reject final delivery when the controlled current-source state changes."""
        self.validations += 1
        if self.changed:
            raise MemoryPolicyError("memory_source_changed")


class Port:
    """Return declared protocol fixtures and cancellation barriers without actual model-quality evidence."""

    def __init__(self, *, blocking=False, content=None, finish="stop", preset="fast"):
        """Configure fixed completion faults and expose client cleanup independently of extraction tracking."""
        self.blocking = blocking
        self.content = content or json.dumps(
            dict(status="selected", quote="I prefer Vietnamese.")
        )
        self.finish = finish
        self.preset = preset
        self.calls = []
        self.joined = False
        self.entered = asyncio.Event()
        self.cleaning = asyncio.Event()

    async def complete(self, **kwargs):
        """Expose exact inference arguments and finish observable cleanup before the client task closes."""
        self.calls.append(kwargs)
        self.entered.set()
        try:
            if self.blocking:
                await asyncio.Event().wait()
            return CompletionResult(
                self.content, "controlled-core", self.preset, self.finish
            )
        finally:
            self.cleaning.set()
            await asyncio.sleep(0.02)
            self.joined = True


@pytest.mark.asyncio
async def test_fixed_profile_and_response_lifetime_busy_gate():
    """Use agreed CORE/fast only and retain one nonqueued operation until response context exit."""
    journal, port = Journal(), Port()
    extractor = MemoryExtractor(journal, inference=port)
    args = (uuid4(), uuid4(), uuid4(), uuid4())
    async with extractor.operation(*args) as (payload, retained):
        assert payload["status"] == "captured" and len(journal.captures) == 1
        assert extractor.operations and extractor.admission.locked() and port.joined
        assert port.calls[0]["profile"] == "core" and port.calls[0]["preset"] == "fast"
        assert port.calls[0]["temperature"] == 0 and port.calls[0]["max_tokens"] == 512
        with pytest.raises(MemoryPolicyError, match="memory_busy"):
            async with extractor.operation(*args):
                pytest.fail("must reject queued selection")
        await extractor.validate(args[0], args[1], retained)
    assert not extractor.operations and not extractor.admission.locked()


@pytest.mark.asyncio
async def test_preflight_refusal_never_calls_model():
    """Reject missing independent extraction consent before loading source into model input."""
    journal, port = Journal(), Port()
    journal.denied = True
    extractor = MemoryExtractor(journal, inference=port)
    with pytest.raises(MemoryPolicyError):
        async with extractor.operation(uuid4(), uuid4(), uuid4(), uuid4()):
            pytest.fail("must reject")
    assert not port.calls and not extractor.operations


@pytest.mark.asyncio
async def test_insufficiency_creates_no_record():
    """Retain explicit absence instead of persisting generated text or a fabricated quote."""
    journal = Journal()
    extractor = MemoryExtractor(
        journal,
        inference=Port(content='{"status":"insufficient_evidence","quote":null}'),
    )
    async with extractor.operation(uuid4(), uuid4(), uuid4(), uuid4()) as (
        payload,
        retained,
    ):
        assert (
            payload["status"] == "insufficient_evidence" and payload["record"] is None
        )
        assert retained[1] is None and not journal.captures


@pytest.mark.asyncio
@pytest.mark.parametrize("fault", ["finish", "preset", "quote"])
async def test_unverified_completion_never_captures(fault):
    """Reject incomplete/wrong-preset/fabricated output rather than repairing or switching a model."""
    options = (
        {"finish": "length"}
        if fault == "finish"
        else {"preset": "deep"}
        if fault == "preset"
        else {"content": '{"status":"selected","quote":"invented"}'}
    )
    journal = Journal()
    extractor = MemoryExtractor(journal, inference=Port(**options))
    with pytest.raises(MemoryPolicyError):
        async with extractor.operation(uuid4(), uuid4(), uuid4(), uuid4()):
            pytest.fail("must reject")
    assert not journal.captures and not extractor.operations


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mode", ["cancel", "repeated_cancel", "timeout", "shutdown", "owner", "receipt"]
)
async def test_selection_joins_model_for_all_interruptions(mode):
    """Drain a real owned asyncio model-client task before releasing source/operation admission."""
    journal, port = Journal(), Port(blocking=True)
    extractor = MemoryExtractor(
        journal, inference=port, model_timeout=0.01 if mode == "timeout" else 60
    )
    owner, receipt = uuid4(), uuid4()

    async def consume():
        """Enter the source/model operation that must never capture while the port remains blocked."""
        async with extractor.operation(owner, receipt, uuid4(), uuid4()):
            pytest.fail("must not yield")

    work = asyncio.create_task(consume())
    await port.entered.wait()
    if mode == "shutdown":
        await extractor.shutdown()
    elif mode in ("owner", "receipt"):
        await extractor.cancel_owner(uuid4())
        assert not work.done()
        await extractor.cancel_owner(owner, receipt if mode == "receipt" else None)
    elif mode != "timeout":
        work.cancel()
        if mode == "repeated_cancel":
            await port.cleaning.wait()
            work.cancel()
    with pytest.raises(
        MemoryPolicyError if mode == "timeout" else asyncio.CancelledError
    ):
        await work
    assert (
        port.joined
        and not journal.captures
        and not extractor.operations
        and not extractor.admission.locked()
    )
    await extractor.shutdown()


@pytest.mark.asyncio
@pytest.mark.parametrize("fault", ["source", "send"])
async def test_final_delivery_fence_and_failed_send_release_ownership(fault):
    """Fence changed generated data before headers and close selection context even if ASGI send fails."""
    journal = Journal()
    extractor = MemoryExtractor(journal, inference=Port())
    owner, receipt = uuid4(), uuid4()
    context = extractor.operation(owner, receipt, uuid4(), uuid4())
    payload, retained = await context.__aenter__()
    response = MemorySelectionResponse(
        context, extractor, owner, receipt, payload, retained
    )
    messages = []

    async def send(message):
        """Capture only delivered protocol frames or inject a declared transport failure."""
        if fault == "send":
            raise OSError("controlled transport failure")
        messages.append(message)

    if fault == "source":
        journal.changed = True
        await response({"type": "http"}, None, send)
        assert messages[0]["status"] == 409 and b"Vietnamese" not in b"".join(
            m.get("body", b"") for m in messages
        )
    else:
        with pytest.raises(OSError):
            await response({"type": "http"}, None, send)
    assert not extractor.operations and not extractor.admission.locked()


@pytest.mark.parametrize("value", [0, -1, 61, True, float("nan")])
def test_model_deadline_rejects_invalid_values(value):
    """Keep malformed or unbounded extraction deadlines from reaching the existing CORE client."""
    with pytest.raises(ValueError):
        MemoryExtractor(Journal(), inference=Port(), model_timeout=value)


@pytest.mark.parametrize(
    "extra",
    [
        dict(owner_id=str(uuid4())),
        dict(text="caller source"),
        dict(file_id=str(uuid4())),
        dict(model_id="replacement"),
        dict(provenance={}),
    ],
)
def test_extraction_input_cannot_override_source_or_model(extra):
    """Reject hidden source adapters and caller-derived authoritative memory metadata."""
    with pytest.raises(ValueError):
        ExtractionInput.model_validate(
            dict(
                consent_id=str(uuid4()),
                conversation_id=str(uuid4()),
                message_id=str(uuid4()),
                **extra,
            )
        )


class RetentionJournal:
    """Return bounded synthetic maintenance pages without claiming actual expiry SQL execution."""

    def __init__(self):
        """Initialize stable owner ordering and observe every bounded purge call."""
        self.owners = sorted([uuid4() for _ in range(12)])
        self.calls = []

    async def retention_owners(self, after, *, limit):
        """Return no more than the requested page size after the supplied cursor."""
        assert limit == 10
        return [owner for owner in self.owners if after is None or owner > after][
            :limit
        ]

    async def purge_owner(self, owner, *, limit):
        """Observe the declared per-owner bound rather than touching data or model state."""
        assert limit == 100
        self.calls.append(owner)
        return dict(records=1, receipts=2)


@pytest.mark.asyncio
async def test_retention_rotates_bounded_owner_pages():
    """Process ten then two owners, reset on exhaustion and revisit the beginning without an unbounded batch."""
    journal = RetentionJournal()
    worker = MemoryRetention(journal)
    assert await worker.tick() == dict(records=10, receipts=20)
    assert await worker.tick() == dict(records=2, receipts=4)
    assert await worker.tick() == dict(records=0, receipts=0) and worker.cursor is None
    assert journal.calls == journal.owners
    await worker.tick()
    assert len(journal.calls) == 22


@pytest.mark.asyncio
async def test_retention_shutdown_joins_active_database_child():
    """Cancel the worker only after its outstanding controlled storage cleanup is joined."""
    entered = asyncio.Event()
    joined = []

    class Blocking:
        """Expose cleanup ownership independently of the retention worker's own task."""

        async def retention_owners(self, *args, **kwargs):
            """Wait inside storage work and finish cleanup on cancellation."""
            entered.set()
            try:
                await asyncio.Event().wait()
            finally:
                await asyncio.sleep(0.02)
                joined.append(True)

    worker = MemoryRetention(Blocking(), interval=0.01)
    worker.start()
    await entered.wait()
    with pytest.raises(RuntimeError):
        worker.start()
    await worker.shutdown()
    assert joined == [True] and worker.task.done()
    with pytest.raises(RuntimeError):
        worker.start()


@pytest.mark.parametrize("interval", [0, -1, 31, True, float("nan")])
def test_retention_interval_is_bounded(interval):
    """Reject invalid automatic cleanup scheduling before a task is created."""
    with pytest.raises(ValueError):
        MemoryRetention(RetentionJournal(), interval=interval)
