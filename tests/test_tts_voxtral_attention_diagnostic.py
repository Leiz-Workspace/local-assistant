"""Test the closed original-weight counterfactual, historical input bindings, strict first receipts and synthetic native paired forwarding."""

import base64
import copy
import inspect
import json
import logging
import subprocess
from pathlib import Path

import numpy as np
import pytest

from scripts import tts_voxtral_attention_diagnostic as parent
from scripts import tts_voxtral_attention_runtime as runtime
from scripts import tts_voxtral_auditory_runtime as native
from scripts import tts_voxtral_load as load

logger = logging.getLogger(__name__)


def packet_fixture():
    """Derive historical metadata only, without reading signals or running a model."""
    evidence, rows = parent.historical_cases()
    cases, provenance = [], []
    for number, old in enumerate(rows, 1):
        identity = f"clip-{number:02d}"
        expected = next(row["expected"] for row in evidence["controls_first_responses"] if row["id"] == old["id"])
        cases.append(dict(id=identity, task="presence", signals=[dict(old["signals"][0], id=identity + "-a")]))
        provenance.append(dict(id=identity, historical_id=old["id"], expected=expected, historical_raw_answer=old["raw_text"], historical_conditioning=old["conditioning"]))
    return dict(cases=cases), provenance


def event_fixture():
    """Construct auditable fake responses with exact first tensor/feature receipts and no original neural execution."""
    request, provenance = packet_fixture()
    evidence, _ = parent.historical_cases()
    events = copy.deepcopy(evidence["first_raw_events"][:5])
    events.append(dict(event="ready", cases=4, backends=["eager", "sdpa"], original_weight_worker_limit=1, no_qualification=True))
    replay = []
    for case, source in zip(request["cases"], provenance, strict=True):
        receipt = source["historical_conditioning"]
        observations = []
        for backend in ["eager", "sdpa"]:
            observed = dict(event="auditory", **case, prompt=native.TASKS["presence"][0], maximum_new_tokens=16, conditioning=receipt, generated_token_ids=[10, 2], raw_text="NO", answer="no", parse_error=None, generation_complete=True, seconds=1.0)
            vector = np.zeros(131072, dtype="<f4")
            vector[10] = 1
            observations.append(dict(backend=backend, observation=observed, first_logit_sha256=native.sha(vector.tobytes()), first_logit_argmax=10, greedy_first_token_matches_forward=True))
        events.append(dict(event="pair", id=case["id"], observations=observations, metrics=dict(vector_elements=131072, maximum_absolute_difference=0.0, RMS_difference=0.0, first_logit_argmax_equal=True, full_logit_vectors_equal=True)))
        replay.append(dict(event="conditioning", id=case["id"], conditioning=receipt))
    events.append(dict(event="complete", cases=4, responses=8, original_payload_and_storage_preserved=True, maximum_RSS_RAM_KiB=100, process_virtual_peaks_KiB=dict(VmPeak=200, VmHWM=100), D70_complete=False, reviewer_qualified=False))
    replay.append(dict(event="conditioning_complete", cases=4, original_model_loaded=False))
    return request, events, replay, provenance


def vector_fixture(events):
    """Encode auditable authored first-logit vectors without a model, checkpoint, recorded audio or inference."""
    vector = np.zeros(131072, dtype="<f4")
    vector[10] = 1
    raw = vector.tobytes()
    records = []
    for pair in [row for row in events if row["event"] == "pair"]:
        for item in pair["observations"]:
            record = dict(id=pair["id"], backend=item["backend"], dtype="float32_le", elements=131072, sha256=native.sha(raw), data_base64=base64.b64encode(raw).decode())
            records.append(runtime.VECTOR_PREFIX + json.dumps(record))
    return ("\n".join(records) + "\n").encode()


@pytest.mark.parametrize("mutation", ["none", "missing", "duplicate", "payload", "metric", "oversize"])
def test_full_logit_reconciliation(mutation):
    """Reject incomplete, duplicated, corrupted or inconsistent full vectors rather than trusting worker summary metrics alone."""
    _, events, _, _ = event_fixture()
    raw = vector_fixture(events)
    if mutation == "missing":
        raw = raw.split(b"\n", 1)[1]
    elif mutation == "duplicate":
        raw += raw.split(b"\n", 1)[0] + b"\n"
    elif mutation == "payload":
        raw = raw.replace(b'"data_base64": "A', b'"data_base64": "B', 1)
    elif mutation == "metric":
        events[6]["metrics"]["RMS_difference"] = 1.0
    elif mutation == "oversize":
        raw = b"x" * (8 * 1024**2 + 1)
    assert parent.verify_logit_metrics(events, raw) is (mutation == "none")


