"""Coordinate optional single-process GPU residency without changing disabled inference behavior."""

import asyncio
import logging
from contextlib import asynccontextmanager
from functools import wraps

LOGGER = logging.getLogger(__name__)
_coordinator = None


class AdmissionBusy(RuntimeError):
    """Reject overlapping GPU work or uncertain retirement with a finite public error."""


class GPUAdmission:
    """Reserve one resident voice group against all registered application inference paths."""

    def __init__(self):
        """Initialize an idle coordinator without contacting hardware or loading models."""
        self.residency = None
        self.calls = {}
        self.authorized = {}
        self.poisoned = False

    def acquire(self):
        """Reserve residency atomically before any asynchronous preparation or model allocation."""
        if self.poisoned or self.residency is not None or self.calls:
            LOGGER.warning("gpu_residency_denied")
            raise AdmissionBusy("gpu_busy")
        self.residency = object()
        LOGGER.info("gpu_residency_acquired")
        return self.residency

    def release(self, lease):
        """Release only the exact joined lease with no inference remaining in its critical section."""
        if lease is not self.residency or self.calls or self.poisoned:
            self.poisoned = True
            raise AdmissionBusy("gpu_retirement_unverified")
        self.residency = None
        LOGGER.info("gpu_residency_released")

    def quarantine(self):
        """Close admission permanently for this process after unverified native retirement."""
        self.poisoned = True
        LOGGER.error("gpu_admission_quarantined")

    @asynccontextmanager
    async def borrow(self, lease):
        """Authorize the current task only to use an existing resident group's shared CORE."""
        task = asyncio.current_task()
        if self.poisoned or lease is not self.residency or lease is None:
            raise AdmissionBusy("gpu_busy")
        self.authorized[task] = lease
        try:
            yield
        finally:
            self.authorized.pop(task, None)

    @asynccontextmanager
    async def inference(self):
        """Count complete inference/context operations and prevent inherited child-task bypasses."""
        task = asyncio.current_task()
        if self.poisoned or (
            self.residency is not None
            and self.authorized.get(task) is not self.residency
        ):
            LOGGER.warning("gpu_inference_busy")
            raise AdmissionBusy("gpu_busy")
        self.calls[task] = self.calls.get(task, 0) + 1
        borrowed = task in self.authorized
        try:
            yield
        except asyncio.CancelledError:
            if not borrowed:
                self.quarantine()
            raise
        finally:
            self.calls[task] -= 1
            if not self.calls[task]:
                del self.calls[task]


def bind(coordinator):
    """Install exactly one optional coordinator for a supported single-worker app lifetime."""
    global _coordinator
    if _coordinator is not None:
        raise RuntimeError("gpu_coordinator_already_bound")
    _coordinator = coordinator
    LOGGER.info("gpu_admission_bound")


def unbind(coordinator):
    """Remove only the matching coordinator after the owning application has shut down."""
    global _coordinator
    if _coordinator is not coordinator:
        raise RuntimeError("gpu_coordinator_binding_mismatch")
    _coordinator = None
    LOGGER.info("gpu_admission_unbound")


def guard_gpu(function):
    """Guard an entire asynchronous inference entry point, preserving the disabled call verbatim."""

    @wraps(function)
    async def guarded(*args, **kwargs):
        """Retain admission across templates, classification and inference until the call exits."""
        gate = _coordinator
        if gate is None:
            return await function(*args, **kwargs)
        async with gate.inference():
            return await function(*args, **kwargs)

    return guarded
