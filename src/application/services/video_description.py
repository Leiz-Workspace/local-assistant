"""Compose bounded native frames and private original CORE image questions with joined ownership and host-bound timestamps."""

import asyncio
import base64
import logging
import re
from dataclasses import asdict
from datetime import UTC, datetime
from uuid import UUID

from src.application.ports.video import VideoSample
from src.application.ports.video_description import FrameDescription, VideoDescription
from src.application.ports.vision_chat import ImageChatReply
from src.application.services.ocr_contract import OCR_VERSION
from src.application.services.video_contract import resolve_video, video_input
from src.application.services.vision_chat_policy import bounded_text, digest
from src.application.services.web_fetch_tasks import finish_owned, spawn_owned
from src.application.services.web_search_policy import WebSearchError, WebSearchQuota

logger = logging.getLogger(__name__)
TOTAL_SECONDS = 280
NATIVE_SECONDS = 42
ERRORS = frozenset(
    {
        "video_description_invalid",
        "video_description_unavailable",
        "video_description_closed",
        "video_description_busy",
        "video_description_rate_limited",
        "video_description_native_failed",
        "video_description_native_timeout",
        "video_description_invalid_sample",
        "video_description_invalid_answer",
        "video_description_timeout",
        "video_description_internal",
    }
)


class VideoDescriptionError(Exception):
    """Expose finite composition failures without source pixels, questions or dependency diagnostics."""

    def __init__(self, code):
        """Record bounded error metadata while excluding private media and model-controlled error text."""
        self.code = (
            code
            if type(code) is str and code in ERRORS
            else "video_description_internal"
        )
        super().__init__(self.code)
        logger.warning("video_description_rejected code=%s", self.code)


def validated_sample(sample, source_sha, targets):
    """Revalidate the complete typed native sample before disclosing any frame to the vision dependency."""
    try:
        if (
            type(sample) is not VideoSample
            or sample.persisted is not False
            or sample.content_trust != "untrusted"
        ):
            raise ValueError()
        value = asdict(sample)
        value.pop("content_trust")
        value.pop("persisted")
        value["metadata"]["audio"] = list(value["metadata"]["audio"])
        value["frames"] = list(value["frames"])
        for frame in value["frames"]:
            frame["png_base64"] = base64.b64encode(frame.pop("png")).decode("ascii")
        return resolve_video(value, source_sha, targets)
    except Exception:
        raise VideoDescriptionError("video_description_invalid_sample") from None


