"""Test original-tensor pread provenance, fail-closed coverage and genuine tiny native assignment without downloading models."""

import copy
import json
import logging
import os
import struct
import subprocess
import tempfile
from pathlib import Path

from scripts import tts_local_review_pread as loader


def tiny_manifest(directory, change=None):
    """Author a tiny BF16 safetensors-shaped payload for metadata guards without importing a neural SDK."""
    header = {"thinker.weight": dict(dtype="BF16", shape=[2], data_offsets=[0, 4])}
    weight_map = {"thinker.weight": "model-00001-of-00001.safetensors"}
    if change == "dtype":
        header["thinker.weight"]["dtype"] = "F32"
    elif change == "shape":
        header["thinker.weight"]["shape"] = [True]
    elif change == "offset":
        header["thinker.weight"]["data_offsets"] = [0, 5]
    elif change == "missing":
        weight_map["thinker.other"] = "model-00001-of-00001.safetensors"
    elif change == "foreign":
        weight_map["foreign.weight"] = "model-00001-of-00001.safetensors"
    elif change == "traversal":
        weight_map["thinker.weight"] = "../model-00001-of-00001.safetensors"
    raw = json.dumps(header).encode()
    (directory / "model-00001-of-00001.safetensors").write_bytes(struct.pack("<Q", len(raw)) + raw + b"\x00\x00\x80\x3f")
    (directory / "model.safetensors.index.json").write_text(json.dumps(dict(weight_map=weight_map)))


def test_header_provenance_and_complete_payload(tmp_path):
    """Bind complete tiny original bytes and reject expected-name/shape mismatches before native allocation."""
    import hashlib

    import pytest

    tiny_manifest(tmp_path)
    manifest = loader.tensor_manifest(tmp_path)
    loader.require_coverage(manifest, {"thinker.weight": [2]})
    row = manifest["thinker.weight"]
    assert loader.file_tensor_hash(tmp_path / row["shard"], row) == hashlib.sha256(b"\x00\x00\x80\x3f").hexdigest()
    for expected in [{}, {"thinker.other": [2]}, {"thinker.weight": [3]}]:
        with pytest.raises(ValueError, match="expected_key_shape_coverage"):
            loader.require_coverage(manifest, expected)


def test_corrupt_or_foreign_headers_rejected(tmp_path):
    """Reject foreign components, incomplete indexes, traversal, invalid dtype/shape/offsets and symlink shards."""
    import pytest

    for change in ["dtype", "shape", "offset", "missing", "foreign", "traversal"]:
        tiny_manifest(tmp_path, change)
        with pytest.raises(ValueError):
            loader.tensor_manifest(tmp_path)
    tiny_manifest(tmp_path)
    shard = tmp_path / "model-00001-of-00001.safetensors"
    original = shard.read_bytes()
    shard.write_bytes(struct.pack("<Q", 2**25))
    with pytest.raises(ValueError, match="header_bound"):
        loader.tensor_manifest(tmp_path)
    target = tmp_path / "actual"
    target.write_bytes(original)
    shard.unlink()
    shard.symlink_to(target)
    with pytest.raises(ValueError, match="shard_symlink"):
        loader.tensor_manifest(tmp_path)
    with pytest.raises(ValueError, match="duplicate_key"):
        loader.unique_object([("same", 1), ("same", 2)])


def test_genuine_sdk_fixture_under_sealed_12g_bound(tmp_path):
    """Execute authored tiny native tensors in the existing offline isolated SDK, retaining failure logs without installing dependencies."""
    from scripts import tts_local_review as review
    from scripts.tts_local_review_assets import PROJECT

    command = review.sandbox("imports", tmp_path)
    position = command.index("--chdir")
    command[position:position] = ["--ro-bind", str(PROJECT / "tests/test_tts_local_review_pread.py"), "/app/fixture.py"]
    command[-1] = "/app/fixture.py"
    started = subprocess.run(command, capture_output=True, timeout=90, check=False)
    logging.getLogger(__name__).info("local_pread_tiny_sdk_fixture exit_code=%d stdout=%s stderr=%s", started.returncode, started.stdout.decode(), started.stderr.decode())
    assert started.returncode == 0, started.stderr.decode()
    assert json.loads(started.stdout.splitlines()[-1])["native_pread_fixture_passed"]


