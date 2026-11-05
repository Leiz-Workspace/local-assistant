"""Verify fixed resident CPU capabilities and unchanged backend/decoder construction without loading private models."""

from types import SimpleNamespace
import sys

import pytest

from benchmarks.scripts import vi_voice_resident_worker as target


def scope(role="turbo", threads=4):
    """Describe one finite authored worker capability with role-specific original identity."""
    return dict(
        role=role,
        cpu_threads=threads,
        max_requests=6 if role == "vad" else 4,
        native_authorized=True,
        scope_sha256="a" * 64,
        model=target.ROLE_MODELS[role],
        policy=target.ROLE_POLICIES[role],
        voice="Trúc Ly" if role == "turbo" else None,
    )


@pytest.mark.parametrize(
    "role,threads",
    [
        ("vad", 2),
        ("turbo", 2),
        ("turbo", 4),
        ("turbo", 8),
        ("whisper-small-ct2", 4),
        ("qwen3-asr-0.6b", 8),
    ],
)
def test_only_declared_role_profile_capabilities_pass(role, threads):
    """Keep each original model bound to the declared finite thread allocation."""
    value = scope(role, threads)
    assert target.validate_scope(value) is value


@pytest.mark.parametrize(
    "field,bad",
    [
        ("role", "other"),
        ("cpu_threads", True),
        ("cpu_threads", 3),
        ("max_requests", 5),
        ("max_requests", True),
        ("native_authorized", 1),
        ("scope_sha256", "x" * 64),
        ("model", "other"),
        ("policy", "other"),
        ("voice", "other"),
    ],
)
def test_invalid_capabilities_fail_before_model_import(field, bad):
    """Refuse modified model/settings/budget or pseudo-boolean authorization before inference can start."""
    value = scope()
    value[field] = bad
    with pytest.raises(ValueError, match="resident_"):
        target.validate_scope(value)


def test_detector_keeps_original_two_threads():
    """Do not turn ASR/TTS CPU allocation into an undeclared VAD setting change."""
    with pytest.raises(ValueError, match="vad_threads"):
        target.validate_scope(scope("vad", 4))


def test_baseline_calls_the_original_runtime_without_reimplementation(monkeypatch):
    """Keep the two-thread baseline's model loading and inference fields exactly on the original constructor."""
    called = []

    def init(self, candidate):
        """Expose an authored baseline initialization without importing model frameworks."""
        called.append(candidate)
        self.execution = {"device": "cpu"}

    monkeypatch.setattr(target.Runtime, "__init__", init)
    runtime = target.ProfileRuntime("turbo", 2)
    assert called == ["turbo"] and runtime.execution["cpu_threads"] == 2


def test_qwen_changes_only_thread_count_after_original_load(monkeypatch):
    """Retain original weights/precision/attention/decoding and change only the declared Torch CPU count."""
    called = []

    def init(self, candidate):
        """Model the original load once with explicit dtype/attention metadata."""
        called.append(("load", candidate))
        state = {"threads": 2}
        self.engine = SimpleNamespace(
            torch=SimpleNamespace(
                set_num_threads=lambda n: state.update(threads=n),
                get_num_threads=lambda: state["threads"],
            )
        )
        self.execution = dict(
            device="cpu",
            parameter_dtype="torch.float32",
            attention_implementation="eager",
        )

    monkeypatch.setattr(target.Runtime, "__init__", init)
    runtime = target.ProfileRuntime("qwen3-asr-0.6b", 8)
    assert called == [("load", "qwen3-asr-0.6b")]
    assert (
        runtime.execution["parameter_dtype"] == "torch.float32"
        and runtime.execution["attention_implementation"] == "eager"
    )
    assert runtime.engine.torch.get_num_threads() == 8


def test_whisper_retains_precision_model_and_explicit_original_decode_method(
    monkeypatch,
):
    """Assert the sole constructor difference is cpu_threads while inherited transcription remains unchanged."""
    from scripts.asr_evaluation_worker import Runtime as OriginalASR

    calls = []

    def model(path, **kwargs):
        """Record the model constructor without opening any weights or SDK runtime."""
        calls.append((path, kwargs))
        return SimpleNamespace(
            model=SimpleNamespace(device="cpu", compute_type="int8_float32")
        )

    monkeypatch.setitem(sys.modules, "ctranslate2", SimpleNamespace(__version__="test"))
    monkeypatch.setitem(
        sys.modules,
        "faster_whisper",
        SimpleNamespace(WhisperModel=model, __version__="test"),
    )
    runtime = target.ProfileRuntime("whisper-small-ct2", 4)
    assert calls == [
        (
            "/model",
            dict(
                device="cpu",
                compute_type="int8",
                cpu_threads=4,
                num_workers=1,
                local_files_only=True,
            ),
        )
    ]
    assert runtime.engine.transcribe.__func__ is OriginalASR.transcribe


@pytest.mark.parametrize("threads", [4, 8])
def test_tts_uses_original_precision_and_checks_all_session_threads(
    monkeypatch, threads
):
    """Exercise the public thread argument while retaining original voice/backend/precision and zero retries."""
    import numpy

    calls = []

    def engine(**kwargs):
        """Return only the immutable engine metadata needed for load verification."""
        calls.append(kwargs)
        session = SimpleNamespace(
            get_providers=lambda: ["CPUExecutionProvider"],
            get_session_options=lambda: SimpleNamespace(
                intra_op_num_threads=threads, inter_op_num_threads=1
            ),
        )
        nested = SimpleNamespace(
            babble_retries=0,
            denoiser=object(),
            **{
                name: session
                for name in (
                    "sess_pre",
                    "sess_dec",
                    "sess_ac",
                    "sess_codec_dec",
                    "sess_codec_step",
                )
            },
        )
        return SimpleNamespace(
            backend="onnx",
            engine=nested,
            _preset_voices={"Trúc Ly": {}, "Ngọc Huyền": {}},
            watermarker=None,
        )

    monkeypatch.setitem(sys.modules, "numpy", numpy)
    monkeypatch.setitem(sys.modules, "onnxruntime", SimpleNamespace(__version__="test"))
    monkeypatch.setitem(sys.modules, "vieneu", SimpleNamespace())
    monkeypatch.setitem(
        sys.modules, "vieneu.v3turbo", SimpleNamespace(V3TurboVieNeuTTS=engine)
    )
    monkeypatch.setattr(target, "FrameObserver", lambda engine: None)
    runtime = target.ProfileRuntime("turbo", threads)
    assert (
        calls[0]["threads"] == threads
        and calls[0]["precision"] == "fp32"
        and calls[0]["babble_retries"] == 0
    )
    assert all(x["intra_threads"] == threads for x in runtime.execution["sessions"])
