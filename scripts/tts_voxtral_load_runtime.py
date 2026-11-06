"""Implement a closed, load-only Voxtral integrity worker with bounded headers and exact CPU BF16/FP32 payload auditing."""

import hashlib
import json
import logging
import math
import os
import re
import resource
import struct
import sys
import time
from pathlib import Path

logger = logging.getLogger(__name__)
LOAD_EXECUTION_ALLOWED = False
DTYPE_BYTES = {"BF16": 2, "F32": 4}
CHUNK_BYTES = 65536


def require_permission():
    """Reject original checkpoint loading before SDK import or filesystem access until its separate scope is approved."""
    if not LOAD_EXECUTION_ALLOWED:
        logger.warning("voxtral_original_load_blocked reason=not_approved")
        raise ValueError("voxtral_original_load_not_approved")


def unique_object(pairs):
    """Reject duplicate JSON identities in a checkpoint index, configuration or shard header."""
    value = {}
    for name, item in pairs:
        if name in value:
            raise ValueError("voxtral_duplicate_key")
        value[name] = item
    return value


def bounded_json(path, limit=2 * 1024**2):
    """Read only a bounded regular JSON file without accepting symlinks or oversized metadata."""
    if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= limit:
        raise ValueError("voxtral_json_bound")
    return json.loads(path.read_bytes(), object_pairs_hook=unique_object)


def checkpoint_manifest(directory):
    """Validate index/header coverage, shapes, mixed dtypes and contiguous payload offsets without allocating tensor storage."""
    index = bounded_json(directory / "model.safetensors.index.json")
    weight_map = index["weight_map"]
    if type(weight_map) is not dict or not weight_map or any(type(name) is not str or not name.startswith(("audio_tower.", "language_model.", "multi_modal_projector.")) for name in weight_map):
        raise ValueError("voxtral_index_names")
    if any(type(shard) is not str or re.fullmatch(r"model-[0-9]{5}-of-[0-9]{5}\.safetensors", shard) is None for shard in weight_map.values()):
        raise ValueError("voxtral_index_shards")
    manifest = {}
    for shard in sorted(set(weight_map.values())):
        path = directory / shard
        if path.is_symlink() or not path.is_file():
            raise ValueError("voxtral_shard_type")
        with path.open("rb") as stream:
            prefix = stream.read(8)
            if len(prefix) != 8:
                raise ValueError("voxtral_header_bound")
            length = struct.unpack("<Q", prefix)[0]
            if not 2 <= length <= 2 * 1024**2:
                raise ValueError("voxtral_header_bound")
            raw = stream.read(length)
            if len(raw) != length:
                raise ValueError("voxtral_header_truncated")
            header = json.loads(raw, object_pairs_hook=unique_object)
        keys = set(header) - {"__metadata__"}
        if keys != {name for name, filename in weight_map.items() if filename == shard}:
            raise ValueError("voxtral_header_coverage")
        spans = []
        for name in sorted(keys):
            row = header[name]
            shape, offsets, dtype = row["shape"], row["data_offsets"], row["dtype"]
            if dtype not in DTYPE_BYTES or type(shape) is not list or not shape or any(type(n) is not int or n <= 0 for n in shape):
                raise ValueError("voxtral_tensor_shape_dtype")
            if type(offsets) is not list or len(offsets) != 2 or any(type(n) is not int or n < 0 for n in offsets):
                raise ValueError("voxtral_tensor_offsets")
            start, end = offsets
            if end - start != math.prod(shape) * DTYPE_BYTES[dtype] or end + 8 + length > path.stat().st_size:
                raise ValueError("voxtral_tensor_offsets")
            spans.append((start, end))
            manifest[name] = dict(shard=shard, shape=shape, dtype=dtype, offset=8 + length + start, bytes=end - start)
        spans.sort()
        if not spans or spans[0][0] != 0 or any(a[1] != b[0] for a, b in zip(spans, spans[1:])) or spans[-1][1] + 8 + length != path.stat().st_size:
            raise ValueError("voxtral_payload_coverage")
    if sum(row["bytes"] for row in manifest.values()) != index["metadata"]["total_size"]:
        raise ValueError("voxtral_index_total")
    logger.info("voxtral_load_headers_verified tensors=%d", len(manifest))
    return manifest


def file_tensor_hash(path, row):
    """Hash the complete declared serialized payload with bounded reads independently from safetensors."""
    value = hashlib.sha256()
    with path.open("rb") as stream:
        stream.seek(row["offset"])
        remaining = row["bytes"]
        while remaining:
            raw = stream.read(min(remaining, CHUNK_BYTES))
            if not raw:
                raise ValueError("voxtral_tensor_truncated")
            value.update(raw)
            remaining -= len(raw)
    return value.hexdigest()


def tensor_hash(tensor, dtype):
    """Hash a contiguous CPU tensor without copying or casting its original BF16 or FP32 payload."""
    import torch

    expected = {"BF16": torch.bfloat16, "F32": torch.float32}[dtype]
    if tensor.device.type != "cpu" or tensor.dtype != expected or not tensor.is_contiguous():
        raise ValueError("voxtral_tensor_storage")
    view = memoryview(tensor.detach().reshape(-1).view(torch.uint8).numpy()).cast("B")
    value = hashlib.sha256()
    for start in range(0, len(view), CHUNK_BYTES):
        value.update(view[start:start + CHUNK_BYTES])
    return value.hexdigest()


