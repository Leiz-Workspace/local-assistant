"""Run one qualified official CPU ASR backend on sealed reference-free waveforms inside an offline readonly evaluation namespace."""

import hashlib
import importlib.metadata
import json
import logging
import os
import re
import resource
import stat
import sys
import time
from pathlib import Path

logger = logging.getLogger(__name__)
CANDIDATES = {"qwen3-asr-0.6b", "whisper-small-ct2"}


def validate_request(request):
    """Reject labels, arbitrary paths, unknown models, ambiguous cases or unbounded inputs before importing an inference engine."""
    if (
        type(request) is not dict
        or set(request) != {"candidate", "mode", "cases"}
        or request["candidate"] not in CANDIDATES
        or request["mode"] not in {"imports", "load", "predict"}
    ):
        raise ValueError("asr_request")
    cases = request["cases"]
    if (
        type(cases) is not list
        or len(cases) > 100
        or (request["mode"] == "predict") != bool(cases)
    ):
        raise ValueError("asr_cases")
    identities = set()
    for case in cases:
        if type(case) is not dict or set(case) != {
            "id",
            "language",
            "filename",
            "sample_count",
            "waveform_sha256",
        }:
            raise ValueError("asr_case_fields")
        if (
            not isinstance(case["id"], str)
            or re.fullmatch(r"[a-z0-9_-]{1,80}", case["id"]) is None
            or case["id"] in identities
            or case["language"] not in {"vi_vn", "en_us"}
        ):
            raise ValueError("asr_case_identity")
        if (
            type(case["filename"]) is not str
            or re.fullmatch(r"[a-z0-9_-]{1,80}\.f32", case["filename"]) is None
            or type(case["sample_count"]) is not int
            or not 16000 <= case["sample_count"] <= 320000
            or re.fullmatch(r"[a-f0-9]{64}", str(case["waveform_sha256"])) is None
        ):
            raise ValueError("asr_case_waveform")
        identities.add(case["id"])
    logger.info(
        "asr_worker_request_verified candidate=%s cases=%d",
        request["candidate"],
        len(cases),
    )


def load_waveform(case, root=Path("/samples")):
    """Read exact bounded finite float32 bytes, rejecting symlinks and digest/count drift before a model receives them."""
    import numpy as np

    path = root / case["filename"]
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise ValueError("asr_waveform_type")
        raw = stream.read(320000 * 4 + 1)
    if (
        len(raw) != case["sample_count"] * 4
        or hashlib.sha256(raw).hexdigest() != case["waveform_sha256"]
    ):
        raise ValueError("asr_waveform_integrity")
    waveform = np.frombuffer(raw, dtype="<f4").copy()
    if not np.isfinite(waveform).all() or float(np.abs(waveform).max()) > 1:
        raise ValueError("asr_waveform_range")
    logger.info("asr_worker_waveform_verified samples=%d", len(waveform))
    return waveform


def qwen_prompt(processor, language):
    """Use the official empty-context audio chat template and forced-language suffix without references, extra instructions or transcript repair."""
    messages = [
        dict(role="system", content=""),
        dict(role="user", content=[dict(type="audio", audio="")]),
    ]
    return (
        processor.apply_chat_template(
            messages, add_generation_prompt=True, tokenize=False
        )
        + f"language {language}<asr_text>"
    )


