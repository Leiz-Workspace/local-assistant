"""Bridge accepted speech rendering to the unchanged voice pipeline with exact original-answer and native provenance."""

import asyncio
import hashlib
import logging
from dataclasses import replace
from uuid import UUID

from benchmarks.scripts.vi_voice_campaign import ResearchTTS
from benchmarks.scripts.vi_voice_worker import validate_message
from benchmarks.scripts.vi_workflow_reading_policy import (
    MODEL,
    POLICY,
    VOICE,
    check_text,
    plan_chunk,
    prepare_answer,
    sha,
)
from src.application.ports.voice import VoiceSpeech
from src.application.services.voice_pipeline import VoicePipeline
from src.application.services.web_fetch_tasks import finish_owned, spawn_owned

LOGGER = logging.getLogger(__name__)


def check_binding(expected):
    """Require measured preset/reference hashes before any cold worker factory can be invoked."""
    if (
        type(expected) is not dict
        or set(expected) != {"speaker_sha256", "reference_codes_sha256"}
        or any(
            type(value) is not str
            or len(value) != 64
            or any(char not in "0123456789abcdef" for char in value)
            for value in expected.values()
        )
    ):
        raise ValueError("workflow_reading_reference_binding")


def live():
    """Reject a late result from a dependency that suppressed an in-flight cancellation."""
    if asyncio.current_task().cancelling():
        raise asyncio.CancelledError()


def verify_speech(speech, owner, spoken, language):
    """Require complete bounded PCM and exact rendered-text/owner/model/language provenance before rebinding."""
    if (
        type(speech) is not VoiceSpeech
        or (speech.owner_id, speech.text_sha256, speech.language, speech.model_id)
        != (owner, sha(spoken), language, MODEL)
        or speech.complete is not True
        or type(speech.sample_count) is not int
        or not 1 <= speech.sample_count <= 480000
        or type(speech.pcm_s16le) is not bytes
        or len(speech.pcm_s16le) != speech.sample_count * 2
    ):
        LOGGER.warning("workflow_reading_rejected code=speech_binding")
        raise ValueError("workflow_reading_speech_binding")


class ReadingTTS:
    """Render speech separately and publish original-answer-bound PCM only after backend and audit verification."""

    def __init__(self, backend, audit):
        """Bind one trusted reading backend and mandatory owner-controlled asynchronous trace sink."""
        if (
            backend.model_id != MODEL
            or backend.reading_profile != POLICY
            or not callable(audit)
        ):
            raise ValueError("workflow_reading_backend_contract")
        self.backend, self.audit, self.busy = backend, audit, False
        self.model_id = MODEL
        LOGGER.info("workflow_reading_bridge_initialized product_activation=False")

    async def synthesize(self, owner, answer, language):
        """Keep admission occupied through synthesis, audit and joined dependency cancellation without altering CORE text."""
        if type(owner) is not UUID or language != "vi":
            raise ValueError("workflow_reading_request_contract")
        if self.busy:
            raise ValueError("workflow_reading_busy")
        self.busy = True
        try:
            spoken, trace = prepare_answer(answer)
            live()
            speech = await self.backend.synthesize(owner, spoken, language)
            live()
            verify_speech(speech, owner, spoken, language)
            await self.audit(trace)
            live()
            LOGGER.info(
                "workflow_reading_rebound original_sha256=%s spoken_sha256=%s",
                trace.original_sha256,
                trace.spoken_sha256,
            )
            return replace(speech, text_sha256=trace.original_sha256)
        finally:
            self.busy = False
            LOGGER.info("workflow_reading_bridge_retired")


def verify_native(result, message, directory, expected_binding):
    """Verify the actual profile/input/plans/caps/chunk bytes before converting any native output to playback PCM."""
    trace = result["prosody_trace"]
    plans = trace["reading_plans"]
    if (
        trace.get("reading_policy") != POLICY
        or trace.get("spoken_input_sha256") != sha(message["text"])
        or trace.get("voice_binding") != expected_binding
        or not 1 <= len(plans) <= 8
        or trace["chunks"] != [plan["normalized"] for plan in plans]
        or trace["phonemes"] != [plan["phones"] for plan in plans]
        or len(result["chunks"]) != len(plans)
        or len(trace["native_chunk_sha256"]) != len(plans)
        or len(trace["gaps"]) != len(plans) - 1
        or len(trace["reading_tokens"]) != len(plans)
        or result["generation_complete"] is not True
    ):
        raise ValueError("workflow_reading_native_trace")
    for index, (plan, group) in enumerate(zip(plans, result["chunks"], strict=True)):
        tokens = trace["reading_tokens"][index]
        if (
            tokens.get("decoded_exact") is not True
            or tokens.get("unknown_tokens") != 0
            or type(tokens.get("token_ids")) is not list
            or not tokens["token_ids"]
            or any(type(value) is not int or value < 0 for value in tokens["token_ids"])
        ):
            raise ValueError("workflow_reading_native_tokens")

        def recorded_cap(phones):
            """Rebuild edit provenance with only the two actual worker-reported cap inputs."""
            if phones == plan["raw"]:
                return plan["original_cap"]
            if phones == plan["phones"]:
                return plan["reading_cap"]
            raise ValueError("workflow_reading_unrecorded_cap")

        if plan_chunk(plan["normalized"], plan["raw"], recorded_cap) != plan:
            raise ValueError("workflow_reading_native_plan")
        if (
            group["eos"] is not True
            or type(group["frames"]) is not int
            or not 1 <= group["frames"] <= plan["shared_cap"]
        ):
            raise ValueError("workflow_reading_native_frames")
        raw = (directory / f"{message['id']}-chunk-{index}.f32").read_bytes()
        if hashlib.sha256(raw).hexdigest() != trace["native_chunk_sha256"][index]:
            raise ValueError("workflow_reading_native_chunk_hash")
    LOGGER.info("workflow_reading_native_verified chunks=%d", len(plans))


