"""Protect reference-free ASR requests, official prompt conventions, readonly offline execution and owned timeout cleanup without model inference."""

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from scripts.asr_evaluation_runner import (
    prepare_runtime_identity,
    public_request,
    qualification_case,
    run_worker,
    sandbox_command,
)
from scripts.asr_evaluation_worker import (
    Runtime,
    load_waveform,
    qwen_prompt,
    validate_request,
)


def source_case():
    """Supply a parent-only reference fixture for testing the request projection boundary."""
    return dict(
        id="vi_vn-0000",
        language="vi_vn",
        filename="123.wav",
        waveform_path="/private/vi_vn-0000.f32",
        sample_count=16000,
        waveform_sha256="a" * 64,
        reference="private reference",
        raw_reference="raw label",
    )


def test_reference_fields_and_upstream_paths_never_enter_worker_request():
    """Project only immutable waveform identity and public language, withholding labels and parent filesystem locations."""
    request = public_request("qwen3-asr-0.6b", "predict", [source_case()])
    assert "reference" not in json.dumps(request) and "/private" not in json.dumps(
        request
    )
    assert request["cases"][0]["filename"] == "vi_vn-0000.f32"


@pytest.mark.parametrize(
    "fault",
    [
        "reference",
        "candidate",
        "path",
        "count",
        "bool_count",
        "duplicate",
        "digest",
        "language",
        "empty",
        "extra",
    ],
)
def test_reference_injection_arbitrary_path_and_ambiguous_request_refuse(fault):
    """Fail before importing a model when requests carry labels, unsupported scope or unbounded/ambiguous input."""
    request = public_request("qwen3-asr-0.6b", "predict", [source_case()])
    row = request["cases"][0]
    if fault == "reference":
        row["reference"] = "injected"
    elif fault == "candidate":
        request["candidate"] = "another-model"
    elif fault == "path":
        row["filename"] = "../labels.json"
    elif fault == "count":
        row["sample_count"] = 320001
    elif fault == "bool_count":
        row["sample_count"] = True
    elif fault == "duplicate":
        request["cases"].append(row)
    elif fault == "digest":
        row["waveform_sha256"] = "not-a-digest"
    elif fault == "language":
        row["language"] = "auto"
    elif fault == "empty":
        request["cases"] = []
    elif fault == "extra":
        request["remote_url"] = "https://example.com"
    with pytest.raises(ValueError):
        validate_request(request)


def test_import_qualification_does_not_allow_cases_or_predictions():
    """Keep source-import qualification distinct from any candidate benchmark/model input."""
    request = public_request("whisper-small-ct2", "imports", [source_case()])
    assert request["cases"] == []
    request["cases"] = public_request("whisper-small-ct2", "predict", [source_case()])[
        "cases"
    ]
    with pytest.raises(ValueError):
        validate_request(request)


def test_exact_float_input_bits_are_preserved_and_owned_by_the_inference_call(tmp_path):
    """Read complete unquantized common samples with no reference/audio text and no alias into a parent buffer."""
    raw = np.linspace(-0.5, 0.5, 16000, dtype="<f4").tobytes()
    row = public_request("qwen3-asr-0.6b", "predict", [source_case()])["cases"][0]
    row["waveform_sha256"] = hashlib.sha256(raw).hexdigest()
    (tmp_path / row["filename"]).write_bytes(raw)
    array = load_waveform(row, tmp_path)
    assert array.tobytes() == raw and array.flags.writeable


@pytest.mark.parametrize(
    "fault", ["truncated", "extended", "digest", "nan", "range", "symlink", "fifo"]
)
def test_corrupt_nonfinite_oversized_or_nonregular_waveform_refuse(tmp_path, fault):
    """Refuse the entire case rather than repairing/clipping samples or blocking on a special file."""
    raw = np.zeros(16000, dtype="<f4").tobytes()
    row = public_request("qwen3-asr-0.6b", "predict", [source_case()])["cases"][0]
    path = tmp_path / row["filename"]
    if fault == "nan":
        raw = np.full(16000, float("nan"), dtype="<f4").tobytes()
    elif fault == "range":
        raw = np.full(16000, 2, dtype="<f4").tobytes()
    row["waveform_sha256"] = hashlib.sha256(raw).hexdigest()
    if fault == "truncated":
        raw = raw[:-1]
    elif fault == "extended":
        raw += b"x"
    elif fault == "digest":
        row["waveform_sha256"] = "b" * 64
    if fault == "fifo":
        os.mkfifo(path)
    elif fault == "symlink":
        target = tmp_path / "target"
        target.write_bytes(raw)
        path.symlink_to(target)
    else:
        path.write_bytes(raw)
    with pytest.raises((ValueError, OSError)):
        load_waveform(row, tmp_path)


