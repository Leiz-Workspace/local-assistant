"""Compare original nominated ASR candidates with and without unchanged Silero gating on a new retained-corpus subset, without selecting models."""

import argparse
import hashlib
import json
import logging
from pathlib import Path

import numpy as np

from scripts.asr_evaluation_assets import ROOT as ASR_ROOT
from scripts.asr_evaluation_assets import verify_file
from scripts.asr_evaluation_corpus import (
    float_wav,
    save_bytes,
    select_rows,
    selected_audio,
)
from scripts.asr_evaluation_metrics import score
from scripts.asr_evaluation_runner import (
    core_snapshot,
    public_request,
    run_worker,
    sandbox_command,
)
from scripts.tts_local_review import require_headroom
from scripts.vad_evaluation import ROOT as VAD_ROOT
from scripts.vad_evaluation import sandbox, verify_provision
from scripts.vad_evaluation_worker import validate_segments

logger = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parents[1] / "data/backups/d72-vad-asr-comparison-first"


def sha(raw):
    """Bind complete public evaluation bytes without logging audio or reference content."""
    return hashlib.sha256(raw).hexdigest()


def publish(path, value):
    """Create one immutable result or freeze exclusively, retaining all first failures."""
    save_bytes(
        Path(path), (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()
    )


def gated_waveform(raw, spans):
    """Preserve exact source sample bytes for ordered half-open spans and pad only subsecond ASR inputs explicitly."""
    if type(raw) is not bytes or len(raw) % 4 or not 16000 <= len(raw) // 4 <= 320000:
        raise ValueError("voice_pcm_source_bound")
    validate_segments(spans, len(raw) // 4)
    selected = b"".join(raw[row["start"] * 4 : row["end"] * 4] for row in spans)
    retained = len(selected) // 4
    padding = max(0, 16000 - retained) if retained else 0
    logger.info(
        "voice_gated_samples retained=%d explicit_padding=%d", retained, padding
    )
    return selected + b"\0" * (padding * 4), retained, padding


def replace_mount(command, old, new):
    """Replace exactly one known sample mount while retaining the original worker, SDK and resource caps."""
    command = list(command)
    if command.count(str(old)) != 1:
        raise ValueError("voice_sample_mount_identity")
    command[command.index(str(old))] = str(new)
    return command


def heldout_rows(value, language, old_cases):
    """Select twenty new utterances and sentence identities without inspecting any model prediction."""
    rows, _ = select_rows(value, language, count=100)
    filenames = {
        row["filename"]
        for row in old_cases
        if row.get("language") == language
        and row.get("kind") == "independent_public_speech"
    }
    sentences = {
        row["sentence_id"]
        for row in old_cases
        if row.get("language") == language
        and row.get("kind") == "independent_public_speech"
    }
    chosen = []
    for row in rows:
        if row["filename"] in filenames or row["sentence_id"] in sentences:
            continue
        chosen.append(row)
        sentences.add(row["sentence_id"])
        if len(chosen) == 20:
            break
    if len(chosen) != 20:
        raise ValueError("voice_heldout_count")
    return chosen


def prepare(root=ROOT):
    """Freeze the next twenty unused eligible speech rows per language plus authored controls before inference."""
    root = Path(root)
    root.mkdir(mode=0o700, exist_ok=False)
    samples = root / "vad-inputs"
    samples.mkdir(mode=0o700)
    original = json.loads((ASR_ROOT / "prepared/corpus.json").read_text())
    provision = json.loads((ASR_ROOT / "corpus-provisioned.json").read_text())
    for record in provision["results"]:
        verify_file(
            ASR_ROOT
            / "corpus"
            / record["language"]
            / record["expected_spec"]["filename"],
            record["expected_spec"],
        )
    cases = []
    for language in ("vi_vn", "en_us"):
        directory = ASR_ROOT / "corpus" / language
        rows = heldout_rows(
            (directory / "test.tsv").read_text(), language, original["cases"]
        )
        originals = selected_audio(directory / "test.tar.gz", rows)
        for row in rows:
            raw, metadata = float_wav(originals[row["filename"]])
            identity = f"heldout-{row['id']}"
            save_bytes(samples / (identity + ".f32"), raw)
            cases.append(
                dict(
                    row,
                    id=identity,
                    source_sha256=sha(originals[row["filename"]]),
                    waveform_sha256=sha(raw),
                    sample_count=metadata["sample_count"],
                    waveform_path=str(samples / (identity + ".f32")),
                )
            )
    rng = np.random.default_rng(112)
    signals = [
        np.zeros(48000, dtype="<f4"),
        rng.normal(0, 0.01, 48000).astype("<f4"),
        rng.uniform(-0.02, 0.02, 48000).astype("<f4"),
        np.full(48000, 0.01, dtype="<f4"),
        (np.sin(np.arange(48000) * 2 * np.pi * 440 / 16000) * 0.05).astype("<f4"),
    ]
    for index, signal in enumerate(signals):
        raw, identity = signal.tobytes(), f"negative-{index}"
        save_bytes(samples / (identity + ".f32"), raw)
        cases.append(
            dict(
                id=identity,
                language="vi_vn" if index % 2 else "en_us",
                kind="authored_no_speech",
                reference="",
                sample_count=len(signal),
                waveform_sha256=sha(raw),
                source_sha256=sha(raw),
                waveform_path=str(samples / (identity + ".f32")),
            )
        )
    for language in ("vi_vn", "en_us"):
        source = next(
            row
            for row in cases
            if row["language"] == language
            and row["kind"] == "independent_public_speech"
            and row["sample_count"] <= 288000
        )
        raw = b"\0" * 64000 + Path(source["waveform_path"]).read_bytes() + b"\0" * 64000
        identity = "padded-" + language
        save_bytes(samples / (identity + ".f32"), raw)
        cases.append(
            dict(
                source,
                id=identity,
                waveform_sha256=sha(raw),
                sample_count=len(raw) // 4,
                waveform_path=str(samples / (identity + ".f32")),
                embedded_start_sample=16000,
                embedded_end_sample=16000 + source["sample_count"],
                padding_samples_each_side=16000,
            )
        )
    if len(cases) != 47:
        raise ValueError("voice_corpus_count")
    result = dict(
        description="Locally held out from D68/D69: next20eligible original FLEURS rows per language; five new authored negatives and two padded composites. Not proof of absence from model pretraining or sample-level word labels.",
        cases=cases,
        original_speech_rows=40,
        source_clock_policy="Preserve half-open source-sample spans; concatenated ASR positions are not original timestamps.",
        source_samples_repaired=False,
        models_selected=False,
    )
    publish(root / "corpus.json", result)
    publish(
        root / "source-freeze.json",
        dict(
            description="Implementation/configuration bytes frozen before any new inference; existing model artifacts remain pinned and verified separately.",
            source_sha256={
                str(path): sha(path.read_bytes())
                for path in [
                    Path(__file__),
                    Path("scripts/asr_evaluation_worker.py"),
                    Path("scripts/vad_evaluation_worker.py"),
                    Path("configs/asr-evaluation-candidates.json"),
                    Path("configs/vad-evaluation-candidate.json"),
                    Path(
                        "docs/ADR/112-bounded-voice-composition-without-model-selection.md"
                    ),
                ]
            },
        ),
    )
    logger.info("voice_heldout_packet_frozen speech=40 negatives=5 composites=2")
    return result


def execute(root=ROOT):
    """Run one original VAD worker and both original ASR candidates sequentially, retaining first raw outputs and all nonselection limits."""
    root = Path(root)
    corpus = json.loads((root / "corpus.json").read_text())
    cases = corpus["cases"]
    freeze = json.loads((root / "source-freeze.json").read_text())
    if any(
        sha(Path(name).read_bytes()) != expected
        for name, expected in freeze["source_sha256"].items()
    ):
        raise ValueError("voice_source_freeze_drift")
    verify_provision()
    configuration = json.loads(
        Path("configs/asr-evaluation-candidates.json").read_text()
    )
    for candidate in configuration["candidates"]:
        for spec in candidate["artifacts"]:
            verify_file(
                ASR_ROOT
                / "models"
                / candidate["id"]
                / candidate["revision"]
                / spec["filename"],
                spec,
            )
    for case in cases:
        raw = Path(case["waveform_path"]).read_bytes()
        if sha(raw) != case["waveform_sha256"] or len(raw) != 4 * case["sample_count"]:
            raise ValueError("voice_source_drift")
    before = core_snapshot()
    request = dict(
        mode="predict",
        cases=[
            {key: row[key] for key in ("id", "sample_count", "waveform_sha256")}
            | {"filename": Path(row["waveform_path"]).name}
            for row in cases
        ],
    )
    publish(root / "vad-request.json", request)
    require_headroom()
    process, stdout, stderr = run_worker(
        replace_mount(sandbox(), VAD_ROOT / "samples", root / "vad-inputs"),
        request,
        timeout=180,
    )
    vad_process = process
    save_bytes(root / "vad-stdout.jsonl", stdout)
    save_bytes(root / "vad-stderr.log", stderr)
    publish(root / "vad-process.json", process)
    if process["exit_code"] or process["timed_out"]:
        raise ValueError("voice_vad_failed")
    events = [json.loads(line) for line in stdout.splitlines()]
    forward = {
        row["id"]: row
        for row in events
        if row["event"] == "observation" and row["pass_name"] == "forward"
    }
    reverse = {
        row["id"]: row
        for row in events
        if row["event"] == "observation" and row["pass_name"] == "reverse"
    }
    if (
        len(forward) != 47
        or len(reverse) != 47
        or any(
            forward[row["id"]]["status"] != "ok"
            or forward[row["id"]]["segments"] != reverse[row["id"]]["segments"]
            or forward[row["id"]]["probability_sha256"]
            != reverse[row["id"]]["probability_sha256"]
            for row in cases
        )
    ):
        raise ValueError("voice_vad_incomplete_or_replay_drift")
    inputs = root / "asr-inputs"
    inputs.mkdir(mode=0o700)
    pairs, requests = [], []
    for case in cases:
        observation = forward[case["id"]]
        if (
            observation["waveform_sha256"] != case["waveform_sha256"]
            or observation["sample_count"] != case["sample_count"]
        ):
            raise ValueError("voice_vad_source_binding")
        raw = Path(case["waveform_path"]).read_bytes()
        gated, retained, padding = gated_waveform(raw, observation["segments"])
        pairs.append(
            dict(
                id=case["id"],
                spans=observation["segments"],
                retained_samples=retained,
                ASR_tail_padding=padding,
                original_samples=case["sample_count"],
                VAD_seconds=observation["wall_seconds"],
            )
        )
        for mode, payload in (("ungated", raw), ("gated", gated)):
            if not payload:
                continue
            identity = case["id"] + "-" + mode
            path = inputs / (identity + ".f32")
            save_bytes(path, payload)
            requests.append(
                dict(
                    case,
                    id=identity,
                    waveform_path=str(path),
                    sample_count=len(payload) // 4,
                    waveform_sha256=sha(payload),
                )
            )
    publish(root / "gating-map.json", pairs)
    publish(
        root / "asr-freeze.json",
        dict(
            description="Reference-free complete ASR inputs frozen after the first VAD result and before ASR predictions; no retries or source edits.",
            request_cases=[
                {
                    k: row[k]
                    for k in ("id", "language", "sample_count", "waveform_sha256")
                }
                for row in requests
            ],
            input_sha256={
                path.name: sha(path.read_bytes()) for path in sorted(inputs.iterdir())
            },
        ),
    )
    results = []
    for candidate in configuration["candidates"]:
        identity = candidate["id"]
        model = ASR_ROOT / "models" / identity / candidate["revision"]
        public = public_request(identity, "predict", requests)
        publish(root / (identity + "-request.json"), public)
        require_headroom()
        process, stdout, stderr = run_worker(
            replace_mount(
                sandbox_command(identity, model), ASR_ROOT / "prediction-inputs", inputs
            ),
            public,
        )
        save_bytes(root / (identity + "-stdout.jsonl"), stdout)
        save_bytes(root / (identity + "-stderr.log"), stderr)
        publish(root / (identity + "-process.json"), process)
        predictions = [
            json.loads(line)
            for line in stdout.splitlines()
            if json.loads(line)["event"] == "prediction"
        ]
        variants = {}
        for mode in ("ungated", "gated"):
            projected = []
            for row in predictions:
                if row["id"].endswith("-" + mode):
                    projected.append(dict(row, id=row["id"].removesuffix("-" + mode)))
            early = [
                dict(
                    id=pair["id"],
                    status="ok",
                    text="",
                    wall_seconds=pair["VAD_seconds"],
                )
                for pair in pairs
                if mode == "gated" and pair["retained_samples"] == 0
            ]
            variants[mode] = score(cases, projected + early)
        result = dict(
            candidate=identity,
            process=process,
            scores=variants,
            no_speech_ASR_early_exits=sum(
                pair["retained_samples"] == 0 for pair in pairs
            ),
        )
        publish(root / (identity + "-comparison.json"), result)
        results.append(result)
        if (
            process["exit_code"]
            or process["timed_out"]
            or len(predictions) != len(requests)
        ):
            raise ValueError("voice_asr_incomplete")
    after = core_snapshot()
    if any(
        before[key] != after[key] for key in ("pid", "start_ticks", "command_sha256")
    ):
        raise ValueError("voice_core_changed")
    result = dict(
        description="First bounded original-candidate VAD/gated-versus-ungated ASR comparison; no model choice, deployment, word-level retention certification or TTS listening.",
        candidates=results,
        VAD_process=vad_process,
        gating_map=pairs,
        core_before=before,
        core_after=after,
        model_selected=None,
        D72_complete=False,
    )
    publish(root / "comparison.json", result)
    logger.info("voice_vad_asr_comparison_complete candidates=2 models_selected=0")
    return result


def main():
    """Prepare or execute exactly one exclusive retained-corpus comparison without downloading artifacts or altering previous evaluations."""
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("prepare", "execute"))
    args = parser.parse_args()
    if args.mode == "prepare":
        prepare()
    else:
        execute()


if __name__ == "__main__":
    main()
