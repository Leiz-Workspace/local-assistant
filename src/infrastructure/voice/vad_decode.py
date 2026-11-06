"""Observe unchanged official SileroVADv5 CPU segmentation on sealed reference-free waveforms inside an offline evaluation namespace."""

import hashlib
import importlib.metadata
import logging
import math
import os
import re
import stat
import time
from pathlib import Path

logger = logging.getLogger(__name__)


def validate_request(request):
    """Refuse labels, remote paths, ambiguous identities or unbounded waveforms before importing model libraries."""
    if (
        type(request) is not dict
        or set(request) != {"mode", "cases"}
        or request["mode"] not in {"imports", "load", "smoke", "predict"}
    ):
        raise ValueError("vad_request")
    cases = request["cases"]
    if (
        type(cases) is not list
        or len(cases) > 47
        or bool(cases) != (request["mode"] in {"smoke", "predict"})
    ):
        raise ValueError("vad_cases")
    if (
        request["mode"] == "predict"
        and len(cases) != 47
        or (request["mode"] == "smoke" and len(cases) != 1)
    ):
        raise ValueError("vad_case_count")
    identities = set()
    for case in cases:
        if type(case) is not dict or set(case) != {
            "id",
            "filename",
            "sample_count",
            "waveform_sha256",
        }:
            raise ValueError("vad_case_fields")
        if (
            type(case["id"]) is not str
            or re.fullmatch("[a-z0-9_-]{1,80}", case["id"]) is None
            or case["id"] in identities
        ):
            raise ValueError("vad_case_identity")
        if (
            type(case["filename"]) is not str
            or re.fullmatch("[a-z0-9_-]{1,80}\\.f32", case["filename"]) is None
            or type(case["sample_count"]) is not int
            or (not 16000 <= case["sample_count"] <= 512000)
            or (type(case["waveform_sha256"]) is not str)
            or (re.fullmatch("[a-f0-9]{64}", case["waveform_sha256"]) is None)
        ):
            raise ValueError("vad_case_waveform")
        identities.add(case["id"])
    logger.info(
        "vad_reference_free_request_verified cases=%d mode=%s",
        len(cases),
        request["mode"],
    )


def load_waveform(case, root=Path("/samples")):
    """Return owned exact finite float32 samples from a bounded regular source while rejecting links, count drift and signal repair."""
    import numpy as np

    descriptor = os.open(
        root / case["filename"],
        os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK,
    )
    with os.fdopen(descriptor, "rb") as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise ValueError("vad_waveform_type")
        raw = stream.read(512000 * 4 + 1)
    if (
        len(raw) != case["sample_count"] * 4
        or hashlib.sha256(raw).hexdigest() != case["waveform_sha256"]
    ):
        raise ValueError("vad_waveform_integrity")
    values = np.frombuffer(raw, dtype="<f4").copy()
    if not np.isfinite(values).all() or float(np.abs(values).max()) > 1:
        raise ValueError("vad_waveform_range")
    logger.info("vad_waveform_verified samples=%d", len(values))
    return values


def validate_segments(segments, samples):
    """Reject impossible, overlapping, floating-point or out-of-source sample intervals rather than repairing official model output."""
    if type(segments) is not list or len(segments) > 128:
        raise ValueError("vad_segments")
    previous = 0
    for segment in segments:
        if (
            type(segment) is not dict
            or set(segment) != {"start", "end"}
            or type(segment["start"]) is not int
            or (type(segment["end"]) is not int)
            or (not previous <= segment["start"] < segment["end"] <= samples)
        ):
            raise ValueError("vad_segment_bounds")
        previous = segment["end"]


