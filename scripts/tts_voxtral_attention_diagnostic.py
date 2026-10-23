"""Prepare a source-bound four-case eager/SDPA counterfactual and keep its original-weight execution separately closed."""

import argparse
import base64
import json
import logging
import math
from pathlib import Path

from scripts import tts_voxtral_attention_runtime as runtime
from scripts import tts_voxtral_auditory as auditory
from scripts import tts_voxtral_auditory_runtime as native
from scripts import tts_voxtral_load as load
from scripts.asr_evaluation_corpus import save_bytes
from scripts.asr_evaluation_runner import core_snapshot, run_worker
from scripts.tts_local_review import publish_json, require_headroom
from scripts.tts_local_review_assets import digest

logger = logging.getLogger(__name__)
PACKET = load.ROOT / "attention-110-packet"
OUTPUT = load.ROOT / "attention-110-first"
WORKER = load.PROJECT / "scripts/tts_voxtral_attention_runtime.py"
FIRST_EVIDENCE = load.PROJECT / "docs/evidence/d70-voxtral-auditory-first.json"
FIRST_EVIDENCE_SHA256 = "00fb1ff895a1bc5552020e32bdecea17d49663c940c77ba1d91c32b125898844"


def require_packet_path():
    """Reject redirected packet roots or parents before publishing opaque copies or reading a prepared diagnostic packet."""
    if PACKET.is_symlink() or any(path.is_symlink() for path in PACKET.absolute().parents):
        logger.warning("voxtral_attention_packet_path_rejected reason=symlink")
        raise ValueError("voxtral_attention_packet_symlink")


def historical_cases():
    """Read the immutable first campaign identity before deriving any diagnostic packet or parent expectations."""
    if digest(FIRST_EVIDENCE) != FIRST_EVIDENCE_SHA256:
        raise ValueError("voxtral_attention_first_evidence_changed")
    evidence = json.loads(FIRST_EVIDENCE.read_text())
    rows = [row for row in evidence["first_raw_events"] if row.get("event") == "auditory" and row.get("task") == "presence"]
    if len(rows) != 4:
        raise ValueError("voxtral_attention_prior_coverage")
    return evidence, rows


def validate_packet(request, provenance):
    """Bind all four diagnostic sources, historical features and parent expectations directly to the immutable first evidence."""
    runtime.validate_request(request)
    evidence, original = historical_cases()
    if type(provenance) is not list or len(provenance) != 4:
        raise ValueError("voxtral_attention_provenance_coverage")
    for number, (case, source, old) in enumerate(zip(request["cases"], provenance, original, strict=True), 1):
        identity = f"clip-{number:02d}"
        expected = next(row["expected"] for row in evidence["controls_first_responses"] if row["id"] == old["id"])
        if case["signals"] != [dict(old["signals"][0], id=identity + "-a")] or source != dict(id=identity, historical_id=old["id"], expected=expected, historical_raw_answer=old["raw_text"], historical_conditioning=old["conditioning"]):
            raise ValueError("voxtral_attention_packet_not_historical")
    logger.info("voxtral_attention_packet_historical_binding_verified cases=4")


