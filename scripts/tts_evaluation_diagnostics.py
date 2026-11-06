"""Own separate TTS listening-copy preparation and a single reference-blind ASR roundtrip, retaining authored-text proxy limits and native provenance."""

import argparse
import json
import logging
from pathlib import Path

import numpy as np

from scripts.asr_evaluation_corpus import save_bytes
from scripts.asr_evaluation_metrics import edit_distance, normalize
from scripts.asr_evaluation_runner import (
    core_snapshot,
    prepare_runtime_identity,
    run_worker,
    sandbox_command,
)
from scripts.asr_evaluation_worker import validate_request as validate_asr_request
from scripts.tts_audio_diagnostics import validate_request
from scripts.tts_evaluation import PROJECT, ROOT, read_output, sha, verify_outputs
from scripts.tts_evaluation_assets import PINS

logger = logging.getLogger(__name__)


def diagnostic_identity(candidate, case_id):
    """Encode the pinned decimal model identifier into the already bounded leaf-name alphabet without changing its recorded family identity."""
    if candidate not in PINS:
        raise ValueError("tts_diagnostic_candidate")
    identity = candidate.replace(".", "_") + "-" + case_id
    logger.debug("tts_diagnostic_leaf_identity_created candidate=%s", candidate)
    return identity


def diagnostic_namespace(samples, output, root=ROOT):
    """Expose no model at all while creating separately hashed ASR/listening copies inside a finite CPU-only offline namespace."""
    output = Path(output)
    if (
        output.is_symlink()
        or not output.is_dir()
        or output.stat().st_mode & 0o077
        or any(output.iterdir())
    ):
        raise ValueError("tts_diagnostics_empty_output")
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
        str(Path(root) / "venv"),
        "/venv",
        "--ro-bind",
        str(samples),
        "/samples",
        "--bind",
        str(output),
        "/output",
        "--dir",
        "/app",
        "--dir",
        "/app/scripts",
    ]
    for name in ["tts_audio_diagnostics.py", "tts_waveform.py"]:
        command.extend(
            ["--ro-bind", str(PROJECT / "scripts" / name), "/app/scripts/" + name]
        )
    command.extend(
        [
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
        ]
    )
    for name in ["passwd", "group"]:
        command.extend(
            ["--ro-bind", str(Path(root) / "runtime-source" / name), "/etc/" + name]
        )
    for key, value in dict(
        PATH="/venv/bin:/usr/bin",
        PYTHONPATH="/app",
        LANG="C.UTF-8",
        PYTHONDONTWRITEBYTECODE="1",
        HOME="/tmp",
        CUDA_VISIBLE_DEVICES="",
        OMP_NUM_THREADS="2",
        OPENBLAS_NUM_THREADS="2",
        MKL_NUM_THREADS="2",
    ).items():
        command.extend(["--setenv", key, value])
    return command + [
        "--chdir",
        "/app",
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
        "-m",
        "scripts.tts_audio_diagnostics",
    ]