def test_permission_denied_before_access(monkeypatch, tmp_path):
    """Block controller and actual no-model worker before any original SDK/model/audio request or first-output creation."""
    assert runtime.EXECUTION_ALLOWED is False
    monkeypatch.setattr(parent, "OUTPUT", tmp_path / "absent")
    with pytest.raises(ValueError, match="not_approved"):
        parent.run()
    assert not parent.OUTPUT.exists()
    command = load.command()
    command[command.index(str(load.WORKER))] = str(parent.WORKER)
    result = subprocess.run(command, capture_output=True, timeout=15)
    assert result.returncode != 0 and b"voxtral_attention_diagnostic_not_approved" in result.stderr and not result.stdout
    logger.info("voxtral_attention_original_execution_denied before_access=True")


def test_namespace_boundaries():
    """Exclude parent source/gold/credentials and exclude checkpoint weights entirely from independent replay."""
    for replay in [False, True]:
        command = parent.command(replay=replay)
        assert "--unshare-all" in command and "--as=12884901888" in command and "--cpu=1200:1201" in command
        assert "/samples" in command and ("/model" not in command if replay else "/model" in command)
        assert not any("parent-only" in part or "tts_voxtral_attention_diagnostic.py" in part for part in command)
        assert str(parent.WORKER) in command and str(load.WORKER) in command
        assert ("--conditioning-only" in command) is replay


def test_packet_symlink_rejected_before_preparation(tmp_path, monkeypatch):
    """Reject redirected packet storage before creating copies or reading original model/audio inputs."""
    redirected = tmp_path / "redirected"
    redirected.symlink_to(tmp_path, target_is_directory=True)
    monkeypatch.setattr(parent, "PACKET", redirected / "new-packet")
    with pytest.raises(ValueError, match="packet_symlink"):
        parent.prepare()
    assert not (tmp_path / "new-packet").exists()


@pytest.mark.parametrize("mutation", ["labels", "backend", "length", "boolsize", "source", "gold", "features"])
def test_packet_rejects_unapproved_changes(mutation):
    """Refuse source replacement, metadata leakage, prompt overrides and rewritten historical expectations/features."""
    request, provenance = packet_fixture()
    parent.validate_packet(request, provenance)
    if mutation == "labels":
        request["expected"] = "yes"
    elif mutation == "backend":
        request["cases"][0]["backend"] = "eager"
    elif mutation == "length":
        request["cases"].pop()
    elif mutation == "boolsize":
        request["cases"][0]["signals"][0]["sample_count"] = True
    elif mutation == "source":
        request["cases"][0]["signals"][0]["sha256"] = "0" * 64
    elif mutation == "gold":
        provenance[0]["expected"] = "no"
    else:
        provenance[0]["historical_conditioning"]["BF16_feature_sha256"] = "0" * 64
    with pytest.raises(ValueError):
        parent.validate_packet(request, provenance)


@pytest.mark.parametrize("mutation", ["none", "backend", "EOS", "raw", "feature", "replay", "nan", "bool", "hash", "tokens", "qualified", "peak", "greedy"])
def test_first_observation_audit(mutation):
    """Recompute strict raw coverage and reject invalid evidence without promoting backend answers into qualification."""
    request, events, replay, provenance = event_fixture()
    first = events[6]["observations"][0]
    if mutation == "backend":
        first["backend"] = "other"
    elif mutation == "EOS":
        first["observation"]["generated_token_ids"][-1] = 151645
    elif mutation == "raw":
        first["observation"]["raw_text"] = "YES"
    elif mutation == "feature":
        first["observation"]["conditioning"] = dict(first["observation"]["conditioning"], BF16_feature_sha256="0" * 64)
    elif mutation == "replay":
        replay.pop()
    elif mutation == "nan":
        events[6]["metrics"]["RMS_difference"] = float("nan")
    elif mutation == "bool":
        events[6]["metrics"]["full_logit_vectors_equal"] = 1
    elif mutation == "hash":
        first["first_logit_sha256"] = "z" * 64
    elif mutation == "tokens":
        first["observation"]["generated_token_ids"][0] = True
    elif mutation == "qualified":
        events[-1]["reviewer_qualified"] = True
    elif mutation == "peak":
        events[-1]["process_virtual_peaks_KiB"]["VmPeak"] = True
    elif mutation == "greedy":
        first["greedy_first_token_matches_forward"] = False
    assert parent.audit(request, events, replay, provenance) is (mutation == "none")


