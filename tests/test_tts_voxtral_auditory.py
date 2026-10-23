"""Test closed Voxtral auditory execution, strict blind requests and native synthetic conditioning without original weights or D70 audio."""

import copy
import inspect
import json
import logging
import subprocess
from pathlib import Path

import numpy as np
import pytest

from scripts import tts_voxtral_auditory as parent
from scripts import tts_voxtral_auditory_runtime as runtime
from scripts import tts_voxtral_load as load

logger = logging.getLogger(__name__)


def request_fixture():
    """Describe twelve opaque cases with no reference labels, source names or generation overrides."""
    rows = []
    for i, task in enumerate(["presence"] * 4 + ["language"] * 2 + ["comparison"] * 6, 1):
        identity = f"clip-{i:02d}"
        rows.append(dict(id=identity, task=task, signals=[dict(id=identity + "-" + letter, sample_count=32000, sha256="0" * 64) for letter in ("ab" if task == "comparison" else "a")]))
    return dict(mode="controls", cases=rows)


def test_original_auditory_guard_closed():
    """Reject original audio inference before SDK, model, request or signal access."""
    assert runtime.AUDITORY_EXECUTION_ALLOWED is False
    with pytest.raises(ValueError, match="not_approved"):
        runtime.main()


def test_blind_request_coverage():
    """Accept complete declared controls and reject reference leakage, overrides and out-of-bound signals."""
    request = request_fixture()
    runtime.validate_request(request)
    invalid = []
    for key, value in [("expected", "yes"), ("max_new_tokens", 1000)]:
        changed = copy.deepcopy(request)
        changed["cases"][0][key] = value
        invalid.append(changed)
    for key, value in [("sample_count", True), ("sample_count", 320001), ("id", "../gold"), ("sha256", "bad")]:
        changed = copy.deepcopy(request)
        changed["cases"][0]["signals"][0][key] = value
        invalid.append(changed)
    changed = copy.deepcopy(request)
    changed["cases"].pop()
    invalid.append(changed)
    changed = copy.deepcopy(request)
    changed["cases"][0]["task"] = "review"
    invalid.append(changed)
    for changed in invalid:
        with pytest.raises(ValueError):
            runtime.validate_request(changed)


@pytest.mark.parametrize("task,raw,wanted", [("presence", " YES\n", "yes"), ("language", "Vietnamese", "vietnamese"), ("comparison", "EQUAL", "equal")])
def test_preregistered_closed_label_normalization(task, raw, wanted):
    """Normalize only case and outer whitespace before any new model answer has been observed."""
    assert runtime.parse_answer(task, raw) == wanted


@pytest.mark.parametrize("raw", ['{"naturalness":"natural","notes":"Even rhythm."}', '{"naturalness":"uncertain","notes":"Unable to judge pronunciation confidently."}'])
def test_strict_review_JSON(raw):
    """Retain explicit uncertainty and audible notes without generating MOS or repairing model text."""
    assert runtime.parse_answer("review", raw) == json.loads(raw)


@pytest.mark.parametrize("task,raw", [("presence", "Yes."), ("comparison", "first because it clips"), ("language", "English or Vietnamese"), ("review", '```json\n{"naturalness":"natural","notes":"Fine."}\n```'), ("review", '{"naturalness":"natural","naturalness":"unnatural","notes":"Fine."}'), ("review", '{"naturalness":"natural","notes":"Fine.","MOS":5}'), ("review", '{"naturalness":"natural","notes":""}')])
def test_answer_repair_and_label_invention_rejected(task, raw):
    """Refuse unapproved punctuation/prose/schema changes rather than repairing first responses into favorable labels."""
    with pytest.raises(ValueError):
        runtime.parse_answer(task, raw)


