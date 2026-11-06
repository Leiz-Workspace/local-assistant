"""Protect native TTS sample fidelity, bounded exclusive output publication and separately declared rational ASR transformations without model execution."""

import hashlib
import struct

import numpy as np
import pytest

from scripts.tts_waveform import (
    OutputStore,
    asr_input,
    describe,
    wave_bytes,
    write_exclusive,
)


@pytest.mark.parametrize("rate", [22050, 24000])
def test_native_float_wave_preserves_real_sample_bits_and_complete_riff_counts(rate):
    """Check the uncompressed interoperability contract independently of serialization metadata."""
    values = np.array([0, 0.1, -0.2, 1.05], dtype="<f4")
    wav = wave_bytes(values, rate)
    assert wav[:4] == b"RIFF" and wav[8:12] == b"WAVE"
    assert struct.unpack_from("<I", wav, 4)[0] + 8 == len(wav)
    assert struct.unpack_from("<HHIIHH", wav, 20) == (3, 1, rate, rate * 4, 4, 32)
    assert wav[36:40] == b"fact" and struct.unpack_from("<I", wav, 44)[0] == len(values)
    assert (
        wav[48:52] == b"data" and struct.unpack_from("<I", wav, 52)[0] == values.nbytes
    )
    assert wav[56:] == values.tobytes()


def test_native_diagnostics_do_not_normalize_peaks_or_treat_sample_amplitude_as_speech_truth():
    """Retain full-scale overflow and low-amplitude counts without claiming naturalness or editing the waveform."""
    values = np.array([0, 0.1, -1.1, 0], dtype="<f4")
    original = values.tobytes()
    result = describe(values, 24000)
    assert (
        result["absolute_peak"] == pytest.approx(1.1)
        and result["full_scale_or_above_samples"] == 1
    )
    assert (
        result["leading_low_amplitude_samples"]
        == result["trailing_low_amplitude_samples"]
        == 1
    )
    assert result["native_sample_transform"] is False and values.tobytes() == original


def test_nonfinite_native_output_is_retained_as_failure_evidence_without_nan_repair(
    tmp_path,
):
    """Preserve actual broken model bytes while refusing to present them as a valid rendered signal or ASR input."""
    values = np.array([0, np.nan, np.inf], dtype="<f4")
    result = OutputStore(tmp_path).save(values, 24000, "failed-output")
    assert (
        result["finite"] is False
        and result["signal_valid"] is False
        and result["RMS"] is None
    )
    assert (tmp_path / result["raw_filename"]).read_bytes() == values.tobytes()
    with pytest.raises(ValueError):
        asr_input(values, 24000, lambda signal, up, down: signal)


@pytest.mark.parametrize("fault", ["dtype", "stereo", "empty", "rate", "too_long"])
def test_unsupported_or_unbounded_output_is_not_silently_cast_mixed_or_truncated(fault):
    """Fail the entire malformed shape/rate/duration boundary rather than fabricating a usable audio segment."""
    values, rate = np.zeros(100, dtype="<f4"), 24000
    if fault == "dtype":
        values = values.astype(np.float64)
    elif fault == "stereo":
        values = values.reshape(2, 50)
    elif fault == "empty":
        values = values[:0]
    elif fault == "rate":
        rate = 48000
    elif fault == "too_long":
        values = np.zeros(480001, dtype="<f4")
    with pytest.raises(ValueError):
        wave_bytes(values, rate)


def test_foreign_output_and_symlink_are_never_overwritten_or_adopted(tmp_path):
    """Refuse publication before creating a sibling raw file when the target WAV already belongs to someone else."""
    foreign = tmp_path / "foreign.wav"
    foreign.write_bytes(b"keep")
    values = np.zeros(100, dtype="<f4")
    store = OutputStore(tmp_path)
    with pytest.raises(FileExistsError):
        store.save(values, 24000, "foreign")
    assert foreign.read_bytes() == b"keep" and not (tmp_path / "foreign.f32").exists()
    (tmp_path / "linked.wav").symlink_to(foreign)
    with pytest.raises(FileExistsError):
        store.save(values, 24000, "linked")
    assert foreign.read_bytes() == b"keep" and not (tmp_path / "linked.f32").exists()