def test_first_output_cannot_be_retried(tmp_path, monkeypatch):
    """Reject a second approved attempt before preparation verification or model launch."""
    monkeypatch.setattr(runtime, "EXECUTION_ALLOWED", True)
    monkeypatch.setattr(parent, "OUTPUT", tmp_path)
    with pytest.raises(ValueError, match="first_output_exists"):
        parent.run()


@pytest.mark.parametrize("valid", [False, True])
def test_one_phase_preserves_first_failure_and_never_qualifies(tmp_path, monkeypatch, valid):
    """Retain partial or complete first receipts, run one replay and grant no model/backend/qualification gate on either outcome."""
    request, events, replay, provenance = event_fixture()
    packet = tmp_path / "packet"
    packet.mkdir()
    (packet / "request.json").write_text(json.dumps(request))
    (packet / "parent-only.json").write_text(json.dumps(dict(cases=provenance)))
    monkeypatch.setattr(runtime, "EXECUTION_ALLOWED", True)
    monkeypatch.setattr(parent, "PACKET", packet)
    monkeypatch.setattr(parent, "OUTPUT", tmp_path / "first")
    def fixture_preparation():
        """Provide fixed preparation metadata without opening original artifacts or SDK inventories."""
        return dict(fixture=True)

    def fixture_bindings():
        """Provide stable source bindings without inventing an original filesystem audit."""
        return dict(fixture="unchanged")

    def fixture_headroom():
        """Provide a stubbed host guard without allocating memory or reserving host RAM."""
        return dict(fixture_headroom=True)

    def fixture_core():
        """Provide stable process identity without contacting the real CORE service."""
        return dict(pid=1, start_ticks=2, command_sha256="same")

    def fixture_waveform(*args):
        """Return authored zeros without accessing any original signal."""
        return np.zeros(1600, dtype="<f4")

    monkeypatch.setattr(load, "verify_preparation", fixture_preparation)
    monkeypatch.setattr(parent, "bindings", fixture_bindings)
    monkeypatch.setattr(parent, "require_headroom", fixture_headroom)
    monkeypatch.setattr(parent, "core_snapshot", fixture_core)
    monkeypatch.setattr(native, "waveform", fixture_waveform)
    calls = []
    raw = ("\n".join(json.dumps(row) for row in events) + "\n").encode() if valid else b'{"partial":\n'

    def fixture_worker(command, supplied, timeout):
        """Return first synthetic worker bytes without creating a process, loading weights or evaluating audio."""
        calls.append(dict(command=command, request=supplied, timeout=timeout))
        replayed = ("\n".join(json.dumps(row) for row in replay) + "\n").encode()
        stderr = b"retained fixture stderr\n" + vector_fixture(events) if len(calls) == 1 else b"retained fixture stderr\n"
        return dict(exit_code=0 if valid else 1, timed_out=False, owned_process_reaped=True), raw if len(calls) == 1 else replayed, stderr

    monkeypatch.setattr(parent, "run_worker", fixture_worker)
    result = parent.run()
    assert result["observation_complete"] is valid
    assert result["D70_complete"] is False and result["reviewer_qualified"] is False and result["backend_selected"] is False
    assert (parent.OUTPUT / "worker.stdout.jsonl").read_bytes() == raw
    assert (parent.OUTPUT / "worker.stderr.log").read_bytes() == b"retained fixture stderr\n" + vector_fixture(events)
    assert [row["timeout"] for row in calls] == [900, 120]
    assert "--conditioning-only" not in calls[0]["command"] and "--conditioning-only" in calls[1]["command"]
    with pytest.raises(ValueError, match="first_output_exists"):
        parent.run()
    assert len(calls) == 2
    logger.info("voxtral_attention_first_phase_fixture_validated valid=%s retained=True no_retry=True", valid)