def prepare():
    """Copy only the four historical presence signals with immutable provenance; do not claim fresh held-out qualification."""
    require_packet_path()
    evidence, rows = historical_cases()
    for name, expected in evidence["first_raw_and_receipt_sha256"].items():
        if digest(load.PROJECT / name) != expected:
            raise ValueError("voxtral_attention_prior_receipt_changed")
    load.check_budget(load.ROOT, reserve=4 * 1024**2)
    PACKET.mkdir(mode=0o700, exist_ok=False)
    (PACKET / "inputs").mkdir(mode=0o700)
    cases, provenance = [], []
    for number, old in enumerate(rows, 1):
        signal = old["signals"][0]
        raw = native.waveform(signal, auditory.CONTROL_PACKET / "inputs").tobytes()
        identity = f"clip-{number:02d}"
        current = dict(signal, id=identity + "-a")
        save_bytes(PACKET / "inputs" / (current["id"] + ".f32"), raw)
        cases.append(dict(id=identity, task="presence", signals=[current]))
        expected = next(row["expected"] for row in evidence["controls_first_responses"] if row["id"] == old["id"])
        provenance.append(dict(id=identity, historical_id=old["id"], expected=expected, historical_raw_answer=old["raw_text"], historical_conditioning=old["conditioning"]))
    request = dict(cases=cases)
    validate_packet(request, provenance)
    publish_json(PACKET / "request.json", request)
    publish_json(PACKET / "parent-only.json", dict(description="Historical ADR109 source/expectation/feature provenance, excluded from workers. Not fresh qualification or naturalness labels.", prior_evidence_sha256=digest(load.PROJECT / "docs/evidence/d70-voxtral-auditory-first.json"), cases=provenance))
    logger.info("voxtral_attention_packet_prepared cases=4 original_predictions=0 historical_controls=True")
    return request


def command(replay=False):
    """Mount pure native helpers and opaque signals; the independent replay receives metadata without original weights."""
    value = load.command(None if replay else load.ROOT / "model")
    value[value.index(str(load.WORKER))] = str(WORKER)
    extra = ["--ro-bind", str(load.WORKER), "/app/tts_voxtral_load_runtime.py", "--ro-bind", str(auditory.WORKER), "/app/tts_voxtral_auditory_runtime.py", "--ro-bind", str(PACKET / "inputs"), "/samples"]
    if replay:
        extra += ["--dir", "/assets"]
        for name in ["tekken.json", "preprocessor_config.json"]:
            extra += ["--ro-bind", str(load.ROOT / "model" / name), "/assets/" + name]
    index = value.index("--chdir")
    value[index:index] = extra
    return value + (["--conditioning-only"] if replay else [])


def audit(request, events, replay, provenance):
    """Require exact first raw/EOS/feature/metric coverage while granting no qualification regardless of backend answers."""
    try:
        runtime.validate_request(request)
        if [row.get("event") for row in events] != ["headers", "schema", "shard", "shard", "integrity", "ready"] + ["pair"] * 4 + ["complete"] or not auditory.native_load_matches(events):
            return False
        if events[5] != dict(event="ready", cases=4, backends=["eager", "sdpa"], original_weight_worker_limit=1, no_qualification=True):
            return False
        if len(replay) != 5 or replay[-1] != dict(event="conditioning_complete", cases=4, original_model_loaded=False) or len(provenance) != 4:
            return False
        final = events[-1]
        if final.get("cases") != 4 or final.get("responses") != 8 or final.get("D70_complete") is not False or final.get("reviewer_qualified") is not False or final.get("original_payload_and_storage_preserved") is not True or type(final.get("maximum_RSS_RAM_KiB")) is not int or final["maximum_RSS_RAM_KiB"] <= 0 or type(final["process_virtual_peaks_KiB"]["VmPeak"]) is not int or not 0 < final["process_virtual_peaks_KiB"]["VmPeak"] <= 12 * 1024**2:
            return False
        for case, pair, checked, source in zip(request["cases"], events[6:-1], replay[:-1], provenance, strict=True):
            if pair.get("id") != case["id"] or source.get("id") != case["id"] or [row.get("backend") for row in pair["observations"]] != ["eager", "sdpa"]:
                return False
            receipt = source["historical_conditioning"]
            if checked != dict(event="conditioning", id=case["id"], conditioning=receipt):
                return False
            for item in pair["observations"]:
                row, tokens = item["observation"], item["observation"]["generated_token_ids"]
                if any(row.get(key) != case[key] for key in ["id", "task", "signals"]) or row.get("event") != "auditory" or row.get("prompt") != native.TASKS["presence"][0] or row.get("maximum_new_tokens") != 16 or row.get("conditioning") != receipt or row.get("generation_complete") is not True or row.get("parse_error") is not None or type(tokens) is not list or not 1 <= len(tokens) <= 16 or any(type(token) is not int or token < 0 for token in tokens) or tokens[-1] != 2 or native.parse_answer("presence", row["raw_text"]) != row.get("answer"):
                    return False
                if type(item.get("first_logit_sha256")) is not str or len(item["first_logit_sha256"]) != 64 or any(c not in "0123456789abcdef" for c in item["first_logit_sha256"]) or type(item.get("first_logit_argmax")) is not int or not 0 <= item["first_logit_argmax"] < 131072 or type(item.get("greedy_first_token_matches_forward")) is not bool or item["greedy_first_token_matches_forward"] != (tokens[0] == item["first_logit_argmax"]):
                    return False
                if type(row.get("seconds")) not in {int, float} or not math.isfinite(row["seconds"]) or row["seconds"] < 0:
                    return False
            metrics = pair["metrics"]
            if metrics.get("vector_elements") != 131072 or any(type(metrics.get(key)) not in {int, float} or not math.isfinite(metrics[key]) or metrics[key] < 0 for key in ["maximum_absolute_difference", "RMS_difference"]):
                return False
            first, second = pair["observations"]
            if any(type(metrics.get(key)) is not bool for key in ["first_logit_argmax_equal", "full_logit_vectors_equal"]) or metrics.get("first_logit_argmax_equal") != (first["first_logit_argmax"] == second["first_logit_argmax"]) or metrics.get("full_logit_vectors_equal") != (first["first_logit_sha256"] == second["first_logit_sha256"]):
                return False
    except (KeyError, ValueError, TypeError, AttributeError):
        return False
    return True


