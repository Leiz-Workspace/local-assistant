"""Own authenticated optional voice groups with finite budgets and verified GPU retirement."""

import asyncio
import logging
import time

from src.application.services.gpu_admission import AdmissionBusy
from src.application.services.voice_pipeline import VoiceError
from src.application.services.web_fetch_tasks import finish_owned, spawn_owned

LOGGER = logging.getLogger(__name__)


class VoiceSession:
    """Associate one explicit native group with one authenticated credential-bound principal."""

    def __init__(self, factory, admission, valid):
        """Inject trusted runtime/authentication capabilities without loading models or reading audio."""
        self.factory, self.admission, self.valid = factory, admission, valid
        self.owner = self.runtime = self.lease = None
        self.preparation = self.active = self.operation = None
        self.state, self.error = "idle", None
        self.attempts = self.preparations = 0
        self.seen, self.cancelled = set(), set()
        self.closed = False
        self.retirement = asyncio.Lock()

    def authorize(self, actor):
        """Reject stale credentials and foreign group access before reading a request body."""
        if self.closed or not self.valid(actor):
            raise VoiceError("closed")
        if self.owner is not None and self.owner != actor:
            raise VoiceError("busy")

    def status(self, actor):
        """Expose finite readiness/quota/error state without any owner or operation identifiers."""
        self.authorize(actor)
        return dict(
            state=self.state,
            remaining=max(0, 24 - self.attempts),
            preparations_remaining=max(0, 3 - self.preparations),
            error=self.error,
        )

    async def prepare(self, actor):
        """Reserve credential ownership and resident GPU capacity before starting explicit preparation."""
        self.authorize(actor)
        if self.state not in {"idle", "error"} or self.preparation or self.runtime:
            raise VoiceError("busy")
        if self.preparations >= 3 or self.attempts >= 24:
            raise VoiceError("closed")
        lease = self.admission.acquire()
        self.owner, self.lease = actor, lease
        self.preparations += 1
        self.state, self.error = "preparing", None
        self.preparation = spawn_owned(self.load())
        LOGGER.info("voice_prepare_admitted count=%d", self.preparations)

    async def load(self):
        """Publish readiness only after actual runtime startup and a fresh identity recheck."""
        try:
            self.runtime = self.factory(
                self.owner.principal, self.admission, self.lease
            )
            await self.runtime.start()
            self.authorize(self.owner)
            self.state = "ready"
        except BaseException:
            self.error = (
                getattr(self.runtime, "startup_error", None) or "dependency_failed"
            )
            try:
                await finish_owned(spawn_owned(self.retire()))
            except BaseException:
                self.admission.quarantine()
            self.state = "error"
            LOGGER.warning("voice_prepare_failed")
        finally:
            self.preparation = None

    async def submit(self, actor, operation, read_body, disconnected):
        """Reserve one nonqueued turn before body admission and join cancellation through completion."""
        self.authorize(actor)
        key = (actor, operation)
        if self.state != "ready" or self.active is not None:
            raise VoiceError("busy")
        if self.attempts >= 24 or key in self.seen or key in self.cancelled:
            raise VoiceError("closed")
        self.seen.add(key)
        self.attempts += 1
        self.state, self.operation = "busy", key
        self.active = spawn_owned(
            self.execute(actor, operation, read_body, disconnected)
        )
        LOGGER.info("voice_turn_admitted count=%d", self.attempts)
        try:
            return await asyncio.shield(self.active)
        except asyncio.CancelledError:
            self.active.cancel()
            try:
                await finish_owned(self.active)
            except BaseException:
                LOGGER.info("voice_turn_cancel_joined")
            raise
        finally:
            self.active = self.operation = None
            if self.state == "busy":
                self.state = "ready" if self.runtime else "idle"

    async def execute(self, actor, operation, read_body, disconnected):
        """Publish only current complete owner-bound results with bounded read/work/disconnect handling."""
        task = None
        started = time.monotonic()
        try:
            async with asyncio.timeout(65):
                raw = await read_body()
                self.authorize(actor)
                task = spawn_owned(self.runtime.ask(raw, operation))
                while not task.done():
                    if not self.valid(actor) or await disconnected():
                        raise asyncio.CancelledError()
                    await asyncio.wait({task}, timeout=0.1)
                result = task.result()
                self.authorize(actor)
                if (
                    actor,
                    operation,
                ) in self.cancelled or asyncio.current_task().cancelling():
                    raise asyncio.CancelledError()
                return dict(
                    result, id=operation, server_seconds=time.monotonic() - started
                )
        except BaseException as error:
            if task and not task.done():
                task.cancel()
                try:
                    await finish_owned(task)
                except BaseException:
                    LOGGER.info("voice_dependency_cancel_joined")
            if not (
                isinstance(error, VoiceError)
                and error.code in {"invalid_input", "no_speech"}
            ):
                await finish_owned(spawn_owned(self.retire()))
            if isinstance(error, (VoiceError, asyncio.CancelledError, AdmissionBusy)):
                raise
            raise VoiceError(
                "timeout" if isinstance(error, TimeoutError) else "dependency_failed"
            ) from None

    async def cancel(self, actor, operation):
        """Cancel only this authenticated owner's operation, retaining bounded early-cancel tombstones."""
        self.authorize(actor)
        key = (actor, operation)
        if len(self.cancelled) >= 64 and key not in self.cancelled:
            raise VoiceError("closed")
        self.cancelled.add(key)
        if self.operation == key and self.active:
            self.active.cancel()
            try:
                await finish_owned(self.active)
            except BaseException:
                LOGGER.info("voice_cancel_joined")
        LOGGER.info("voice_cancel_completed")

    async def retire(self):
        """Release GPU ownership only after native close proves joined workers and borrowed-CORE quiescence."""
        async with self.retirement:
            await self.retire_joined()

    async def retire_joined(self):
        """Serialize idempotent retirement across cancellation, revocation, expiry and shutdown."""
        self.state = "retiring"
        if self.runtime:
            try:
                await self.runtime.close()
            except BaseException:
                self.admission.quarantine()
                self.state, self.error = "error", "retirement_unverified"
                raise
        if self.lease is not None:
            self.admission.release(self.lease)
        self.runtime = self.owner = self.lease = None
        self.state = "idle"
        LOGGER.info("voice_group_retired")

    async def release(self, actor):
        """Join this owner's preparation/turn before closing the ready session without a retry refund."""
        self.authorize(actor)
        for task in (self.preparation, self.active):
            if task:
                task.cancel()
                try:
                    await finish_owned(task)
                except BaseException:
                    LOGGER.info("voice_release_task_joined")
        await self.retire()

    async def watch(self):
        """Retire revoked, expired or unhealthy groups while preserving ownership until cleanup joins."""
        while not self.closed:
            await asyncio.sleep(1)
            if self.owner and not self.valid(self.owner):
                await self.stop()
            elif self.runtime and self.state in {"ready", "busy"}:
                try:
                    self.runtime.health()
                except Exception:
                    await self.stop()

    async def stop(self):
        """Join owned tasks and retain a quarantined lease if cleanup cannot be verified."""
        for task in (self.preparation, self.active):
            if task:
                task.cancel()
                try:
                    await finish_owned(task)
                except BaseException:
                    LOGGER.info("voice_stop_task_joined")
        await self.retire()

    async def close(self):
        """Permanently close admission and join all owned work during application shutdown."""
        self.closed = True
        await self.stop()
        LOGGER.info("voice_service_closed")
