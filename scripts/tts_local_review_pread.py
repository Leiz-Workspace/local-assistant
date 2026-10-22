"""Load original Thinker BF16 tensors through native pread and independently audit complete parameter bytes without rewriting checkpoints."""

import hashlib
import json
import logging
import math
import re
import struct
from pathlib import Path

logger = logging.getLogger(__name__)
CHUNK_BYTES = 65536


def unique_object(pairs):
    """Reject duplicate manifest/header keys instead of silently replacing tensor provenance."""
    result = {}
    for name, value in pairs:
        if name in result:
            raise ValueError("pread_duplicate_key")
        result[name] = value
    return result


def tensor_manifest(directory):
    """Cross-check bounded original index and every shard header before any tensor allocation."""
    directory = Path(directory)
    index = directory / "model.safetensors.index.json"
    if index.stat().st_size > 2 * 1024**2:
        raise ValueError("pread_index_bound")
    weight_map = json.loads(index.read_bytes(), object_pairs_hook=unique_object)["weight_map"]
    if not weight_map or any(type(name) is not str or not name.startswith(("thinker.", "talker.", "token2wav.")) for name in weight_map):
        raise ValueError("pread_foreign_component")
    if any(type(name) is not str or re.fullmatch(r"model-[0-9]{5}-of-[0-9]{5}\.safetensors", name) is None for name in weight_map.values()):
        raise ValueError("pread_shard_name")
    manifest = {}
    for filename in sorted(set(weight_map.values())):
        path = directory / filename
        if path.is_symlink():
            raise ValueError("pread_shard_symlink")
        with path.open("rb") as stream:
            prefix = stream.read(8)
            if len(prefix) != 8:
                raise ValueError("pread_header_bound")
            length = struct.unpack("<Q", prefix)[0]
            if not 2 <= length <= 2 * 1024**2:
                raise ValueError("pread_header_bound")
            header = json.loads(stream.read(length), object_pairs_hook=unique_object)
        keys = set(header) - {"__metadata__"}
        if keys != {name for name, shard in weight_map.items() if shard == filename}:
            raise ValueError("pread_index_header_coverage")
        for name in sorted(keys):
            if not name.startswith("thinker."):
                continue
            row = header[name]
            shape, offsets = row["shape"], row["data_offsets"]
            if row["dtype"] != "BF16" or type(shape) is not list or any(type(size) is not int or size <= 0 for size in shape):
                raise ValueError("pread_shape_dtype")
            if type(offsets) is not list or len(offsets) != 2 or any(type(offset) is not int or offset < 0 for offset in offsets):
                raise ValueError("pread_offsets")
            start, end = offsets
            if end - start != math.prod(shape) * 2 or end + 8 + length > path.stat().st_size:
                raise ValueError("pread_offsets")
            manifest[name] = dict(shard=filename, shape=shape, offset=8 + length + start, bytes=end - start)
    if not manifest:
        raise ValueError("pread_empty_thinker")
    logger.info("local_pread_manifest_verified tensors=%d bytes=%d", len(manifest), sum(row["bytes"] for row in manifest.values()))
    return manifest


def require_coverage(manifest, expected):
    """Require exact original names and shapes against the genuine meta model before loading any parameter."""
    if set(manifest) != set(expected) or any(tuple(row["shape"]) != tuple(expected[name]) for name, row in manifest.items()):
        raise ValueError("pread_expected_key_shape_coverage")
    logger.info("local_pread_expected_coverage_verified tensors=%d", len(expected))


