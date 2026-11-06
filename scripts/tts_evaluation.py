"""Freeze authored VI/EN TTS cases and own bounded original SDK runs, verifying private native audio independently without changing production models."""

import argparse
import hashlib
import json
import logging
import math
import os
import stat
from pathlib import Path

import numpy as np

from scripts.asr_evaluation_corpus import save_bytes
from scripts.asr_evaluation_runner import (
    core_snapshot,
    prepare_runtime_identity,
    run_worker,
)
from scripts.tts_evaluation_assets import (
    PINS,
    ROOT,
    verify_models,
    verify_runtime_snapshot,
)
from scripts.tts_evaluation_worker import validate_request
from scripts.tts_waveform import describe, wave_bytes

logger = logging.getLogger(__name__)
PROJECT = Path(__file__).resolve().parents[1]
TEXTS = {
    "en": [
        "Hello, thank you for coming today.",
        "Where did you put the blue notebook?",
        "There are twenty three books on the shelf.",
        "The meeting is on October twenty second.",
        "Please close the window before you leave.",
        "After the rain stopped, we walked beside the river and watched the birds.",
    ],
    "vi": [
        "Xin chào, cảm ơn bạn đã đến hôm nay.",
        "Bạn để quyển sổ màu xanh ở đâu?",
        "Có hai mươi ba quyển sách trên giá.",
        "Cuộc họp vào ngày hai mươi hai tháng mười.",
        "Vui lòng đóng cửa sổ trước khi ra ngoài.",
        "Sau khi mưa tạnh, chúng tôi đi dọc bờ sông và ngắm những cánh chim bay.",
    ],
}
KINDS = [
    "greeting",
    "question",
    "spoken_number",
    "spoken_date",
    "instruction",
    "long_phrase",
]


def sha(raw):
    """Fingerprint exact bytes without embedding waveform content or text in operational logs."""
    return hashlib.sha256(raw).hexdigest()


def cases():
    """Return the fixed twelve authored neutral texts, keeping corresponding scenarios distinct from independent human quality labels."""
    result = [
        dict(
            id=f"{language}-{index + 1:02d}",
            language=language,
            text=text,
            kind=KINDS[index],
        )
        for language, texts in TEXTS.items()
        for index, text in enumerate(texts)
    ]
    if len(result) != 12 or any(len(row["text"].encode()) > 160 for row in result):
        raise ValueError("tts_authored_corpus")
    return result


def prepare(root=ROOT):
    """Publish the text corpus exclusively before any scored waveform without reading existing candidate output."""
    corpus = dict(
        description="D70 twelve authored texts frozen before common-case synthesis; six scenarios per language, not independent human TTS ratings. VI Auto is a distinct unsupported-language diagnostic, never a fallback/retry.",
        cases=cases(),
        selected_model=None,
    )
    save_bytes(
        Path(root) / "corpus.json",
        (json.dumps(corpus, ensure_ascii=False, indent=2) + "\n").encode(),
    )
    logger.info("tts_authored_corpus_prepared cases=12")


def worker_request(candidate, mode, corpus):
    """Expand fixed cases into explicit capability checks and separately named Auto diagnostics without output-dependent fallback."""
    selected = []
    if mode == "smoke":
        language = "vi" if candidate == "piper-vi" else "en"
        selected = [
            dict(
                id="qualification-" + language,
                text="Xin chào." if language == "vi" else "Hello.",
                language=language,
                variant="explicit",
            )
        ]
    elif mode == "predict":
        for case in corpus["cases"]:
            if candidate.startswith("piper-") and candidate[-2:] != case["language"]:
                continue
            selected.append(
                {key: case[key] for key in ["id", "text", "language"]}
                | dict(variant="explicit")
            )
        if candidate == "qwen3-tts-0.6b":
            selected.extend(
                dict(
                    id=case["id"] + "-auto",
                    text=case["text"],
                    language="vi",
                    variant="auto_diagnostic",
                )
                for case in corpus["cases"]
                if case["language"] == "vi"
            )
    request = dict(mode=mode, candidate=candidate, cases=selected)
    validate_request(request)
    return request


def model_directory(candidate, root=ROOT):
    """Expose only one pinned model/voice checkpoint directory, including Qwen's mandatory bundled codec."""
    directory = Path(root) / "models" / candidate / PINS[candidate][1]
    if candidate == "piper-en":
        directory /= "en/en_US/ljspeech/medium"
    elif candidate == "piper-vi":
        directory /= "vi/vi_VN/vais1000/medium"
    return directory


