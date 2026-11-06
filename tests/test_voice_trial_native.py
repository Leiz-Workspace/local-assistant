"""Test browser native scope, separate waveform bindings and transient-media erasure without neural inference."""

import io
import json
from types import SimpleNamespace
from uuid import uuid4

import numpy as np
import pytest

from apps.voice_trial import native, worker
from apps.voice_trial.audio import decode_wave, encode_wave
from src.application.services.voice_pipeline import digest


def scope(role):
    """Describe one exact finite browser research capability with unchanged stage identities."""
    return dict(
        role=role,
        native_authorized=True,
        max_requests=24,
        mode="voice",
        model=native.cuda.resident.ROLE_MODELS[role],
        policy=native.cuda.resident.ROLE_POLICIES[role],
        cpu_threads=2 if role == "vad" else 8,
        voice="Trúc Ly" if role == "turbo" else None,
        execution_backend="cuda-original-precision"
        if role == "qwen3-asr-0.6b"
        else "cpu",
        scope_sha256="a" * 64,
    )


@pytest.mark.parametrize("role", ["vad", "qwen3-asr-0.6b", "turbo"])
def test_fixed_bounded_scope_reuses_existing_roles(role):
    """Keep the sole qualified lane explicit without claiming product selection or allowing Whisper fallback."""
    assert worker.validate_scope(scope(role))["max_requests"] == 24


@pytest.mark.parametrize(
    "field,value",
    [
        ("role", "whisper-small-ct2"),
        ("max_requests", 25),
        ("max_requests", True),
        ("cpu_threads", 4),
        ("model", "new-model"),
        ("policy", "other"),
        ("execution_backend", "cpu"),
        ("scope_sha256", "g" * 64),
        ("native_authorized", 1),
    ],
)
def test_altered_scope_fails_before_runtime_loading(field, value):
    """Reject different models, budgets, resources and missing authorization before any model constructor."""
    value_scope = scope("qwen3-asr-0.6b")
    value_scope[field] = value
    with pytest.raises(ValueError, match="trial_worker_scope"):
        worker.validate_scope(value_scope)


@pytest.mark.asyncio
async def test_asr_uses_original_pcm_and_never_detector_copy(tmp_path):
    """Verify original float bytes and digest on the actual browser ASR port rather than a fake source path mapping."""
    (tmp_path / "inputs").mkdir()
    messages = []

    async def call(message):
        """Inspect exact admitted original bytes before returning an authored unedited transcript."""
        messages.append(message)
        raw = (tmp_path / "inputs/source.f32").read_bytes()
        assert digest(raw) == message["waveform_sha256"]
        assert np.frombuffer(raw, dtype="<f4")[0] == 0.125
        return {"asr": {"text": "original transcript", "output_cap_reached": False}}

    runtime = SimpleNamespace(
        root=tmp_path,
        workers=[None, SimpleNamespace(call=call)],
        counts=dict(vad=0, asr=0, core=0, tts=0),
    )
    audio = decode_wave(encode_wave(b"\0\x10" * 16000))
    ports = native.Ports(runtime, audio, "trial-fixture")
    value = await ports.transcribe(uuid4(), audio, "vi")
    assert value.text == "original transcript" and runtime.counts["asr"] == 1
    with pytest.raises(Exception):
        await ports.transcribe(uuid4(), audio, "vi")
    assert len(messages) == 1


def test_turn_erasure_removes_all_RAM_input_output_and_private_diagnostics(tmp_path):
    """Delete user input/detector/native chunks and truncate diagnostics after the joined turn."""
    runtime = native.NativeRuntime()
    runtime.root = tmp_path
    root_worker = tmp_path / "worker"
    for folder in (tmp_path / "inputs", tmp_path / "views", root_worker / "native"):
        folder.mkdir(parents=True)
        (folder / "private.f32").write_bytes(b"user audio")
    runtime.workers = [
        SimpleNamespace(directory=root_worker, log=io.BytesIO(b"private user log"))
    ]
    runtime.server = SimpleNamespace(log=io.BytesIO(b"private CORE log"))
    runtime.erase_turn()
    assert not list(tmp_path.rglob("*.f32"))
    assert runtime.workers[0].log.getvalue() == runtime.server.log.getvalue() == b""


@pytest.mark.asyncio
async def test_non_RAM_temp_environment_stops_before_any_model_loading(monkeypatch):
    """Keep anonymous conversion files in RAM by refusing a normal disk temp directory."""
    monkeypatch.setattr(native.tempfile, "gettempdir", lambda: "/tmp")
    runtime = native.NativeRuntime()
    with pytest.raises(RuntimeError, match="RAM_tempdir"):
        await runtime.start()
    assert not runtime.workers and runtime.server is None


@pytest.mark.parametrize("role", ["vad", "qwen3-asr-0.6b", "turbo"])
def test_command_binds_new_entry_and_explicit_dynamic_input_directory(
    monkeypatch, tmp_path, role
):
    """Preserve original command controls while making the browser worker manifest the sole entry point."""
    calls = []

    def base(*args, **kwargs):
        """Record the readonly source directory passed to the existing qualified namespace builder."""
        calls.append((args, kwargs))
        return [
            "bwrap",
            "--unshare-all",
            "--remount-ro",
            "/",
            "python",
            "old-worker",
            "sha",
        ]

    monkeypatch.setattr(native.cuda, "command", base)
    monkeypatch.setattr(native.cuda.resident, "command", base)
    args = native.worker_command(
        role, tmp_path / "out", tmp_path / "scope", "a" * 64, tmp_path / "original"
    )
    assert args[-2] == "/app/apps/voice_trial/worker.py" and "--unshare-all" in args
    assert calls[0][0][-1] == tmp_path / "original"
    if role == "qwen3-asr-0.6b":
        assert calls[0][1]["mode"] == "quality"


@pytest.mark.asyncio
async def test_retirement_receipt_keeps_only_control_metrics_and_erases_workspace(
    monkeypatch, tmp_path
):
    """Retain auditable exit/count/resource metadata without persisting private media or model content."""
    monkeypatch.setattr(native, "AUDIT_ROOT", tmp_path / "audit")
    (tmp_path / "audit").mkdir()
    runtime = native.NativeRuntime()
    runtime.root = tmp_path / "ephemeral-session"
    runtime.root.mkdir()
    removed = []

    async def close(force=False):
        """Represent completed owned process retirement without native model access."""
        return None

    runtime.workers = [
        SimpleNamespace(
            candidate="vad",
            process=SimpleNamespace(pid=42, returncode=0),
            failure=None,
            peak_rss=100,
            peak_vram=0,
            close=close,
        )
    ]
    runtime.temp = SimpleNamespace(cleanup=lambda: removed.append(True))
    await runtime.close()
    receipt = next((tmp_path / "audit/lifetimes").glob("*.json"))
    data = json.loads(receipt.read_text())
    assert data["workers"][0]["returncode"] == 0 and removed == [True]
    assert (
        "audio_base64" not in data and "transcript" not in data and "answer" not in data
    )