def test_valid_output_is_private_complete_and_hash_bound(tmp_path):
    """Bind every reported filename/count/hash to complete original samples and an independently readable container."""
    values = np.linspace(-0.5, 0.5, 1000, dtype="<f4")
    result = OutputStore(tmp_path).save(values, 22050, "en-greeting")
    assert (
        hashlib.sha256((tmp_path / result["wav_filename"]).read_bytes()).hexdigest()
        == result["wav_sha256"]
    )
    assert result["raw_bytes"] == 4000 and result["sample_count"] == 1000
    assert all(
        (tmp_path / result[key]).stat().st_mode & 0o777 == 0o600
        for key in ["raw_filename", "wav_filename"]
    )


@pytest.mark.parametrize("stem", ["../escape", "absolute/path", "UPPER", "", "a" * 81])
def test_output_identifiers_cannot_escape_or_widen_the_owned_result_capability(
    tmp_path, stem
):
    """Reject arbitrary worker-controlled filenames before touching the output filesystem."""
    with pytest.raises(ValueError):
        OutputStore(tmp_path).save(np.zeros(1, dtype="<f4"), 24000, stem)
    assert not list(tmp_path.iterdir())


def test_aggregate_budget_refuses_before_another_file_is_written(tmp_path):
    """Keep cumulative output allocation finite independently of the kernel per-file cap."""
    store = OutputStore(tmp_path)
    store.total_bytes = 64 * 1024**2
    with pytest.raises(ValueError, match="tts_output_total_bound"):
        store.save(np.zeros(1, dtype="<f4"), 24000, "bounded")
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("rate,up,down", [(24000, 2, 3), (22050, 320, 441)])
def test_resampler_uses_exact_rational_rate_and_records_separate_peak_scaling(
    rate, up, down
):
    """Verify dependency injection and source/count/scale contracts without pretending an authored unit resampler measures actual speech."""
    values = np.zeros(rate, dtype="<f4")
    original = values.tobytes()

    def authored_resampler(signal, actual_up, actual_down):
        """Return a known overshoot fixture only to test the declared ASR input normalization boundary."""
        assert signal is values and (actual_up, actual_down) == (up, down)
        return np.full(16000, 1.25, dtype="<f4")

    converted, metadata = asr_input(values, rate, authored_resampler)
    assert len(converted) == 16000 and float(converted.max()) == 1
    assert (
        metadata["unit_peak_scale"] == 0.8
        and metadata["native_original_modified"] is False
    )
    assert values.tobytes() == original


@pytest.mark.parametrize("fault", ["count", "nan"])
def test_broken_resampler_is_not_trimmed_zero_filled_or_accepted(fault):
    """Require complete anti-alias output accounting before replaying a model-generated waveform into ASR."""

    def authored_resampler(signal, up, down):
        """Inject a bad resampler contract for a controlled negative unit test."""
        return (
            np.zeros(15999, dtype="<f4")
            if fault == "count"
            else np.full(16000, np.nan, dtype="<f4")
        )

    with pytest.raises(ValueError):
        asr_input(np.zeros(24000, dtype="<f4"), 24000, authored_resampler)


def test_exclusive_writer_refuses_special_destination_and_oversized_data(tmp_path):
    """Keep output helper semantics independent of the container writer or synthesis SDK."""
    path = tmp_path / "exists"
    path.write_bytes(b"retain")
    with pytest.raises(FileExistsError):
        write_exclusive(path, b"replacement")
    with pytest.raises(ValueError):
        write_exclusive(tmp_path / "large", bytes(16 * 1024**2 + 1))
    assert path.read_bytes() == b"retain"
