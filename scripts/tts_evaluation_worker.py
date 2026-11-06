"""Measure original nominated CPU TTS SDKs in a sealed namespace, retaining first native waveforms and explicit unsupported-language observations."""

import contextlib
import hashlib
import importlib.metadata
import json
import logging
import os
import re
import resource
import sys
import time
from pathlib import Path

logger = logging.getLogger(__name__)
CANDIDATES = {"qwen3-tts-0.6b", "piper-en", "piper-vi"}
QWEN_OPTIONS = dict(
    do_sample=True,
    top_k=50,
    top_p=1.0,
    temperature=0.9,
    repetition_penalty=1.05,
    subtalker_dosample=True,
    subtalker_top_k=50,
    subtalker_top_p=1.0,
    subtalker_temperature=0.9,
    max_new_tokens=192,
    non_streaming_mode=True,
)


def validate_request(request):
    """Reject arbitrary paths, voices, generation overrides, ambiguous identities and unbounded text before importing neural libraries."""
    if (
        type(request) is not dict
        or set(request) != {"mode", "candidate", "cases"}
        or request["mode"] not in {"imports", "load", "smoke", "predict"}
        or request["candidate"] not in CANDIDATES
    ):
        raise ValueError("tts_request")
    cases = request["cases"]
    expected = 18 if request["candidate"] == "qwen3-tts-0.6b" else 6
    count = {"imports": 0, "load": 0, "smoke": 1, "predict": expected}[request["mode"]]
    if type(cases) is not list or len(cases) != count:
        raise ValueError("tts_case_count")
    identities = set()
    for case in cases:
        if type(case) is not dict or set(case) != {"id", "text", "language", "variant"}:
            raise ValueError("tts_case_fields")
        if (
            type(case["id"]) is not str
            or re.fullmatch(r"[a-z0-9_-]{1,80}", case["id"]) is None
            or case["id"] in identities
        ):
            raise ValueError("tts_case_identity")
        text = case["text"]
        if (
            type(text) is not str
            or not text.strip()
            or len(text.encode("utf-8")) > 160
            or any(ord(char) < 32 for char in text)
        ):
            raise ValueError("tts_case_text")
        if (case["language"], case["variant"]) not in {
            ("en", "explicit"),
            ("vi", "explicit"),
            ("vi", "auto_diagnostic"),
        }:
            raise ValueError("tts_case_language")
        if request["candidate"].startswith("piper-") and (
            case["language"] != request["candidate"][-2:]
            or case["variant"] != "explicit"
        ):
            raise ValueError("tts_piper_voice_language")
        identities.add(case["id"])
    if request["mode"] == "predict" and request["candidate"] == "qwen3-tts-0.6b":
        if any(
            sum((case["language"], case["variant"]) == pair for case in cases) != 6
            for pair in [
                ("en", "explicit"),
                ("vi", "explicit"),
                ("vi", "auto_diagnostic"),
            ]
        ):
            raise ValueError("tts_qwen_coverage")
    logger.info(
        "tts_request_verified candidate=%s cases=%d mode=%s",
        request["candidate"],
        len(cases),
        request["mode"],
    )


class GenerationObserver:
    """Observe genuine inner generated sequences and outer codec lengths while returning the exact original objects and forwarding every argument."""

    def __init__(self, engine):
        """Attach transparent recorders to one original loaded Qwen talker without changing model/configuration parameters."""
        self.inner = engine.model.talker.generate
        self.outer = engine.model.generate
        self.eos = engine.model.config.talker_config.codec_eos_token_id
        self.observations = []
        self.codec_lengths = []
        engine.model.talker.generate = self.record_inner
        engine.model.generate = self.record_outer

    def reset(self):
        """Start a fresh observation without altering any original model state or decoder defaults."""
        self.observations.clear()
        self.codec_lengths.clear()

    def record_inner(self, *args, **kwargs):
        """Retain original last-token EOS evidence and emitted token count without adding duplicate generation keyword arguments."""
        result = self.inner(*args, **kwargs)
        sequences = result.sequences
        if (
            len(sequences.shape) != 2
            or sequences.shape[0] != 1
            or sequences.shape[1] < 1
        ):
            raise ValueError("tts_qwen_generation_sequence")
        self.observations.append(
            dict(
                sequence_tokens=int(sequences.shape[1]),
                last_token=int(sequences[0, -1].item()),
                ended_with_eos=bool(sequences[0, -1].item() == self.eos),
            )
        )
        return result

    def record_outer(self, *args, **kwargs):
        """Retain codec frame lengths from the original outer return without modifying codec tensors or replacing hidden states."""
        result = self.outer(*args, **kwargs)
        self.codec_lengths.extend(int(codes.shape[0]) for codes in result[0])
        return result

    def metadata(self):
        """Report complete EOS evidence separately from a finite generation budget, refusing to equate missing EOS with complete speech."""
        complete = (
            len(self.observations) == 1
            and len(self.codec_lengths) == 1
            and self.observations[0]["ended_with_eos"]
        )
        return dict(
            inner_generations=list(self.observations),
            codec_frames=list(self.codec_lengths),
            generation_complete=complete,
            maximum_new_tokens=192,
        )


