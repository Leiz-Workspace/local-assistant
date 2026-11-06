"""Own one fixed-CORE archived-query selection with bounded quota/deadlines and joined cancellation, without provider or source I/O."""

import asyncio
import logging
import re
from datetime import UTC, datetime
from uuid import UUID

from src.application.ports.discovery_recovery import DiscoveryCheckpoint
from src.application.services.discovery_recovery_policy import (
    DiscoveryRecoveryError,
    recovery_messages,
    resolve_recovery,
    validate_checkpoint,
)
from src.application.services.research_policy import canonical_query
from src.application.services.web_fetch_tasks import finish_owned, spawn_owned
from src.application.services.web_search_policy import WebSearchError, WebSearchQuota

logger = logging.getLogger(__name__)
TOTAL_SECONDS = 20
MODEL_SECONDS = 15


class DiscoveryRecoveryService:
    """Select genuine archived query IDs for an explicit owner/goal without replaying provider requests or sharing private history."""

    def __init__(
        self,
        checkpoint,
        *,
        archive_sha256,
        corpus_sha256,
        inference,
        expected_model,
        quota=None,
        utcnow=None,
    ):
        """Bind a trusted pinned catalog, model and clock while leaving their lifetimes externally owned."""
        if (
            type(checkpoint) is not DiscoveryCheckpoint
            or type(expected_model) is not str
            or re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", expected_model) is None
        ):
            raise DiscoveryRecoveryError("recovery_invalid")
        self.checkpoint, self.pins = checkpoint, (archive_sha256, corpus_sha256)
        self.inference, self.expected_model = inference, expected_model
        self.quota = quota if quota is not None else WebSearchQuota()
        self.utcnow = utcnow if utcnow is not None else self.system_utc
        self.admission, self.operations, self.closing = asyncio.Lock(), set(), False
        validate_checkpoint(checkpoint, checkpoint.owner_id, self.pins, self.utcnow())
        logger.info("discovery_recovery_service_initialized provider_requests=0")

    @staticmethod
    def system_utc():
        """Read host UTC separately from archived observations and untrusted source date declarations."""
        return datetime.now(UTC)

    async def recover(self, owner, goal):
        """Admit one nonqueued charged model selection and retain ownership until nested cancellation cleanup completes."""
        if self.closing:
            raise DiscoveryRecoveryError("recovery_closed")
        if self.inference is None:
            raise DiscoveryRecoveryError("recovery_unavailable")
        if type(owner) is not UUID:
            raise DiscoveryRecoveryError("recovery_owner_invalid")
        try:
            goal = canonical_query(goal)
        except Exception:
            raise DiscoveryRecoveryError("recovery_invalid") from None
        validate_checkpoint(self.checkpoint, owner, self.pins, self.utcnow())
        messages = recovery_messages(goal, self.checkpoint)
        if self.admission.locked():
            raise DiscoveryRecoveryError("recovery_busy")
        await self.admission.acquire()
        caller, task = asyncio.current_task(), None
        try:
            self.operations.add(caller)
            try:
                self.quota.charge(owner)
            except WebSearchError:
                raise DiscoveryRecoveryError("recovery_rate_limited") from None
            task = spawn_owned(self.run(owner, goal, messages))
            try:
                return await asyncio.shield(task)
            except asyncio.CancelledError:
                task.cancel()
                try:
                    await finish_owned(task)
                except BaseException:
                    logger.info("discovery_recovery_cancelled_operation_joined")
                raise
        except asyncio.CancelledError:
            raise
        except DiscoveryRecoveryError:
            raise
        except Exception:
            raise DiscoveryRecoveryError("recovery_internal") from None
        finally:
            if getattr(self.inference, "closing", False):
                self.closing = True
            self.operations.discard(caller)
            self.admission.release()
            logger.info("discovery_recovery_operation_closed")

    async def run(self, owner, goal, messages):
        """Validate one complete fixed-model result against still-current pinned metadata before publishing any source pointer."""
        try:
            async with asyncio.timeout(TOTAL_SECONDS) as total:
                try:
                    async with asyncio.timeout(MODEL_SECONDS) as model:
                        completion = await self.inference.complete(
                            profile="core",
                            messages=messages,
                            preset="fast",
                            temperature=0,
                            max_tokens=512,
                        )
                    if model.expired():
                        raise TimeoutError()
                except TimeoutError:
                    raise DiscoveryRecoveryError("recovery_model_timeout") from None
                except asyncio.CancelledError:
                    raise
                except Exception:
                    raise DiscoveryRecoveryError("recovery_model_failed") from None
                if asyncio.current_task().cancelling():
                    raise asyncio.CancelledError()
                validate_checkpoint(self.checkpoint, owner, self.pins, self.utcnow())
                result = resolve_recovery(
                    completion,
                    self.expected_model,
                    self.checkpoint,
                    goal,
                    self.utcnow(),
                )
                if total.expired():
                    raise DiscoveryRecoveryError("recovery_timeout")
                return result
        except TimeoutError:
            raise DiscoveryRecoveryError("recovery_timeout") from None

    async def shutdown(self):
        """Join only this service's owning callers and preserve shared checkpoint/model dependencies."""
        self.closing = True
        current = asyncio.current_task()
        tasks = [task for task in self.operations if task is not current]
        for task in tasks:
            task.cancel()
        for task in tasks:
            try:
                await finish_owned(task)
            except BaseException:
                logger.info("discovery_recovery_shutdown_operation_joined")
        logger.info("discovery_recovery_shutdown_complete")