def file_tensor_hash(path, row):
    """Independently hash exact serialized tensor payload using bounded ordinary reads, separate from safetensors."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        stream.seek(row["offset"])
        remaining = row["bytes"]
        while remaining:
            block = stream.read(min(CHUNK_BYTES, remaining))
            if not block:
                raise ValueError("pread_truncated_payload")
            digest.update(block)
            remaining -= len(block)
    return digest.hexdigest()


def tensor_hash(tensor):
    """Hash all original CPU BF16 bytes through a zero-copy byte view, avoiding a whole-tensor serialization copy."""
    import torch

    if tensor.device.type != "cpu" or tensor.dtype != torch.bfloat16 or not tensor.is_contiguous():
        raise ValueError("pread_tensor_storage_dtype_device")
    view = memoryview(tensor.detach().reshape(-1).view(torch.uint8).numpy()).cast("B")
    digest = hashlib.sha256()
    for offset in range(0, len(view), CHUNK_BYTES):
        digest.update(view[offset:offset + CHUNK_BYTES])
    return digest.hexdigest()


def read_original_state(directory, manifest):
    """Read only exact original Thinker tensors with native pread and verify each complete payload independently."""
    from safetensors import safe_open

    state, receipts = {}, {}
    for filename in sorted({row["shard"] for row in manifest.values()}):
        path = Path(directory) / filename
        with safe_open(path, framework="pt", device="cpu", backend="pread") as stream:
            for name, row in sorted(manifest.items()):
                if row["shard"] != filename:
                    continue
                tensor = stream.get_tensor(name)
                if list(tensor.shape) != row["shape"]:
                    raise ValueError("pread_tensor_shape")
                expected_hash = file_tensor_hash(path, row)
                if tensor_hash(tensor) != expected_hash:
                    raise ValueError("pread_original_payload_mismatch")
                state[name] = tensor
                receipts[name] = dict(sha256=expected_hash, shape=row["shape"], bytes=row["bytes"], pointer=tensor.data_ptr())
        logger.info("local_pread_shard_verified shard=%s cumulative_tensors=%d", filename, len(state))
    return state, receipts


def verify_native_state(model, state, receipts):
    """Reject missing, foreign, copied, cast or mutated native parameters after genuine Transformers assignment."""
    actual = model.state_dict()
    if {"thinker." + name for name in actual} != set(receipts) or set(state) != set(receipts):
        raise ValueError("pread_native_coverage")
    rows = {}
    for name, tensor in actual.items():
        original = "thinker." + name
        receipt = receipts[original]
        if list(tensor.shape) != receipt["shape"] or tensor.data_ptr() != receipt["pointer"] or state[original].data_ptr() != receipt["pointer"]:
            raise ValueError("pread_native_shape_storage_changed")
        if tensor_hash(tensor) != receipt["sha256"]:
            raise ValueError("pread_native_payload_changed")
        rows[original] = {key: value for key, value in receipt.items() if key != "pointer"}
    logger.info("local_pread_native_fidelity_verified tensors=%d bytes=%d", len(rows), sum(row["bytes"] for row in rows.values()))
    return dict(backend="pread", tensors=len(rows), bytes=sum(row["bytes"] for row in rows.values()), complete_original_payload_sha256=rows, original_storage_shared=True, dtype="torch.bfloat16", device="cpu")


def load_thinker(directory, config, emit):
    """Construct the genuine meta schema and native CPU BF16 model from exact unmodified original pread tensors."""
    import torch
    from transformers import Qwen2_5OmniThinkerForConditionalGeneration

    manifest = tensor_manifest(directory)
    with torch.device("meta"):
        schema = Qwen2_5OmniThinkerForConditionalGeneration(config)
    require_coverage(manifest, {"thinker." + name: tensor.shape for name, tensor in schema.state_dict().items()})
    del schema
    emit("pread_manifest", tensors=len(manifest), bytes=sum(row["bytes"] for row in manifest.values()))
    state, receipts = read_original_state(directory, manifest)
    emit("pread_payload_verified", tensors=len(receipts))
    model, loading = Qwen2_5OmniThinkerForConditionalGeneration.from_pretrained(
        None, config=config, state_dict=state, dtype=torch.bfloat16, device_map="cpu",
        attn_implementation="eager", local_files_only=True, trust_remote_code=False, output_loading_info=True,
    )
    if any(loading[key] for key in ["missing_keys", "unexpected_keys", "mismatched_keys", "error_msgs"]):
        raise ValueError("pread_native_loading_info")
    fidelity = verify_native_state(model, state, receipts)
    emit("pread_fidelity", **fidelity)
    return model, loading