def test_exact_waveform_integrity(tmp_path):
    """Preserve full float32 samples and reject symlinks, mutation and nonfinite values."""
    values = np.linspace(-0.2, 0.2, 32000, dtype="<f4")
    raw = values.tobytes()
    signal = dict(id="clip-01-a", sample_count=len(values), sha256=runtime.sha(raw))
    path = tmp_path / "clip-01-a.f32"
    path.write_bytes(raw)
    assert np.array_equal(runtime.waveform(signal, tmp_path), values)
    path.write_bytes(raw[:-4])
    with pytest.raises(ValueError):
        runtime.waveform(signal, tmp_path)
    path.unlink()
    (tmp_path / "target").write_bytes(raw)
    path.symlink_to("target")
    with pytest.raises(ValueError):
        runtime.waveform(signal, tmp_path)


def native_processor_probe():
    """Exercise local native processor FLOAT WAV roundtrips on synthetic signals without any original checkpoint or recorded audio mount."""
    import os

    import numpy as np
    import torch
    import tts_voxtral_auditory_runtime as auditory

    os.sched_setaffinity(0, {0, 1})
    torch.set_num_threads(2)
    torch.set_num_interop_threads(1)
    assert not Path("/model").exists() and not Path("/samples").exists()
    native = auditory.processor(Path("/assets"))
    zeros = np.zeros(32000, dtype="<f4")
    tone = (np.sin(np.arange(48000) * 2 * np.pi * 440 / 16000) * 0.1).astype("<f4")
    observations = []
    for task, signals in [("presence", [zeros]), ("language", [tone]), ("comparison", [zeros, tone]), ("review", [tone])]:
        inputs, receipt = auditory.conditioning(native, task, signals)
        assert receipt["source_sha256"] == receipt["native_source_prefix_sha256"]
        assert inputs.input_features.dtype == torch.bfloat16
        observations.append(dict(task=task, **receipt))
    print(json.dumps(dict(original_weights_mounted=False, original_audio_mounted=False, model_predictions=0, observations=observations)), flush=True)


def test_native_synthetic_processor_in_sealed_sdk(tmp_path):
    """Verify pinned tokenizer/feature interoperability and full 30-second padding using exact readonly metadata and no weights."""
    probe = tmp_path / "probe.py"
    probe.write_text('"""Verify only synthetic native conditioning with no model or recorded-audio access."""\nimport json\nfrom pathlib import Path\n\n' + inspect.getsource(native_processor_probe) + '\n\nnative_processor_probe()\n')
    command = load.command()
    index = command.index("--chdir")
    mounts = ["--dir", "/assets", "--ro-bind", str(Path(runtime.__file__).resolve()), "/app/tts_voxtral_auditory_runtime.py", "--ro-bind", str(probe), "/app/probe.py"]
    for name in ["tekken.json", "preprocessor_config.json"]:
        mounts += ["--ro-bind", str(load.ROOT / "model" / name), "/assets/" + name]
    command[index:index] = mounts
    command[-1] = "/app/probe.py"
    result = subprocess.run(command, capture_output=True, timeout=60)
    logger.info("voxtral_native_synthetic_processor exit_code=%d stdout=%s stderr=%s", result.returncode, result.stdout.decode(), result.stderr.decode())
    assert result.returncode == 0, result.stderr.decode()
    value = json.loads(result.stdout.splitlines()[-1])
    assert not value["original_weights_mounted"] and not value["original_audio_mounted"] and value["model_predictions"] == 0
    assert [row["audio_tokens"] for row in value["observations"]] == [375, 375, 750, 375]


