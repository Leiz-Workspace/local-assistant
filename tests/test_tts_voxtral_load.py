"""Test the closed load-only protocol with adversarial metadata and a tiny synthetic native checkpoint, never original Voxtral weights."""

import copy
import hashlib
import inspect
import json
import logging
import struct
import subprocess
from pathlib import Path

import pytest

from scripts import tts_voxtral_load as controller
from scripts import tts_voxtral_load_runtime as runtime

logger = logging.getLogger(__name__)


def fixture_shard(directory, shape=None, dtype="BF16", offsets=None, trailing=b""):
    """Create a tiny handcrafted safetensor payload for independent malformed-header checks without Torch."""
    directory.mkdir(exist_ok=True)
    name = "audio_tower.test.weight"
    shard = "model-00001-of-00001.safetensors"
    raw = b"\x01\x02\x03\x04"
    header = {name: dict(shape=shape or [2], dtype=dtype, data_offsets=offsets or [0, len(raw)])}
    encoded = json.dumps(header).encode()
    (directory / shard).write_bytes(struct.pack("<Q", len(encoded)) + encoded + raw + trailing)
    (directory / "model.safetensors.index.json").write_text(json.dumps(dict(metadata=dict(total_size=4), weight_map={name: shard})))
    logger.info("voxtral_handcrafted_header_fixture_created bytes=4")
    return shard


def test_original_permission_closed_before_access(tmp_path, monkeypatch):
    """Keep original model execution closed independently of the retired preparation approval."""
    assert runtime.LOAD_EXECUTION_ALLOWED is False
    monkeypatch.setattr(controller, "OUTPUT", tmp_path / "absent")
    with pytest.raises(ValueError, match="not_approved"):
        controller.run()
    with pytest.raises(ValueError, match="not_approved"):
        runtime.main()
    assert not (tmp_path / "absent").exists()


def test_explicit_load_permission_can_open_only_load_guard(monkeypatch):
    """Verify the explicit approval switch without importing a model SDK or starting any original-weight process."""
    monkeypatch.setattr(runtime, "LOAD_EXECUTION_ALLOWED", True)
    assert runtime.require_permission() is None
    logger.info("voxtral_approved_load_guard_fixture_passed model_started=False")


def test_worker_denied_inside_actual_namespace():
    """Prove the actual no-model offline namespace rejects the worker before importing Torch or loading weights."""
    result = subprocess.run(controller.command(), capture_output=True, timeout=15)
    assert result.returncode != 0 and b"voxtral_original_load_not_approved" in result.stderr
    assert not result.stdout


def test_namespace_exact_exposure():
    """Mount only the new SDK/worker/checkpoint and exclude samples, credentials, references and old helper sources."""
    command = controller.command(controller.ROOT / "model")
    assert "--unshare-all" in command and "--clearenv" in command
    assert "--as=12884901888" in command
    assert "/samples" not in command and "/sources" not in command
    assert not any("tts_local_review_worker.py" in item or "parent-only" in item or "approval.json" in item or "sdk_probe.py" in item for item in command)
    assert command.count("/model") == 1 and str(controller.ROOT / "model") in command
    mounts = [command[i + 1:i + 3] for i, token in enumerate(command) if token == "--ro-bind"]
    assert mounts == [["/usr", "/usr"], [str(controller.ROOT / "venv"), "/venv"], [str(controller.ROOT / "model"), "/model"], [str(controller.WORKER), "/app/worker.py"]]


def test_preparation_rejects_symlink_root(tmp_path, monkeypatch):
    """Reject redirected prepared roots before reading SDK inventories or any checkpoint payload."""
    link = tmp_path / "redirect"
    link.symlink_to(tmp_path, target_is_directory=True)
    monkeypatch.setattr(controller, "ROOT", link)
    with pytest.raises(ValueError, match="private_root"):
        controller.verify_preparation()


