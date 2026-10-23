"""Define a closed paired eager/SDPA diagnostic using unchanged native Voxtral helpers, never qualification or common-audio review."""

import base64
import json
import logging
import math
import os
import re
import resource
import sys
from pathlib import Path

logger = logging.getLogger(__name__)
EXECUTION_ALLOWED = False
VECTOR_PREFIX = "VOXTRAL_LOGIT_VECTOR "


def require_permission():
    """Reject the new original-weight diagnostic before request, SDK, checkpoint or audio access until explicitly approved."""
    if not EXECUTION_ALLOWED:
        logger.warning("voxtral_attention_diagnostic_blocked reason=not_approved")
        raise ValueError("voxtral_attention_diagnostic_not_approved")


def validate_request(request):
    """Accept exactly four blind single-signal presence cases without labels, backend choices or decoder overrides."""
    if type(request) is not dict or set(request) != {"cases"} or type(request["cases"]) is not list or len(request["cases"]) != 4:
        raise ValueError("voxtral_attention_request")
    for number, row in enumerate(request["cases"], 1):
        identity = f"clip-{number:02d}"
        if type(row) is not dict or set(row) != {"id", "task", "signals"} or row.get("id") != identity or row.get("task") != "presence" or type(row.get("signals")) is not list or len(row["signals"]) != 1:
            raise ValueError("voxtral_attention_case")
        signal = row["signals"][0]
        if type(signal) is not dict or set(signal) != {"id", "sample_count", "sha256"} or signal.get("id") != identity + "-a" or type(signal.get("sample_count")) is not int or not 1600 <= signal["sample_count"] <= 320000 or type(signal.get("sha256")) is not str or re.fullmatch("[0-9a-f]{64}", signal["sha256"]) is None:
            raise ValueError("voxtral_attention_signal")
    logger.info("voxtral_attention_blind_request_validated cases=4")


def compare_case(model, native, row):
    """Record one first response and an explicit uncached first-logit vector per fixed backend without repairing either answer."""
    import torch
    from tts_voxtral_auditory_runtime import (
        conditioning,
        observe,
        tensor_fingerprint,
        waveform,
    )

    observations, vectors = [], []
    for backend in ["eager", "sdpa"]:
        model.set_attn_implementation(backend)
        assert all(config._attn_implementation == backend for config in [model.config, model.audio_tower.config, model.language_model.config])
        inputs, receipt = conditioning(native, "presence", [waveform(row["signals"][0], Path("/samples"))])
        with torch.inference_mode():
            vector = model(**inputs, use_cache=False, logits_to_keep=1).logits[0, -1].float().contiguous()
        if vector.shape != (131072,) or not torch.isfinite(vector).all():
            raise ValueError("voxtral_attention_logits")
        event = observe(model, native, row, Path("/samples"))
        assert event["conditioning"] == receipt
        observations.append(dict(backend=backend, observation=event, first_logit_sha256=tensor_fingerprint(vector), first_logit_argmax=int(vector.argmax()), greedy_first_token_matches_forward=bool(event["generated_token_ids"] and event["generated_token_ids"][0] == int(vector.argmax()))))
        record = dict(id=row["id"], backend=backend, dtype="float32_le", elements=131072, sha256=tensor_fingerprint(vector), data_base64=base64.b64encode(vector.detach().numpy().astype("<f4", copy=False).tobytes()).decode("ascii"))
        sys.stderr.write(VECTOR_PREFIX + json.dumps(record, separators=(",", ":")) + "\n")
        sys.stderr.flush()
        vectors.append(vector)
    delta = vectors[0] - vectors[1]
    metrics = dict(vector_elements=131072, maximum_absolute_difference=float(delta.abs().max()), RMS_difference=float(delta.square().mean().sqrt()), first_logit_argmax_equal=int(vectors[0].argmax()) == int(vectors[1].argmax()), full_logit_vectors_equal=observations[0]["first_logit_sha256"] == observations[1]["first_logit_sha256"])
    assert all(math.isfinite(metrics[key]) for key in ["maximum_absolute_difference", "RMS_difference"])
    logger.info("voxtral_attention_case_saved case_id=%s backends=2 original_answers_unchanged=True", row["id"])
    return dict(id=row["id"], observations=observations, metrics=metrics)


def main():
    """Run one separately approved paired diagnostic or a model-free conditioning replay within retained CPU/memory isolation."""
    logging.basicConfig(level=logging.INFO)
    require_permission()
    if sys.argv[1:] not in [[], ["--conditioning-only"]]:
        raise ValueError("voxtral_attention_mode")
    if resource.getrlimit(resource.RLIMIT_AS) != (12 * 1024**3, 12 * 1024**3) or os.environ.get("HF_HUB_OFFLINE") != "1" or os.environ.get("CUDA_VISIBLE_DEVICES") != "":
        raise ValueError("voxtral_attention_boundary")
    request = json.loads(sys.stdin.buffer.read(65537))
    validate_request(request)
    os.sched_setaffinity(0, {0, 1})
    import torch
    from tts_voxtral_auditory_runtime import conditioning, processor, waveform
    from tts_voxtral_load_runtime import emit, load_native, tensor_hash

    assert torch.version.cuda is None
    torch.set_num_threads(2)
    torch.set_num_interop_threads(1)
    if sys.argv[1:] == ["--conditioning-only"]:
        native = processor(Path("/assets"))
        for row in request["cases"]:
            _, receipt = conditioning(native, "presence", [waveform(row["signals"][0], Path("/samples"))])
            emit("conditioning", id=row["id"], conditioning=receipt)
        emit("conditioning_complete", cases=4, original_model_loaded=False)
        return
    model = load_native(Path("/model"), emit)
    before = {name: (tensor.data_ptr(), tensor_hash(tensor, "F32" if tensor.dtype == torch.float32 else "BF16")) for name, tensor in model.state_dict().items()}
    native = processor(Path("/model"))
    emit("ready", cases=4, backends=["eager", "sdpa"], original_weight_worker_limit=1, no_qualification=True)
    for row in request["cases"]:
        emit("pair", **compare_case(model, native, row))
    for name, tensor in model.state_dict().items():
        assert (tensor.data_ptr(), tensor_hash(tensor, "F32" if tensor.dtype == torch.float32 else "BF16")) == before[name]
    peaks = {line.split(":")[0]: int(line.split()[1]) for line in Path("/proc/self/status").read_text().splitlines() if line.startswith(("VmPeak:", "VmHWM:"))}
    emit("complete", cases=4, responses=8, original_payload_and_storage_preserved=True, maximum_RSS_RAM_KiB=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss, process_virtual_peaks_KiB=peaks, D70_complete=False, reviewer_qualified=False)


if __name__ == "__main__":
    main()