def prepare_diagnostics(runs, output, root=ROOT):
    """Reverify actual original runs, copy exact successful native samples and transform them once without making any auditory/naturalness judgement."""
    output = Path(output)
    output.mkdir(mode=0o700, exist_ok=False)
    samples, generated = output / "native-inputs", output / "generated"
    samples.mkdir(mode=0o700)
    generated.mkdir(mode=0o700)
    inputs, references = [], []
    for directory in (Path(run).resolve() for run in runs):
        result = json.loads((directory / "result.json").read_text())
        frozen = json.loads((directory / "freeze.json").read_text())
        if sha((directory / "freeze.json").read_bytes()) != result[
            "freeze_sha256"
        ] or result["events"] != [
            json.loads(line)
            for line in (directory / "worker.stdout.jsonl").read_bytes().splitlines()
        ]:
            raise ValueError("tts_diagnostic_original_evidence")
        verify_outputs(directory / "generated", frozen["request"], result["events"])
        requests = {case["id"]: case for case in frozen["request"]["cases"]}
        for row in result["events"]:
            if row.get("event") != "observation" or row["status"] != "ok":
                continue
            identity = diagnostic_identity(result["candidate"], row["id"])
            metadata = row["audio"]
            raw = read_output(directory / "generated", metadata["raw_filename"])
            save_bytes(samples / (identity + ".f32"), raw)
            inputs.append(
                dict(
                    id=identity,
                    filename=identity + ".f32",
                    sample_count=metadata["sample_count"],
                    sample_rate=metadata["sample_rate"],
                    waveform_sha256=metadata["waveform_sha256"],
                )
            )
            references.append(
                dict(
                    id=identity,
                    candidate=result["candidate"],
                    original_id=row["id"],
                    original_run=str(directory.relative_to(PROJECT)),
                    language=row["language"],
                    variant=row["variant"],
                    authored_text=requests[row["id"]]["text"],
                    original_mode=result["mode"],
                    native_waveform_sha256=metadata["waveform_sha256"],
                )
            )
    request = dict(cases=inputs)
    validate_request(request)
    frozen = dict(
        description="Separate full-timeline listening copies and rational16k ASR inputs; native samples untouched, parent-only authored texts never mounted into any ASR namespace. No naturalness judgement.",
        request=request,
        references=references,
        source_sha256={
            str(path.relative_to(PROJECT)): sha(path.read_bytes())
            for path in sorted((PROJECT / "scripts").glob("tts_*.py"))
        },
    )
    save_bytes(
        output / "freeze.json",
        (json.dumps(frozen, ensure_ascii=False, indent=2) + "\n").encode(),
    )
    process, stdout, stderr = run_worker(
        diagnostic_namespace(samples, generated, root), request, timeout=180
    )
    save_bytes(output / "worker.stdout.jsonl", stdout)
    save_bytes(output / "worker.stderr.log", stderr)
    events = [json.loads(line) for line in stdout.splitlines()]
    transformed = [row for row in events if row["event"] == "transformed"]
    expected = {case["id"]: case for case in inputs}
    seen, names = set(), set()
    for row in transformed:
        identity = row["id"]
        if identity not in expected or identity in seen:
            raise ValueError("tts_diagnostic_return_identity")
        seen.add(identity)
        native = expected[identity]
        audio = row["asr"]
        raw = read_output(generated, identity + ".f32")
        values = np.frombuffer(raw, dtype="<f4")
        preview = row["preview"]
        encoded = read_output(generated, identity + ".ogg")
        if (
            audio["source_waveform_sha256"] != native["waveform_sha256"]
            or audio["sample_rate"] != 16000
            or len(values) != audio["sample_count"]
            or len(values)
            != (native["sample_count"] * 16000 + native["sample_rate"] - 1)
            // native["sample_rate"]
            or sha(raw) != audio["waveform_sha256"]
            or not np.isfinite(values).all()
            or np.max(np.abs(values)) > 1
            or audio["native_original_modified"] is not False
            or sha(encoded) != preview["sha256"]
            or len(encoded) != preview["bytes"]
            or not encoded.startswith(b"OggS")
            or preview["native_original_modified"] is not False
            or preview["actual_listening_completed"] is not False
            or row["naturalness_score"] is not None
        ):
            raise ValueError("tts_diagnostic_transformation_integrity")
        names.update([identity + ".f32", identity + ".ogg"])
    if names != {path.name for path in generated.iterdir()}:
        raise ValueError("tts_diagnostic_unaccounted_files")
    result = dict(
        description="Actual separate transformed outputs, not an audio listening/MOS evaluation.",
        process=process,
        events=events,
        expected=len(inputs),
        transformed=len(transformed),
        complete=len(seen) == len(inputs) and process["exit_code"] == 0,
        freeze_sha256=sha((output / "freeze.json").read_bytes()),
        actual_audio_inspection_complete=False,
    )
    save_bytes(output / "result.json", (json.dumps(result, indent=2) + "\n").encode())
    logger.info(
        "tts_separate_diagnostics_retained expected=%d transformed=%d",
        len(inputs),
        len(transformed),
    )


