"""Own the approved isolated local audio-review qualification and blind first-output review while preserving D70 acceptance and original system evidence."""

import argparse
import hashlib
import json
import logging
import os
import wave
from pathlib import Path

import numpy as np

from scripts.asr_evaluation_corpus import save_bytes
from scripts.asr_evaluation_runner import (
    core_snapshot,
    prepare_runtime_identity,
    run_worker,
)
from scripts.tts_local_review_assets import PROJECT, ROOT, digest, specs, verify
from scripts.tts_local_review_worker import (
    MAX_TOKENS,
    PROMPT,
    SYSTEM,
    parse_judgement,
    validate_request,
)

logger = logging.getLogger(__name__)


def sha(raw):
    """Bind complete signal, request, source and runtime bytes to immutable local evaluation evidence."""
    return hashlib.sha256(raw).hexdigest()


def publish_json(path, value):
    """Publish private first evidence exclusively without overwriting earlier packets, failures or results."""
    save_bytes(path, (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode())


def prepare():
    """Freeze nine separately sourced opaque qualification controls and parent-only expectations before any reviewer prediction."""
    packet = ROOT / "qualification"
    packet.mkdir(mode=0o700, exist_ok=False)
    inputs = packet / "inputs"
    inputs.mkdir(mode=0o700)
    rows, expected, provenance = [], [], []
    controls = PROJECT / "data/backups/d70-public-audio-qualification-packet"
    old = json.loads((controls / "packet.json").read_text())
    for index, item in enumerate(old["cases"]):
        path = controls / "inputs" / (item["id"] + ".wav")
        raw = path.read_bytes()
        if sha(raw) != item["upload_sha256"]:
            raise ValueError("local_qualification_prior_waveform_hash")
        with wave.open(str(path)) as stream:
            if stream.getnchannels() != 1 or stream.getsampwidth() != 2:
                raise ValueError("local_qualification_prior_waveform_format")
            rate = stream.getframerate()
            values = np.frombuffer(stream.readframes(stream.getnframes()), dtype="<i2").astype(np.float32) / 32767
        if rate != 16000:
            import math

            from scipy.signal import resample_poly

            divisor = math.gcd(rate, 16000)
            values = resample_poly(values, 16000 // divisor, rate // divisor).astype(np.float32)
            if float(np.abs(values).max()) > 1:
                # Preserve the original qualification distortion while bounding only this separately declared resampled inspection copy.
                scale = float(np.abs(values).max())
                values = values / scale
            else:
                scale = 1.0
        else:
            scale = 1.0
        record_signal(inputs, rows, values)
        expected.append([
            dict(presence="speech", language="english"),
            dict(presence="speech", language="vietnamese"),
            dict(presence="silence", naturalness="not_applicable"),
            dict(presence="non_speech", naturalness="not_applicable"),
            dict(presence="speech", naturalness="unnatural", audible_defects=True),
        ][index])
        provenance.append(dict(source=str(path.relative_to(PROJECT)), source_sha256=sha(raw), source_rate=rate, PCM16_divisor=32767, resample="scipy.signal.resample_poly" if rate != 16000 else None, separate_inspection_peak_divisor=scale))
    corpus = json.loads((PROJECT / "data/backups/d68-asr-evaluation/prepared/corpus.json").read_text())
    selected = [next(row for row in corpus["cases"] if row["language"] == language and row["kind"] == "independent_public_speech" and row["sample_count"] <= 320000) for language in ["en_us", "vi_vn"]]
    for item in selected:
        raw = Path(item["waveform_path"]).read_bytes()
        if sha(raw) != item["waveform_sha256"]:
            raise ValueError("local_qualification_public_source_hash")
        record_signal(inputs, rows, np.frombuffer(raw, dtype="<f4"))
        expected.append(dict(presence="speech", language="english" if item["language"] == "en_us" else "vietnamese"))
        provenance.append(dict(source=item["waveform_path"], source_sha256=sha(raw), transform=None, original_modified=False))
    for item in selected:
        values = np.frombuffer(Path(item["waveform_path"]).read_bytes(), dtype="<f4").copy()
        start, end = len(values) // 4, 3 * len(values) // 4
        values[start:end] = 0
        record_signal(inputs, rows, values)
        expected.append(dict(presence="speech", naturalness="unnatural", audible_defects=True))
        provenance.append(dict(source=item["waveform_path"], source_sha256=item["waveform_sha256"], transform="separate copy: middle half replaced with exact zeros", zero_span=[start, end], original_modified=False))
    request = dict(mode="qualify", cases=rows)
    validate_request(request)
    publish_json(packet / "request.json", request)
    publish_json(packet / "parent-only.json", dict(description="Predeclared qualification expectations and source transformations; never mounted in reviewer namespace. No candidate names or reference text are sent to the reviewer.", expectations=expected, provenance=provenance))
    logger.info("local_audio_review_controls_frozen cases=%d", len(rows))


def require_qualification():
    """Require genuine complete frozen first controls and unchanged protocol/runtime before any common-output review is prepared or executed."""
    path = ROOT / "qualification-first"
    result = json.loads((path / "result.json").read_text())
    frozen = json.loads((path / "freeze.json").read_text())
    if not result["observation_complete"] or not result["qualification"]["passed"] or result["freeze_sha256"] != sha((path / "freeze.json").read_bytes()):
        raise ValueError("local_review_qualification_gate")
    expected = json.loads((ROOT / "qualification/parent-only.json").read_text())["expectations"]
    if not qualification_checks(frozen["request"], result["events"], expected)["passed"]:
        raise ValueError("local_review_qualification_recompute")
    if any(sha((PROJECT / name).read_bytes()) != value for name, value in frozen["source_sha256"].items()):
        raise ValueError("local_review_qualification_protocol_changed")
    if frozen["runtime_inventory_sha256"] != sha((ROOT / "runtime-integrity.json").read_bytes()):
        raise ValueError("local_review_qualification_runtime_changed")
    logger.info("local_audio_review_qualification_gate_passed")


def prepare_review():
    """Prepare all24 original full-timeline16k diagnostic copies in a fixed shuffled blind order only after successful first qualification."""
    require_qualification()
    original = PROJECT / "data/backups/d70-common-audio-diagnostics-first"
    events = json.loads((original / "result.json").read_text())["events"]
    source_rows = [row for row in events if row["event"] == "transformed"]
    if len(source_rows) != 24 or len({row["id"] for row in source_rows}) != 24:
        raise ValueError("local_review_original_coverage")
    packet = ROOT / "review"
    packet.mkdir(mode=0o700, exist_ok=False)
    inputs = packet / "inputs"
    inputs.mkdir(mode=0o700)
    rows, mapping = [], []
    for index in np.random.default_rng(7).permutation(24):
        source = source_rows[int(index)]
        raw = (original / "generated" / (source["id"] + ".f32")).read_bytes()
        if sha(raw) != source["asr"]["waveform_sha256"] or len(raw) != source["asr"]["sample_count"] * 4:
            raise ValueError("local_review_original_signal_hash")
        record_signal(inputs, rows, np.frombuffer(raw, dtype="<f4"))
        mapping.append(dict(id=rows[-1]["id"], original_id=source["id"], original_diagnostic=source["asr"]))
    request = dict(mode="review", cases=rows)
    validate_request(request)
    publish_json(packet / "request.json", request)
    publish_json(packet / "parent-only.json", dict(description="Complete original24output identity/resampling/level provenance; not mounted in the reviewer namespace. No generation retry or native modification.", seed=7, mapping=mapping))
    logger.info("local_audio_review_common_packet_frozen cases=24")


def runtime_entries():
    """Inventory every isolated SDK file and symlink without importing it or changing accepted runtimes."""
    entries = {}
    for path in sorted((ROOT / "venv").rglob("*")):
        if path.is_symlink():
            entries[str(path.relative_to(ROOT))] = dict(kind="symlink", target=os.readlink(path))
        elif path.is_file():
            entries[str(path.relative_to(ROOT))] = dict(kind="file", bytes=path.stat().st_size, sha256=digest(path))
    return entries


def snapshot_runtime():
    """Freeze installed original SDK bytes before the first import/load rather than refreshing a mismatched runtime later."""
    entries = runtime_entries()
    publish_json(ROOT / "runtime-integrity.json", dict(description="Complete separate local-reviewer SDK inventory before first execution, including files and symlink targets; no existing runtime mutated.", files=entries))
    logger.info("local_audio_review_runtime_frozen entries=%d", len(entries))


def record_signal(directory, rows, values):
    """Store one opaque complete float32 inspection copy and bind its length/hash without modifying the source signal."""
    raw = np.asarray(values, dtype="<f4").tobytes()
    identity = f"clip-{len(rows) + 1:02d}"
    save_bytes(directory / (identity + ".f32"), raw)
    rows.append(dict(id=identity, sample_count=len(values), sha256=sha(raw)))


def sandbox(mode, samples):
    """Expose only approved readonly model/SDK/worker/blind samples in a credential-free CPU namespace within the exact ADR-098 limits."""
    command = ["/usr/bin/bwrap", "--unshare-all", "--die-with-parent", "--new-session", "--cap-drop", "ALL", "--clearenv", "--ro-bind", "/usr", "/usr", "--symlink", "usr/bin", "/bin", "--symlink", "usr/lib", "/lib", "--symlink", "usr/lib64", "/lib64", "--ro-bind", str(ROOT / "venv"), "/venv", "--ro-bind", str(ROOT / "model"), "/model", "--dir", "/app", "--ro-bind", str(PROJECT / "scripts/tts_local_review_worker.py"), "/app/worker.py", "--ro-bind", str(samples), "/samples", "--proc", "/proc", "--dev", "/dev", "--size", str(128 * 1024**2), "--tmpfs", "/tmp", "--dir", "/etc"]
    for name in ["passwd", "group"]:
        command.extend(["--ro-bind", str(ROOT / "runtime-source" / name), "/etc/" + name])
    environment = dict(PATH="/venv/bin:/usr/bin", LANG="C.UTF-8", PYTHONDONTWRITEBYTECODE="1", CUDA_VISIBLE_DEVICES="", HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", HF_HOME="/tmp/hf", HOME="/tmp", USER="asr-evaluation", LOGNAME="asr-evaluation", OMP_NUM_THREADS="2", MKL_NUM_THREADS="2", OPENBLAS_NUM_THREADS="2", NUMBA_NUM_THREADS="2", NUMBA_CACHE_DIR="/tmp/numba", TOKENIZERS_PARALLELISM="false", HF_HUB_DISABLE_TELEMETRY="1")
    for key, value in environment.items():
        command.extend(["--setenv", key, value])
    cpu = 14400 if mode == "review" else 1200
    return command + ["--chdir", "/app", "--remount-ro", "/", "--", "/usr/bin/prlimit", "--as=12884901888", f"--cpu={cpu}:{cpu+1}", "--nofile=128", "--fsize=16777216", "--core=0", "--", "/venv/bin/python", "/app/worker.py"]


def audit_events(request, events):
    """Reconcile complete source-bound review coverage, raw JSON and actual EOS before treating an observation as usable."""
    observations = [event for event in events if event.get("event") == "review"]
    if [event.get("id") for event in observations] != [row["id"] for row in request["cases"]]:
        return False
    if [event["event"] for event in events].count("complete") != 1:
        return False
    if request["mode"] != "imports" and [event["event"] for event in events].count("ready") != 1:
        return False
    for source, result in zip(request["cases"], observations, strict=True):
        if any(result.get(key) != value for key, value in dict(source_sha256=source["sha256"], sample_count=source["sample_count"], sample_rate=16000, generation_complete=True).items()):
            return False
        if result.get("audio_tokens", 0) <= 0 or result.get("feature_frames", 0) <= 0:
            return False
        try:
            if parse_judgement(result["raw_text"]) != result["judgement"]:
                return False
        except (ValueError, KeyError):
            return False
    return True


def qualification_checks(request, events, expectations):
    """Apply frozen factual/severe-defect controls to first responses without substituting transcripts, proxies or favourable labels."""
    if not audit_events(request, events) or len(expectations) != 9:
        return dict(passed=False, checks=[], reason="incomplete_unusable_observations")
    rows = [event for event in events if event["event"] == "review"]
    checks = []
    for row, expected in zip(rows, expectations, strict=True):
        value = row["judgement"]
        matched = all((bool(value["artifacts"]) if key == "audible_defects" else value[key] == wanted) for key, wanted in expected.items())
        if "language" in expected:
            matched = matched and value["confidence"] in {"high", "medium"}
        checks.append(dict(id=row["id"], passed=matched))
    return dict(passed=all(row["passed"] for row in checks), checks=checks, reason="all_first_controls_required")


def run(mode, output):
    """Freeze and execute one bounded owned first run, preserving partial failures and verifying unchanged CORE identity/recovery."""
    output = Path(output)
    if mode == "review":
        require_qualification()
    output.mkdir(mode=0o700, exist_ok=False)
    if mode in {"imports", "load"}:
        samples = ROOT / "empty-inputs"
        samples.mkdir(mode=0o700, exist_ok=True)
        request = dict(mode=mode, cases=[])
    else:
        packet = ROOT / ("qualification" if mode == "qualify" else "review")
        samples = packet / "inputs"
        request = json.loads((packet / "request.json").read_text())
        if request["mode"] != mode:
            raise ValueError("local_review_mode")
    validate_request(request)
    (ROOT / "runtime-source").mkdir(mode=0o700, exist_ok=True)
    prepare_runtime_identity(ROOT)
    if runtime_entries() != json.loads((ROOT / "runtime-integrity.json").read_text())["files"]:
        raise ValueError("local_review_runtime_integrity")
    artifacts = {row["filename"]: verify(ROOT / "model" / row["filename"], row) for row in specs()}
    sources = {str(path.relative_to(PROJECT)): sha(path.read_bytes()) for path in [*sorted((PROJECT / "scripts").glob("tts_local_review*.py")), *sorted((PROJECT / "tests").glob("test_tts_local_review*.py")), PROJECT / "docs/ADR/098-proposed-isolated-audio-reviewer.md"]}
    publish_json(output / "freeze.json", dict(description="Before first local audio-conditioned inference; blind request, exact original model/worker limits, no model replacement or AC waiver.", request=request, source_sha256=sources, model_sha256=artifacts, prompt=PROMPT, system=SYSTEM, seed=7, maximum_new_tokens=MAX_TOKENS, runtime_inventory_sha256=sha((ROOT / "runtime-integrity.json").read_bytes()), wall_limit_seconds=7200 if mode == "review" else 600, address_space_bytes=12884901888))
    before = core_snapshot()
    publish_json(output / "core-before.json", before)
    metadata, stdout, stderr = run_worker(sandbox(mode, samples), request, timeout=7200 if mode == "review" else 600)
    save_bytes(output / "worker.stdout.jsonl", stdout)
    save_bytes(output / "worker.stderr.log", stderr)
    events, event_parse_error = [], False
    for line in stdout.splitlines():
        try:
            events.append(json.loads(line))
        except ValueError:
            event_parse_error = True
    after = core_snapshot()
    assert all(before[key] == after[key] for key in ["pid", "start_ticks", "command_sha256"])
    assert all(sha((PROJECT / name).read_bytes()) == value for name, value in sources.items())
    complete = metadata["exit_code"] == 0 and not metadata["timed_out"] and not event_parse_error and audit_events(request, events)
    result = dict(description="Actual isolated original-model audio evaluation; not human MOS, TTS selection or automatic D70 acceptance.", mode=mode, process=metadata, events=events, observation_complete=complete, core_before=before, core_after=after, freeze_sha256=sha((output / "freeze.json").read_bytes()), D70_complete=False, D71_started=False)
    if mode == "qualify":
        expectations = json.loads((ROOT / "qualification/parent-only.json").read_text())["expectations"]
        result["qualification"] = qualification_checks(request, events, expectations) if complete else dict(passed=False, reason="worker_failed_or_incomplete")
    publish_json(output / "result.json", result)
    logger.info("local_audio_review_retired mode=%s exit_code=%d complete=%s", mode, metadata["exit_code"], complete)


def main():
    """Prepare fixed controls or execute one explicit owner-approved evaluation mode without alternate model or decoder options."""
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", required=True, choices=["prepare", "prepare-review", "snapshot-runtime", "imports", "load", "qualify", "review"])
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.mode == "prepare":
        prepare()
    elif args.mode == "prepare-review":
        prepare_review()
    elif args.mode == "snapshot-runtime":
        snapshot_runtime()
    elif args.output is None:
        parser.error("--output is required for execution")
    else:
        run(args.mode, args.output)


if __name__ == "__main__":
    main()
