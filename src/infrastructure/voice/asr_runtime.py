"""Serve original ASR checkpoints on explicitly bounded CUDA with unchanged decoding and isolated package provenance."""

import contextlib
import hashlib
import json
import logging
import os
import sys
import time

LOGGER = logging.getLogger(__name__)
ROLES = ("whisper-small-ct2", "qwen3-asr-0.6b")


def configure_torch(torch):
    """Retain float32 eager math and bound the PyTorch allocator without changing a model checkpoint."""
    if (
        torch.__version__.split("+")[0] != "2.10.0"
        or torch.version.cuda != "12.8"
        or (not torch.cuda.is_available())
    ):
        raise ValueError("cuda_torch_runtime")
    torch.set_num_threads(8)
    torch.set_num_interop_threads(1)
    torch.manual_seed(7)
    torch.cuda.set_device(0)
    total = torch.cuda.get_device_properties(0).total_memory
    torch.cuda.set_per_process_memory_fraction(4 * 1024**3 / total, 0)
    torch.set_float32_matmul_precision("highest")
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    torch.backends.cudnn.deterministic = True
    LOGGER.info("cuda_float32_controls_verified allocator_bytes=%d", 4 * 1024**3)


class Runtime:
    """Use original raw ASR decoding methods with only the execution device changed to CUDA."""

    def __init__(self, role):
        """Load fixed original weights directly onto the GPU and assert precision/backend identity."""
        from src.infrastructure.voice.asr_decode import Runtime as Original

        self.role = role
        started = time.perf_counter()
        self.torch = None
        if role == "qwen3-asr-0.6b":
            import torch
            from qwen_asr.core.transformers_backend import (
                Qwen3ASRForConditionalGeneration,
                Qwen3ASRProcessor,
            )

            configure_torch(torch)
            self.torch = torch
            self.engine = Original.__new__(Original)
            self.engine.candidate = role
            self.engine.torch = torch
            self.engine.model = Qwen3ASRForConditionalGeneration.from_pretrained(
                "/model",
                dtype=torch.float32,
                local_files_only=True,
                attn_implementation="eager",
                device_map={"": "cuda:0"},
            ).eval()
            self.engine.processor = Qwen3ASRProcessor.from_pretrained(
                "/model", local_files_only=True, fix_mistral_regex=True
            )
            if (
                str(self.engine.model.device) != "cuda:0"
                or self.engine.model.dtype != torch.float32
            ):
                raise ValueError("cuda_qwen_model_precision")
            self.execution = dict(
                device="cuda:0",
                parameter_dtype="torch.float32",
                attention_implementation="eager",
                torch_version=torch.__version__,
                tf32=False,
                allocator_cap_bytes=4 * 1024**3,
            )
        else:
            raise ValueError("voice_fixed_asr_profile")
        self.load_seconds = time.perf_counter() - started
        self.execution.update(
            cpu_threads=8,
            logical_CPU_affinity=sorted(os.sched_getaffinity(0)),
            execution_backend="cuda-original-precision",
        )
        LOGGER.info("cuda_original_asr_loaded role=%s", role)

    def transcribe(self, waveform, language):
        """Materialize all original decoded text and synchronize CUDA before returning measured completion."""
        if self.torch:
            self.torch.cuda.synchronize()
        started = time.perf_counter()
        result = self.engine.transcribe(waveform, language)
        if self.torch:
            self.torch.cuda.synchronize()
        result["wall_seconds"] = time.perf_counter() - started
        return result


def emit(event, **fields):
    """Flush finite JSON protocol records without mixing SDK output or private credentials."""
    print(
        json.dumps(dict(event=event, **fields), ensure_ascii=False, allow_nan=False),
        flush=True,
    )


def serve(scope, manifest_sha):
    """Serve a single fixed quality/native scope, retaining one explicit no-user-content readiness inference."""
    import numpy as np
    from src.infrastructure.voice.asr_decode import load_waveform
    from src.infrastructure.voice.waveform import validate_message

    with contextlib.redirect_stdout(sys.stderr):
        runtime = Runtime(scope["role"])
        warm = np.zeros(16000, dtype="<f4")
        warmed = runtime.transcribe(warm, "vi_vn")
    if warmed["output_cap_reached"]:
        raise ValueError("cuda_readiness_output_cap")
    emit(
        "ready",
        candidate=scope["role"],
        profile="resident-latency",
        manifest_sha256=manifest_sha,
        execution=runtime.execution,
        load_seconds=runtime.load_seconds,
        readiness=dict(
            model_calls=1,
            source_sha256=hashlib.sha256(warm.tobytes()).hexdigest(),
            sample_count=16000,
            seconds=warmed["wall_seconds"],
            text_sha256=hashlib.sha256(warmed["text"].encode()).hexdigest(),
            output_cap_reached=False,
        ),
    )
    seen = set()
    for _ in range(scope["max_requests"] + 1):
        raw = sys.stdin.buffer.readline(16385)
        if not raw or len(raw) > 16384 or (not raw.endswith(b"\n")):
            raise ValueError("cuda_message_bound")
        message = json.loads(raw)
        if message == {"op": "close"}:
            emit("closed", calls=len(seen), readiness_calls=1)
            return
        language = message.get("language", "vi_vn")
        if language not in ("vi_vn", "en_us") or (
            scope["mode"] == "voice" and "language" in message
        ):
            raise ValueError("cuda_language_scope")
        checked = {k: v for k, v in message.items() if k != "language"}
        validate_message(checked)
        if (
            checked["op"] != "transcribe"
            or checked["id"] in seen
            or len(seen) >= scope["max_requests"]
        ):
            raise ValueError("cuda_call_budget_or_duplicate")
        seen.add(checked["id"])
        started = time.perf_counter()
        with contextlib.redirect_stdout(sys.stderr):
            result = runtime.transcribe(load_waveform(checked), language)
        emit(
            "result",
            id=checked["id"],
            operation="transcribe",
            worker_wall_seconds=time.perf_counter() - started,
            asr=result,
        )
    raise ValueError("cuda_request_ceiling")