def proxy_metrics(references, predictions):
    """Compute unchanged D68 normalization/edit primitives on authored TTS references without falsely labelling the speech independent public/human-rated truth."""
    expected = {case["id"]: case for case in references}
    if len(expected) != len(references):
        raise ValueError("tts_proxy_reference_identity")
    seen, rows, groups = set(), [], {}
    for prediction in predictions:
        identity = prediction["id"]
        if identity not in expected or identity in seen:
            raise ValueError("tts_proxy_prediction_identity")
        seen.add(identity)
        case = expected[identity]
        if prediction["status"] != "ok":
            rows.append(dict(id=identity, status="error"))
            continue
        reference, hypothesis = (
            normalize(case["authored_text"]),
            normalize(prediction["text"]),
        )
        words, characters = reference.split(), reference.replace(" ", "")
        row = dict(
            id=identity,
            status="ok",
            authored_text=case["authored_text"],
            ASR_prediction=prediction["text"],
            word_edits=edit_distance(words, hypothesis.split()),
            reference_words=len(words),
            character_edits=edit_distance(characters, hypothesis.replace(" ", "")),
            reference_characters=len(characters),
        )
        group = groups.setdefault(
            case["candidate"] + "/" + case["language"] + "/" + case["variant"],
            dict(
                observed=0,
                word_edits=0,
                reference_words=0,
                character_edits=0,
                reference_characters=0,
            ),
        )
        group["observed"] += 1
        for key in [
            "word_edits",
            "reference_words",
            "character_edits",
            "reference_characters",
        ]:
            group[key] += row[key]
        rows.append(row)
    for group in groups.values():
        group.update(
            WER=group["word_edits"] / group["reference_words"],
            CER=group["character_edits"] / group["reference_characters"],
        )
    return dict(
        description="Qwen-ASR roundtrip intelligibility proxy on authored texts, potentially related-family biased; not independent TTS truth, naturalness or MOS.",
        expected=len(expected),
        observed=len(rows),
        complete=len(rows) == len(expected)
        and all(row["status"] == "ok" for row in rows),
        groups=groups,
        cases=rows,
        naturalness_score=None,
        model_selected=None,
    )


