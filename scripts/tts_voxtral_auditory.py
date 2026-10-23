"""Prepare blind Voxtral controls and a closed conditional auditory campaign while preserving original signals, labels and models."""

import argparse
import json
import logging
import math
from collections import Counter
from pathlib import Path

from scripts import tts_voxtral_auditory_runtime as runtime
from scripts import tts_voxtral_load as load
from scripts.asr_evaluation_corpus import save_bytes
from scripts.asr_evaluation_runner import core_snapshot, run_worker
from scripts.tts_local_review import publish_json, require_headroom
from scripts.tts_local_review_assets import digest

logger = logging.getLogger(__name__)
ROOT = load.ROOT
PROJECT = load.PROJECT
WORKER = PROJECT / "scripts/tts_voxtral_auditory_runtime.py"
CONTROL_PACKET = ROOT / "auditory-109-controls"
CONTROL_RUN = ROOT / "auditory-109-controls-first"
REVIEW_PACKET = ROOT / "auditory-109-review"
REVIEW_RUN = ROOT / "auditory-109-review-first"
SOURCES = {
    "en_us-0003": (111360, "5894637cd15d7869a99a602b903ec864fbfc612cbef700adc132a1137e9fc25b"),
    "vi_vn-0003": (115200, "6b4013b14911055329ca32ae0442d03b07c54c353f4b2d3eb0e95bca2b4fafaa"),
}