def load_native(directory, emit):
    """Load an already authorized native checkpoint through pread and verify exact storage after genuine Transformers assignment."""
    import torch
    from safetensors import safe_open
    from transformers import VoxtralConfig, VoxtralForConditionalGeneration

    manifest = checkpoint_manifest(directory)
    emit("headers", tensors=len(manifest), bytes=sum(row["bytes"] for row in manifest.values()))
    config = VoxtralConfig.from_dict(bounded_json(directory / "config.json"))
    config._attn_implementation = "eager"
    with torch.device("meta"):
        schema = VoxtralForConditionalGeneration(config)
    schema.to(dtype=torch.bfloat16)
    if schema._keep_in_fp32_modules_strict != ["embed_positions"]:
        raise ValueError("voxtral_native_FP32_rule")
    schema.audio_tower.embed_positions.to(dtype=torch.float32)
    expected = schema.state_dict()
    if set(expected) != set(manifest) or any(list(expected[name].shape) != row["shape"] or str(expected[name].dtype) != {"BF16": "torch.bfloat16", "F32": "torch.float32"}[row["dtype"]] for name, row in manifest.items()):
        raise ValueError("voxtral_native_schema")
    del expected, schema
    emit("schema", matched=True)
    state, receipts = {}, {}
    for shard in sorted({row["shard"] for row in manifest.values()}):
        with safe_open(directory / shard, framework="pt", device="cpu", backend="pread") as stream:
            for name, row in manifest.items():
                if row["shard"] != shard:
                    continue
                tensor = stream.get_tensor(name)
                expected_hash = file_tensor_hash(directory / shard, row)
                if list(tensor.shape) != row["shape"] or tensor_hash(tensor, row["dtype"]) != expected_hash:
                    raise ValueError("voxtral_original_tensor_mismatch")
                state[name] = tensor
                receipts[name] = dict(sha256=expected_hash, shape=row["shape"], dtype=row["dtype"], bytes=row["bytes"], pointer=tensor.data_ptr())
        emit("shard", name=shard, cumulative_tensors=len(state))
    model, loading = VoxtralForConditionalGeneration.from_pretrained(
        None, config=config, state_dict=state, dtype=torch.bfloat16,
        attn_implementation="eager", local_files_only=True, trust_remote_code=False, output_loading_info=True,
    )
    if any(loading[key] for key in ["missing_keys", "unexpected_keys", "mismatched_keys", "error_msgs"]):
        raise ValueError("voxtral_native_loading_info")
    actual = model.state_dict()
    if set(actual) != set(receipts) or any(tensor.device.type != "cpu" for tensor in list(model.parameters()) + list(model.buffers())):
        raise ValueError("voxtral_native_storage_coverage")
    for name, tensor in actual.items():
        row = receipts[name]
        if list(tensor.shape) != row["shape"] or tensor.data_ptr() != row["pointer"] or tensor_hash(tensor, row["dtype"]) != row["sha256"]:
            raise ValueError("voxtral_native_payload_changed")
    model.eval()
    public = {name: {key: value for key, value in row.items() if key != "pointer"} for name, row in receipts.items()}
    emit("integrity", backend="pread", tensors=len(public), bytes=sum(row["bytes"] for row in public.values()), original_storage_shared=True, tensor_receipts=public, all_parameters_and_buffers_CPU=True)
    logger.info("voxtral_native_load_integrity_verified tensors=%d audio_calls=0", len(public))
    return model


def emit(event, **fields):
    """Emit complete machine-auditable first load observations without audio scores or naturalness labels."""
    print(json.dumps(dict(event=event, **fields), sort_keys=True), flush=True)


def main():
    """Run only the separately approved original load under the retained CPU and address-space bounds; never predict."""
    logging.basicConfig(level=logging.INFO)
    require_permission()
    if len(sys.argv) != 1 or os.environ.get("HF_HUB_OFFLINE") != "1" or os.environ.get("CUDA_VISIBLE_DEVICES") != "":
        raise ValueError("voxtral_worker_scope")
    if resource.getrlimit(resource.RLIMIT_AS) != (12 * 1024**3, 12 * 1024**3):
        raise ValueError("voxtral_worker_address_space")
    os.sched_setaffinity(0, {0, 1})
    import torch

    if torch.version.cuda is not None:
        raise ValueError("voxtral_worker_CPU_only")
    torch.set_num_threads(2)
    torch.set_num_interop_threads(1)
    started = time.monotonic()
    emit("started", mode="load_integrity_only", address_space_cap_bytes=12 * 1024**3, CPU_threads=2)
    model = load_native(Path("/model"), emit)
    assert model is not None
    peaks = {line.split(":")[0]: int(line.split()[1]) for line in Path("/proc/self/status").read_text().splitlines() if line.startswith(("VmPeak:", "VmHWM:"))}
    emit("complete", model_loaded=True, audio_calls=0, elapsed_seconds=time.monotonic() - started, maximum_RSS_RAM_KiB=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss, process_virtual_peaks_KiB=peaks, D70_complete=False)


if __name__ == "__main__":
    main()