def paired_native_probe():
    """Exercise the new pairing path on random miniature layers and authored silence, with the real vocabulary/processor and no original weights."""
    import os

    import paired_runtime
    import torch
    from transformers import VoxtralConfig, VoxtralForConditionalGeneration
    from tts_voxtral_auditory_runtime import processor, sha

    assert not Path("/model").exists()
    os.sched_setaffinity(0, {0, 1})
    torch.set_num_threads(2)
    torch.set_num_interop_threads(1)
    torch.manual_seed(110)
    config = VoxtralConfig(audio_config=dict(hidden_size=8, intermediate_size=32, num_hidden_layers=1, num_attention_heads=2, num_key_value_heads=2, num_mel_bins=128, max_source_positions=1500), text_config=dict(model_type="llama", hidden_size=8, intermediate_size=16, num_hidden_layers=1, num_attention_heads=2, num_key_value_heads=1, head_dim=4, vocab_size=131072, max_position_embeddings=4096), hidden_size=8, vocab_size=131072, audio_token_id=24)
    config._attn_implementation = "eager"
    model = VoxtralForConditionalGeneration(config).to(dtype=torch.bfloat16).eval()
    model.audio_tower.embed_positions.to(dtype=torch.float32)
    raw = Path("/samples/clip-01-a.f32").read_bytes()
    row = dict(id="clip-01", task="presence", signals=[dict(id="clip-01-a", sample_count=len(raw) // 4, sha256=sha(raw))])
    observed = paired_runtime.compare_case(model, processor(Path("/assets")), row)
    assert [item["backend"] for item in observed["observations"]] == ["eager", "sdpa"]
    assert observed["metrics"]["vector_elements"] == 131072
    assert observed["observations"][0]["observation"]["conditioning"] == observed["observations"][1]["observation"]["conditioning"]
    assert all(len(item["observation"]["generated_token_ids"]) <= 16 for item in observed["observations"])
    print(json.dumps(dict(original_weights_mounted=False, recorded_audio_mounted=False, original_model_predictions=0, parameters=sum(t.numel() for t in model.parameters()), actual_native_pairing_exercised=True, model_is_random=True, paired=observed)), flush=True)


def test_real_native_pairing_on_authored_synthetic_input(tmp_path):
    """Run actual native forward/generation for both backends without mounting any original model weights or recorded audio."""
    probe = tmp_path / "probe.py"
    probe.write_text('"""Run a synthetic random-model pairing fixture only."""\nimport json\nfrom pathlib import Path\n\n' + inspect.getsource(paired_native_probe) + '\n\npaired_native_probe()\n')
    samples = tmp_path / "authored-samples"
    samples.mkdir()
    (samples / "clip-01-a.f32").write_bytes(np.zeros(3200, dtype="<f4").tobytes())
    command = load.command()
    index = command.index("--chdir")
    extra = ["--ro-bind", str(probe), "/app/probe.py", "--ro-bind", str(parent.WORKER), "/app/paired_runtime.py", "--ro-bind", str(parent.auditory.WORKER), "/app/tts_voxtral_auditory_runtime.py", "--ro-bind", str(samples), "/samples", "--dir", "/assets"]
    for name in ["tekken.json", "preprocessor_config.json"]:
        extra += ["--ro-bind", str(load.ROOT / "model" / name), "/assets/" + name]
    command[index:index] = extra
    command[-1] = "/app/probe.py"
    result = subprocess.run(command, capture_output=True, timeout=90)
    logger.info("voxtral_attention_native_pair_fixture exit_code=%d stdout=%s stderr_bytes=%d", result.returncode, result.stdout.decode(), len(result.stderr))
    assert result.returncode == 0, result.stderr.decode()
    observed = json.loads(result.stdout.splitlines()[-1])
    assert observed["actual_native_pairing_exercised"] and observed["model_is_random"]
    assert observed["original_model_predictions"] == 0 and not observed["original_weights_mounted"] and not observed["recorded_audio_mounted"]
    assert parent.verify_logit_metrics([dict(event="pair", **observed["paired"])], result.stderr)
