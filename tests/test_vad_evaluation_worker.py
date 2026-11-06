"""Protect sealed VAD inputs, exact official window/reset observation, source integrity and real readonly offline execution without model inference."""

import hashlib
import json
import os
import subprocess
import sys
from types import SimpleNamespace

import numpy as np
import pytest

from scripts.asr_evaluation_runner import prepare_runtime_identity
from scripts.vad_evaluation import sandbox, worker_request
from scripts.vad_evaluation_worker import (
    Observer,
    Runtime,
    load_waveform,
    validate_request,
    validate_segments,
)


def authored_case(identity="speech", samples=16000):
    """Build a small authored request fixture independent of actual corpus predictions."""
    return dict(
        id=identity,
        filename=identity + ".f32",
        sample_count=samples,
        waveform_sha256="a" * 64,
    )


def test_labels_and_timeline_ground_truth_never_enter_model_request():
    """Withhold parent-only coarse labels/offsets and upstream text from the worker."""
    cases = [
        dict(
            authored_case(str(i)),
            reference="upstream words",
            timeline_origin_samples=32000,
            kind="positive",
        )
        for i in range(47)
    ]
    request = worker_request("predict", cases)
    assert "reference" not in json.dumps(request) and "timeline" not in json.dumps(
        request
    )
    assert len(request["cases"]) == 47


@pytest.mark.parametrize(
    "fault",
    [
        "label",
        "path",
        "duplicate",
        "mode",
        "count",
        "bool_count",
        "digest",
        "rate",
        "missing",
        "too_many",
    ],
)
def test_invalid_or_labelled_request_cannot_reach_sdk_import(fault):
    """Reject injection, scope drift and ambiguous/unbounded samples before any native model execution."""
    request = worker_request("smoke", [authored_case()])
    row = request["cases"][0]
    if fault == "label":
        row["kind"] = "expected speech"
    elif fault == "path":
        row["filename"] = "../corpus.json"
    elif fault == "duplicate":
        request["mode"] = "predict"
        request["cases"] = [row] * 47
    elif fault == "mode":
        request["mode"] = "tune-threshold"
    elif fault == "count":
        row["sample_count"] = 512001
    elif fault == "bool_count":
        row["sample_count"] = True
    elif fault == "digest":
        row["waveform_sha256"] = "xyz"
    elif fault == "rate":
        row["sampling_rate"] = 48000
    elif fault == "missing":
        request["mode"] = "predict"
    elif fault == "too_many":
        request["cases"] *= 48
    with pytest.raises(ValueError):
        validate_request(request)


def test_exact_float_waveform_is_owned_and_bit_identical(tmp_path):
    """Avoid hidden quantization, resampling or an SDK file decoder in the VAD input boundary."""
    raw = np.linspace(-0.5, 0.5, 16000, dtype="<f4").tobytes()
    case = authored_case()
    case["waveform_sha256"] = hashlib.sha256(raw).hexdigest()
    (tmp_path / case["filename"]).write_bytes(raw)
    waveform = load_waveform(case, tmp_path)
    assert waveform.tobytes() == raw and waveform.flags.writeable


@pytest.mark.parametrize(
    "fault", ["truncated", "extra", "hash", "nan", "range", "symlink", "fifo"]
)
def test_untrusted_waveform_cannot_be_repaired_adopted_or_block_on_special_file(
    tmp_path, fault
):
    """Refuse corrupt signals and filesystem tricks before reporting a model probability."""
    raw = np.zeros(16000, dtype="<f4").tobytes()
    if fault == "nan":
        raw = np.full(16000, np.nan, dtype="<f4").tobytes()
    elif fault == "range":
        raw = np.full(16000, 2, dtype="<f4").tobytes()
    case = authored_case()
    case["waveform_sha256"] = hashlib.sha256(raw).hexdigest()
    if fault == "truncated":
        raw = raw[:-1]
    elif fault == "extra":
        raw += b"x"
    elif fault == "hash":
        case["waveform_sha256"] = "b" * 64
    path = tmp_path / case["filename"]
    if fault == "fifo":
        os.mkfifo(path)
    elif fault == "symlink":
        (tmp_path / "other").write_bytes(raw)
        path.symlink_to(tmp_path / "other")
    else:
        path.write_bytes(raw)
    with pytest.raises((ValueError, OSError)):
        load_waveform(case, tmp_path)


@pytest.mark.parametrize(
    "segments",
    [
        [dict(start=-1, end=10)],
        [dict(start=0, end=16001)],
        [dict(start=True, end=10)],
        [dict(start=1.5, end=10)],
        [dict(start=2, end=2)],
        [dict(start=0, end=20), dict(start=19, end=30)],
    ],
)
def test_impossible_overlapping_or_rounded_timestamps_are_not_silently_repaired(
    segments,
):
    """Keep complete original integer sample bounds instead of clamping malformed SDK output into apparent correctness."""
    with pytest.raises(ValueError):
        validate_segments(segments, 16000)


def test_adjacent_exact_half_open_intervals_remain_valid():
    """Accept meaningful end/start equality without inventing overlap or changing source coordinates."""
    validate_segments([dict(start=0, end=8000), dict(start=8000, end=16000)], 16000)