class Runtime:
    """Load one genuine original Qwen or curated Piper CPU runtime with explicit devices, threads and separately measured imports/load."""

    def __init__(self, candidate, load):
        """Import only the selected family and load its pinned local checkpoint without network access or optional neural helpers."""
        started = time.perf_counter()
        import numpy as np

        self.numpy, self.candidate = np, candidate
        self.execution, self.load_seconds, self.observer = None, None, None
        if candidate == "qwen3-tts-0.6b":
            import torch
            from qwen_tts import Qwen3TTSModel

            torch.set_num_threads(2)
            torch.set_num_interop_threads(1)
            self.torch = torch
            packages = ["torch", "torchaudio", "transformers", "qwen-tts", "numpy"]
        else:
            import onnxruntime as ort
            from piper.config import PiperConfig, SynthesisConfig
            from piper.voice import ESPEAK_DATA_DIR, PiperVoice

            self.ort = ort
            packages = ["onnxruntime", "numpy"]
        self.versions = {name: importlib.metadata.version(name) for name in packages}
        if candidate.startswith("piper"):
            self.versions["piper_qualified_original_source"] = "1.8.0"
        self.import_seconds = time.perf_counter() - started
        if load:
            started = time.perf_counter()
            if candidate == "qwen3-tts-0.6b":
                self.engine = Qwen3TTSModel.from_pretrained(
                    "/model",
                    device_map="cpu",
                    dtype=torch.float32,
                    attn_implementation="eager",
                    local_files_only=True,
                )
                devices = sorted(
                    {
                        str(parameter.device)
                        for parameter in self.engine.model.parameters()
                    }
                )
                dtypes = sorted(
                    {
                        str(parameter.dtype)
                        for parameter in self.engine.model.parameters()
                        if parameter.is_floating_point()
                    }
                )
                if devices != ["cpu"] or dtypes != ["torch.float32"]:
                    raise ValueError("tts_qwen_device_dtype")
                self.execution = dict(
                    device="cpu",
                    floating_dtypes=dtypes,
                    parameter_devices=devices,
                    torch_threads=torch.get_num_threads(),
                    supported_languages=self.engine.get_supported_languages(),
                    supported_speakers=self.engine.get_supported_speakers(),
                    speaker="Ryan",
                    standard_engine_normalization=False,
                    synchronous_whole_call_audio=True,
                )
                self.observer = GenerationObserver(self.engine)
            else:
                ort.set_seed(7)
                voice_name = (
                    "en_US-ljspeech-medium"
                    if candidate == "piper-en"
                    else "vi_VN-vais1000-medium"
                )
                config = PiperConfig.from_dict(
                    json.loads(Path(f"/model/{voice_name}.onnx.json").read_text())
                )
                options = ort.SessionOptions()
                options.intra_op_num_threads, options.inter_op_num_threads = 2, 1
                session = ort.InferenceSession(
                    f"/model/{voice_name}.onnx",
                    sess_options=options,
                    providers=["CPUExecutionProvider"],
                )
                if (
                    session.get_providers() != ["CPUExecutionProvider"]
                    or config.sample_rate != 22050
                    or config.num_speakers != 1
                ):
                    raise ValueError("tts_piper_execution")
                self.engine = PiperVoice(
                    session=session,
                    config=config,
                    espeak_data_dir=ESPEAK_DATA_DIR,
                    download_dir=Path("/tmp"),
                    use_tashkeel=False,
                )
                self.synthesis = SynthesisConfig(
                    speaker_id=0,
                    length_scale=1.0,
                    noise_scale=config.noise_scale,
                    noise_w_scale=config.noise_w_scale,
                    normalize_audio=True,
                    volume=1.0,
                )
                self.execution = dict(
                    device="cpu",
                    providers=session.get_providers(),
                    ONNX_intra_op_threads=options.intra_op_num_threads,
                    ONNX_inter_op_threads=options.inter_op_num_threads,
                    espeak_voice=config.espeak_voice,
                    sample_rate=config.sample_rate,
                    speaker_id=0,
                    standard_engine_normalization=True,
                    standard_engine_clipping=True,
                    noise_scale=config.noise_scale,
                    noise_w_scale=config.noise_w_scale,
                    length_scale=1.0,
                    volume=1.0,
                    use_tashkeel=False,
                    alignments=False,
                )
            self.load_seconds = time.perf_counter() - started
        logger.info(
            "tts_original_runtime_ready candidate=%s loaded=%s", candidate, load
        )

    def synthesize(self, case):
        """Run exactly one first attempt with fixed settings and fully materialize returned native audio, retaining genuine first-yield and completion times."""
        if self.candidate == "qwen3-tts-0.6b":
            self.torch.manual_seed(7)
            self.numpy.random.seed(7)
            self.observer.reset()
            language = (
                "Auto"
                if case["variant"] == "auto_diagnostic"
                else {"en": "English", "vi": "Vietnamese"}[case["language"]]
            )
            started = time.perf_counter()
            wavs, rate = self.engine.generate_custom_voice(
                text=case["text"],
                language=language,
                speaker="Ryan",
                instruct=None,
                **QWEN_OPTIONS,
            )
            elapsed = time.perf_counter() - started
            if len(wavs) != 1 or rate != 24000:
                raise ValueError("tts_qwen_native_return")
            values = wavs[0]
            metadata = dict(
                self.observer.metadata(),
                first_available_audio_seconds=elapsed,
                full_call_seconds=elapsed,
                chunks=1,
                audio_availability="synchronous_complete_waveform",
            )
        else:
            self.ort.set_seed(7)
            started = time.perf_counter()
            chunks, first = [], None
            count = 0
            for chunk in self.engine.synthesize(
                case["text"], self.synthesis, include_alignments=False
            ):
                if first is None:
                    first = time.perf_counter() - started
                if (
                    chunk.sample_rate != 22050
                    or chunk.sample_channels != 1
                    or chunk.audio_float_array.dtype != self.numpy.dtype("float32")
                    or chunk.audio_float_array.ndim != 1
                ):
                    raise ValueError("tts_piper_native_chunk")
                chunks.append(chunk.audio_float_array)
                count += len(chunk.audio_float_array)
                if len(chunks) > 8 or count > 22050 * 20:
                    raise ValueError("tts_piper_audio_bound")
            elapsed = time.perf_counter() - started
            if not chunks:
                raise ValueError("tts_piper_no_audio")
            values, rate = self.numpy.concatenate(chunks), 22050
            metadata = dict(
                generation_complete=True,
                first_available_audio_seconds=first,
                full_call_seconds=elapsed,
                chunks=len(chunks),
                audio_availability="first_complete_sentence_yield",
            )
        logger.info(
            "tts_original_synthesis_returned candidate=%s id=%s samples=%d",
            self.candidate,
            case["id"],
            len(values),
        )
        return values, rate, metadata