def test_qwen_prompt_uses_empty_context_audio_and_forced_language_suffix():
    """Verify the official backend prompt format without inserting labels or synthetic task instructions."""

    class Processor:
        """Observe the exact prompt boundary without replacing a model in any benchmark."""

        def apply_chat_template(self, messages, **kwargs):
            """Assert the upstream empty-context message schema and chat-template options."""
            assert messages == [
                dict(role="system", content=""),
                dict(role="user", content=[dict(type="audio", audio="")]),
            ]
            assert kwargs == dict(add_generation_prompt=True, tokenize=False)
            return "official-template"

    assert (
        qwen_prompt(Processor(), "Vietnamese")
        == "official-templatelanguage Vietnamese<asr_text>"
    )


def test_whisper_lazy_segment_generator_is_fully_materialized_with_declared_controls():
    """Ensure inference timing/coverage includes generator consumption and never enables optional VAD/timestamps/retries."""
    from types import SimpleNamespace

    observed = []

    class Model:
        """Expose an authored lazy inference boundary for lifecycle testing only."""

        def transcribe(self, audio, **kwargs):
            """Record explicit CPU evaluation decoding options and return an unconsumed generator."""
            assert kwargs["vad_filter"] is False and kwargs["temperature"] == 0.0
            assert (
                kwargs["condition_on_previous_text"] is False
                and kwargs["without_timestamps"] is True
            )
            assert kwargs["language"] == "vi" and kwargs["max_new_tokens"] == 256

            def iterator():
                """Delay observable work until the segment iterator is consumed."""
                observed.append("consumed")
                yield SimpleNamespace(text=" xin chào", tokens=[1, 2])

            return iterator(), SimpleNamespace(duration=1, duration_after_vad=1)

    runtime = object.__new__(Runtime)
    runtime.candidate, runtime.model = "whisper-small-ct2", Model()
    result = runtime.transcribe(np.zeros(16000, dtype="<f4"), "vi_vn")
    assert (
        observed == ["consumed"]
        and result["text"] == " xin chào"
        and result["wall_seconds"] > 0
    )


def test_qwen_generation_does_not_duplicate_the_official_backend_return_dict_option():
    """Exercise the SDK generation boundary that already supplies return_dict internally, preserving raw decoded text."""
    from contextlib import nullcontext
    from types import SimpleNamespace

    class Inputs(dict):
        """Represent only the device/dtype movement boundary for an authored unit test."""

        def to(self, target):
            """Keep the authored tensor fixture unchanged while observing the backend call protocol."""
            return self

    class Processor:
        """Observe exact processor and decode options without performing model inference."""

        def apply_chat_template(self, messages, **kwargs):
            """Return a fixed upstream-template placeholder only for this controlled unit test."""
            return "template"

        def __call__(self, **kwargs):
            """Confirm a complete single waveform reaches the processor without hidden labels."""
            assert len(kwargs["audio"][0]) == 16000 and kwargs["padding"] is True
            return Inputs(input_ids=np.array([[1, 2, 3]]))

        def batch_decode(self, tokens, **kwargs):
            """Verify only newly generated tokens are decoded without cleanup or transcript repair."""
            assert tokens.tolist() == [[99, 151645]]
            assert kwargs == dict(
                skip_special_tokens=True, clean_up_tokenization_spaces=False
            )
            return [" raw output "]

    class Model:
        """Provide an authored generation-call contract matching the official wrapper's internal return-dict behavior."""

        device, dtype = "cpu", "float32"
        generation_config = SimpleNamespace(eos_token_id=[151645, 151643])

        def generate(self, **kwargs):
            """Reject the previously duplicated keyword and retain the declared deterministic token ceiling."""
            assert "return_dict_in_generate" not in kwargs
            assert kwargs["max_new_tokens"] == 256 and kwargs["do_sample"] is False
            return SimpleNamespace(sequences=np.array([[1, 2, 3, 99, 151645]]))

    runtime = object.__new__(Runtime)
    runtime.candidate, runtime.model, runtime.processor = (
        "qwen3-asr-0.6b",
        Model(),
        Processor(),
    )
    runtime.torch = SimpleNamespace(inference_mode=nullcontext)
    result = runtime.transcribe(np.zeros(16000, dtype="<f4"), "en_us")
    assert result["text"] == " raw output " and result["generated_tokens"] == 2
    assert result["output_cap_reached"] is False