class Runtime:
    """Import and load exactly one official candidate backend with explicit CPU/thread/precision/generation controls."""

    def __init__(self, candidate, load=True):
        """Measure import and load separately while retaining concrete versions and avoiding optional model factories."""
        started = time.perf_counter()
        self.candidate = candidate
        if candidate == "qwen3-asr-0.6b":
            import torch
            from qwen_asr.core.transformers_backend import (
                Qwen3ASRForConditionalGeneration,
                Qwen3ASRProcessor,
            )

            torch.set_num_threads(2)
            torch.set_num_interop_threads(1)
            torch.manual_seed(7)
            self.torch = torch
            model_class, processor_class = (
                Qwen3ASRForConditionalGeneration,
                Qwen3ASRProcessor,
            )
            self.versions = {
                name: importlib.metadata.version(name)
                for name in [
                    "torch",
                    "transformers",
                    "numpy",
                    "librosa",
                    "soundfile",
                    "tokenizers",
                ]
            }
        else:
            import ctranslate2
            from faster_whisper import WhisperModel, __version__

            model_class = WhisperModel
            self.versions = dict(
                faster_whisper_source=__version__,
                ctranslate2=ctranslate2.__version__,
                av=importlib.metadata.version("av"),
                numpy=importlib.metadata.version("numpy"),
                tokenizers=importlib.metadata.version("tokenizers"),
            )
        self.import_seconds = time.perf_counter() - started
        started = time.perf_counter()
        self.load_seconds = None
        self.execution = None
        if load:
            if candidate == "qwen3-asr-0.6b":
                self.model = (
                    model_class.from_pretrained(
                        "/model",
                        dtype=torch.float32,
                        local_files_only=True,
                        attn_implementation="eager",
                    )
                    .to("cpu")
                    .eval()
                )
                self.processor = processor_class.from_pretrained(
                    "/model", local_files_only=True, fix_mistral_regex=True
                )
                if str(self.model.device) != "cpu" or self.model.dtype != torch.float32:
                    raise ValueError("asr_qwen_device")
                self.execution = dict(
                    device=str(self.model.device),
                    parameter_dtype=str(self.model.dtype),
                    attention_implementation="eager",
                )
            else:
                self.model = model_class(
                    "/model",
                    device="cpu",
                    compute_type="int8",
                    cpu_threads=2,
                    num_workers=1,
                    local_files_only=True,
                )
                self.execution = dict(
                    device=str(self.model.model.device),
                    requested_compute_type="int8",
                    engine_compute_type=str(self.model.model.compute_type),
                )
                if self.execution["device"] != "cpu":
                    raise ValueError("asr_whisper_device")
            self.load_seconds = time.perf_counter() - started
        logger.info(
            "asr_candidate_runtime_ready candidate=%s loaded=%s", candidate, load
        )

    def transcribe(self, waveform, language):
        """Materialize the entire bounded inference output, retain raw decoding and identify potential generation-limit exhaustion."""
        started = time.perf_counter()
        if self.candidate == "qwen3-asr-0.6b":
            name = {"vi_vn": "Vietnamese", "en_us": "English"}[language]
            with self.torch.inference_mode():
                inputs = self.processor(
                    text=[qwen_prompt(self.processor, name)],
                    audio=[waveform],
                    return_tensors="pt",
                    padding=True,
                )
                inputs = inputs.to(self.model.device).to(self.model.dtype)
                generated = self.model.generate(
                    **inputs,
                    max_new_tokens=256,
                    do_sample=False,
                )
                tokens = generated.sequences[:, inputs["input_ids"].shape[1] :]
                text = self.processor.batch_decode(
                    tokens, skip_special_tokens=True, clean_up_tokenization_spaces=False
                )[0]
                token_count = int(tokens.shape[1])
                eos = self.model.generation_config.eos_token_id
                eos = [eos] if isinstance(eos, int) else eos
                capped = token_count >= 256 and int(tokens[0, -1]) not in (eos or [])
                extra = dict(
                    generated_tokens=token_count,
                    output_cap_reached=capped,
                    text_postprocessing="raw_decode_no_repetition_repair",
                )
        else:
            iterator, info = self.model.transcribe(
                waveform,
                language={"vi_vn": "vi", "en_us": "en"}[language],
                beam_size=5,
                temperature=0.0,
                condition_on_previous_text=False,
                initial_prompt=None,
                vad_filter=False,
                word_timestamps=False,
                without_timestamps=True,
                max_new_tokens=256,
                no_speech_threshold=0.6,
                log_prob_threshold=-1.0,
                compression_ratio_threshold=2.4,
            )
            segments = list(iterator)
            text = "".join(part.text for part in segments)
            counts = [len(part.tokens) for part in segments]
            extra = dict(
                segment_token_counts=counts,
                output_cap_reached=any(count >= 256 for count in counts),
                duration_seconds=info.duration,
                duration_after_vad_seconds=info.duration_after_vad,
                text_postprocessing="raw_materialized_segments_no_host_repair",
            )
        if type(text) is not str or len(text) > 8192:
            raise ValueError("asr_output_bound")
        return dict(text=text, wall_seconds=time.perf_counter() - started, **extra)


def emit(event, **fields):
    """Flush each bounded observation immediately so an interrupted candidate retains its actual completed cases."""
    print(json.dumps(dict(event=event, **fields), ensure_ascii=False), flush=True)


def main():
    """Execute one reference-free request and report finite errors without SDK traceback, credentials or fabricated predictions."""
    logging.basicConfig(level=logging.INFO)
    raw = sys.stdin.buffer.read(128 * 1024 + 1)
    if len(raw) > 128 * 1024:
        raise ValueError("asr_request_bound")
    request = json.loads(raw)
    validate_request(request)
    affinity = sorted(os.sched_getaffinity(0))[:2]
    if len(affinity) != 2:
        raise ValueError("asr_cpu_affinity")
    os.sched_setaffinity(0, affinity)
    runtime = Runtime(request["candidate"], load=request["mode"] != "imports")
    emit(
        "ready",
        candidate=request["candidate"],
        versions=runtime.versions,
        execution=runtime.execution,
        import_seconds=runtime.import_seconds,
        load_seconds=runtime.load_seconds,
        cpu_only=True,
        threads=2,
        logical_CPU_affinity=affinity,
    )
    for case in request["cases"]:
        try:
            waveform = load_waveform(case)
            result = runtime.transcribe(waveform, case["language"])
            emit(
                "prediction",
                id=case["id"],
                status="error" if result["output_cap_reached"] else "ok",
                error="asr_generation_limit" if result["output_cap_reached"] else None,
                waveform_sha256=case["waveform_sha256"],
                sample_count=case["sample_count"],
                **result,
            )
        except Exception as error:
            logger.warning(
                "asr_case_failed id=%s exception_class=%s",
                case["id"],
                type(error).__name__,
            )
            emit(
                "prediction",
                id=case["id"],
                status="error",
                error_class=type(error).__name__,
                detail=str(error)[:512],
            )
    emit(
        "complete",
        peak_lifetime_process_RSS_KiB=resource.getrusage(
            resource.RUSAGE_SELF
        ).ru_maxrss,
        process_CPU_seconds=resource.getrusage(resource.RUSAGE_SELF).ru_utime
        + resource.getrusage(resource.RUSAGE_SELF).ru_stime,
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        emit("error", exception_class=type(error).__name__, detail=str(error)[:512])
        raise SystemExit(1) from None