def observe(runtime, case, store):
    """Retain native complete/invalid/truncated audio or an actual SDK refusal, without retrying, turning unsupported silence into success or repairing output."""
    started = time.perf_counter()
    base = dict(
        id=case["id"],
        language=case["language"],
        variant=case["variant"],
        text_sha256=hashlib.sha256(case["text"].encode()).hexdigest(),
    )
    try:
        values, rate, timing = runtime.synthesize(case)
        audio = store.save(values, rate, case["id"])
        status = (
            "ok"
            if audio["signal_valid"] and timing["generation_complete"]
            else "invalid_or_incomplete_audio"
        )
        return dict(base, status=status, audio=audio, **timing)
    except Exception as error:
        unsupported = (
            runtime.candidate == "qwen3-tts-0.6b"
            and case["language"] == "vi"
            and case["variant"] == "explicit"
            and isinstance(error, ValueError)
            and str(error).startswith("Unsupported languages:")
        )
        logger.warning(
            "tts_first_attempt_failed id=%s error_class=%s unsupported=%s",
            case["id"],
            type(error).__name__,
            unsupported,
        )
        return dict(
            base,
            status="unsupported_language" if unsupported else "error",
            error_class=type(error).__name__,
            detail=str(error)[:512],
            full_call_seconds=time.perf_counter() - started,
        )


def emit(event, **fields):
    """Flush finite bounded metadata independently from private waveform bytes so interrupted measurements retain first observations."""
    print(
        json.dumps(dict(event=event, **fields), ensure_ascii=False, allow_nan=False),
        flush=True,
    )


def main():
    """Execute one isolated original family/voice qualification or fixed measurement with no references, host credentials or default selection."""
    logging.basicConfig(level=logging.INFO)
    raw = sys.stdin.buffer.read(65537)
    if len(raw) > 65536:
        raise ValueError("tts_request_size")
    request = json.loads(raw)
    validate_request(request)
    os.sched_setaffinity(0, {0, 1})
    with contextlib.redirect_stdout(sys.stderr):
        runtime = Runtime(request["candidate"], load=request["mode"] != "imports")
    from scripts.tts_waveform import OutputStore

    emit(
        "ready",
        candidate=request["candidate"],
        versions=runtime.versions,
        execution=runtime.execution,
        import_seconds=runtime.import_seconds,
        load_seconds=runtime.load_seconds,
        logical_CPU_affinity=sorted(os.sched_getaffinity(0)),
    )
    store = OutputStore("/output")
    for case in request["cases"]:
        with contextlib.redirect_stdout(sys.stderr):
            observation = observe(runtime, case, store)
        emit("observation", **observation)
    usage = resource.getrusage(resource.RUSAGE_SELF)
    emit(
        "complete",
        peak_lifetime_process_RSS_KiB=usage.ru_maxrss,
        process_CPU_seconds=usage.ru_utime + usage.ru_stime,
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        emit("error", error_class=type(error).__name__, detail=str(error)[:512])
        raise SystemExit(1) from None