def test_actual_namespace_has_no_host_reference_credentials_network_gpu_or_writable_model(
    tmp_path,
):
    """Exercise real kernel isolation using only stdlib and empty authored mounts, independently of private model artifacts."""
    for name in ["runtime-source/qwen-backend-source", "prediction-inputs", "model"]:
        (tmp_path / name).mkdir(parents=True)
    (tmp_path / "venv").symlink_to(Path(sys.prefix))
    prepare_runtime_identity(tmp_path)
    command = sandbox_command("qwen3-asr-0.6b", tmp_path / "model", tmp_path)
    code = '''"""Probe the real evaluation namespace without loading or scoring a model."""
import json, os, pathlib, resource, socket
import pwd
assert pwd.getpwuid(os.getuid()).pw_name == 'asr-evaluation'
assert pathlib.Path('/etc/passwd').read_text().count(':x:') == 1
assert not pathlib.Path('/home').exists()
assert not pathlib.Path('/prepared').exists()
assert not any('TOKEN' in key or 'VAULT' in key for key in os.environ if key != 'TOKENIZERS_PARALLELISM')
assert os.environ['CUDA_VISIBLE_DEVICES'] == ''
assert not list(pathlib.Path('/dev').glob('nvidia*'))
assert resource.getrlimit(resource.RLIMIT_AS)[0] == 8589934592
assert not list(pathlib.Path('/samples').iterdir())
try:
 pathlib.Path('/model/forbidden').write_text('x')
 raise AssertionError('writable model')
except OSError:
 pass
connection=socket.socket()
connection.settimeout(1)
assert connection.connect_ex(('127.0.0.1',8080)) != 0
connection.close()
stat=os.statvfs('/tmp')
assert stat.f_blocks * stat.f_frsize == 128*1024**2
print(json.dumps({'isolated':True}))
'''
    result = subprocess.run(
        command[:-1] + ["-c", code], capture_output=True, timeout=10
    )
    assert result.returncode == 0, result.stderr.decode()
    assert json.loads(result.stdout) == {"isolated": True}


def test_timeout_reaps_owned_process_without_returning_success_or_retrying():
    """Stop an actual hanging controlled child and preserve its already-flushed observation."""
    code = 'import time; print("partial",flush=True); time.sleep(60)'
    metadata, stdout, _ = run_worker([sys.executable, "-c", code], {}, timeout=0.15)
    assert (
        metadata["timed_out"]
        and metadata["exit_code"] != 0
        and metadata["owned_process_reaped"]
    )
    assert stdout == b"partial\n"


def test_real_existing_speech_qualification_excludes_reference_and_common_corpus(
    tmp_path,
):
    """Exercise the accepted native normalizer on the pinned existing public fixture without running ASR or scoring it."""
    case = qualification_case(tmp_path)
    assert case["reference"] is None and case["kind"] == "qualification_only_not_scored"
    assert case["sample_count"] == 176000
    assert len(Path(case["waveform_path"]).read_bytes()) == 176000 * 4
    assert not (tmp_path / "prepared").exists()
    assert (
        public_request("qwen3-asr-0.6b", "predict", [case])["cases"][0]["id"]
        == "qualification-jfk"
    )
