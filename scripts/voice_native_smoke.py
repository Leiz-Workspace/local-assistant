"""Exercise buffered voice composition with retained nominated model artifacts in isolated evaluation only, without product model selection."""

import asyncio
import io
import json
import logging
import wave
from dataclasses import asdict
from pathlib import Path
from uuid import uuid4

import numpy as np

from scripts.asr_evaluation_assets import ROOT as ASR_ROOT
from scripts.asr_evaluation_assets import verify_file
from scripts.asr_evaluation_corpus import save_bytes
from scripts.asr_evaluation_runner import (
    core_snapshot,
    public_request,
    run_worker,
    sandbox_command,
)
from scripts.tts_evaluation import sandbox as tts_sandbox
from scripts.tts_evaluation import verify_outputs
from scripts.tts_evaluation_assets import verify_models, verify_runtime_snapshot
from scripts.tts_local_review import require_headroom
from scripts.voice_vad_comparison import ROOT as COMPARISON
from scripts.voice_vad_comparison import publish, replace_mount
from src.application.ports.voice import VoiceSpeech, VoiceTranscript
from src.application.services.voice_pipeline import VoicePipeline, digest
from src.application.services.web_fetch_tasks import finish_owned, spawn_owned
from src.infrastructure.audio_normalizer import NativeAudioNormalizer
from src.infrastructure.inference.llama_adapter import LlamaInferenceAdapter

logger = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parents[1] / "data/backups/d72-native-voice-smoke-first"
MATRIX = tuple(
    (asr, tts, language)
    for asr in ("qwen3-asr-0.6b", "whisper-small-ct2")
    for tts, language in (
        ("qwen3-tts-0.6b", "en"),
        ("piper-en", "en"),
        ("piper-vi", "vi"),
    )
)


