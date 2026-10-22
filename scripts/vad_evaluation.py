"""Prepare and audit a frozen offline SileroVADv5 corpus without selecting a model, altering prior ASR evidence or exposing reference labels to inference."""

import argparse
import hashlib
import json
import logging
import math
import statistics
from pathlib import Path

import numpy as np

from scripts.asr_evaluation_corpus import save_bytes
from scripts.asr_evaluation_runner import (
    core_snapshot,
    prepare_runtime_identity,
    run_worker,
)
from scripts.vad_evaluation_worker import validate_request, validate_segments

logger = logging.getLogger(__name__)
PROJECT = Path(__file__).resolve().parents[1]
ROOT = (PROJECT / "data/backups/d69-vad-evaluation").resolve()


def digest(raw):
    """Fingerprint complete waveform/source bytes without logging signal contents or reference text."""
    return hashlib.sha256(raw).hexdigest()


def verify_artifact(raw, spec):
    """Check exact pinned original Git blob and complete size before adopting any official source/model artifact."""
    if (
        type(raw) is not bytes
        or len(raw) != spec["bytes"]
        or not 1 <= len(raw) <= 3 * 1024**2
    ):
        raise ValueError("vad_artifact_size")
    actual = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
    if actual != spec["git_blob_sha1"]:
        raise ValueError("vad_artifact_hash")
    logger.info("vad_official_artifact_verified bytes=%d", len(raw))
    return digest(raw)


def verify_provision(root=ROOT):
    """Reverify the four bounded pinned original v5 artifacts and refuse any substituted model/source or symlink."""
    config = json.loads((PROJECT / "configs/vad-evaluation-candidate.json").read_text())
    receipt = json.loads((root / "provisioned.json").read_text())
    assert config["repository"] == "snakers4/silero-vad" and config["tag"] == "v5.0"
    assert (
        config["commit"]
        == receipt["commit"]
        == "5cd2ba54db059f961e7545d4f211b44f005a6dfb"
    )
    assert len(receipt["records"]) == len(config["artifacts"]) == 4
    for spec, record in zip(config["artifacts"], receipt["records"], strict=True):
        path = root / "official" / Path(spec["path"]).name
        if path.is_symlink():
            raise ValueError("vad_artifact_symlink")
        assert all(
            record[key] == spec[key] for key in ["path", "bytes", "git_blob_sha1"]
        )
        assert verify_artifact(path.read_bytes(), spec) == record["sha256"]
    return config