class VerifiedReadingWorker:
    """Wrap an owned native worker with strict reading-profile and actual-output provenance checks."""

    def __init__(self, worker, expected_binding):
        """Keep original lifecycle/resource attributes while verifying the fixed research lane at readiness."""
        ready = worker.ready
        if (
            ready.get("candidate"),
            ready.get("profile"),
            ready.get("voice"),
            ready.get("reading_policy"),
        ) != ("turbo", "workflow-reading", VOICE, POLICY):
            raise ValueError("workflow_reading_ready_contract")
        check_binding(expected_binding)
        self.worker, self.expected_binding = worker, dict(expected_binding)

    def __getattr__(self, name):
        """Expose the unchanged owned worker's directory and measured lifecycle/resource metadata."""
        return getattr(self.worker, name)

    async def call(self, message):
        """Forward one exact speech request and stop the owned worker if its first result fails verification."""
        validate_message(message)
        if message["op"] != "synthesize" or message.get("voice") != VOICE:
            raise ValueError("workflow_reading_worker_request")
        try:
            result = await self.worker.call(message)
            verify_native(
                result, message, self.worker.directory / "native", self.expected_binding
            )
            return result
        except BaseException:
            await finish_owned(spawn_owned(self.worker.close(force=True)))
            raise

    async def close(self, force=False):
        """Delegate joined cleanup to the original worker without creating another process or retry."""
        await self.worker.close(force=force)


class ReadingResearchTTS(ResearchTTS):
    """Reuse original native-to-playback conversion with verified reading workers for cold and resident research lanes."""

    reading_profile = POLICY

    def __init__(
        self, worker, slot, ledger, deadline, core_pid, worker_factory, expected_binding
    ):
        """Inject a separately authorized bounded worker factory and the accepted Truc Ly binding, without loading it."""
        check_binding(expected_binding)
        if worker is None and not callable(worker_factory):
            raise ValueError("workflow_reading_factory_required")
        super().__init__("turbo", worker, slot, ledger, deadline, core_pid)
        self.worker_factory, self.expected_binding = (
            worker_factory,
            dict(expected_binding),
        )
        if worker is not None:
            self.worker = VerifiedReadingWorker(worker, expected_binding)

    async def synthesize(self, owner, answer, language):
        """Start only an explicitly supplied cold worker and preserve owned cleanup after every first outcome."""
        if type(owner) is not UUID or language != "vi":
            raise ValueError("workflow_reading_backend_request")
        check_text(answer, 4096)
        try:
            if self.worker is None:
                worker = await self.worker_factory(
                    self.slot / "tts", self.deadline, self.core_pid
                )
                try:
                    self.worker = VerifiedReadingWorker(worker, self.expected_binding)
                except BaseException:
                    await finish_owned(spawn_owned(worker.close(force=True)))
                    raise
            return await super().synthesize(owner, answer, language)
        except BaseException:
            if self.worker is not None:
                await finish_owned(spawn_owned(self.worker.close(force=True)))
            raise


def compose_workflow(asr, llm, backend, audit, *, asr_model, timeout=180):
    """Inject the research reading port into the original VI-first pipeline without changing model choices or defaults."""
    if asr_model not in {"qwen3-asr-0.6b", "whisper-small-ct2"}:
        raise ValueError("workflow_reading_asr_lane")
    LOGGER.info("workflow_reading_composed asr=%s deployment=False", asr_model)
    return VoicePipeline(
        asr=asr,
        llm=llm,
        tts=ReadingTTS(backend, audit),
        asr_model=asr_model,
        llm_model="qwen3.5-9b-core",
        tts_model=MODEL,
        timeout=timeout,
    )