class Observer:
    """Record original model reset/window outputs without changing recurrent state, probabilities or official postprocessing."""

    def __init__(self, model):
        """Attach a fresh per-recording observer to the reusable official model."""
        self.model = model
        self.probabilities = []
        self.resets = 0

    def reset_states(self):
        """Forward the official recording reset and retain an external-reset count distinct from model-internal initialization."""
        self.model.reset_states()
        self.resets += 1
        logger.debug("vad_official_recording_reset")

    def __call__(self, waveform, sample_rate):
        """Retain each finite official512-sample probability while returning the original unmodified tensor to segmentation."""
        if sample_rate != 16000 or tuple(waveform.shape) != (512,):
            raise ValueError("vad_window_contract")
        output = self.model(waveform, sample_rate)
        probability = float(output.item())
        if not math.isfinite(probability) or not 0 <= probability <= 1:
            raise ValueError("vad_probability")
        self.probabilities.append(probability)
        if len(self.probabilities) > 1000:
            raise ValueError("vad_window_bound")
        return output


class Runtime:
    """Load the pinned unchanged official v5 helper and CPU-only ONNX model with measured import/load and concrete versions."""

    def __init__(self, load):
        """Qualify genuine CPU imports and original one-thread ONNX settings without invoking any download factory."""
        started = time.perf_counter()
        import numpy as np
        import torch
        from utils_vad import OnnxWrapper, get_speech_timestamps

        torch.set_num_threads(2)
        torch.set_num_interop_threads(1)
        self.torch, self.numpy, self.segment = (torch, np, get_speech_timestamps)
        self.versions = {
            name: importlib.metadata.version(name)
            for name in ["torch", "torchaudio", "onnxruntime", "numpy"]
        }
        self.import_seconds = time.perf_counter() - started
        self.load_seconds, self.execution = (None, None)
        if load:
            started = time.perf_counter()
            self.model = OnnxWrapper("/official/silero_vad.onnx", force_onnx_cpu=True)
            providers = self.model.session.get_providers()
            options = self.model.session.get_session_options()
            if (
                providers != ["CPUExecutionProvider"]
                or options.intra_op_num_threads != 1
                or options.inter_op_num_threads != 1
            ):
                raise ValueError("vad_execution_provider")
            self.execution = dict(
                providers=providers,
                ONNX_intra_op_threads=options.intra_op_num_threads,
                ONNX_inter_op_threads=options.inter_op_num_threads,
                torch_threads=torch.get_num_threads(),
                recurrent_state_shape=list(self.model._state.shape),
                device="cpu",
            )
            self.load_seconds = time.perf_counter() - started
        logger.info("vad_official_runtime_ready loaded=%s", load)

    def observe(self, waveform):
        """Time the complete unchanged official segmentation, including its bounded final-window padding and source-length clamping."""
        observer = Observer(self.model)
        original_sha256 = hashlib.sha256(waveform.tobytes()).hexdigest()
        started = time.perf_counter()
        segments = self.segment(
            self.torch.from_numpy(waveform),
            observer,
            threshold=0.5,
            sampling_rate=16000,
            min_speech_duration_ms=250,
            max_speech_duration_s=float("inf"),
            min_silence_duration_ms=100,
            speech_pad_ms=30,
            return_seconds=False,
            visualize_probs=False,
            progress_tracking_callback=None,
        )
        seconds = time.perf_counter() - started
        if hashlib.sha256(waveform.tobytes()).hexdigest() != original_sha256:
            raise ValueError("vad_source_mutated")
        validate_segments(segments, len(waveform))
        expected = (len(waveform) + 511) // 512
        if len(observer.probabilities) != expected or observer.resets != 1:
            raise ValueError("vad_window_reset_count")
        raw = self.numpy.asarray(observer.probabilities, dtype="<f4").tobytes()
        return dict(
            segments=segments,
            window_probabilities=observer.probabilities,
            probability_sha256=hashlib.sha256(raw).hexdigest(),
            model_windows=expected,
            external_recording_resets=observer.resets,
            padded_final_window_samples=-len(waveform) % 512,
            source_samples_modified=False,
            wall_seconds=seconds,
        )
