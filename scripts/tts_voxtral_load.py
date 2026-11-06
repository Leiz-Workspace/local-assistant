"""Define the closed ADR-108 one-shot load/integrity controller, preserving the prepared SDK, original services and all audio labels."""

import argparse
import json
import logging
import math
from pathlib import Path

from scripts import tts_voxtral_load_runtime as runtime
from scripts.asr_evaluation_corpus import save_bytes
from scripts.asr_evaluation_runner import core_snapshot, run_worker
from scripts.tts_local_review import publish_json, require_headroom
from scripts.tts_local_review_assets import digest, verify
from scripts.tts_voxtral_preparation import (
    MANIFEST,
    MANIFEST_SHA256,
    PROJECT,
    ROOT,
    check_budget,
    imports_command,
    inventory,
)

logger = logging.getLogger(__name__)
OUTPUT = ROOT / "load-integrity-108-first"
WORKER = PROJECT / "scripts/tts_voxtral_load_runtime.py"
WALL_SECONDS = 600


def command(model=None):
    """Expose only the pinned SDK, load worker and nominated readonly checkpoint inside an offline CPU namespace."""
    value = imports_command(ROOT)
    index = value.index("--dir", value.index("/venv") + 1)
    stop = value.index("--chdir")
    value[index:stop] = []
    value[index:index] = ["--dir", "/app", "--ro-bind", str(WORKER), "/app/worker.py", "--proc", "/proc", "--dev", "/dev", "--size", str(128 * 1024**2), "--tmpfs", "/tmp"]
    if model is not None:
        value[index:index] = ["--ro-bind", str(model), "/model"]
    environment = dict(PATH="/venv/bin:/usr/bin", LANG="C.UTF-8", PYTHONDONTWRITEBYTECODE="1", CUDA_VISIBLE_DEVICES="", HOME="/tmp", USER="asr-evaluation", LOGNAME="asr-evaluation", HF_HOME="/tmp/hf", HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", HF_HUB_DISABLE_TELEMETRY="1", OMP_NUM_THREADS="2", MKL_NUM_THREADS="2", OPENBLAS_NUM_THREADS="2", TOKENIZERS_PARALLELISM="false")
    for key, item in environment.items():
        value[index:index] = ["--setenv", key, item]
    value[-1] = "/app/worker.py"
    return value


def verify_preparation():
    """Reverify the reviewed original artifact and SDK hashes without refreshing a mismatched prepared runtime."""
    if any(path.is_symlink() for path in [ROOT, *ROOT.absolute().parents]) or ROOT.stat().st_mode & 0o077:
        raise ValueError("voxtral_load_private_root")
    if digest(MANIFEST) != MANIFEST_SHA256:
        raise ValueError("voxtral_load_manifest_changed")
    preparation_path = PROJECT / "docs/evidence/d70-voxtral-preparation-completed.json"
    preparation = json.loads(preparation_path.read_text())
    for name, expected in preparation["preparation_receipt_sha256"].items():
        if digest(PROJECT / name) != expected:
            raise ValueError("voxtral_load_preparation_receipt_changed")
    if inventory(ROOT / "venv") != json.loads((ROOT / "runtime-integrity.json").read_text())["files"]:
        raise ValueError("voxtral_load_SDK_changed")
    manifest = json.loads(MANIFEST.read_text())
    artifacts = {row["filename"]: verify(ROOT / "model" / row["filename"], row) for row in manifest["files"]}
    if set(artifacts) != {path.name for path in (ROOT / "model").iterdir()}:
        raise ValueError("voxtral_load_artifact_coverage")
    check_budget(ROOT, reserve=16 * 1024**2)
    logger.info("voxtral_load_prepared_inputs_verified artifacts=9")
    return dict(artifacts=artifacts, preparation_evidence_sha256=digest(preparation_path), SDK_integrity_sha256=digest(ROOT / "runtime-integrity.json"))


def audit_events(events, directory):
    """Independently reject incomplete, cast, copied or changed native payload observations without trusting process exit alone."""
    manifest = runtime.checkpoint_manifest(directory)
    shards = sorted({row["shard"] for row in manifest.values()})
    if type(events) is not list or any(type(row) is not dict for row in events):
        return False
    if [row.get("event") for row in events] != ["started", "headers", "schema", *["shard"] * len(shards), "integrity", "complete"]:
        return False
    if events[0].get("mode") != "load_integrity_only" or events[0].get("address_space_cap_bytes") != 12 * 1024**3 or events[0].get("CPU_threads") != 2:
        return False
    if events[1].get("tensors") != len(manifest) or events[1].get("bytes") != sum(row["bytes"] for row in manifest.values()) or events[2].get("matched") is not True:
        return False
    for event, shard in zip(events[3:3 + len(shards)], shards, strict=True):
        if event.get("name") != shard or event.get("cumulative_tensors") != sum(row["shard"] <= shard for row in manifest.values()):
            return False
    fidelity, completed = events[-2:]
    if fidelity.get("backend") != "pread" or fidelity.get("original_storage_shared") is not True or fidelity.get("all_parameters_and_buffers_CPU") is not True or fidelity.get("tensors") != len(manifest) or fidelity.get("bytes") != sum(row["bytes"] for row in manifest.values()):
        return False
    receipts = fidelity.get("tensor_receipts")
    if type(receipts) is not dict or set(receipts) != set(manifest):
        return False
    for name, row in manifest.items():
        if receipts[name] != dict(sha256=runtime.file_tensor_hash(directory / row["shard"], row), shape=row["shape"], dtype=row["dtype"], bytes=row["bytes"]):
            return False
    if completed.get("model_loaded") is not True or type(completed.get("audio_calls")) is not int or completed["audio_calls"] != 0 or completed.get("D70_complete") is not False:
        return False
    elapsed, rss, peaks = completed.get("elapsed_seconds"), completed.get("maximum_RSS_RAM_KiB"), completed.get("process_virtual_peaks_KiB")
    if type(elapsed) not in {int, float} or not math.isfinite(elapsed) or not 0 < elapsed <= WALL_SECONDS or type(rss) is not int or rss <= 0:
        return False
    if type(peaks) is not dict or set(peaks) != {"VmPeak", "VmHWM"} or any(type(n) is not int or n <= 0 for n in peaks.values()) or peaks["VmPeak"] > 12 * 1024**2:
        return False
    return True


def run():
    """Execute at most one separately approved load, retaining original failures and checking unchanged CORE identity afterward."""
    runtime.require_permission()
    if OUTPUT.exists() or OUTPUT.is_symlink():
        raise ValueError("voxtral_load_first_output_exists")
    frozen = verify_preparation()
    headroom = require_headroom()
    before = core_snapshot()
    OUTPUT.mkdir(mode=0o700)
    sources = {str(path.relative_to(PROJECT)): digest(path) for path in [WORKER, Path(__file__)]}
    publish_json(OUTPUT / "freeze.json", dict(description="One original-weight load/integrity-only attempt, no audio inputs or predictions.", inputs=frozen, source_sha256=sources, headroom=headroom, core_before=before, address_space_cap_bytes=12 * 1024**3, timeout_seconds=WALL_SECONDS))
    headroom = require_headroom()
    metadata, stdout, stderr = run_worker(command(ROOT / "model"), {}, timeout=WALL_SECONDS)
    save_bytes(OUTPUT / "worker.stdout.jsonl", stdout)
    save_bytes(OUTPUT / "worker.stderr.log", stderr)
    after = core_snapshot()
    original_core = all(before[key] == after[key] for key in ["pid", "start_ticks", "command_sha256"])
    parsed = []
    parse_failed = False
    try:
        parsed = [json.loads(line, object_pairs_hook=runtime.unique_object) for line in stdout.splitlines()]
    except (ValueError, TypeError):
        parse_failed = True
    inputs_after = verify_preparation()
    sources_unchanged = all(digest(PROJECT / name) == expected for name, expected in sources.items())
    passed = metadata["exit_code"] == 0 and not metadata["timed_out"] and not parse_failed and original_core and sources_unchanged and inputs_after == frozen and audit_events(parsed, ROOT / "model")
    result = dict(description="First original checkpoint load/integrity observation; never an auditory quality or D70 acceptance result.", status="PASS_LOAD_INTEGRITY_ONLY" if passed else "FAIL_LOAD_INTEGRITY_ONLY", process=metadata, events=parsed, raw_parse_failed=parse_failed, core_before=before, core_after=after, inputs_preserved=inputs_after == frozen, sources_preserved=sources_unchanged, last_prelaunch_headroom=headroom, audio_requests=0, naturalness_qualified=False, D70_complete=False, D71_started=False)
    publish_json(OUTPUT / "result.json", result)
    logger.info("voxtral_first_load_saved status=%s no_retry=True", result["status"])
    return result


def main():
    """Keep the original-weight one-shot entry point closed until the owner approves ADR-108 explicitly."""
    logging.basicConfig(level=logging.INFO)
    argparse.ArgumentParser(description=__doc__).parse_args()
    run()


if __name__ == "__main__":
    main()