def synthetic_SDPA_probe():
    """Compare native eager/SDPA and exercise bounded generation on a tiny random checkpoint, not the retained original model."""
    import os

    import torch
    from transformers import VoxtralConfig, VoxtralForConditionalGeneration

    os.sched_setaffinity(0, {0, 1})
    torch.set_num_threads(2)
    torch.set_num_interop_threads(1)
    torch.manual_seed(109)
    assert not Path("/model").exists() and not Path("/samples").exists()
    config = VoxtralConfig(audio_config=dict(model_type="voxtral_encoder", hidden_size=8, intermediate_size=16, num_hidden_layers=1, num_attention_heads=2, num_key_value_heads=2, head_dim=4, num_mel_bins=4, max_source_positions=4), text_config=dict(model_type="llama", hidden_size=8, intermediate_size=16, num_hidden_layers=1, num_attention_heads=2, num_key_value_heads=1, head_dim=4, vocab_size=64, max_position_embeddings=32), hidden_size=8, vocab_size=64, audio_token_id=24)
    config._attn_implementation = "eager"
    model = VoxtralForConditionalGeneration(config).to(dtype=torch.bfloat16).eval()
    model.audio_tower.embed_positions.to(dtype=torch.float32)
    identities = {name: (tensor.data_ptr(), tensor.detach().clone()) for name, tensor in model.state_dict().items()}
    ids = torch.tensor([[1, 24, 24, 5]])
    features = torch.randn(1, 4, 8, dtype=torch.bfloat16)
    with torch.inference_mode():
        eager = model(input_ids=ids, input_features=features, logits_to_keep=1).logits
        model.set_attn_implementation("sdpa")
        actual = model(input_ids=ids, input_features=features, logits_to_keep=1).logits
        generated = model.generate(input_ids=ids, input_features=features, attention_mask=torch.ones_like(ids), do_sample=False, num_beams=1, max_new_tokens=2, eos_token_id=2, pad_token_id=11, bos_token_id=1, use_cache=True, logits_to_keep=1)
    torch.testing.assert_close(eager, actual, rtol=0.1, atol=0.01)
    assert 1 <= generated.shape[1] - ids.shape[1] <= 2
    for name, tensor in model.state_dict().items():
        pointer, original = identities[name]
        assert tensor.data_ptr() == pointer and torch.equal(tensor, original)
    assert all(cfg._attn_implementation == "sdpa" for cfg in [model.config, model.audio_tower.config, model.language_model.config])
    print(json.dumps(dict(original_weights_mounted=False, original_audio_mounted=False, tiny_parameters=sum(t.numel() for t in model.parameters()), native_SDPA_passed=True, original_storage_preserved=True, maximum_logit_difference=float((eager - actual).abs().max()), generated_tokens=int(generated.shape[1] - ids.shape[1]))), flush=True)


def test_native_tiny_audio_SDPA_and_decoder(tmp_path):
    """Validate the actual pinned SDK attention switch and decode kwargs without original-model or recorded-audio access."""
    probe = tmp_path / "probe.py"
    probe.write_text('"""Verify tiny native SDPA and bounded decode, never original checkpoint weights or audio."""\nimport json\nfrom pathlib import Path\n\n' + inspect.getsource(synthetic_SDPA_probe) + '\n\nsynthetic_SDPA_probe()\n')
    command = load.command()
    index = command.index("--chdir")
    command[index:index] = ["--ro-bind", str(probe), "/app/probe.py"]
    command[-1] = "/app/probe.py"
    result = subprocess.run(command, capture_output=True, timeout=30)
    logger.info("voxtral_tiny_SDPA exit_code=%d stdout=%s stderr=%s", result.returncode, result.stdout.decode(), result.stderr.decode())
    assert result.returncode == 0, result.stderr.decode()
    observed = json.loads(result.stdout.splitlines()[-1])
    assert observed["tiny_parameters"] == 2760 and observed["native_SDPA_passed"] and observed["original_storage_preserved"]


