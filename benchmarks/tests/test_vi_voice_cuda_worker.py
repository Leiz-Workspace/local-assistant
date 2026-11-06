"""Verify exact CUDA ASR scope and unchanged float32/int8 decoding construction without GPU or model dependencies."""

from types import SimpleNamespace
import sys

import pytest

from benchmarks.scripts import vi_voice_cuda_worker as target


def scope(mode="voice"):
    """Describe a finite CUDA capability with the original Qwen model identity."""
    return dict(
        role="qwen3-asr-0.6b",
        model="qwen3-asr-0.6b",
        policy="original-asr-decoding",
        native_authorized=True,
        mode=mode,
        max_requests={"probe": 0, "quality": 40, "voice": 4}[mode],
        execution_backend="cuda-original-precision",
        cpu_threads=8,
        scope_sha256="a" * 64,
    )


@pytest.mark.parametrize("mode", ["probe", "quality", "voice"])
def test_scope_fixes_phase_and_model_budget(mode):
    """Keep zero-weights probes separate from40case quality or4call native inference."""
    value = scope(mode)
    assert target.validate_scope(value) is value


@pytest.mark.parametrize(
    "field,value",
    [
        ("role", "new-model"),
        ("model", "other"),
        ("mode", "other"),
        ("max_requests", 5),
        ("max_requests", True),
        ("execution_backend", "cpu"),
        ("native_authorized", 1),
        ("cpu_threads", 4),
        ("cpu_threads", True),
        ("scope_sha256", "g" * 64),
    ],
)
def test_modified_capability_fails_before_loading(field, value):
    """Reject changed model/precision/budgets rather than silently accepting another runtime."""
    data = scope()
    data[field] = value
    with pytest.raises(ValueError, match="cuda_scope"):
        target.validate_scope(data)


def torch_fixture():
    """Expose a source-free authored CUDA configuration interface for exact precision/control tests."""
    calls = []
    cuda = SimpleNamespace(
        is_available=lambda: True,
        set_device=lambda x: calls.append(("device", x)),
        get_device_properties=lambda x: SimpleNamespace(total_memory=16 * 1024**3),
        set_per_process_memory_fraction=lambda f, d: calls.append(("fraction", f, d)),
    )
    torch = SimpleNamespace(
        __version__="2.10.0+cu128",
        version=SimpleNamespace(cuda="12.8"),
        cuda=cuda,
        set_num_threads=lambda n: calls.append(("threads", n)),
        set_num_interop_threads=lambda n: calls.append(("interop", n)),
        manual_seed=lambda n: calls.append(("seed", n)),
        set_float32_matmul_precision=lambda v: calls.append(("precision", v)),
        backends=SimpleNamespace(
            cuda=SimpleNamespace(matmul=SimpleNamespace(allow_tf32=True)),
            cudnn=SimpleNamespace(allow_tf32=True, deterministic=False),
        ),
        float32="fp32",
    )
    return torch, calls


def test_cuda_configuration_never_enables_tf32_or_changes_dtype():
    """Bound the allocator to4GiB and retain deterministic original-version float32 controls."""
    torch, calls = torch_fixture()
    target.configure_torch(torch)
    assert ("fraction", 0.25, 0) in calls and ("precision", "highest") in calls
    assert ("threads", 8) in calls and ("seed", 7) in calls
    assert (
        torch.backends.cuda.matmul.allow_tf32 is False
        and torch.backends.cudnn.allow_tf32 is False
    )


@pytest.mark.parametrize("bad", ["version", "cuda", "unavailable"])
def test_incompatible_runtime_has_no_fallback(bad):
    """Refuse a different Torch core/CUDA build or unavailable device rather than changing the approved precision."""
    torch, calls = torch_fixture()
    if bad == "version":
        torch.__version__ = "2.13.0+cu130"
    elif bad == "cuda":
        torch.version.cuda = "13.0"
    else:
        torch.cuda.is_available = lambda: False
    with pytest.raises(ValueError, match="cuda_torch_runtime"):
        target.configure_torch(torch)
    assert not calls


def test_qwen_loader_preserves_checkpoint_precision_and_original_decoder(monkeypatch):
    """Load directly to CUDA with the same fp32/eager/local checkpoint and inherited generation method."""
    from scripts.asr_evaluation_worker import Runtime as Original

    torch, _ = torch_fixture()
    calls = []

    class Model:
        """Represent only the constructor/device metadata used for precision verification."""

        device = "cuda:0"
        dtype = "fp32"

        @classmethod
        def from_pretrained(cls, path, **kwargs):
            """Record exact pinned-model loading controls without reading weights."""
            calls.append((path, kwargs))
            return cls()

        def eval(self):
            """Keep the authored model in inference state."""
            return self

    class Processor:
        """Expose the original local tokenizer/processor constructor only."""

        @classmethod
        def from_pretrained(cls, *args, **kwargs):
            """Return a source-free processor stub without remote model discovery."""
            assert kwargs == dict(local_files_only=True, fix_mistral_regex=True)
            return object()

    monkeypatch.setitem(sys.modules, "torch", torch)
    monkeypatch.setitem(sys.modules, "qwen_asr", SimpleNamespace())
    monkeypatch.setitem(sys.modules, "qwen_asr.core", SimpleNamespace())
    monkeypatch.setitem(
        sys.modules,
        "qwen_asr.core.transformers_backend",
        SimpleNamespace(
            Qwen3ASRForConditionalGeneration=Model, Qwen3ASRProcessor=Processor
        ),
    )
    runtime = target.Runtime("qwen3-asr-0.6b")
    assert calls == [
        (
            "/model",
            dict(
                dtype="fp32",
                local_files_only=True,
                attn_implementation="eager",
                device_map={"": "cuda:0"},
            ),
        )
    ]
    assert runtime.engine.transcribe.__func__ is Original.transcribe