class VideoDescriptionService:
    """Own one sparse clip-description operation while retaining externally shared native and vision dependencies."""

    def __init__(self, *, sampler, vision, expected_model, quota=None, utcnow=None):
        """Bind fixed trusted dependencies and independent process-local clip quota without starting work."""
        if (
            type(expected_model) is not str
            or re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", expected_model) is None
        ):
            raise VideoDescriptionError("video_description_invalid")
        self.sampler, self.vision, self.expected_model = sampler, vision, expected_model
        self.quota = quota if quota is not None else WebSearchQuota()
        self.utcnow = utcnow if utcnow is not None else self.system_utc
        self.operations, self.admission, self.closing = set(), asyncio.Lock(), False
        logger.info("video_description_service_initialized")

    @staticmethod
    def system_utc():
        """Read host reply UTC without treating it as video capture/publication time."""
        return datetime.now(UTC)

    async def describe(self, owner, raw, targets, question):
        """Admit one complete explicit-byte operation and retain ownership until all nested native/model work retires."""
        if self.closing:
            raise VideoDescriptionError("video_description_closed")
        if (
            self.sampler is None
            or self.vision is None
            or getattr(self.vision, "closing", False)
        ):
            raise VideoDescriptionError("video_description_unavailable")
        if type(owner) is not UUID:
            raise VideoDescriptionError("video_description_invalid")
        try:
            source_sha = video_input(raw, targets)
            question = bounded_text(question, 2048)
        except Exception:
            raise VideoDescriptionError("video_description_invalid") from None
        if self.admission.locked():
            raise VideoDescriptionError("video_description_busy")
        await self.admission.acquire()
        caller, task = asyncio.current_task(), None
        try:
            self.operations.add(caller)
            try:
                self.quota.charge(owner)
            except WebSearchError:
                raise VideoDescriptionError("video_description_rate_limited") from None
            task = spawn_owned(self.run(owner, raw, targets, question, source_sha))
            try:
                return await asyncio.shield(task)
            except asyncio.CancelledError:
                task.cancel()
                try:
                    await finish_owned(task)
                except BaseException:
                    logger.info("video_description_cancelled_work_joined")
                raise
        except asyncio.CancelledError:
            raise
        except VideoDescriptionError:
            raise
        except Exception:
            raise VideoDescriptionError("video_description_internal") from None
        finally:
            self.operations.discard(caller)
            self.admission.release()
            logger.info("video_description_operation_closed")

    async def sample(self, raw, targets):
        """Shield the actual native thread and join its real exit despite caller timeout or repeated cancellation."""
        task = spawn_owned(asyncio.to_thread(self.sampler.sample, raw, targets))
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            try:
                await finish_owned(task)
            except BaseException:
                logger.info("video_description_native_cancel_joined")
            raise

    async def run(self, owner, raw, targets, question, source_sha):
        """Acquire frames once, describe them sequentially and publish only complete host-timestamped unverified results."""
        try:
            async with asyncio.timeout(TOTAL_SECONDS) as total:
                try:
                    async with asyncio.timeout(NATIVE_SECONDS) as native:
                        sample = await self.sample(raw, targets)
                    if native.expired():
                        raise TimeoutError()
                except TimeoutError:
                    raise VideoDescriptionError(
                        "video_description_native_timeout"
                    ) from None
                except asyncio.CancelledError:
                    raise
                except Exception:
                    raise VideoDescriptionError(
                        "video_description_native_failed"
                    ) from None
                if asyncio.current_task().cancelling():
                    raise asyncio.CancelledError()
                sample = validated_sample(sample, source_sha, targets)
                frames = []
                for frame in sample.frames:
                    if total.expired():
                        raise VideoDescriptionError("video_description_timeout")
                    answer = await self.vision.answer(owner, frame.png, "png", question)
                    if asyncio.current_task().cancelling():
                        raise asyncio.CancelledError()
                    if total.expired():
                        raise VideoDescriptionError("video_description_timeout")
                    if (
                        type(answer) is not ImageChatReply
                        or answer.owner_id != owner
                        or answer.source_sha256 != frame.png_sha256
                        or answer.question_sha256 != digest(question.encode())
                        or answer.processor != OCR_VERSION
                        or answer.model_id != self.expected_model
                        or answer.confidence is not None
                        or answer.semantic_validation is not False
                        or answer.persisted is not False
                        or answer.content_trust != "untrusted"
                    ):
                        raise VideoDescriptionError("video_description_invalid_answer")
                    try:
                        if (
                            bounded_text(answer.answer, 8192) != answer.answer
                            or type(answer.uncertainties) is not tuple
                            or len(answer.uncertainties) > 16
                        ):
                            raise ValueError()
                        if any(
                            bounded_text(item, 512) != item
                            for item in answer.uncertainties
                        ):
                            raise ValueError()
                        if (answer.width, answer.height) != (
                            frame.width,
                            frame.height,
                        ) or re.fullmatch(
                            r"[0-9a-f]{64}", answer.normalized_sha256
                        ) is None:
                            raise ValueError()
                        if (
                            type(answer.model_attempts) is not int
                            or answer.model_attempts != 1
                            or type(answer.native_attempts) is not int
                            or answer.native_attempts != 1
                        ):
                            raise ValueError()
                    except Exception:
                        raise VideoDescriptionError(
                            "video_description_invalid_answer"
                        ) from None
                    frames.append(
                        FrameDescription(
                            frame.requested_ms,
                            frame.frame_index,
                            frame.pts,
                            frame.relative_time_num,
                            frame.relative_time_den,
                            frame.png_sha256,
                            answer.answer,
                            answer.uncertainties,
                            answer.model_id,
                        )
                    )
                    logger.info(
                        "video_frame_description_complete index=%d", frame.frame_index
                    )
                received = self.utcnow()
                if (
                    type(received) is not datetime
                    or received.tzinfo is None
                    or received.utcoffset().total_seconds() != 0
                ):
                    raise VideoDescriptionError("video_description_invalid_answer")
                if total.expired():
                    raise VideoDescriptionError("video_description_timeout")
                return VideoDescription(
                    owner,
                    source_sha,
                    digest(question.encode()),
                    sample.metadata,
                    tuple(frames),
                    received,
                )
        except TimeoutError:
            raise VideoDescriptionError("video_description_timeout") from None

    async def shutdown(self):
        """Cancel and join only this service's owning callers while leaving shared dependencies and unrelated tasks intact."""
        self.closing = True
        current = asyncio.current_task()
        tasks = [task for task in self.operations if task is not current]
        for task in tasks:
            task.cancel()
        for task in tasks:
            try:
                await finish_owned(task)
            except BaseException:
                logger.info("video_description_shutdown_operation_joined")
        logger.info("video_description_shutdown_complete")