def bindings():
    """Bind all diagnostic and reused source, immutable first evidence, request, provenance, SDK and complete opaque inputs."""
    paths = [Path(__file__), WORKER, load.WORKER, auditory.WORKER, load.PROJECT / "scripts/tts_voxtral_load.py", load.PROJECT / "scripts/tts_voxtral_auditory.py", load.PROJECT / "docs/evidence/d70-voxtral-auditory-first.json", load.PROJECT / "docs/evidence/d70-voxtral-load-first.json", load.ROOT / "runtime-integrity.json", PACKET / "request.json", PACKET / "parent-only.json", *sorted((PACKET / "inputs").glob("*.f32"))]
    return {str(path.relative_to(load.PROJECT)): digest(path) for path in paths}


def verify_logit_metrics(events, stderr):
    """Independently decode bounded raw first-logit vectors and recompute hashes, argmax, differences and RMS outside the model worker."""
    import numpy as np

    try:
        if len(stderr) > 8 * 1024**2:
            return False
        pairs = [row for row in events if row.get("event") == "pair"]
        records = [json.loads(line[len(runtime.VECTOR_PREFIX):], object_pairs_hook=native.unique_object) for line in stderr.decode().splitlines() if line.startswith(runtime.VECTOR_PREFIX)]
        expected = [(pair["id"], item) for pair in pairs for item in pair["observations"]]
        if not pairs or len(records) != len(expected):
            return False
        vectors = []
        for record, (identity, item) in zip(records, expected, strict=True):
            if set(record) != {"id", "backend", "dtype", "elements", "sha256", "data_base64"} or record["id"] != identity or record["backend"] != item["backend"] or record["dtype"] != "float32_le" or record["elements"] != 131072 or len(record["data_base64"]) != 699052:
                return False
            raw = base64.b64decode(record["data_base64"], validate=True)
            if len(raw) != 131072 * 4 or native.sha(raw) != record["sha256"] or record["sha256"] != item["first_logit_sha256"]:
                return False
            vector = np.frombuffer(raw, dtype="<f4")
            if not np.isfinite(vector).all() or int(vector.argmax()) != item["first_logit_argmax"]:
                return False
            vectors.append(vector)
        for number, pair in enumerate(pairs):
            first, second = vectors[2 * number:2 * number + 2]
            difference = first - second
            metrics = pair["metrics"]
            maximum = float(np.abs(difference).max())
            rms = float(np.sqrt(np.mean(np.square(difference))))
            if not math.isclose(metrics["maximum_absolute_difference"], maximum, rel_tol=1e-6, abs_tol=1e-7) or not math.isclose(metrics["RMS_difference"], rms, rel_tol=1e-5, abs_tol=1e-7) or metrics["first_logit_argmax_equal"] != (int(first.argmax()) == int(second.argmax())) or metrics["full_logit_vectors_equal"] != (first.tobytes() == second.tobytes()):
                return False
    except (ValueError, TypeError, KeyError, AttributeError, UnicodeError):
        return False
    logger.info("voxtral_attention_full_logits_independently_verified vectors=%d", len(vectors))
    return True