def replay(diagnostics, output):
    """Replay all eligible transformed waveforms once through frozen D68 ASR using an owned reference-free staging root and unchanged original SDK/model."""
    diagnostics, output = Path(diagnostics), Path(output)
    result = json.loads((diagnostics / "result.json").read_text())
    frozen = json.loads((diagnostics / "freeze.json").read_text())
    if result["complete"] is not True or result["freeze_sha256"] != sha(
        (diagnostics / "freeze.json").read_bytes()
    ):
        raise ValueError("tts_proxy_diagnostic_complete")
    output.mkdir(mode=0o700, exist_ok=False)
    staging = output / "staging"
    staging.mkdir(mode=0o700)
    (staging / "runtime-source").mkdir(mode=0o700)
    (staging / "prediction-inputs").mkdir(mode=0o700)
    original = PROJECT / "data/backups/d68-asr-evaluation"
    (staging / "venv").symlink_to(original / "venv", target_is_directory=True)
    (staging / "runtime-source/qwen-backend-source").symlink_to(
        original / "runtime-source/qwen-backend-source", target_is_directory=True
    )
    prepare_runtime_identity(staging)
    references = {case["id"]: case for case in frozen["references"]}
    inputs, eligible, ineligible = [], [], []
    for row in result["events"]:
        if row["event"] != "transformed":
            continue
        audio, identity = row["asr"], row["id"]
        raw = read_output(diagnostics / "generated", identity + ".f32")
        if (
            len(raw) != audio["sample_count"] * 4
            or sha(raw) != audio["waveform_sha256"]
        ):
            raise ValueError("tts_proxy_input_integrity")
        if not 16000 <= audio["sample_count"] <= 320000:
            ineligible.append(
                dict(
                    id=identity,
                    reason="original_D68_one_to_twenty_second_input_contract",
                    sample_count=audio["sample_count"],
                )
            )
            continue
        save_bytes(staging / "prediction-inputs" / (identity + ".f32"), raw)
        inputs.append(
            dict(
                id=identity,
                filename=identity + ".f32",
                language={"en": "en_us", "vi": "vi_vn"}[
                    references[identity]["language"]
                ],
                sample_count=audio["sample_count"],
                waveform_sha256=audio["waveform_sha256"],
            )
        )
        eligible.append(references[identity])
    request = dict(candidate="qwen3-asr-0.6b", mode="predict", cases=inputs)
    validate_asr_request(request)
    save_bytes(
        output / "freeze.json",
        (
            json.dumps(
                dict(
                    description="One reference-blind ASR replay after all TTS processes retired; no native sample repair or reference text in worker mounts.",
                    request=request,
                    references=eligible,
                    ineligible=ineligible,
                    diagnostic_result_sha256=sha(
                        (diagnostics / "result.json").read_bytes()
                    ),
                ),
                ensure_ascii=False,
                indent=2,
            )
            + "\n"
        ).encode(),
    )
    model = original / "models/qwen3-asr-0.6b/5eb144179a02acc5e5ba31e748d22b0cf3e303b0"
    before = core_snapshot()
    process, stdout, stderr = run_worker(
        sandbox_command("qwen3-asr-0.6b", model, staging), request, timeout=900
    )
    save_bytes(output / "worker.stdout.jsonl", stdout)
    save_bytes(output / "worker.stderr.log", stderr)
    events = [json.loads(line) for line in stdout.splitlines()]
    after = core_snapshot()
    if any(
        before[key] != after[key] for key in ["pid", "start_ticks", "command_sha256"]
    ):
        raise ValueError("tts_proxy_CORE_changed")
    predictions = [row for row in events if row["event"] == "prediction"]
    expected = {row["id"]: row for row in inputs}
    for row in predictions:
        if row["status"] == "ok" and (
            row.get("output_cap_reached") is not False
            or any(
                row[key] != expected[row["id"]][key]
                for key in ["sample_count", "waveform_sha256"]
            )
        ):
            raise ValueError("tts_proxy_prediction_source_cap")
    scored = proxy_metrics(eligible, predictions)
    save_bytes(
        output / "result.json",
        (
            json.dumps(
                dict(
                    description="First ASR roundtrip diagnostic, not independent human TTS/naturalness evidence.",
                    process=process,
                    events=events,
                    metrics=scored,
                    ineligible=ineligible,
                    core_before=before,
                    core_after=after,
                    freeze_sha256=sha((output / "freeze.json").read_bytes()),
                ),
                ensure_ascii=False,
                indent=2,
            )
            + "\n"
        ).encode(),
    )
    logger.info(
        "tts_first_ASR_proxy_retained eligible=%d observed=%d ineligible=%d",
        len(eligible),
        len(predictions),
        len(ineligible),
    )


def main():
    """Create distinct diagnostic copies or replay ASR once without selecting a TTS default or changing any historical evaluation files."""
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["prepare", "replay"], required=True)
    parser.add_argument("--runs", nargs="*", type=Path)
    parser.add_argument("--diagnostics", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    if arguments.mode == "prepare" and arguments.runs:
        prepare_diagnostics(arguments.runs, arguments.output)
    elif arguments.mode == "replay" and arguments.diagnostics:
        replay(arguments.diagnostics, arguments.output)
    else:
        parser.error("prepare requires --runs; replay requires --diagnostics")


if __name__ == "__main__":
    main()