@pytest.mark.parametrize("kind", ["dtype", "shape", "boolshape", "offset", "booloffset", "trailing", "symlink", "traversal", "duplicate", "oversized", "truncated", "total", "coverage"])
def test_malformed_headers_rejected(tmp_path, kind):
    """Reject malformed checkpoint authority and payload bounds before loading any tensor storage."""
    kwargs = {}
    if kind == "dtype":
        kwargs["dtype"] = "F64"
    elif kind == "shape":
        kwargs["shape"] = [-2]
    elif kind == "boolshape":
        kwargs["shape"] = [True, 2]
    elif kind == "offset":
        kwargs["offsets"] = [1, 5]
    elif kind == "booloffset":
        kwargs["offsets"] = [False, 4]
    elif kind == "trailing":
        kwargs["trailing"] = b"x"
    shard = fixture_shard(tmp_path, **kwargs)
    path = tmp_path / shard
    index = tmp_path / "model.safetensors.index.json"
    if kind == "symlink":
        path.rename(tmp_path / "original")
        path.symlink_to("original")
    elif kind == "traversal":
        index.write_text(index.read_text().replace(shard, "../" + shard))
    elif kind == "duplicate":
        index.write_text('{"weight_map":{},"weight_map":{}}')
    elif kind == "oversized":
        path.write_bytes(struct.pack("<Q", 3 * 1024**2))
    elif kind == "truncated":
        path.write_bytes(struct.pack("<Q", 64) + b"{}")
    elif kind == "total":
        index.write_text(index.read_text().replace('"total_size": 4', '"total_size": 6'))
    elif kind == "coverage":
        index.write_text(index.read_text().replace("audio_tower.test.weight", "audio_tower.other.weight"))
    with pytest.raises(ValueError):
        runtime.checkpoint_manifest(tmp_path)


def test_payload_hash_truncation(tmp_path):
    """Hash all serialized bytes and fail if the declared payload becomes truncated after header validation."""
    shard = fixture_shard(tmp_path)
    row = next(iter(runtime.checkpoint_manifest(tmp_path).values()))
    assert runtime.file_tensor_hash(tmp_path / shard, row) == hashlib.sha256(b"\x01\x02\x03\x04").hexdigest()
    (tmp_path / shard).write_bytes(b"")
    with pytest.raises(ValueError, match="truncated"):
        runtime.file_tensor_hash(tmp_path / shard, row)


def test_first_output_and_host_headroom_fail_closed(tmp_path, monkeypatch):
    """Reject a repeated attempt or insufficient host guard without launching a worker or overwriting its first evidence."""
    monkeypatch.setattr(runtime, "LOAD_EXECUTION_ALLOWED", True)
    monkeypatch.setattr(controller, "OUTPUT", tmp_path)
    with pytest.raises(ValueError, match="first_output_exists"):
        controller.run()
    absent = tmp_path / "not-created"
    monkeypatch.setattr(controller, "OUTPUT", absent)
    def fixture_preparation():
        """Provide no checkpoint data while testing the prelaunch host guard."""
        logger.info("voxtral_empty_preparation_fixture_verified")
        return {}

    monkeypatch.setattr(controller, "verify_preparation", fixture_preparation)

    def reject_headroom():
        """Simulate a failed resource preflight without allocating memory or invoking the original model."""
        raise ValueError("insufficient_fixture_headroom")

    monkeypatch.setattr(controller, "require_headroom", reject_headroom)
    with pytest.raises(ValueError, match="headroom"):
        controller.run()
    assert not absent.exists()