def test_observer_returns_the_original_output_and_forwards_real_reset():
    """Ensure audit instrumentation cannot change original model probabilities or suppress recurrent-state reset."""
    calls = []
    output = SimpleNamespace(item=lambda: 0.25)

    class Model:
        """Expose an authored unit-only window/reset boundary without loading an ONNX model."""

        def reset_states(self):
            """Retain an observable external reset invocation."""
            calls.append("reset")

        def __call__(self, waveform, rate):
            """Return the exact authored output object for observer identity verification."""
            calls.append(rate)
            return output

    observer = Observer(Model())
    observer.reset_states()
    assert observer(np.zeros(512, dtype="<f4"), 16000) is output
    assert (
        calls == ["reset", 16000]
        and observer.resets == 1
        and observer.probabilities == [0.25]
    )


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -0.1, 1.1])
def test_nonfinite_or_out_of_range_model_probability_refuses(value):
    """Reject invalid native output rather than interpreting it as silence or clipping its score."""
    observer = Observer(lambda waveform, rate: SimpleNamespace(item=lambda: value))
    with pytest.raises(ValueError):
        observer(np.zeros(512, dtype="<f4"), 16000)


def test_real_namespace_refuses_host_network_credentials_gpu_references_and_writes(
    tmp_path,
):
    """Exercise actual kernel mounts/network/resource enforcement with no private SDK/model dependency."""
    for name in ["official", "samples", "runtime-source"]:
        (tmp_path / name).mkdir()
    (tmp_path / "venv").symlink_to(sys.prefix)
    prepare_runtime_identity(tmp_path)
    code = '''"""Inspect actual VAD evaluation isolation using only stdlib."""
import json, os, pathlib, pwd, resource, socket
assert not pathlib.Path('/home').exists() and not pathlib.Path('/corpus.json').exists()
assert pwd.getpwuid(os.getuid()).pw_name=='asr-evaluation'
assert not any('TOKEN' in key or 'VAULT' in key for key in os.environ)
assert os.environ['CUDA_VISIBLE_DEVICES']=='' and not list(pathlib.Path('/dev').glob('nvidia*'))
assert resource.getrlimit(resource.RLIMIT_AS)[0]==3221225472
assert resource.getrlimit(resource.RLIMIT_CPU)==(180,181)
assert not list(pathlib.Path('/samples').iterdir())
connection=socket.socket(); connection.settimeout(1)
assert connection.connect_ex(('127.0.0.1',8080)) != 0
connection.close()
try:
 pathlib.Path('/official/forbidden').write_text('x')
 raise AssertionError('writable model/source')
except OSError:
 pass
info=os.statvfs('/tmp'); assert info.f_blocks*info.f_frsize==128*1024**2
print(json.dumps({'isolated':True}))
'''
    result = subprocess.run(
        sandbox(tmp_path)[:-1] + ["-c", code], capture_output=True, timeout=10
    )
    assert result.returncode == 0, result.stderr.decode()
    assert json.loads(result.stdout) == dict(isolated=True)


def test_original_segmentation_tail_padding_is_counted_without_modifying_source():
    """Validate final incomplete model-window accounting and a reset per recording independently of actual VAD predictions."""

    class Model:
        """Return a fixed authored window probability for lifecycle accounting only."""

        def reset_states(self):
            """Expose the expected reset boundary without native state."""
            return None

        def __call__(self, waveform, rate):
            """Supply a bounded scalar for a complete official-size model window."""
            return SimpleNamespace(item=lambda: 0.1)

    def segment(audio, observer, **kwargs):
        """Emulate only the official reset/window/pad protocol, never claim an actual model output."""
        observer.reset_states()
        for index in range(0, len(audio), 512):
            chunk = audio[index : index + 512]
            observer(np.pad(chunk, (0, 512 - len(chunk))), 16000)
        return []

    runtime = object.__new__(Runtime)
    runtime.model, runtime.numpy, runtime.segment = Model(), np, segment
    runtime.torch = SimpleNamespace(from_numpy=lambda values: values)
    original = np.zeros(16003, dtype="<f4")
    result = runtime.observe(original)
    assert (
        result["model_windows"] == 32 and result["padded_final_window_samples"] == 381
    )
    assert (
        result["external_recording_resets"] == 1
        and result["source_samples_modified"] is False
    )
    assert len(original) == 16003 and not original.any()


def test_sdk_source_mutation_is_not_reported_as_unchanged_audio():
    """Refuse a decoder/helper that modifies the common waveform even if its returned timestamp list looks valid."""

    def mutate(audio, observer, **kwargs):
        """Corrupt only an authored unit fixture to verify the ownership/integrity defense."""
        audio[0] = 1
        return []

    runtime = object.__new__(Runtime)
    runtime.model, runtime.segment = object(), mutate
    runtime.torch = SimpleNamespace(from_numpy=lambda values: values)
    with pytest.raises(ValueError, match="vad_source_mutated"):
        runtime.observe(np.zeros(16000, dtype="<f4"))
