"""Verify promoted numerical behavior and import boundaries against retained original definitions without models."""

import ast
import dataclasses
import importlib
from pathlib import Path

import numpy as np
import pytest

from apps.voice_trial import audio as old_audio
from benchmarks.scripts import vi_voice_detector_peak as old_detector
from benchmarks.scripts import vi_workflow_reading_policy as old_policy
from src.infrastructure.voice import (
    audio,
    detector,
    reading_policy,
    resources,
    waveform,
)


@pytest.mark.parametrize("amplitude", [0, 1, 2, 32, 1000, 16384, 32767, -32768])
def test_detector_copy_and_original_pcm_are_exact(amplitude):
    """Retain every byte, source clock and finite gain at zero, quiet and full-scale input boundaries."""
    pcm = np.full(16000, amplitude, dtype="<i2").tobytes()
    raw = old_audio.encode_wave(pcm)
    previous = old_audio.decode_wave(raw)
    promoted = audio.decode_wave(raw)
    assert promoted == previous
    view = detector.detector_view(promoted)
    before = old_detector.detector_view(previous)
    assert dataclasses.asdict(view) == dataclasses.asdict(before)
    assert promoted.pcm_s16le == pcm


@pytest.mark.parametrize(
    "text",
    [
        "Chị sẽ nhắc bạn lúc 09:15 ngày 14/11.",
        "Bạn muốn học Python hay dùng API của ứng dụng?",
        "Chương VI và Chương XI, vi phạm và xi măng.",
        "Server kết nối GitHub. Bạn có muốn kiểm tra không?",
        "Xin chào bạn. Chị có thể giúp gì?",
    ],
)
def test_reading_render_and_trace_are_exact(text, monkeypatch):
    """Keep the accepted source-to-spoken policy without adding pronunciation or Roman-number rules."""

    def clock():
        """Fix only host measurement time so separate calls can compare identical provenance fields."""
        return 10.0

    import time

    monkeypatch.setattr(time, "perf_counter", clock)
    actual, trace = reading_policy.prepare_answer(text)
    expected, prior = old_policy.prepare_answer(text)
    assert actual == expected and dataclasses.asdict(trace) == dataclasses.asdict(prior)


@pytest.mark.parametrize("rate", [16000, 22050, 48000])
def test_native_quantization_and_wav_encoding_are_exact(rate):
    """Retain original signed rounding, endpoint scaling and native file bytes on all supported rates."""
    from benchmarks.scripts.vi_voice_campaign import pcm_wave
    from benchmarks.scripts.vi_voice_worker import native_bytes

    values = np.linspace(-1, 1, 257, dtype=np.float32)
    assert resources.pcm_wave(values.tobytes(), rate) == pcm_wave(
        values.tobytes(), rate
    )
    if rate == 16000:
        with pytest.raises(ValueError):
            waveform.native_bytes(values, rate)
        with pytest.raises(ValueError):
            native_bytes(values, rate)
    else:
        assert waveform.native_bytes(values, rate) == native_bytes(values, rate)


def test_promoted_imports_have_no_benchmark_or_private_backup_dependencies():
    """Fail if application adapters import operators/corpora or hardcode private retained artifact paths."""
    for path in Path("src/infrastructure/voice").glob("*.py"):
        text = path.read_text()
        tree = ast.parse(text)
        assert ast.get_docstring(tree), path
        assert "data/backups" not in text, path
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                assert ast.get_docstring(node), (path, node.name)
            if isinstance(node, ast.ImportFrom):
                assert not (node.module or "").startswith(("benchmarks", "scripts")), (
                    path,
                    node.module,
                )
            if isinstance(node, ast.Import):
                assert not any(
                    x.name.startswith(("benchmarks", "scripts")) for x in node.names
                )


@pytest.mark.parametrize(
    "module,original,names",
    [
        (
            "src.infrastructure.voice.asr_decode",
            "scripts.asr_evaluation_worker",
            ["qwen_prompt", "Runtime.transcribe"],
        ),
        (
            "src.infrastructure.voice.vad_decode",
            "scripts.vad_evaluation_worker",
            [
                "validate_request",
                "load_waveform",
                "validate_segments",
                "Observer",
                "Runtime",
            ],
        ),
        (
            "src.infrastructure.voice.asr_runtime",
            "benchmarks.scripts.vi_voice_cuda_worker",
            ["configure_torch", "Runtime.transcribe"],
        ),
        (
            "src.infrastructure.voice.waveform",
            "benchmarks.scripts.vi_voice_worker",
            ["native_bytes", "FrameObserver"],
        ),
    ],
)
def test_extracted_decoder_ast_has_identical_numeric_logic(module, original, names):
    """Compare full model math/decoder/segment definitions structurally without importing a model SDK."""
    first = ast.parse(Path(importlib.import_module(module).__file__).read_text())
    second = ast.parse(Path(importlib.import_module(original).__file__).read_text())
    for name in names:
        lhs, rhs = first, second
        for part in name.split("."):
            lhs = next(
                n
                for n in lhs.body
                if isinstance(n, (ast.ClassDef, ast.FunctionDef)) and n.name == part
            )
            rhs = next(
                n
                for n in rhs.body
                if isinstance(n, (ast.ClassDef, ast.FunctionDef)) and n.name == part
            )
        assert ast.dump(lhs, include_attributes=False) == ast.dump(
            rhs, include_attributes=False
        ), name
