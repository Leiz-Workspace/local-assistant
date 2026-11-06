"""Research whole-clip speech admission without trimming PCM, changing models or enabling a product default."""

import asyncio
import logging
from dataclasses import dataclass
from uuid import UUID
from src.application.ports.voice import VoiceTranscript
from src.application.services.voice_pipeline import VoiceError, normalized
from src.application.services.web_fetch_tasks import finish_owned, spawn_owned

LOGGER = logging.getLogger(__name__)
VAD_MODEL = "silero-vad-v5.0-5cd2ba54"
POLICY = "whole-clip-presence-v1"


@dataclass(frozen=True, slots=True, repr=False)
class SpeechPresence:
    """Bind one complete detector decision to an owner, exact PCM and original sample clock."""

    owner_id: UUID
    source_sha256: str
    pcm_sha256: str
    sample_count: int
    first_pts: int
    time_base_num: int
    time_base_den: int
    model_id: str
    segments: tuple[tuple[int, int], ...]
    complete: bool = True


def validate_presence(value, owner, audio):
    """Reject stale, malformed or differently bound evidence instead of interpreting detector failure as silence."""
    if (
        type(value) is not SpeechPresence
        or value.complete is not True
        or type(value.owner_id) is not UUID
        or (type(value.sample_count) is not int)
        or any(
            (
                type(x) is not int
                for x in (value.first_pts, value.time_base_num, value.time_base_den)
            )
        )
        or (
            (
                value.owner_id,
                value.source_sha256,
                value.pcm_sha256,
                value.sample_count,
                value.first_pts,
                value.time_base_num,
                value.time_base_den,
                value.model_id,
            )
            != (
                owner,
                audio.source_sha256,
                audio.pcm_sha256,
                audio.sample_count,
                audio.first_pts,
                audio.time_base_num,
                audio.time_base_den,
                VAD_MODEL,
            )
        )
        or (type(value.segments) is not tuple)
        or (len(value.segments) > 128)
    ):
        raise VoiceError("invalid_result")
    previous = 0
    for segment in value.segments:
        if (
            type(segment) is not tuple
            or len(segment) != 2
            or any((type(x) is not int for x in segment))
            or (not previous <= segment[0] < segment[1] <= audio.sample_count)
        ):
            raise VoiceError("invalid_result")
        previous = segment[1]
    LOGGER.info(
        "voice_presence_verified segments=%d policy=%s", len(value.segments), POLICY
    )
    return bool(value.segments)


class WholeClipASR:
    """Optionally gate one explicit pipeline ASR call while forwarding the identical full audio on acceptance."""

    def __init__(self, *, detector, asr, asr_model):
        """Inject trusted dependencies without loading models, selecting candidates or owning shared workers."""
        if (
            type(asr_model) is not str
            or not 1 <= len(asr_model) <= 128
            or (not asr_model.isascii())
            or any((not (x.isalnum() or x in "_.-/") for x in asr_model))
        ):
            raise VoiceError("invalid_input")
        self.detector, self.asr, self.asr_model = (detector, asr, asr_model)
        self.active, self.closed = (None, False)
        LOGGER.info(
            "voice_presence_initialized policy=%s product_activation=False", POLICY
        )

    def live(self):
        """Reject dependencies that suppress cancellation or return after local shutdown."""
        if asyncio.current_task().cancelling():
            raise asyncio.CancelledError()
        if self.closed:
            raise VoiceError("closed")

    async def transcribe(self, owner, audio, language):
        """Keep admission until detector or ASR work finishes or is cancelled and joined."""
        if self.closed:
            raise VoiceError("closed")
        if type(owner) is not UUID or language not in ("vi", "en"):
            raise VoiceError("invalid_input")
        normalized(audio)
        if self.active is not None:
            raise VoiceError("busy")
        task = spawn_owned(self.run(owner, audio, language))
        self.active = task
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            task.cancel()
            try:
                await finish_owned(task)
            except BaseException:
                LOGGER.info("voice_presence_cancelled_work_joined")
            raise
        finally:
            self.active = None
            LOGGER.info("voice_presence_operation_retired")

    async def run(self, owner, audio, language):
        """Refuse empty presence before ASR and preserve unmodified transcript provenance on acceptance."""
        try:
            decision = await self.detector.detect(owner, audio)
            self.live()
            if not validate_presence(decision, owner, audio):
                LOGGER.info("voice_presence_refused downstream_calls=0")
                return VoiceTranscript(
                    owner,
                    audio.source_sha256,
                    audio.pcm_sha256,
                    language,
                    "",
                    self.asr_model,
                )
            result = await self.asr.transcribe(owner, audio, language)
            self.live()
            if (
                type(result) is not VoiceTranscript
                or result.complete is not True
                or (
                    result.owner_id,
                    result.source_sha256,
                    result.pcm_sha256,
                    result.language,
                    result.model_id,
                )
                != (
                    owner,
                    audio.source_sha256,
                    audio.pcm_sha256,
                    language,
                    self.asr_model,
                )
            ):
                raise VoiceError("invalid_result")
            LOGGER.info("voice_presence_forwarded full_pcm=True clock_preserved=True")
            return result
        except (VoiceError, asyncio.CancelledError):
            raise
        except Exception:
            raise VoiceError("dependency_failed") from None

    async def shutdown(self):
        """Close only local admission and join owned calls without retiring externally owned models."""
        self.closed = True
        if self.active is not None:
            self.active.cancel()
            try:
                await finish_owned(self.active)
            except BaseException:
                LOGGER.info("voice_presence_shutdown_work_joined")
        LOGGER.info("voice_presence_shutdown_complete")
