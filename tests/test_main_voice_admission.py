"""Verify reversible managed inference guards and group-lifetime GPU exclusion without native inference."""

import asyncio
import importlib

import pytest

from apps.api.voice_admission import ManagedGPUCalls, TARGETS
from src.application.services.gpu_admission import AdmissionBusy, GPUAdmission


@pytest.mark.asyncio
async def test_residency_covers_idle_lifetime_and_does_not_inherit_to_children():
    """Keep residency exclusive between turns and require an explicit current-task borrow capability."""
    gate = GPUAdmission()
    async with gate.inference():
        with pytest.raises(AdmissionBusy):
            gate.acquire()
    lease = gate.acquire()
    with pytest.raises(AdmissionBusy):
        async with gate.inference():
            pass
    async with gate.borrow(lease):
        async with gate.inference():
            async with gate.inference():
                assert gate.calls[asyncio.current_task()] == 2

        async def child():
            """Attempt to bypass residency from a child that did not receive explicit authority."""
            async with gate.inference():
                pass

        with pytest.raises(AdmissionBusy):
            await asyncio.create_task(child())
    gate.release(lease)
    async with gate.inference():
        pass


@pytest.mark.asyncio
async def test_foreign_release_and_uncertain_cancellation_quarantine():
    """Fail closed after wrong ownership or cancelled ordinary inference rather than reopening admission."""
    gate = GPUAdmission()
    gate.acquire()
    with pytest.raises(AdmissionBusy):
        gate.release(object())
    assert gate.poisoned
    gate = GPUAdmission()
    started = asyncio.Event()

    async def ordinary():
        """Hold a simulated native inference until its owning task is cancelled."""
        async with gate.inference():
            started.set()
            await asyncio.Future()

    task = asyncio.create_task(ordinary())
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert gate.poisoned and not gate.calls
    with pytest.raises(AdmissionBusy):
        gate.acquire()


@pytest.mark.asyncio
async def test_all_declared_entry_points_are_guarded_and_restored():
    """Cover direct context/vision/structured/coding calls and the pre-imported file OCR alias."""
    originals = []
    for module_name, class_name, name in TARGETS:
        module = importlib.import_module(module_name)
        owner = getattr(module, class_name) if class_name else module
        originals.append((owner, name, getattr(owner, name)))
    gate = GPUAdmission()
    guards = ManagedGPUCalls(gate)
    guards.start()
    lease = gate.acquire()
    try:
        for owner, name, original in originals:
            wrapped = getattr(owner, name)
            assert wrapped.__wrapped__ is original
            with pytest.raises(AdmissionBusy):
                await wrapped()
    finally:
        gate.release(lease)
        guards.close()
    assert all(getattr(owner, name) is original for owner, name, original in originals)