def tiny_native_probe():
    """Exercise native mixed-dtype pread loading on fewer than ten thousand synthetic parameters inside a model-free namespace."""
    import os

    import torch
    import worker
    from safetensors.torch import save_file
    from transformers import VoxtralConfig, VoxtralForConditionalGeneration

    assert not Path("/model").exists() and not Path("/samples").exists()
    os.sched_setaffinity(0, {0, 1})
    torch.set_num_threads(2)
    torch.set_num_interop_threads(1)
    torch.manual_seed(7)
    config = VoxtralConfig(audio_config=dict(model_type="voxtral_encoder", hidden_size=8, intermediate_size=16, num_hidden_layers=1, num_attention_heads=2, num_key_value_heads=2, head_dim=4, num_mel_bins=4, max_source_positions=4), text_config=dict(model_type="llama", hidden_size=8, intermediate_size=16, num_hidden_layers=1, num_attention_heads=2, num_key_value_heads=1, head_dim=4, vocab_size=64, max_position_embeddings=32), hidden_size=8, vocab_size=64, audio_token_id=24)
    model = VoxtralForConditionalGeneration(config).to(dtype=torch.bfloat16)
    model.audio_tower.embed_positions.to(dtype=torch.float32)
    state = model.state_dict()
    assert sum(t.numel() for t in state.values()) < 10000
    directory = Path("/tmp/tiny-model")
    directory.mkdir()
    (directory / "config.json").write_text(config.to_json_string())
    names = sorted(state)
    halves = [names[:len(names) // 2], names[len(names) // 2:]]
    weight_map = {}
    for i, keys in enumerate(halves, 1):
        shard = f"model-{i:05d}-of-00002.safetensors"
        save_file({name: state[name] for name in keys}, directory / shard)
        weight_map.update({name: shard for name in keys})
    (directory / "model.safetensors.index.json").write_text(json.dumps(dict(metadata=dict(total_size=sum(t.numel() * t.element_size() for t in state.values())), weight_map=weight_map)))
    expected = {name: worker.tensor_hash(tensor, "F32" if tensor.dtype == torch.float32 else "BF16") for name, tensor in state.items()}
    events = []

    def record(event, **fields):
        """Capture exact tiny-checkpoint loader events without invoking an original-weight worker or prediction."""
        events.append(dict(event=event, **fields))

    loaded = worker.load_native(directory, record)
    assert set(loaded.state_dict()) == set(expected)
    for name, tensor in loaded.state_dict().items():
        assert worker.tensor_hash(tensor, "F32" if tensor.dtype == torch.float32 else "BF16") == expected[name]
    tensor = loaded.audio_tower.embed_positions.weight
    try:
        worker.tensor_hash(tensor, "BF16")
    except ValueError:
        pass
    else:
        raise AssertionError("accepted_FP32_as_BF16")
    print(json.dumps(dict(tiny_parameters=sum(t.numel() for t in state.values()), tensors=len(state), native_load_passed=True, mixed_dtype_preserved=True, all_buffers_CPU=all(b.device.type == "cpu" for b in loaded.buffers()), original_weights_mounted=False, audio_calls=0, events=[event["event"] for event in events])), flush=True)


def test_tiny_native_pread_load_in_sealed_sdk(tmp_path):
    """Test the real pinned SDK load path and FP32 preservation without mounting original checkpoint weights or audio."""
    command = controller.command()
    probe = tmp_path / "fixture.py"
    probe.write_text('"""Run only a tiny synthetic native SDK load, without checkpoint or audio mounts."""\nimport json\nfrom pathlib import Path\n\n' + inspect.getsource(tiny_native_probe) + '\n\ntiny_native_probe()\n')
    index = command.index("--chdir")
    command[index:index] = ["--ro-bind", str(probe), "/app/fixture.py"]
    command[-1] = "/app/fixture.py"
    result = subprocess.run(command, capture_output=True, timeout=30)
    logger.info("voxtral_tiny_fixture exit_code=%d stdout=%s stderr=%s", result.returncode, result.stdout.decode(), result.stderr.decode())
    assert result.returncode == 0, result.stderr.decode()
    value = json.loads(result.stdout.splitlines()[-1])
    assert value["native_load_passed"] and value["mixed_dtype_preserved"] and value["all_buffers_CPU"]
    assert value["tiny_parameters"] < 10000 and not value["original_weights_mounted"] and value["audio_calls"] == 0
    assert value["events"] == ["headers", "schema", "shard", "shard", "integrity"]


def test_event_auditor_requires_full_integrity(tmp_path):
    """Reject raw-success claims unless every original payload and terminal resource/scope observation agrees."""
    shard = fixture_shard(tmp_path)
    manifest = runtime.checkpoint_manifest(tmp_path)
    name, row = next(iter(manifest.items()))
    events = [dict(event="started", mode="load_integrity_only", address_space_cap_bytes=12 * 1024**3, CPU_threads=2), dict(event="headers", tensors=1, bytes=4), dict(event="schema", matched=True), dict(event="shard", name=shard, cumulative_tensors=1), dict(event="integrity", backend="pread", tensors=1, bytes=4, original_storage_shared=True, all_parameters_and_buffers_CPU=True, tensor_receipts={name: dict(sha256=runtime.file_tensor_hash(tmp_path / shard, row), shape=[2], dtype="BF16", bytes=4)}), dict(event="complete", model_loaded=True, audio_calls=0, D70_complete=False, elapsed_seconds=1.5, maximum_RSS_RAM_KiB=1024, process_virtual_peaks_KiB=dict(VmPeak=2048, VmHWM=1024))]
    assert controller.audit_events(events, tmp_path)
    invalid = [events[:-1], events + [events[-1]], [None], []]
    for key, value in [("original_storage_shared", False), ("all_parameters_and_buffers_CPU", False), ("bytes", 6)]:
        changed = copy.deepcopy(events)
        changed[-2][key] = value
        invalid.append(changed)
    for key, value in [("audio_calls", 1), ("D70_complete", True), ("elapsed_seconds", float("nan")), ("maximum_RSS_RAM_KiB", None)]:
        changed = copy.deepcopy(events)
        changed[-1][key] = value
        invalid.append(changed)
    changed = copy.deepcopy(events)
    changed[-2]["tensor_receipts"][name]["dtype"] = "F32"
    invalid.append(changed)
    for value in invalid:
        assert not controller.audit_events(value, tmp_path)


if __name__ == "__main__":
    tiny_native_probe()