def publish_packet(directory, mode, items):
    """Publish full opaque float32 copies and separate parent-only provenance exclusively before any neural execution."""
    import numpy as np

    if directory.is_symlink() or any(path.is_symlink() for path in directory.absolute().parents):
        raise ValueError("voxtral_packet_symlink")
    directory.mkdir(mode=0o700, exist_ok=False)
    (directory / "inputs").mkdir(mode=0o700)
    cases, mapping = [], []
    for number, i in enumerate(np.random.default_rng(109).permutation(len(items)), 1):
        item = items[int(i)]
        identity, signals = f"clip-{number:02d}", []
        for position, values in enumerate(item["values"]):
            raw = np.asarray(values, dtype="<f4").tobytes()
            signal_id = identity + "-" + "ab"[position]
            signals.append(dict(id=signal_id, sample_count=len(raw) // 4, sha256=runtime.sha(raw)))
            save_bytes(directory / "inputs" / (signal_id + ".f32"), raw)
        cases.append(dict(id=identity, task=item["task"], signals=signals))
        mapping.append(dict(id=identity, **{key: value for key, value in item.items() if key != "values"}))
    request = dict(mode=mode, cases=cases)
    runtime.validate_request(request)
    for row in request["cases"]:
        for signal in row["signals"]:
            runtime.waveform(signal, directory / "inputs")
    publish_json(directory / "request.json", request)
    publish_json(directory / "parent-only.json", dict(description="Parent-only source identities, authored transformations and expected controls; never mounted in the worker. Expectations are not human naturalness/MOS labels.", order_seed=109, mapping=mapping))
    logger.info("voxtral_blind_packet_prepared mode=%s cases=%d model_predictions=0", mode, len(cases))
    return request


def prepare_controls():
    """Freeze twelve candidate-held-out factual, severe-defect and tie controls without touching previous packets or running a model."""
    import numpy as np

    load.check_budget(ROOT, reserve=16 * 1024**2)
    items = []
    for language_index, (identity, (count, expected)) in enumerate(SOURCES.items()):
        path = PROJECT / "data/backups/d68-asr-evaluation/prepared" / (identity + ".f32")
        raw = path.read_bytes()
        if len(raw) != count * 4 or runtime.sha(raw) != expected:
            raise ValueError("voxtral_control_original_source")
        values = np.frombuffer(raw, dtype="<f4")
        items += [dict(task="presence", values=[values], expected="yes", source=identity, source_sha256=expected), dict(task="language", values=[values], expected="english" if identity.startswith("en_") else "vietnamese", source=identity, source_sha256=expected)]
        gap = values.copy()
        gap[len(values) // 4:3 * len(values) // 4] = 0
        for defect_index, altered in enumerate([np.clip(values * 40, -1, 1).astype("<f4"), gap]):
            if np.array_equal(values, altered):
                raise ValueError("voxtral_control_ineffective_transform")
            first = (language_index + defect_index) % 2 == 0
            items.append(dict(task="comparison", values=[altered, values] if first else [values, altered], expected="first" if first else "second", source=identity, source_sha256=expected, transform="clip(40*x,-1,1)" if defect_index == 0 else "middle_half_exact_zeros", damaged_position=1 if first else 2))
        items.append(dict(task="comparison", values=[values, values], expected="equal", source=identity, source_sha256=expected, transform="identical_pair"))
    items += [dict(task="presence", values=[np.zeros(64000, dtype="<f4")], expected="no", source="authored_zeros"), dict(task="presence", values=[np.random.default_rng(109).normal(0, 0.05, 64000).astype("<f4")], expected="no", source="authored_noise", seed=109)]
    request = publish_packet(CONTROL_PACKET, "controls", items)
    load.check_budget(ROOT)
    return request


def worker_command(mode, replay=False):
    """Mount only pure runtime sources and opaque signals, excluding parent labels; replay has metadata but no checkpoint weights."""
    if mode not in {"controls", "review"}:
        raise ValueError("voxtral_auditory_command_mode")
    command = load.command(None if replay else ROOT / "model")
    index = command.index(str(load.WORKER))
    command[index] = str(WORKER)
    extra = ["--ro-bind", str(load.WORKER), "/app/tts_voxtral_load_runtime.py", "--ro-bind", str((CONTROL_PACKET if mode == "controls" else REVIEW_PACKET) / "inputs"), "/samples"]
    if replay:
        extra += ["--dir", "/assets"]
        for name in ["tekken.json", "preprocessor_config.json"]:
            extra += ["--ro-bind", str(ROOT / "model" / name), "/assets/" + name]
    index = command.index("--chdir")
    command[index:index] = extra
    command[command.index("--cpu=1200:1201")] = "--cpu=3600:3601" if mode == "controls" else "--cpu=7200:7201"
    if replay:
        command += ["--conditioning-only"]
    return command


def audit_events(request, events):
    """Reject incomplete first responses, wrong EOS, altered prompts, missing conditioning or invented review labels."""
    try:
        runtime.validate_request(request)
        if type(events) is not list or any(type(event) is not dict for event in events):
            return False
        names = [event.get("event") for event in events]
        if names[:6] != ["headers", "schema", "shard", "shard", "integrity", "ready"] or names[6:] != ["auditory"] * len(request["cases"]) + ["complete"]:
            return False
        ready, completed = events[5], events[-1]
        if ready.get("mode") != request["mode"] or ready.get("cases") != len(request["cases"]) or ready.get("attention") != "sdpa" or ready.get("native_payload_unchanged") is not True or ready.get("native_storage_unchanged") is not True or completed.get("mode") != request["mode"] or completed.get("cases") != len(request["cases"]) or completed.get("D70_complete") is not False:
            return False
        peaks = completed.get("process_virtual_peaks_KiB")
        if type(completed.get("maximum_RSS_RAM_KiB")) is not int or completed["maximum_RSS_RAM_KiB"] <= 0 or type(peaks) is not dict or set(peaks) != {"VmPeak", "VmHWM"} or any(type(n) is not int or n <= 0 for n in peaks.values()) or peaks["VmPeak"] > 12 * 1024**2:
            return False
        for source, observed in zip(request["cases"], events[6:-1], strict=True):
            task = source["task"]
            for key in ["id", "task", "signals"]:
                if observed.get(key) != source[key]:
                    return False
            if observed.get("prompt") != runtime.TASKS[task][0] or observed.get("maximum_new_tokens") != runtime.TASKS[task][1] or observed.get("generation_complete") is not True or observed.get("parse_error") is not None:
                return False
            tokens = observed.get("generated_token_ids")
            if type(tokens) is not list or not 1 <= len(tokens) <= runtime.TASKS[task][1] or any(type(token) is not int or token < 0 for token in tokens) or tokens[-1] != runtime.EOS_ID:
                return False
            if runtime.parse_answer(task, observed["raw_text"]) != observed.get("answer"):
                return False
            receipt = observed["conditioning"]
            source_hashes = [signal["sha256"] for signal in source["signals"]]
            if receipt.get("source_sha256") != source_hashes or receipt.get("native_source_prefix_sha256") != source_hashes or receipt.get("source_sample_counts") != [signal["sample_count"] for signal in source["signals"]] or receipt.get("sample_rate") != 16000 or receipt.get("native_padded_samples_per_signal") != 480000 or receipt.get("feature_shape") != [len(source_hashes), 128, 3000] or receipt.get("audio_tokens") != runtime.AUDIO_TOKENS_PER_CHUNK * len(source_hashes) or type(receipt.get("input_tokens")) is not int or not 1 <= receipt["input_tokens"] <= runtime.MAX_INPUT_TOKENS:
                return False
            for key in ["FP32_feature_sha256", "BF16_feature_sha256", "input_ids_sha256"]:
                if type(receipt.get(key)) is not str or len(receipt[key]) != 64 or any(c not in "0123456789abcdef" for c in receipt[key]):
                    return False
            if type(observed.get("seconds")) not in {int, float} or not math.isfinite(observed["seconds"]) or observed["seconds"] < 0:
                return False
    except (KeyError, ValueError, TypeError):
        return False
    return True


def quality_checks(request, events, mapping):
    """Require all twelve predeclared controls, balanced defect orientation and two identical-pair ties without editing first answers."""
    if request.get("mode") != "controls" or not audit_events(request, events) or type(mapping) is not list or len(mapping) != 12:
        return False
    if Counter(row.get("expected") for row in mapping if row.get("task") == "comparison") != Counter(first=2, second=2, equal=2):
        return False
    if Counter(row.get("expected") for row in mapping if row.get("task") == "presence") != Counter(yes=2, no=2) or Counter(row.get("expected") for row in mapping if row.get("task") == "language") != Counter(english=1, vietnamese=1):
        return False
    return all(row.get("id") == expected.get("id") and row.get("task") == expected.get("task") and row.get("answer") == expected.get("expected") for row, expected in zip(events[6:-1], mapping, strict=True))


def require_controls():
    """Recompute first controls and all raw packet/source/feature bindings before any conditional common-audio preparation."""
    result = json.loads((CONTROL_RUN / "result.json").read_text())
    frozen = json.loads((CONTROL_RUN / "freeze.json").read_text())
    request = json.loads((CONTROL_PACKET / "request.json").read_text())
    mapping = json.loads((CONTROL_PACKET / "parent-only.json").read_text())["mapping"]
    if frozen.get("mode") != "controls" or frozen.get("request") != request or set(frozen.get("bound_sha256", {})) != {str(path.relative_to(PROJECT)) for path in bound_paths(CONTROL_PACKET, request)}:
        raise ValueError("voxtral_first_controls_freeze_coverage")
    if result.get("observation_complete") is not True or result.get("quality_controls_passed") is not True or result.get("independent_conditioning_matched") is not True or result.get("original_load_receipts_matched") is not True or result.get("freeze_sha256") != digest(CONTROL_RUN / "freeze.json") or not quality_checks(request, result["events"], mapping):
        raise ValueError("voxtral_first_controls_gate")
    for name in ["process", "conditioning_replay_process"]:
        if result[name].get("exit_code") != 0 or result[name].get("timed_out") is not False or result[name].get("owned_process_reaped") is not True:
            raise ValueError("voxtral_first_controls_process")
    for name, expected in frozen["bound_sha256"].items():
        if digest(PROJECT / name) != expected:
            raise ValueError("voxtral_first_controls_binding_changed")
    if any(digest(CONTROL_RUN / name) != result["raw_sha256"][name] for name in ["worker.stdout.jsonl", "worker.stderr.log", "conditioning.stdout.jsonl", "conditioning.stderr.log"]):
        raise ValueError("voxtral_first_controls_raw_changed")
    for row in request["cases"]:
        for signal in row["signals"]:
            runtime.waveform(signal, CONTROL_PACKET / "inputs")
    raw_events = [json.loads(line, object_pairs_hook=runtime.unique_object) for line in (CONTROL_RUN / "worker.stdout.jsonl").read_text().splitlines()]
    replay = [json.loads(line, object_pairs_hook=runtime.unique_object) for line in (CONTROL_RUN / "conditioning.stdout.jsonl").read_text().splitlines()]
    if raw_events != result["events"] or not replay_matches(request, raw_events, replay) or not native_load_matches(raw_events):
        raise ValueError("voxtral_first_controls_raw_mismatch")
    logger.info("voxtral_first_controls_gate_verified original_common_audio_access_allowed=True")


def native_load_matches(events):
    """Bind all first tensor receipts to the independently verified original ADR-108 payloads without inventing a load event."""
    original = json.loads((PROJECT / "docs/evidence/d70-voxtral-load-first.json").read_text())
    return events[:5] == original["first_raw_events"][1:-1]


def replay_matches(request, events, replay):
    """Reconcile every independent no-weights conditioning receipt with the exact first original observations."""
    try:
        observations = [event for event in events if event.get("event") == "auditory"]
        return len(replay) == len(request["cases"]) + 1 and replay[-1] == dict(event="conditioning_complete", cases=len(request["cases"]), original_model_loaded=False) and len(observations) == len(request["cases"]) and all(row == dict(event="conditioning", id=observed["id"], conditioning=observed["conditioning"]) for row, observed in zip(replay[:-1], observations, strict=True))
    except (ValueError, TypeError, KeyError, AttributeError):
        return False


def prepare_review():
    """Copy all twenty-four original full diagnostic signals only after the independent strict first control gate."""
    require_controls()
    import numpy as np

    original = PROJECT / "data/backups/d70-common-audio-diagnostics-first"
    events = json.loads((original / "result.json").read_text())["events"]
    items = []
    for row in events:
        if row.get("event") != "transformed":
            continue
        raw = (original / "generated" / (row["id"] + ".f32")).read_bytes()
        if runtime.sha(raw) != row["asr"]["waveform_sha256"] or len(raw) != row["asr"]["sample_count"] * 4:
            raise ValueError("voxtral_common_original_signal")
        items.append(dict(task="review", values=[np.frombuffer(raw, dtype="<f4")], original_id=row["id"], original_source_sha256=runtime.sha(raw)))
    if len(items) != 24 or len({item["original_id"] for item in items}) != 24:
        raise ValueError("voxtral_common_original_coverage")
    return publish_packet(REVIEW_PACKET, "review", items)


def bound_paths(packet, request):
    """Enumerate every required source, historical payload, packet and runtime binding without trusting a mutable stored subset."""
    paths = [WORKER, Path(__file__), load.WORKER, PROJECT / "scripts/tts_voxtral_load.py", PROJECT / "docs/evidence/d70-voxtral-load-first.json", packet / "request.json", packet / "parent-only.json", ROOT / "runtime-integrity.json"]
    for row in request["cases"]:
        paths += [packet / "inputs" / (signal["id"] + ".f32") for signal in row["signals"]]
    return paths


def run_phase(mode):
    """Own one authorized phase plus a no-weights conditioning replay, retaining partial failures and refusing automatic retries."""
    runtime.require_permission()
    if mode not in {"controls", "review"}:
        raise ValueError("voxtral_auditory_phase_mode")
    if mode == "review":
        require_controls()
    packet, output = (CONTROL_PACKET, CONTROL_RUN) if mode == "controls" else (REVIEW_PACKET, REVIEW_RUN)
    if output.exists() or output.is_symlink():
        raise ValueError("voxtral_auditory_first_output_exists")
    inputs_before = load.verify_preparation()
    request = json.loads((packet / "request.json").read_text())
    runtime.validate_request(request)
    for row in request["cases"]:
        for signal in row["signals"]:
            runtime.waveform(signal, packet / "inputs")
    bound = {str(path.relative_to(PROJECT)): digest(path) for path in bound_paths(packet, request)}
    headroom = require_headroom()
    before = core_snapshot()
    output.mkdir(mode=0o700)
    publish_json(output / "freeze.json", dict(description="First closed-scope auditory phase; gold metadata remains parent-only and features will be independently replayed without model weights.", mode=mode, bound_sha256=bound, request=request, inputs=inputs_before, headroom=headroom, core_before=before))
    require_headroom()
    process, stdout, stderr = run_worker(worker_command(mode), request, timeout=1800 if mode == "controls" else 3600)
    save_bytes(output / "worker.stdout.jsonl", stdout)
    save_bytes(output / "worker.stderr.log", stderr)
    events = []
    parse_error = False
    try:
        events = [json.loads(line, object_pairs_hook=runtime.unique_object) for line in stdout.splitlines()]
    except (ValueError, TypeError):
        parse_error = True
    replay, replay_out, replay_err = run_worker(worker_command(mode, replay=True), request, timeout=300)
    save_bytes(output / "conditioning.stdout.jsonl", replay_out)
    save_bytes(output / "conditioning.stderr.log", replay_err)
    features_matched = False
    try:
        rows = [json.loads(line) for line in replay_out.splitlines()]
        features_matched = replay_matches(request, events, rows)
    except (ValueError, TypeError, KeyError):
        pass
    after = core_snapshot()
    same_core = all(before[key] == after[key] for key in ["pid", "start_ticks", "command_sha256"])
    preserved = load.verify_preparation() == inputs_before and all(digest(PROJECT / name) == expected for name, expected in bound.items())
    payload_matches = native_load_matches(events)
    complete = process["exit_code"] == 0 and process["timed_out"] is False and not parse_error and replay["exit_code"] == 0 and replay["timed_out"] is False and features_matched and payload_matches and same_core and preserved and audit_events(request, events)
    mapping = json.loads((packet / "parent-only.json").read_text())["mapping"]
    passed = complete and quality_checks(request, events, mapping) if mode == "controls" else False
    result = dict(description="First auditory observations; competence controls and qualitative AI review are not human MOS or automatic D70/model-selection acceptance.", mode=mode, process=process, conditioning_replay_process=replay, observation_complete=complete, quality_controls_passed=passed, independent_conditioning_matched=features_matched, original_load_receipts_matched=payload_matches, inputs_and_sources_preserved=preserved, core_before=before, core_after=after, events=events, freeze_sha256=digest(output / "freeze.json"), raw_sha256={name: digest(output / name) for name in ["worker.stdout.jsonl", "worker.stderr.log", "conditioning.stdout.jsonl", "conditioning.stderr.log"]}, D70_complete=False, model_selected=False)
    publish_json(output / "result.json", result)
    logger.info("voxtral_auditory_phase_saved mode=%s complete=%s controls_passed=%s", mode, complete, passed)
    return result


def campaign():
    """Run twelve controls once and prepare/run one conditional twenty-four-audio review only if every independent gate passes."""
    runtime.require_permission()
    if run_phase("controls")["quality_controls_passed"]:
        prepare_review()
        return run_phase("review")
    logger.warning("voxtral_auditory_campaign_stopped first_controls_failed=True no_review=True")
    return None


def main():
    """Allow reversible local control preparation while keeping all original neural auditory execution separately closed."""
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["prepare-controls", "campaign"])
    args = parser.parse_args()
    prepare_controls() if args.action == "prepare-controls" else campaign()


if __name__ == "__main__":
    main()
