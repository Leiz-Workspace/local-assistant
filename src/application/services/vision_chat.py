"""Own one ephemeral image-question operation with isolated native normalization, fixed CORE, finite quotas and joined cleanup."""

import asyncio
import logging
import re
from datetime import UTC, datetime
from uuid import UUID

from src.application.services.vision_chat_policy import (
    ImageChatError,
    bounded_text,
    image_input,
    resolve_answer,
    validate_image,
)
from src.application.services.web_fetch_tasks import finish_owned, spawn_owned
from src.application.services.web_search_policy import WebSearchError, WebSearchQuota

logger = logging.getLogger(__name__)
TOTAL_SECONDS = 75
NATIVE_SECONDS = 27
MODEL_SECONDS = 45


class VisionChatService:
    """Associate explicitly supplied current-operation image bytes with their owner without granting file access or retaining image history."""

    def __init__(
        self, *, normalizer, inference, expected_model, quota=None, utcnow=None
    ):
        """Bind externally owned dependencies and a fresh independent process-local quota with no automatic work."""
        if (
            type(expected_model) is not str
            or re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", expected_model) is None
        ):
            raise ImageChatError("image_chat_invalid")
        self.normalizer, self.inference, self.expected_model = (
            normalizer,
            inference,
            expected_model,
        )
        self.quota = quota if quota is not None else WebSearchQuota()
        self.utcnow = utcnow if utcnow is not None else self.system_utc
        self.operations, self.admission, self.closing = set(), asyncio.Lock(), False
        logger.info("vision_chat_service_initialized")

    @staticmethod
    def system_utc():
        """Read host acquisition UTC without treating it as image creation time or verified publication history."""
        return datetime.now(UTC)

    async def answer(self, owner, raw, suffix, question):
        """Admit one bounded private current-operation image question and hold ownership until all nested work retires."""
        if self.closing:
            raise ImageChatError("image_chat_closed")
        if self.normalizer is None or self.inference is None:
            raise ImageChatError("image_chat_unavailable")
        if type(owner) is not UUID:
            raise ImageChatError("image_chat_invalid")
        source_sha = image_input(raw, suffix)
        try:
            question = bounded_text(question, 2048)
        except Exception:
            raise ImageChatError("image_chat_invalid") from None
        if self.admission.locked():
            raise ImageChatError("image_chat_busy")
        await self.admission.acquire()
        caller, task = asyncio.current_task(), None
        try:
            self.operations.add(caller)
            try:
                self.quota.charge(owner)
            except WebSearchError:
                raise ImageChatError("image_chat_rate_limited") from None
            task = spawn_owned(self.run(owner, raw, suffix, question, source_sha))
            try:
                return await asyncio.shield(task)
            except asyncio.CancelledError:
                task.cancel()
                try:
                    await finish_owned(task)
                except BaseException:
                    logger.info("image_chat_cancelled_operation_joined")
                raise
        except asyncio.CancelledError:
            raise
        except ImageChatError:
            raise
        except Exception:
            raise ImageChatError("image_chat_internal") from None
        finally:
            if getattr(self.inference, "closing", False):
                self.closing = True
            self.operations.discard(caller)
            self.admission.release()
            logger.info("image_chat_operation_closed")

    async def normalize(self, raw, suffix):
        """Shield and join the real native thread without cancelling its future and losing underlying resource ownership."""
        task = spawn_owned(asyncio.to_thread(self.normalizer.normalize, raw, suffix))
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            try:
                await finish_owned(task)
            except BaseException:
                logger.info("image_chat_native_cancellation_joined")
            raise

    async def run(self, owner, raw, suffix, question, source_sha):
        """Bound both complete stages and refuse late results before publishing an unverified owner-associated answer."""
        try:
            async with asyncio.timeout(TOTAL_SECONDS) as total:
                try:
                    async with asyncio.timeout(NATIVE_SECONDS) as native:
                        image = await self.normalize(raw, suffix)
                    if native.expired():
                        raise TimeoutError()
                except TimeoutError:
                    raise ImageChatError("image_chat_native_timeout") from None
                except asyncio.CancelledError:
                    raise
                except Exception:
                    raise ImageChatError("image_chat_native_failed") from None
                if asyncio.current_task().cancelling():
                    raise asyncio.CancelledError()
                validate_image(image, source_sha)
                try:
                    async with asyncio.timeout(MODEL_SECONDS) as model:
                        completion = await self.inference.complete_image(
                            image=image, question=question
                        )
                    if model.expired():
                        raise TimeoutError()
                except TimeoutError:
                    raise ImageChatError("image_chat_model_timeout") from None
                except asyncio.CancelledError:
                    raise
                except ImageChatError:
                    raise
                except Exception:
                    raise ImageChatError("image_chat_model_failed") from None
                if asyncio.current_task().cancelling():
                    raise asyncio.CancelledError()
                validate_image(image, source_sha)
                result = resolve_answer(
                    completion,
                    self.expected_model,
                    owner,
                    question,
                    image,
                    self.utcnow(),
                )
                if total.expired():
                    raise ImageChatError("image_chat_timeout")
                return result
        except TimeoutError:
            raise ImageChatError("image_chat_timeout") from None

    async def shutdown(self):
        """Cancel and join only owning callers while leaving unrelated tasks and shared native/model dependencies intact."""
        self.closing = True
        current = asyncio.current_task()
        tasks = [task for task in self.operations if task is not current]
        for task in tasks:
            task.cancel()
        for task in tasks:
            try:
                await finish_owned(task)
            except BaseException:
                logger.info("image_chat_shutdown_operation_joined")
        logger.info("image_chat_shutdown_complete")