def prepare(root=ROOT, asr_root=None):
    """Create exactly47 predeclared source-bound inputs and parent-only coarse labels before any VAD prediction."""
    root = Path(root)
    asr_root = Path(asr_root or PROJECT / "data/backups/d68-asr-evaluation")
    source = json.loads((asr_root / "prepared/corpus.json").read_text())
    speech = [
        row for row in source["cases"] if row["kind"] == "independent_public_speech"
    ]
    if len(speech) != 40 or any(
        sum(row["language"] == language for row in speech) != 20
        for language in ["vi_vn", "en_us"]
    ):
        raise ValueError("vad_corpus_speech_coverage")
    destination = root / "samples"
    destination.mkdir(mode=0o700, exist_ok=False)
    cases = []
    for row in speech:
        raw = Path(row["waveform_path"]).read_bytes()
        if digest(raw) != row["waveform_sha256"] or len(raw) != row["sample_count"] * 4:
            raise ValueError("vad_corpus_original_integrity")
        path = destination / (row["id"] + ".f32")
        save_bytes(path, raw)
        cases.append(
            dict(
                id=row["id"],
                filename=path.name,
                language=row["language"],
                kind="public_speech_presence",
                waveform_sha256=digest(raw),
                sample_count=row["sample_count"],
                source_sha256=row["source_sha256"],
                sentence_id=row["sentence_id"],
                timeline_origin_samples=0,
            )
        )
    for identity in ["silence", "seed7-noise"]:
        row = next(
            record for record in source["cases"] if record["id"] == identity + "-en_us"
        )
        raw = Path(row["waveform_path"]).read_bytes()
        if digest(raw) != row["waveform_sha256"]:
            raise ValueError("vad_corpus_control_integrity")
        save_bytes(destination / (identity + ".f32"), raw)
        cases.append(
            dict(
                id=identity,
                filename=identity + ".f32",
                kind="known_non_speech",
                waveform_sha256=digest(raw),
                sample_count=len(raw) // 4,
                timeline_origin_samples=0,
            )
        )
    times = np.arange(80000, dtype=np.float64) / 16000
    signals = {
        "sine50hz": (0.05 * np.sin(2 * np.pi * 50 * times)).astype("<f4"),
        "sine500hz": (0.05 * np.sin(2 * np.pi * 500 * times)).astype("<f4"),
        "two-clicks": np.zeros(80000, dtype="<f4"),
    }
    for position in [16000, 48000]:
        signals["two-clicks"][position : position + 80] = 0.5
    for identity, values in signals.items():
        raw = values.tobytes()
        save_bytes(destination / (identity + ".f32"), raw)
        cases.append(
            dict(
                id=identity,
                filename=identity + ".f32",
                kind="known_non_speech",
                waveform_sha256=digest(raw),
                sample_count=len(values),
                timeline_origin_samples=0,
            )
        )
    padding = np.zeros(80000, dtype="<f4").tobytes()
    for language in ["vi_vn", "en_us"]:
        original = next(row for row in speech if row["language"] == language)
        middle = Path(original["waveform_path"]).read_bytes()
        raw = padding + middle + padding
        identity = "padded-" + language
        save_bytes(destination / (identity + ".f32"), raw)
        cases.append(
            dict(
                id=identity,
                filename=identity + ".f32",
                kind="padded_source_composite",
                language=language,
                source_recording_id=original["id"],
                embedded_source_waveform_sha256=digest(middle),
                waveform_sha256=digest(raw),
                sample_count=len(raw) // 4,
                embedded_start_sample=80000,
                embedded_end_sample=80000 + len(middle) // 4,
                timeline_origin_samples=32000,
            )
        )
    if len(cases) != 47 or len({row["waveform_sha256"] for row in cases}) != 47:
        raise ValueError("vad_corpus_uniqueness")
    manifest = dict(
        description="D69 pre-prediction47unique inputs:40 upstream-labelled whole-recording speech-presence/5authored known negatives/2exactly padded source-clock composites. No sample-level human voice labels, ASR predictions or selected model. Two planned forward/reverse passes are repeatability checks, not94 independent inputs.",
        original_D68_corpus_sha256=digest(
            (asr_root / "prepared/corpus.json").read_bytes()
        ),
        cases=cases,
        planned_passes=["forward", "reverse"],
        observations=94,
        model_evaluated=False,
        selected_model=None,
    )
    save_bytes(root / "corpus.json", (json.dumps(manifest, indent=2) + "\n").encode())
    logger.info("vad_corpus_prepared unique_inputs=47 speech=40 negatives=5 padded=2")


def worker_request(mode, cases):
    """Exclude every label, original reference/path and authored timeline ground truth from the sealed inference request."""
    request = dict(
        mode=mode,
        cases=[
            {
                key: case[key]
                for key in ["id", "filename", "sample_count", "waveform_sha256"]
            }
            for case in cases
        ]
        if mode in {"smoke", "predict"}
        else [],
    )
    validate_request(request)
    return request