def sandbox(candidate, output, root=ROOT):
    """Mount one owned output capability and selected readonly SDK/model/source with no network, credentials, GPU or production filesystem."""
    root, output = Path(root), Path(output)
    if (
        output.is_symlink()
        or not output.is_dir()
        or output.stat().st_mode & 0o077
        or any(output.iterdir())
    ):
        raise ValueError("tts_empty_private_output")
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
        "--ro-bind",
        str(model_directory(candidate, root)),
        "/model",
        "--dir",
        "/app",
        "--dir",
        "/app/scripts",
    ]
    for name in ["tts_evaluation_worker.py", "tts_waveform.py"]:
        command.extend(
            ["--ro-bind", str(PROJECT / "scripts" / name), "/app/scripts/" + name]
        )
    if candidate.startswith("piper"):
        command.extend(
            ["--ro-bind", str(root / "runtime-source/piper-curated"), "/sources"]
        )
    command.extend(
        [
            "--bind",
            str(output),
            "/output",
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
            ["--ro-bind", str(root / "runtime-source" / name), "/etc/" + name]
        )
    command.extend(["--chdir", "/app"])
    environment = dict(
        PATH="/venv/bin:/usr/bin",
        PYTHONPATH="/app:/sources",
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
        NUMBA_CACHE_DIR="/tmp/numba",
    )
    for key, value in environment.items():
        command.extend(["--setenv", key, value])
    return command + [
        "--remount-ro",
        "/",
        "--",
        "/usr/bin/prlimit",
        "--as=12884901888",
        "--cpu=3600:3601",
        "--nofile=128",
        "--fsize=16777216",
        "--core=0",
        "--",
        "/venv/bin/python",
        "-m",
        "scripts.tts_evaluation_worker",
    ]


def read_output(directory, filename):
    """Read a bounded owned regular leaf without following links, blocking on special files or accepting permissive publication."""
    if (
        type(filename) is not str
        or Path(filename).name != filename
        or filename in {".", ".."}
    ):
        raise ValueError("tts_parent_output_name")
    descriptor = os.open(
        Path(directory) / filename,
        os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC,
    )
    with os.fdopen(descriptor, "rb") as stream:
        info = os.fstat(stream.fileno())
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_mode & 0o077
            or info.st_size > 16 * 1024**2
        ):
            raise ValueError("tts_parent_output_type_size_mode")
        return stream.read(16 * 1024**2 + 1)


def verify_outputs(directory, request, events):
    """Independently recompute complete raw/WAV hashes and signal metrics and require exact per-request event/file coverage without claiming naturalness."""
    expected = {case["id"]: case for case in request["cases"]}
    rows = [event for event in events if event.get("event") == "observation"]
    seen, filenames = set(), set()
    total = 0
    for row in rows:
        identity = row["id"]
        if identity not in expected or identity in seen:
            raise ValueError("tts_parent_observation_identity")
        seen.add(identity)
        case = expected[identity]
        if row["text_sha256"] != sha(case["text"].encode()) or any(
            row[key] != case[key] for key in ["language", "variant"]
        ):
            raise ValueError("tts_parent_text_binding")
        seconds = row["full_call_seconds"]
        if (
            type(seconds) not in (float, int)
            or not math.isfinite(seconds)
            or seconds <= 0
        ):
            raise ValueError("tts_parent_timing")
        if row["status"] in {"ok", "invalid_or_incomplete_audio"}:
            metadata = row["audio"]
            if (
                metadata["raw_filename"] != identity + ".f32"
                or metadata["wav_filename"] != identity + ".wav"
            ):
                raise ValueError("tts_parent_audio_identity")
            raw, wav = [
                read_output(directory, metadata[key])
                for key in ["raw_filename", "wav_filename"]
            ]
            values = np.frombuffer(raw, dtype="<f4")
            expected_rate = 24000 if request["candidate"] == "qwen3-tts-0.6b" else 22050
            if metadata["sample_rate"] != expected_rate:
                raise ValueError("tts_parent_native_rate")
            actual = describe(values, metadata["sample_rate"])
            if (
                any(metadata[key] != value for key, value in actual.items())
                or len(raw) != metadata["raw_bytes"]
                or len(wav) != metadata["wav_bytes"]
                or sha(wav) != metadata["wav_sha256"]
                or wave_bytes(values, metadata["sample_rate"]) != wav
            ):
                raise ValueError("tts_parent_audio_integrity")
            first = row["first_available_audio_seconds"]
            if (
                type(first) not in (int, float)
                or not math.isfinite(first)
                or not 0 < first <= seconds
                or row["status"] == "ok"
                and not (actual["signal_valid"] and row["generation_complete"])
            ):
                raise ValueError("tts_parent_complete_timing")
            if request["candidate"] == "qwen3-tts-0.6b":
                inner, frames = row["inner_generations"], row["codec_frames"]
                if (
                    len(inner) != 1
                    or len(frames) != 1
                    or type(inner[0]["sequence_tokens"]) is not int
                    or not 1 <= inner[0]["sequence_tokens"] <= 192
                    or inner[0]["ended_with_eos"] != (inner[0]["last_token"] == 2150)
                    or row["generation_complete"] != inner[0]["ended_with_eos"]
                    or frames[0]
                    != inner[0]["sequence_tokens"] - int(inner[0]["ended_with_eos"])
                    or row["maximum_new_tokens"] != 192
                    or first != seconds
                ):
                    raise ValueError("tts_parent_qwen_EOS_timing")
            filenames.update([metadata["raw_filename"], metadata["wav_filename"]])
            total += len(raw) + len(wav)
        elif row["status"] == "unsupported_language":
            if (
                request["candidate"] != "qwen3-tts-0.6b"
                or (case["language"], case["variant"]) != ("vi", "explicit")
                or row.get("error_class") != "ValueError"
                or not row.get("detail", "").startswith("Unsupported languages:")
            ):
                raise ValueError("tts_parent_unsupported_claim")
        elif row["status"] != "error":
            raise ValueError("tts_parent_status")
    if {
        path.name for path in Path(directory).iterdir()
    } != filenames or total > 64 * 1024**2:
        raise ValueError("tts_parent_unaccounted_output")
    complete = (
        len(rows) == len(expected)
        and len([event for event in events if event.get("event") == "complete"]) == 1
    )
    logger.info(
        "tts_native_outputs_independently_verified attempts=%d expected=%d bytes=%d",
        len(rows),
        len(expected),
        total,
    )
    return dict(
        observations_complete=complete,
        expected_attempts=len(expected),
        observed_attempts=len(rows),
        successful_waveforms=sum(row["status"] == "ok" for row in rows),
        unsupported_explicit_Vietnamese=sum(
            row["status"] == "unsupported_language" for row in rows
        ),
        errors=sum(
            row["status"] in {"error", "invalid_or_incomplete_audio"} for row in rows
        ),
        native_file_bytes=total,
        actual_audio_inspection_complete=False,
        model_selected=None,
    )


