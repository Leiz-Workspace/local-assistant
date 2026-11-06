"""Test owner-group lifecycle, bounded attempts and joined retirement under adversarial asynchronous ordering."""

import asyncio
from uuid import uuid4

import pytest

from apps.api.voice_identity import Actor
from src.application.services.gpu_admission import AdmissionBusy, GPUAdmission
from src.application.services.voice_pipeline import VoiceError
from src.application.services.voice_session import VoiceSession


class DeferredRuntime:
    """Model a dependency that completes cancellation cleanup only when explicitly released by a test."""

    def __init__(self, owner, gate, lease):
        """Capture owner and held residency without native resource allocation."""
        self.owner, self.gate, self.lease = owner, gate, lease
        self.started = asyncio.Event()
        self.retired = asyncio.Event()
        self.allow_join = asyncio.Event()

    async def start(self):
        """Immediately report fake readiness without invoking an SDK."""
        return None

    def health(self):
        """Report a finite fake health state."""
        return None

    async def ask(self, raw, operation):
        """Suppress cancellation until cleanup joins and then attempt a stale result publication."""
        self.started.set()
        try:
            await asyncio.Future()
        except asyncio.CancelledError:
            await self.allow_join.wait()
            self.retired.set()
        return {"answer": "stale"}

    async def close(self):
        """Assert shared admission remains held while this owned dependency retires."""
        assert self.gate.residency is self.lease


@pytest.mark.asyncio
async def test_cancelled_late_result_cannot_publish_or_release_early():
    """Retain owner/GPU admission through late dependency cleanup and reject delayed output."""
    gate = GPUAdmission()
    owner = Actor(uuid4(), "a" * 64)
    service = VoiceSession(DeferredRuntime, gate, lambda actor: True)
    await service.prepare(owner)
    await service.preparation
    runtime = service.runtime

    async def body():
        """Supply a neutral fake input only after owner admission."""
        return b"neutral"

    async def disconnected():
        """Keep the test client connected until explicit cancellation."""
        return False

    operation = str(uuid4())
    task = asyncio.create_task(service.submit(owner, operation, body, disconnected))
    await runtime.started.wait()
    cancel = asyncio.create_task(service.cancel(owner, operation))
    await asyncio.sleep(0.01)
    assert (
        not cancel.done() and service.owner == owner and gate.residency is runtime.lease
    )
    with pytest.raises(AdmissionBusy):
        async with gate.inference():
            pass
    runtime.allow_join.set()
    await cancel
    with pytest.raises(asyncio.CancelledError):
        await task
    assert (
        runtime.retired.is_set() and service.runtime is None and gate.residency is None
    )
    await service.close()


@pytest.mark.asyncio
async def test_prepare_factory_failure_consumes_budget_and_releases_verified_empty_group():
    """Avoid leaking reservations when runtime construction fails before acquiring native resources."""
    gate = GPUAdmission()
    owner = Actor(uuid4(), "a" * 64)

    def factory(*args):
        """Reject startup before any worker or model is created."""
        raise RuntimeError("neutral_factory_failure")

    service = VoiceSession(factory, gate, lambda actor: True)
    for _ in range(3):
        await service.prepare(owner)
        await service.preparation
        assert (
            gate.residency is None
            and service.runtime is None
            and service.state == "error"
        )
    with pytest.raises(VoiceError):
        await service.prepare(owner)
    assert service.preparations == 3
    await service.close()


@pytest.mark.asyncio
async def test_retirement_failure_preserves_owner_and_quarantines_gpu():
    """Never clear ownership or reopen admission when a runtime cannot prove it has retired."""
    gate = GPUAdmission()
    owner = Actor(uuid4(), "a" * 64)

    class Runtime(DeferredRuntime):
        """Simulate a worker that cannot establish joined retirement."""

        async def close(self):
            """Fail cleanup without claiming that native work has stopped."""
            raise RuntimeError("neutral_cleanup_failure")

    service = VoiceSession(Runtime, gate, lambda actor: True)
    await service.prepare(owner)
    await service.preparation
    with pytest.raises(RuntimeError):
        await service.release(owner)
    assert gate.poisoned and gate.residency is not None and service.owner == owner
    assert service.status(owner)["error"] == "retirement_unverified"