def sandbox(root=ROOT):
    """Expose only pinned CPU runtime/official source and reference-free samples with fresh namespaces and fixed finite resource caps."""
    command = [
        "/usr/bin/bwrap",
        "--unshare-all",
        "--die-with-parent",
        "--new-session",
        "--cap-drop",
        "ALL",
        "--clearenv",
        "--ro-bind",
        "/usr",
        "/usr",
        "--symlink",
        "usr/bin",
        "/bin",
        "--symlink",
        "usr/lib",
        "/lib",
        "--symlink",
        "usr/lib64",
        "/lib64",
        "--ro-bind",
        str(root / "venv"),
        "/venv",
        "--dir",
        "/app",
        "--ro-bind",
        str(PROJECT / "scripts/vad_evaluation_worker.py"),
        "/app/worker.py",
        "--ro-bind",
        str(root / "official"),
        "/official",
        "--ro-bind",
        str(root / "samples"),
        "/samples",
        "--proc",
        "/proc",
        "--dev",
        "/dev",
        "--size",
        str(128 * 1024**2),
        "--tmpfs",
        "/tmp",
        "--dir",
        "/etc",
        "--ro-bind",
        str(root / "runtime-source/passwd"),
        "/etc/passwd",
        "--ro-bind",
        str(root / "runtime-source/group"),
        "/etc/group",
        "--chdir",
        "/app",
    ]
    environment = dict(
        PATH="/venv/bin:/usr/bin",
        PYTHONPATH="/official",
        LANG="C.UTF-8",
        PYTHONDONTWRITEBYTECODE="1",
        CUDA_VISIBLE_DEVICES="",
        HF_HUB_OFFLINE="1",
        TRANSFORMERS_OFFLINE="1",
        HOME="/tmp",
        USER="asr-evaluation",
        LOGNAME="asr-evaluation",
        OMP_NUM_THREADS="2",
        MKL_NUM_THREADS="2",
        OPENBLAS_NUM_THREADS="2",
    )
    for key, value in environment.items():
        command.extend(["--setenv", key, value])
    return command + [
        "--remount-ro",
        "/",
        "--",
        "/usr/bin/prlimit",
        "--as=3221225472",
        "--cpu=180:181",
        "--nofile=128",
        "--fsize=16777216",
        "--core=0",
        "--",
        "/venv/bin/python",
        "/app/worker.py",
    ]


def overlap(start, end, lower, upper):
    """Count exact half-open integer-sample intersection without rounding to seconds or inventing acoustic boundaries."""
    return max(0, min(end, upper) - max(start, lower))