def evaluate(candidate, mode, output, root=ROOT):
    """Retain an exclusive first run/freeze and partial observations, joining its namespace before verifying original files and CORE recovery."""
    root, output = Path(root), Path(output)
    output.mkdir(mode=0o700, exist_ok=False)
    generated = output / "generated"
    generated.mkdir(mode=0o700)
    verify_models(root)
    if mode == "predict":
        verify_runtime_snapshot(root)
    prepare_runtime_identity(root)
    corpus = json.loads((root / "corpus.json").read_text())
    if corpus["cases"] != cases():
        raise ValueError("tts_corpus_frozen_text")
    request = worker_request(candidate, mode, corpus)
    paths = [
        PROJECT / "configs/tts-evaluation-candidates.json",
        PROJECT / "docs/ADR/096-offline-registry-tts-comparison.md",
        *sorted((PROJECT / "scripts").glob("tts_*.py")),
        *sorted((PROJECT / "tests").glob("test_tts_*.py")),
        root / "models-provisioned.json",
        root / "corpus.json",
        root / "runtime-source/installed-runtime-first.txt",
        root / "runtime-source/piper-curated/curation.json",
    ]
    hashes = {str(path.relative_to(PROJECT)): sha(path.read_bytes()) for path in paths}
    if mode == "predict":
        hashes[str((root / "runtime-integrity.json").relative_to(PROJECT))] = sha(
            (root / "runtime-integrity.json").read_bytes()
        )
    frozen = dict(
        description="D70 pre-execution exact source/protocol/runtime/text freeze; qualification distinct from first scored attempt. No model/default selection.",
        request=request,
        sha256=hashes,
    )
    save_bytes(
        output / "freeze.json",
        (json.dumps(frozen, ensure_ascii=False, indent=2) + "\n").encode(),
    )
    before = core_snapshot()
    save_bytes(
        output / "core-before.json", (json.dumps(before, indent=2) + "\n").encode()
    )
    metadata, stdout, stderr = run_worker(
        sandbox(candidate, generated, root), request, timeout=1800
    )
    save_bytes(output / "worker.stdout.jsonl", stdout)
    save_bytes(output / "worker.stderr.log", stderr)
    events = [json.loads(line) for line in stdout.splitlines()]
    after = core_snapshot()
    if any(
        before[key] != after[key] for key in ["pid", "start_ticks", "command_sha256"]
    ) or any(
        sha((PROJECT / path).read_bytes()) != expected
        for path, expected in hashes.items()
    ):
        raise ValueError("tts_source_or_CORE_changed")
    analysis = verify_outputs(generated, request, events)
    result = dict(
        description="Actual original nominated TTS first observations; no model selected or naturalness/MOS claim from acoustic metrics.",
        candidate=candidate,
        mode=mode,
        process=metadata,
        events=events,
        analysis=analysis,
        core_before=before,
        core_after=after,
        freeze_sha256=sha((output / "freeze.json").read_bytes()),
        selected_model=None,
    )
    save_bytes(
        output / "result.json",
        (json.dumps(result, ensure_ascii=False, indent=2) + "\n").encode(),
    )
    logger.info(
        "tts_first_run_retained candidate=%s mode=%s exit_code=%d observations=%d",
        candidate,
        mode,
        metadata["exit_code"],
        analysis["observed_attempts"],
    )


def main():
    """Prepare authored texts or execute a separate offline qualification/measurement without altering production configuration or source."""
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode",
        choices=["prepare", "imports", "load", "smoke", "predict"],
        required=True,
    )
    parser.add_argument("--candidate", choices=sorted(PINS))
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    if arguments.mode == "prepare":
        prepare()
    elif arguments.candidate is None or arguments.output is None:
        parser.error("--candidate and --output are required for execution")
    else:
        evaluate(arguments.candidate, arguments.mode, arguments.output)


if __name__ == "__main__":
    main()
