"""Protect separate listening/ASR transformations, native provenance and encoder bounds without using them as fabricated naturalness evidence."""

import hashlib
from types import SimpleNamespace

import numpy as np
import pytest

from scripts.tts_audio_diagnostics import (
    encode_preview,
    load_native,
    preview_pcm,
    validate_request,
)


def source(tmp_path):
    """Create a small authored native source and exact request metadata for corruption controls."""
    raw = np.array([0.0, 0.25, -0.5], dtype="<f4").tobytes()
    (tmp_path / "case.f32").write_bytes(raw)
    return dict(
        id="case",
        filename="case.f32",
        sample_rate=24000,
        sample_count=3,
        waveform_sha256=hashlib.sha256(raw).hexdigest(),
    ), raw


@pytest.mark.parametrize(
    "field,value",
    [
        ("id", "../escape"),
        ("filename", "foreign.f32"),
        ("sample_rate", 44100),
        ("sample_count", 0),
        ("waveform_sha256", "wrong"),
        ("speaker", "other"),
    ],
)
def test_diagnostic_request_refuses_foreign_or_unbounded_inputs(tmp_path, field, value):
    """Keep transformation authority limited to prevalidated native leaf files and known rates."""
    case, _ = source(tmp_path)
    case[field] = value
    with pytest.raises(ValueError):
        validate_request(dict(cases=[case]))


def test_exact_native_bits_and_separate_gain_are_preserved(tmp_path):
    """Keep source amplitude/timeline untouched while explicitly labelling separate preview gain and no listening result."""
    case, raw = source(tmp_path)
    validate_request(dict(cases=[case]))
    values = load_native(case, tmp_path)
    preview, metadata = preview_pcm(values)
    assert values.tobytes() == raw
    assert metadata["native_original_modified"] is False
    assert np.max(np.abs(np.frombuffer(preview, dtype="<f4"))) <= 0.95
    assert metadata["preview_gain"] > 0
    assert (tmp_path / "case.f32").read_bytes() == raw


@pytest.mark.parametrize("mutation", ["bits", "count", "symlink", "nonfinite"])
def test_native_source_corruption_is_not_repaired(tmp_path, mutation):
    """Refuse wrong hashes/counts, symlinks and invalid signals before resampling or encoding."""
    case, raw = source(tmp_path)
    if mutation == "bits":
        (tmp_path / "case.f32").write_bytes(b"x" * len(raw))
    elif mutation == "count":
        case["sample_count"] += 1
    elif mutation == "symlink":
        (tmp_path / "case.f32").unlink()
        (tmp_path / "case.f32").symlink_to("missing")
    else:
        raw = np.array([np.nan] * 3, dtype="<f4").tobytes()
        (tmp_path / "case.f32").write_bytes(raw)
        case["waveform_sha256"] = hashlib.sha256(raw).hexdigest()
    with pytest.raises((ValueError, OSError)):
        load_native(case, tmp_path)


def test_silence_preview_gain_is_finite_and_nonfinite_refused():
    """Do not amplify silence into fabricated speech or hide invalid native output."""
    raw, metadata = preview_pcm(np.zeros(10, dtype="<f4"))
    assert metadata["preview_gain"] == 1 and raw == bytes(40)
    with pytest.raises(ValueError):
        preview_pcm(np.array([np.nan], dtype="<f4"))


@pytest.mark.parametrize("kind", ["success", "exit", "oversized", "not_ogg"])
def test_encoder_is_complete_bounded_offline_and_retains_no_native_write(
    monkeypatch, kind
):
    """Fix explicit codec/threads/timeout and reject failed, excessive or foreign encoder outputs."""
    calls = []

    def run(command, **kwargs):
        """Return a controlled encoder response while retaining its complete command and input contract."""
        calls.append((command, kwargs))
        return SimpleNamespace(
            returncode=1 if kind == "exit" else 0,
            stdout=b"OggS" + (bytes(256 * 1024) if kind == "oversized" else b"data")
            if kind != "not_ogg"
            else b"wrong",
            stderr=b"",
        )

    monkeypatch.setattr("scripts.tts_audio_diagnostics.subprocess.run", run)
    if kind == "success":
        assert encode_preview(bytes(40), 24000).startswith(b"OggS")
    else:
        with pytest.raises(ValueError):
            encode_preview(bytes(40), 24000)
    command, options = calls[0]
    assert command[-1] == "pipe:1" and "libopus" in command and "24k" in command
    assert options["input"] == bytes(40) and options["timeout"] == 30