def analyze(cases, events):
    """Recompute coverage, known-negative errors, coarse padding/offset observations and reverse-order exact replay from retained outputs."""
    expected = {case["id"]: case for case in cases}
    if len(expected) != len(cases):
        raise ValueError("vad_analysis_identity")
    observations = [event for event in events if event["event"] == "observation"]
    mapped = {}
    for event in observations:
        key = (event["pass_name"], event["id"])
        if (
            key in mapped
            or event["pass_name"] not in {"forward", "reverse"}
            or event["id"] not in expected
        ):
            raise ValueError("vad_analysis_observation_identity")
        mapped[key] = event
        if event["status"] != "ok":
            continue
        case = expected[event["id"]]
        if (
            event["waveform_sha256"] != case["waveform_sha256"]
            or event["sample_count"] != case["sample_count"]
            or event["source_samples_modified"] is not False
            or event["external_recording_resets"] != 1
        ):
            raise ValueError("vad_analysis_source_reset")
        validate_segments(event["segments"], case["sample_count"])
        probabilities = event["window_probabilities"]
        if (
            len(probabilities) != (case["sample_count"] + 511) // 512
            or event["model_windows"] != len(probabilities)
            or event["padded_final_window_samples"] != (-case["sample_count"]) % 512
            or any(
                type(value) not in (float, int)
                or not math.isfinite(value)
                or not 0 <= value <= 1
                for value in probabilities
            )
        ):
            raise ValueError("vad_analysis_probabilities")
        if (
            digest(np.asarray(probabilities, dtype="<f4").tobytes())
            != event["probability_sha256"]
            or type(event["wall_seconds"]) not in (float, int)
            or not math.isfinite(event["wall_seconds"])
            or event["wall_seconds"] <= 0
        ):
            raise ValueError("vad_analysis_integrity_timing")
    replay, rows = [], []
    for case in cases:
        forward = mapped.get(("forward", case["id"]))
        reverse = mapped.get(("reverse", case["id"]))
        ok = (
            forward is not None
            and reverse is not None
            and forward["status"] == reverse["status"] == "ok"
        )
        same = bool(
            ok
            and all(
                forward[key] == reverse[key]
                for key in [
                    "segments",
                    "probability_sha256",
                    "model_windows",
                    "external_recording_resets",
                    "padded_final_window_samples",
                ]
            )
        )
        replay.append(same)
        if not ok:
            rows.append(dict(id=case["id"], status="incomplete"))
            continue
        segments = forward["segments"]
        row = dict(
            id=case["id"],
            status="ok",
            kind=case["kind"],
            detected_speech=bool(segments),
            segments=segments,
            replay_exact=same,
            waveform_sha256=case["waveform_sha256"],
            timeline_origin_samples=case["timeline_origin_samples"],
            absolute_sample_intervals=[
                dict(
                    start=case["timeline_origin_samples"] + part["start"],
                    end=case["timeline_origin_samples"] + part["end"],
                )
                for part in segments
            ],
        )
        if case["kind"] == "padded_source_composite":
            lower, upper, total = (
                case["embedded_start_sample"],
                case["embedded_end_sample"],
                case["sample_count"],
            )
            row["known_padding_false_positive_samples_beyond_62ms_tolerance"] = sum(
                overlap(part["start"], part["end"], 0, max(0, lower - 992))
                + overlap(part["start"], part["end"], min(total, upper + 992), total)
                for part in segments
            )
            row["detected_inside_embedded_source"] = any(
                overlap(part["start"], part["end"], lower, upper) for part in segments
            )
        rows.append(row)
    complete = len(mapped) == len(cases) * 2 and all(replay)
    successful = [row for row in rows if row["status"] == "ok"]
    speech = [row for row in successful if row["kind"] == "public_speech_presence"]
    negatives = [row for row in successful if row["kind"] == "known_non_speech"]
    times = [event["wall_seconds"] for event in observations if event["status"] == "ok"]
    audio_seconds = sum(
        expected[event["id"]]["sample_count"] / 16000
        for event in observations
        if event["status"] == "ok"
    )
    logger.info(
        "vad_actual_observations_analyzed complete=%s cases=%d successful_pairs=%d",
        complete,
        len(cases),
        len(successful),
    )
    return dict(
        measurement_complete=complete,
        unique_expected_inputs=len(cases),
        expected_observations=len(cases) * 2,
        observed_successful_calls=len(times),
        exact_replayed_inputs=sum(replay),
        speech_observed=len(speech),
        speech_presence_detected=sum(row["detected_speech"] for row in speech),
        known_negatives_observed=len(negatives),
        known_negative_false_positive_inputs=sum(
            row["detected_speech"] for row in negatives
        ),
        cases=rows,
        timing=dict(
            observed_audio_seconds=audio_seconds,
            full_call_seconds=sum(times),
            duration_weighted_RTF=sum(times) / audio_seconds if audio_seconds else None,
            minimum_call_seconds=min(times) if times else None,
            median_call_seconds=statistics.median(times) if times else None,
            maximum_call_seconds=max(times) if times else None,
        ),
        selected_model=None,
    )