def event_fixture(request):
    """Create auditable synthetic first outputs for gate mutation tests, with no neural model or real waveform access."""
    events = [dict(event=name) for name in ["headers", "schema", "shard", "shard", "integrity"]]
    events.append(dict(event="ready", mode=request["mode"], cases=len(request["cases"]), attention="sdpa", native_payload_unchanged=True, native_storage_unchanged=True))
    mapping = []
    comparison_index = 0
    presence_index, language_index = 0, 0
    for row in request["cases"]:
        task = row["task"]
        if task == "comparison":
            answer = ["first", "second", "equal"][comparison_index % 3]
            comparison_index += 1
        elif task == "presence":
            answer = "yes" if presence_index < 2 else "no"
            presence_index += 1
        else:
            answer = "english" if language_index == 0 else "vietnamese"
            language_index += 1
        signals = row["signals"]
        hashes = [signal["sha256"] for signal in signals]
        features = dict(source_sha256=hashes, native_source_prefix_sha256=hashes, native_padded_waveform_sha256=["a" * 64] * len(signals), source_sample_counts=[signal["sample_count"] for signal in signals], sample_rate=16000, native_padded_samples_per_signal=480000, feature_shape=[len(signals), 128, 3000], audio_tokens=375 * len(signals), input_tokens=800, FP32_feature_sha256="1" * 64, BF16_feature_sha256="2" * 64, input_ids_sha256="3" * 64)
        events.append(dict(event="auditory", **row, prompt=runtime.TASKS[task][0], maximum_new_tokens=runtime.TASKS[task][1], generation_complete=True, parse_error=None, generated_token_ids=[7, 2], raw_text=answer.upper(), answer=answer, conditioning=features, seconds=1.0))
        mapping.append(dict(id=row["id"], task=task, expected=answer))
    events.append(dict(event="complete", mode=request["mode"], cases=len(request["cases"]), maximum_RSS_RAM_KiB=1000, process_virtual_peaks_KiB=dict(VmPeak=2000, VmHWM=1000), D70_complete=False))
    return events, mapping


def test_strict_controls_and_independent_replay():
    """Reject modified raw answers, missing EOS, one failed control, altered feature evidence and incomplete replay."""
    request = request_fixture()
    events, mapping = event_fixture(request)
    assert parent.audit_events(request, events)
    assert parent.quality_checks(request, events, mapping)
    replay = [dict(event="conditioning", id=event["id"], conditioning=event["conditioning"]) for event in events[6:-1]]
    replay.append(dict(event="conditioning_complete", cases=12, original_model_loaded=False))
    assert parent.replay_matches(request, events, replay)
    changed = copy.deepcopy(events)
    changed[6]["raw_text"] = "NO"
    assert not parent.quality_checks(request, changed, mapping)
    changed[6]["answer"] = "no"
    assert parent.audit_events(request, changed) and not parent.quality_checks(request, changed, mapping)
    for key, value in [("generated_token_ids", [7, 151645]), ("generation_complete", False), ("parse_error", "bad")]:
        changed = copy.deepcopy(events)
        changed[6][key] = value
        assert not parent.audit_events(request, changed)
    changed = copy.deepcopy(replay)
    changed[0]["conditioning"]["BF16_feature_sha256"] = "4" * 64
    assert not parent.replay_matches(request, events, changed)
    assert not parent.replay_matches(request, events, replay[:-1])


def test_campaign_closed_before_any_model_or_common_input():
    """Reject campaign and phase execution immediately while the original audio scope is unapproved."""
    for action in [parent.campaign, parent.run_phase]:
        with pytest.raises(ValueError, match="not_approved"):
            action() if action == parent.campaign else action("controls")


def test_worker_mounts_exclude_gold_and_replay_weights():
    """Expose only pure sources/opaque samples and strip checkpoint weights from conditioning audit namespaces."""
    for mode in ["controls", "review"]:
        command = parent.worker_command(mode)
        assert "/samples" in command and "/model" in command and "--as=12884901888" in command
        assert str(Path(parent.__file__).resolve()) not in command
        assert not any("parent-only" in item or "request.json" in item for item in command)
        replay = parent.worker_command(mode, replay=True)
        assert "/model" not in replay and "/assets/tekken.json" in replay and replay[-1] == "--conditioning-only"


def test_packet_exclusive_and_blind(tmp_path):
    """Retain full synthetic float32 timelines and keep all expected labels outside the worker request."""
    request = request_fixture()
    _, mapping = event_fixture(request)
    items = [dict(task=row["task"], values=[np.zeros(32000, dtype="<f4")] * len(row["signals"]), expected=expected["expected"], source="fixture-parent-only") for row, expected in zip(request["cases"], mapping, strict=True)]
    directory = tmp_path / "packet"
    actual = parent.publish_packet(directory, "controls", items)
    assert "fixture-parent-only" not in json.dumps(actual) and "expected" not in json.dumps(actual)
    assert len(list((directory / "inputs").iterdir())) == 18
    with pytest.raises(FileExistsError):
        parent.publish_packet(directory, "controls", items)