def pcm_wave(raw, rate):
    """Encode finite bounded mono float samples into an explicitly quantized PCM16 WAV without gain repair."""
    samples = np.frombuffer(raw, dtype="<f4")
    if (
        rate not in (16000, 22050, 24000)
        or not 1 <= len(samples) <= 20 * rate
        or not np.isfinite(samples).all()
        or np.max(np.abs(samples)) > 1
    ):
        raise ValueError("voice_pcm_conversion_bound")
    quantized = (
        np.rint(np.where(samples < 0, samples * 32768, samples * 32767))
        .astype("<i2")
        .tobytes()
    )
    output = io.BytesIO()
    with wave.open(output, "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(rate)
        writer.writeframes(quantized)
    return output.getvalue()


async def joined_io(function, *args, **kwargs):
    """Keep the real bounded native subprocess/thread owned until it exits, even after caller cancellation."""
    task = spawn_owned(asyncio.to_thread(function, *args, **kwargs))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        try:
            await finish_owned(task)
        except BaseException:
            logger.info("voice_native_cancelled_worker_joined")
        raise


class EvaluationASR:
    """Expose one original nominated ASR worker as a private test-only application dependency."""

    def __init__(self, candidate, directory):
        """Bind an exact nominated candidate and an exclusive evaluation artifact directory."""
        self.candidate, self.directory = candidate, Path(directory)

    async def transcribe(self, owner, audio, language):
        """Run one complete reference-free original ASR request and bind its raw text to the admitted source."""
        directory = self.directory / "asr"
        directory.mkdir(mode=0o700)
        samples = directory / "samples"
        samples.mkdir(mode=0o700)
        values = np.frombuffer(audio.pcm_s16le, dtype="<i2").astype("<f4") / np.float32(
            32768
        )
        raw = values.tobytes()
        save_bytes(samples / "source.f32", raw)
        case = dict(
            id="source",
            language={"en": "en_us", "vi": "vi_vn"}[language],
            waveform_path=str(samples / "source.f32"),
            sample_count=len(values),
            waveform_sha256=digest(raw),
        )
        configuration = json.loads(
            Path("configs/asr-evaluation-candidates.json").read_text()
        )
        candidate = next(
            row for row in configuration["candidates"] if row["id"] == self.candidate
        )
        model = ASR_ROOT / "models" / self.candidate / candidate["revision"]
        request = public_request(self.candidate, "predict", [case])
        publish(directory / "request.json", request)
        require_headroom()
        command = replace_mount(
            sandbox_command(self.candidate, model),
            ASR_ROOT / "prediction-inputs",
            samples,
        )
        process, stdout, stderr = await joined_io(
            run_worker, command, request, timeout=120
        )
        save_bytes(directory / "stdout.jsonl", stdout)
        save_bytes(directory / "stderr.log", stderr)
        publish(directory / "process.json", process)
        rows = [
            json.loads(line)
            for line in stdout.splitlines()
            if json.loads(line)["event"] == "prediction"
        ]
        if (
            process["exit_code"]
            or process["timed_out"]
            or len(rows) != 1
            or rows[0]["status"] != "ok"
            or rows[0]["waveform_sha256"] != digest(raw)
            or rows[0]["sample_count"] != len(values)
        ):
            raise ValueError("voice_native_ASR_incomplete")
        return VoiceTranscript(
            owner,
            audio.source_sha256,
            audio.pcm_sha256,
            language,
            rows[0]["text"],
            self.candidate,
        )


class EvaluationTTS:
    """Expose one original nominated TTS worker for an offline wiring test, with full native audio retained separately."""

    def __init__(self, candidate, directory):
        """Bind an explicit evaluation-only voice identity without changing any production default."""
        self.candidate, self.directory = candidate, Path(directory)

    async def synthesize(self, owner, answer, language):
        """Run one fixed-settings first synthesis, verify all native bytes and convert a separate playback buffer."""
        directory = self.directory / "tts"
        directory.mkdir(mode=0o700)
        output = directory / "native"
        output.mkdir(mode=0o700)
        request = dict(
            candidate=self.candidate,
            mode="smoke",
            cases=[
                dict(id="reply", text=answer, language=language, variant="explicit")
            ],
        )
        from scripts.tts_evaluation_worker import validate_request

        publish(directory / "request.json", request)
        validate_request(request)
        require_headroom()
        process, stdout, stderr = await joined_io(
            run_worker, tts_sandbox(self.candidate, output), request, timeout=180
        )
        save_bytes(directory / "stdout.jsonl", stdout)
        save_bytes(directory / "stderr.log", stderr)
        publish(directory / "process.json", process)
        events = [json.loads(line) for line in stdout.splitlines()]
        verify_outputs(output, request, events)
        rows = [row for row in events if row["event"] == "observation"]
        if (
            process["exit_code"]
            or process["timed_out"]
            or len(rows) != 1
            or rows[0]["status"] != "ok"
        ):
            raise ValueError("voice_native_TTS_incomplete")
        metadata = rows[0]["audio"]
        raw = (output / metadata["raw_filename"]).read_bytes()
        converted = pcm_wave(raw, metadata["sample_rate"])
        normalized = await joined_io(NativeAudioNormalizer().normalize, converted)
        publish(
            directory / "playback-conversion.json",
            dict(
                description="Separate PCM16 quantization and native16k resampling for buffered playback; original native float waveform unchanged; no gain normalization, trimming or quality claim.",
                native_sha256=digest(raw),
                PCM16_WAV_sha256=digest(converted),
                playback_pcm_sha256=normalized.pcm_sha256,
                sample_count=normalized.sample_count,
            ),
        )
        return VoiceSpeech(
            owner,
            digest(answer.encode()),
            language,
            self.candidate,
            normalized.pcm_s16le,
            normalized.sample_count,
        )


class EvaluationLLM:
    """Retain the exact first text-only CORE request and response even when a later native TTS stage fails."""

    def __init__(self, directory):
        """Bind an exclusive local evaluation receipt directory without modifying the shared CORE adapter."""
        self.directory = Path(directory)
        self.adapter = LlamaInferenceAdapter()

    async def complete(self, **kwargs):
        """Forward the unchanged voice request once and preserve the actual complete result before downstream validation."""
        publish(
            self.directory / "llm-request.json",
            dict(
                description="Public retained evaluation speech only; no user recording or production persistence.",
                **kwargs,
            ),
        )
        reply = await self.adapter.complete(**kwargs)
        publish(self.directory / "llm-response.json", asdict(reply))
        return reply


async def main():
    """Run a predeclared six-path compatible candidate matrix once and retain failures without a deployment or quality decision."""
    logging.basicConfig(level=logging.INFO)
    ROOT.mkdir(mode=0o700, exist_ok=False)
    publish(
        ROOT / "freeze.json",
        dict(
            description="Six original-candidate wiring paths; Qwen explicitVI remains unsupported and is not silently substituted. First results retained, no default selection.",
            matrix=MATRIX,
            source_sha256={
                str(path): digest(path.read_bytes())
                for path in [
                    Path(__file__),
                    Path("src/application/services/voice_pipeline.py"),
                    Path("src/application/ports/voice.py"),
                    Path("docs/ADR/113-native-voice-evaluation-matrix.md"),
                ]
            },
        ),
    )
    verify_models()
    verify_runtime_snapshot()
    config = json.loads(Path("configs/asr-evaluation-candidates.json").read_text())
    for candidate in config["candidates"]:
        for spec in candidate["artifacts"]:
            verify_file(
                ASR_ROOT
                / "models"
                / candidate["id"]
                / candidate["revision"]
                / spec["filename"],
                spec,
            )
    before = core_snapshot()
    corpus = json.loads((COMPARISON / "corpus.json").read_text())
    sources = {
        language: next(
            case
            for case in corpus["cases"]
            if case["language"] == code and case["kind"] == "independent_public_speech"
        )
        for language, code in [("en", "en_us"), ("vi", "vi_vn")]
    }
    observations = []
    try:
        for index, (asr, tts, language) in enumerate(MATRIX):
            directory = ROOT / f"path-{index:02d}"
            directory.mkdir(mode=0o700)
            case = sources[language]
            raw = Path(case["waveform_path"]).read_bytes()
            if digest(raw) != case["waveform_sha256"]:
                raise ValueError("voice_source_drift")
            wav = pcm_wave(raw, 16000)
            normalized = NativeAudioNormalizer().normalize(wav)
            service = VoicePipeline(
                asr=EvaluationASR(asr, directory),
                llm=EvaluationLLM(directory),
                tts=EvaluationTTS(tts, directory),
                asr_model=asr,
                llm_model="qwen3.5-9b-core",
                tts_model=tts,
                timeout=180,
            )
            try:
                result = await service.complete(
                    uuid4(), normalized, language, explicit_submission=True
                )
                row = asdict(result)
                row["owner_id"] = str(row["owner_id"])
                row["transcript"]["owner_id"] = str(row["transcript"]["owner_id"])
                row["speech"]["owner_id"] = str(row["speech"]["owner_id"])
                pcm = row["speech"].pop("pcm_s16le")
                row["speech"]["pcm_sha256"] = digest(pcm)
                save_bytes(directory / "playback.s16le", pcm)
                observation = dict(
                    index=index,
                    asr=asr,
                    tts=tts,
                    language=language,
                    status="ok",
                    result=row,
                )
            except Exception as exc:
                observation = dict(
                    index=index,
                    asr=asr,
                    tts=tts,
                    language=language,
                    status="failed",
                    error_class=type(exc).__name__,
                    finite_code=getattr(exc, "code", "native_dependency_failed"),
                )
            finally:
                await service.shutdown()
            publish(directory / "result.json", observation)
            observations.append(observation)
    finally:
        after = core_snapshot()
        publish(ROOT / "core-recovery.json", dict(before=before, after=after))
    result = dict(
        description="Actual buffered offline candidate wiring, not subjective naturalness or approved production voice integration.",
        observations=observations,
        successful_paths=sum(row["status"] == "ok" for row in observations),
        models_selected=[],
        D70_listening_completed=False,
        D72_complete=False,
    )
    publish(ROOT / "result.json", result)
    logger.info(
        "voice_native_matrix_complete successful=%d attempted=%d models_selected=0",
        result["successful_paths"],
        len(observations),
    )


if __name__ == "__main__":
    asyncio.run(main())