def evaluate(mode, output, root=ROOT):
    """Freeze current inputs before one owned qualification or planned two-pass measurement and retain partial failures/CORE recovery."""
    output = Path(output)
    output.mkdir(mode=0o700, exist_ok=False)
    verify_provision(root)
    prepare_runtime_identity(root)
    corpus = json.loads((root / "corpus.json").read_text())
    cases = corpus["cases"]
    if mode == "smoke":
        raw = (
            PROJECT
            / "data/backups/d68-asr-evaluation/qualification/qualification-jfk.f32"
        ).read_bytes()
        if (
            digest(raw)
            != "d59ef6da066b7d0f894cc1b9cfb0f78d1512259640ccde0d54adfa3724709613"
        ):
            raise ValueError("vad_smoke_source")
        path = root / "samples/qualification-jfk.f32"
        if not path.exists():
            save_bytes(path, raw)
        if path.is_symlink() or path.read_bytes() != raw:
            raise ValueError("vad_smoke_waveform")
        cases = [
            dict(
                id="qualification-jfk",
                filename=path.name,
                sample_count=len(raw) // 4,
                waveform_sha256=digest(raw),
            )
        ]
    for case in cases:
        path = root / "samples" / case["filename"]
        if path.is_symlink() or digest(path.read_bytes()) != case["waveform_sha256"]:
            raise ValueError("vad_frozen_waveform")
    if any(path.suffix != ".f32" for path in (root / "samples").iterdir()):
        raise ValueError("vad_reference_mount")
    request = worker_request(mode, cases)
    paths = [
        PROJECT / "configs/vad-evaluation-candidate.json",
        PROJECT / "docs/ADR/095-offline-silero-v5-segmentation-evaluation.md",
        *sorted((PROJECT / "scripts").glob("vad_evaluation*.py")),
        *sorted((PROJECT / "tests").glob("test_vad_evaluation*.py")),
        root / "provisioned.json",
        root / "runtime-source/installed-runtime.txt",
        *sorted((root / "official").iterdir()),
    ]
    frozen = dict(
        description="D69 pre-execution official source/runtime/corpus and reference-free request freeze; qualification is separate from two-pass evaluation, no model selected.",
        mode=mode,
        request=request,
        corpus_sha256=digest((root / "corpus.json").read_bytes()),
        sha256={
            str(path.relative_to(PROJECT)): digest(path.read_bytes()) for path in paths
        },
    )
    save_bytes(output / "freeze.json", (json.dumps(frozen, indent=2) + "\n").encode())
    before = core_snapshot()
    save_bytes(
        output / "core-before.json", (json.dumps(before, indent=2) + "\n").encode()
    )
    metadata, stdout, stderr = run_worker(sandbox(root), request, timeout=180)
    save_bytes(output / "worker.stdout.jsonl", stdout)
    save_bytes(output / "worker.stderr.log", stderr)
    events = [json.loads(line) for line in stdout.splitlines()]
    after = core_snapshot()
    assert all(
        before[key] == after[key] for key in ["pid", "start_ticks", "command_sha256"]
    )
    for name, expected in frozen["sha256"].items():
        assert digest((PROJECT / name).read_bytes()) == expected
    assert digest((root / "corpus.json").read_bytes()) == frozen["corpus_sha256"]
    result = dict(
        description="Actual original SileroVADv5 offline observation; evaluation is not default selection, word timestamp certification or proof of improved ASR.",
        mode=mode,
        process=metadata,
        events=events,
        core_before=before,
        core_after=after,
        freeze_sha256=digest((output / "freeze.json").read_bytes()),
        selected_model=None,
    )
    if mode == "predict":
        result["analysis"] = analyze(corpus["cases"], events)
    save_bytes(output / "result.json", (json.dumps(result, indent=2) + "\n").encode())
    logger.info(
        "vad_evaluation_saved mode=%s process_exit_code=%d selected_models=0",
        mode,
        metadata["exit_code"],
    )


def main():
    """Prepare the owned corpus or execute a distinct bounded qualification/measurement without touching production services or model choices."""
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode",
        choices=["prepare", "imports", "load", "smoke", "predict"],
        required=True,
    )
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    if arguments.mode == "prepare":
        prepare()
    elif arguments.output is None:
        parser.error("--output is required for execution")
    else:
        evaluate(arguments.mode, arguments.output)


if __name__ == "__main__":
    main()