def test_review_preparation_checks_gate_first(tmp_path, monkeypatch):
    """Prevent common-audio access or packet creation when strict first controls have not qualified."""
    def reject():
        """Simulate an unqualified first control result without reading any common audio."""
        raise ValueError("fixture_controls_not_qualified")

    monkeypatch.setattr(parent, "require_controls", reject)
    monkeypatch.setattr(parent, "REVIEW_PACKET", tmp_path / "absent")
    with pytest.raises(ValueError, match="not_qualified"):
        parent.prepare_review()
    assert not (tmp_path / "absent").exists()


def test_campaign_conditional_order_without_neural_execution(monkeypatch):
    """Run the orchestration with synthetic results and prove failed controls stop while success admits exactly one review phase."""
    monkeypatch.setattr(runtime, "AUDITORY_EXECUTION_ALLOWED", True)
    calls = []
    allowed = False

    def phase(mode):
        """Record a synthetic phase result without loading original models or accessing common audio."""
        calls.append(mode)
        return dict(quality_controls_passed=allowed, mode=mode)

    def prepare():
        """Record conditional preparation without reading any recorded waveform."""
        calls.append("prepare")

    monkeypatch.setattr(parent, "run_phase", phase)
    monkeypatch.setattr(parent, "prepare_review", prepare)
    assert parent.campaign() is None and calls == ["controls"]
    calls.clear()
    allowed = True
    assert parent.campaign()["mode"] == "review" and calls == ["controls", "prepare", "review"]


def test_actual_auditory_namespace_denied_before_request():
    """Prove the original auditory CLI is closed inside the real no-weights replay namespace before request parsing."""
    result = subprocess.run(parent.worker_command("controls", replay=True), input=b"", capture_output=True, timeout=15)
    assert result.returncode != 0 and not result.stdout and b"voxtral_auditory_not_approved" in result.stderr


def test_real_prepared_controls_are_blind_and_balanced():
    """Inspect the authored packet without exposing expected labels to the worker or executing a reviewer."""
    request = json.loads((parent.CONTROL_PACKET / "request.json").read_text())
    private = json.loads((parent.CONTROL_PACKET / "parent-only.json").read_text())["mapping"]
    runtime.validate_request(request)
    assert len(request["cases"]) == 12 and len(private) == 12
    assert "expected" not in json.dumps(request) and not any(identity in json.dumps(request) for identity in parent.SOURCES)
    assert sorted(row["expected"] for row in private if row["task"] == "comparison") == ["equal", "equal", "first", "first", "second", "second"]
    assert sorted(row["expected"] for row in private if row["task"] == "presence") == ["no", "no", "yes", "yes"]
    for row in request["cases"]:
        for signal in row["signals"]:
            assert runtime.waveform(signal, parent.CONTROL_PACKET / "inputs").size == signal["sample_count"]


def test_review_rejects_duplicate_original_identity(tmp_path, monkeypatch):
    """Refuse duplicate original signals before publishing a supposedly complete twenty-four-audio review packet."""
    original = tmp_path / "data/backups/d70-common-audio-diagnostics-first"
    (original / "generated").mkdir(parents=True)
    raw = np.zeros(1600, dtype="<f4").tobytes()
    (original / "generated/item.f32").write_bytes(raw)
    row = dict(event="transformed", id="item", asr=dict(waveform_sha256=runtime.sha(raw), sample_count=1600))
    (original / "result.json").write_text(json.dumps(dict(events=[row] * 24)))

    def fixture_gate():
        """Allow only synthetic fixture access without claiming actual controls or loading a model."""
        logger.info("voxtral_fixture_gate_open_no_model_execution")

    monkeypatch.setattr(parent, "require_controls", fixture_gate)
    monkeypatch.setattr(parent, "PROJECT", tmp_path)
    monkeypatch.setattr(parent, "REVIEW_PACKET", tmp_path / "absent")
    with pytest.raises(ValueError, match="original_coverage"):
        parent.prepare_review()
    assert not (tmp_path / "absent").exists()