def expect_failure(action, marker):
    """Require a real guard failure in the isolated tiny fixture without treating rejection as an inference observation."""
    try:
        action()
    except ValueError as error:
        assert marker in str(error), (marker, str(error))
    else:
        raise AssertionError("pread_fixture_missing_rejection:" + marker)


def run_sdk_fixture():
    """Exercise genuine native pread, complete byte/storage fidelity and mutation/copy/dtype/coverage failure controls on tiny authored weights."""
    import torch
    from safetensors.torch import save_file
    from transformers import (
        Qwen2_5OmniThinkerConfig,
        Qwen2_5OmniThinkerForConditionalGeneration,
    )

    logging.basicConfig(level=logging.INFO)
    os.sched_setaffinity(0, {0, 1})
    torch.set_num_threads(2)
    torch.set_num_interop_threads(1)
    torch.manual_seed(7)
    config = Qwen2_5OmniThinkerConfig(
        audio_config=dict(d_model=8, encoder_layers=1, encoder_attention_heads=2, encoder_ffn_dim=16, num_mel_bins=4, max_source_positions=16, output_dim=8),
        vision_config=dict(depth=1, hidden_size=8, intermediate_size=16, num_heads=2, patch_size=2, spatial_merge_size=1, out_hidden_size=8),
        text_config=dict(vocab_size=32, hidden_size=8, intermediate_size=16, num_hidden_layers=1, num_attention_heads=2, num_key_value_heads=1, head_dim=4),
    )
    native = Qwen2_5OmniThinkerForConditionalGeneration(config).to(dtype=torch.bfloat16)
    tensors = {"thinker." + name: tensor.clone().contiguous() for name, tensor in native.state_dict().items()}
    tensors["talker.fixture.weight"] = torch.ones(2, dtype=torch.bfloat16)
    events = []
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        filename = "model-00001-of-00001.safetensors"
        save_file(tensors, root / filename)
        (root / "model.safetensors.index.json").write_text(json.dumps(dict(weight_map={name: filename for name in tensors})))
        loaded, info = loader.load_thinker(root, config, lambda event, **fields: events.append(dict(event=event, **fields)))
        assert not any(info.values())
        receipt = events[-1]
        assert receipt["tensors"] == len(tensors) - 1 and receipt["original_storage_shared"]
        assert all(torch.equal(native.state_dict()[name], value) for name, value in loaded.state_dict().items())
        manifest = loader.tensor_manifest(root)
        state, receipts = loader.read_original_state(root, manifest)
        own_receipts = copy.deepcopy(receipts)
        for name, tensor in loaded.state_dict().items():
            own_receipts["thinker." + name]["pointer"] = tensor.data_ptr()
        loaded_state = {"thinker." + name: tensor for name, tensor in loaded.state_dict().items()}
        loader.verify_native_state(loaded, loaded_state, own_receipts)
        first = next(iter(loaded_state))
        copied = dict(loaded_state)
        copied[first] = copied[first].clone()
        expect_failure(lambda: loader.verify_native_state(loaded, copied, own_receipts), "shape_storage_changed")
        expect_failure(lambda: loader.verify_native_state(loaded, {}, own_receipts), "native_coverage")
        expect_failure(lambda: loader.tensor_hash(state[first].float()), "storage_dtype_device")
        with torch.no_grad():
            loaded_state[first].reshape(-1)[0].add_(1)
        expect_failure(lambda: loader.verify_native_state(loaded, loaded_state, own_receipts), "native_payload_changed")
        wrong = copy.deepcopy(manifest)
        wrong[first]["shape"] = [1]
        expect_failure(lambda: loader.read_original_state(root, wrong), "tensor_shape")
        payload = root / filename
        with payload.open("r+b") as stream:
            stream.truncate(payload.stat().st_size - 1)
        expect_failure(lambda: loader.tensor_manifest(root), "offsets")
    print(json.dumps(dict(native_pread_fixture_passed=True, tiny_tensors=len(tensors) - 1, no_original_weights_loaded=True, cap_bytes=12 * 1024**3)), flush=True)


if __name__ == "__main__":
    run_sdk_fixture()