def run():
    """Execute only a separately approved one-worker diagnostic plus one independent feature replay, retaining first failure without retry."""
    runtime.require_permission()
    if OUTPUT.exists() or OUTPUT.is_symlink():
        raise ValueError("voxtral_attention_first_output_exists")
    require_packet_path()
    prepared = load.verify_preparation()
    request = json.loads((PACKET / "request.json").read_text())
    provenance = json.loads((PACKET / "parent-only.json").read_text())["cases"]
    validate_packet(request, provenance)
    for row in request["cases"]:
        native.waveform(row["signals"][0], PACKET / "inputs")
    bound, headroom, before = bindings(), require_headroom(), core_snapshot()
    OUTPUT.mkdir(mode=0o700)
    publish_json(OUTPUT / "freeze.json", dict(description="One paired historical-control diagnostic, never fresh qualification or common24 review.", bound_sha256=bound, prepared=prepared, headroom=headroom, core_before=before, request=request))
    require_headroom()
    process, stdout, stderr = run_worker(command(), request, timeout=900)
    save_bytes(OUTPUT / "worker.stdout.jsonl", stdout)
    save_bytes(OUTPUT / "worker.stderr.log", stderr)
    replay_process, replay_stdout, replay_stderr = run_worker(command(replay=True), request, timeout=120)
    save_bytes(OUTPUT / "conditioning.stdout.jsonl", replay_stdout)
    save_bytes(OUTPUT / "conditioning.stderr.log", replay_stderr)
    events, replay, parse_error = [], [], None
    try:
        events = [json.loads(line, object_pairs_hook=native.unique_object) for line in stdout.splitlines()]
        replay = [json.loads(line, object_pairs_hook=native.unique_object) for line in replay_stdout.splitlines()]
    except (ValueError, TypeError) as failure:
        parse_error = str(failure)
    after = core_snapshot()
    preserved = bindings() == bound and load.verify_preparation() == prepared
    same_core = all(before[key] == after[key] for key in ["pid", "start_ticks", "command_sha256"])
    vectors_verified = parse_error is None and verify_logit_metrics(events, stderr)
    complete = parse_error is None and preserved and same_core and vectors_verified and all(row["exit_code"] == 0 and row["timed_out"] is False and row["owned_process_reaped"] is True for row in [process, replay_process]) and audit(request, events, replay, provenance)
    result = dict(description="Paired first backend observations on previously observed controls; no reviewer/D70 acceptance or automatic backend selection.", process=process, conditioning_replay_process=replay_process, parse_error=parse_error, observation_complete=complete, full_logits_independently_recomputed=vectors_verified, events=events, preserved=preserved, core_before=before, core_after=after, freeze_sha256=digest(OUTPUT / "freeze.json"), raw_sha256={path.name: digest(path) for path in OUTPUT.iterdir() if path.name.endswith((".jsonl", ".log"))}, D70_complete=False, reviewer_qualified=False, backend_selected=False)
    publish_json(OUTPUT / "result.json", result)
    logger.info("voxtral_attention_diagnostic_saved complete=%s reviewer_qualified=False", complete)
    return result


def main():
    """Allow local packet preparation while keeping the separately bounded original-weight diagnostic closed."""
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["prepare", "run"])
    args = parser.parse_args()
    prepare() if args.action == "prepare" else run()


if __name__ == "__main__":
    main()
