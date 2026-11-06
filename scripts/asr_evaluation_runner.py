"""Own one offline ASR subprocess, isolate references from its filesystem, preserve partial failures and measure unchanged CORE recovery."""

import argparse
import hashlib
import json
import logging
import os
import signal
import subprocess
import time
import urllib.request
from pathlib import Path

from scripts.asr_evaluation_assets import ROOT, verify_file
from scripts.asr_evaluation_corpus import save_bytes
from scripts.asr_evaluation_metrics import score
from scripts.asr_evaluation_worker import validate_request

logger = logging.getLogger(__name__)
PROJECT = Path(__file__).resolve().parents[1]


def digest(path):
    """Fingerprint complete owned runtime/input/source bytes for the evaluation record."""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def public_request(candidate, mode, cases):
    """Project only case identity/language/waveform integrity into the worker request, excluding all reference text and upstream labels."""
    rows = (
        [
            dict(
                id=c["id"],
                language=c["language"],
                filename=Path(c["waveform_path"]).name,
                sample_count=c["sample_count"],
                waveform_sha256=c["waveform_sha256"],
            )
            for c in cases
        ]
        if mode == "predict"
        else []
    )
    request = dict(candidate=candidate, mode=mode, cases=rows)
    validate_request(request)
    return request


def sandbox_command(candidate, model, root=ROOT):
    """Mount only the selected official model/source and reference-free samples with CPU/memory/time/namespace bounds and private runtime tmpfs."""
    if candidate not in {"qwen3-asr-0.6b", "whisper-small-ct2"}:
        raise ValueError("asr_candidate")
    source = (
        root
        / "runtime-source"
        / (
            "qwen-backend-source"
            if candidate == "qwen3-asr-0.6b"
            else "faster-whisper-source"
        )
    )
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
        str(PROJECT / "scripts/asr_evaluation_worker.py"),
        "/app/worker.py",
        "--ro-bind",
        str(source),
        "/sources",
        "--ro-bind",
        str(model),
        "/model",
        "--ro-bind",
        str(root / "prediction-inputs"),
        "/samples",
        "--proc",
        "/proc",
        "--dev",
        "/dev",
        "--size",
        str(128 * 1024**2),
        "--tmpfs",
        "/tmp",
        "--chdir",
        "/app",
    ]
    command.extend(
        [
            "--dir",
            "/etc",
            "--ro-bind",
            str(root / "runtime-source/passwd"),
            "/etc/passwd",
            "--ro-bind",
            str(root / "runtime-source/group"),
            "/etc/group",
        ]
    )
    environment = dict(
        PATH="/venv/bin:/usr/bin",
        PYTHONPATH="/sources",
        LANG="C.UTF-8",
        PYTHONDONTWRITEBYTECODE="1",
        CUDA_VISIBLE_DEVICES="",
        HF_HUB_OFFLINE="1",
        TRANSFORMERS_OFFLINE="1",
        HF_HOME="/tmp/hf",
        NUMBA_CACHE_DIR="/tmp/numba",
        HOME="/tmp",
        USER="asr-evaluation",
        LOGNAME="asr-evaluation",
        OMP_NUM_THREADS="2",
        MKL_NUM_THREADS="2",
        OPENBLAS_NUM_THREADS="2",
        NUMBA_NUM_THREADS="2",
        TOKENIZERS_PARALLELISM="false",
    )
    for key, value in environment.items():
        command.extend(["--setenv", key, value])
    return command + [
        "--remount-ro",
        "/",
        "--",
        "/usr/bin/prlimit",
        "--as=8589934592",
        "--cpu=1200:1201",
        "--nofile=128",
        "--fsize=16777216",
        "--core=0",
        "--",
        "/venv/bin/python",
        "/app/worker.py",
    ]


def prepare_runtime_identity(root=ROOT):
    """Provide only a synthetic current UID/GID entry required by SDK imports, never binding the host account or credential databases."""
    for name, value in [
        (
            "passwd",
            f"# Synthetic ASR evaluation identity only.\nasr-evaluation:x:{os.getuid()}:{os.getgid()}:CPU evaluation:/tmp:/bin/false\n",
        ),
        (
            "group",
            f"# Synthetic ASR evaluation group only.\nasr-evaluation:x:{os.getgid()}:\n",
        ),
    ]:
        path = root / "runtime-source" / name
        raw = value.encode()
        if not path.exists():
            save_bytes(path, raw)
        if path.is_symlink() or path.read_bytes() != raw:
            raise ValueError("asr_runtime_identity")
    logger.info("asr_synthetic_runtime_identity_verified")


def run_worker(command, request, timeout=900):
    """Join the owned namespace after normal completion or timeout and retain bounded actual stdout/stderr without retrying inference."""
    started = time.perf_counter()
    process = subprocess.Popen(
        command,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
        env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"},
    )
    timed_out = False
    try:
        stdout, stderr = process.communicate(
            json.dumps(request).encode(), timeout=timeout
        )
    except subprocess.TimeoutExpired:
        timed_out = True
        os.killpg(process.pid, signal.SIGKILL)
        stdout, stderr = process.communicate(timeout=10)
    if len(stdout) > 2 * 1024**2 or len(stderr) > 8 * 1024**2:
        raise ValueError("asr_process_output_bound")
    logger.info(
        "asr_worker_retired exit_code=%d timed_out=%s", process.returncode, timed_out
    )
    return (
        dict(
            exit_code=process.returncode,
            timed_out=timed_out,
            wall_seconds=time.perf_counter() - started,
            owned_process_reaped=process.poll() is not None,
        ),
        stdout,
        stderr,
    )


def core_snapshot():
    """Verify the original CORE process and literal text recovery while recording RSS RAM separately from NVIDIA process allocation VRAM."""
    pid = 37256
    raw = Path(f"/proc/{pid}/stat").read_text()
    fields = raw.rsplit(")", 1)[1].split()
    command_sha = digest(f"/proc/{pid}/cmdline")
    status = Path(f"/proc/{pid}/status").read_text().splitlines()
    rss = int(next(line.split()[1] for line in status if line.startswith("VmRSS:")))
    gpu_raw = subprocess.check_output(
        [
            "nvidia-smi",
            "--query-compute-apps=pid,used_gpu_memory",
            "--format=csv,noheader,nounits",
        ],
        text=True,
    )
    gpu = [
        int(line.split(",")[1].strip())
        for line in gpu_raw.splitlines()
        if line.split(",")[0].strip() == str(pid)
    ]
    payload = dict(
        model="qwen3.5-9b-core",
        messages=[
            dict(
                role="system",
                content="Reply with exactly ASR_CORE_OK and no other text.",
            ),
            dict(role="user", content="Perform the literal echo test."),
        ],
        max_tokens=24,
        temperature=0,
        seed=7,
        cache_prompt=False,
        chat_template_kwargs=dict(enable_thinking=False),
    )
    request = urllib.request.Request(
        "http://127.0.0.1:8080/v1/chat/completions",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        result = json.load(response)
    assert result["choices"][0]["message"]["content"].strip() == "ASR_CORE_OK"
    logger.info("asr_original_core_recovery_pass pid=%d", pid)
    return dict(
        pid=pid,
        start_ticks=int(fields[19]),
        command_sha256=command_sha,
        RSS_RAM_KiB=rss,
        NVIDIA_process_allocation_VRAM_MiB=gpu,
        ordinary_text_recovery=True,
    )


def qualification_case(root=ROOT):
    """Normalize the existing pinned JFK fixture for SDK input qualification, excluding it from the common scored corpus."""
    import numpy as np

    from src.infrastructure.audio_normalizer import NativeAudioNormalizer

    source = PROJECT / "tests/fixtures/audio/jfk.flac"
    if (
        digest(source)
        != "63a4b1e4c1dc655ac70961ffbf518acd249df237e5a0152faae9a4a836949715"
    ):
        raise ValueError("asr_qualification_source")
    audio = NativeAudioNormalizer().normalize(source.read_bytes())
    raw = (
        (np.frombuffer(audio.pcm_s16le, dtype="<i2").astype("<f4") / 32768)
        .astype("<f4")
        .tobytes()
    )
    directory = root / "qualification"
    directory.mkdir(mode=0o700, exist_ok=True)
    path = directory / "qualification-jfk.f32"
    if not path.exists():
        save_bytes(path, raw)
    if path.is_symlink() or path.read_bytes() != raw:
        raise ValueError("asr_qualification_waveform")
    logger.info(
        "asr_nonbenchmark_qualification_prepared samples=%d", audio.sample_count
    )
    return dict(
        id="qualification-jfk",
        language="en_us",
        waveform_path=str(path),
        sample_count=audio.sample_count,
        waveform_sha256=digest(path),
        source_sha256=audio.source_sha256,
        reference=None,
        kind="qualification_only_not_scored",
    )


def evaluate(candidate, mode, output):
    """Freeze exact current inputs before execution and save actual observations plus recovery without selecting/deploying a model."""
    output = Path(output)
    output.mkdir(mode=0o700, exist_ok=False)
    prepare_runtime_identity()
    config = json.loads(
        (PROJECT / "configs/asr-evaluation-candidates.json").read_text()
    )
    selected = next(row for row in config["candidates"] if row["id"] == candidate)
    model = ROOT / "models" / candidate / selected["revision"]
    for spec in selected["artifacts"]:
        verify_file(model / spec["filename"], spec)
    inventory = json.loads((ROOT / "runtime-source/source-inventory.json").read_text())
    for item in inventory["files"]:
        assert digest(ROOT / "runtime-source" / item["path"]) == item["sha256"]
    corpus_path = ROOT / "prepared/corpus.json"
    corpus = json.loads(corpus_path.read_text())
    cases = [qualification_case()] if mode == "smoke" else corpus["cases"]
    inputs = ROOT / "prediction-inputs"
    inputs.mkdir(mode=0o700, exist_ok=True)
    for case in cases:
        source = Path(case["waveform_path"])
        destination = inputs / source.name
        if not destination.exists():
            os.link(source, destination)
        if destination.is_symlink() or digest(destination) != case["waveform_sha256"]:
            raise ValueError("asr_input_freeze")
    if any(path.suffix != ".f32" or not path.is_file() for path in inputs.iterdir()):
        raise ValueError("asr_reference_free_mount")
    request = public_request(candidate, "predict" if mode == "smoke" else mode, cases)
    frozen = dict(
        description="Pre-execution local ASR inputs; labels stay in parent, selected model/source are readonly, no selection/deployment.",
        candidate=candidate,
        mode=mode,
        corpus_sha256=digest(corpus_path),
        request=request,
        source_sha256={
            str(path.relative_to(PROJECT)): digest(path)
            for path in [
                PROJECT / "configs/asr-evaluation-candidates.json",
                PROJECT / "docs/ADR/094-offline-registry-asr-comparison.md",
                *sorted((PROJECT / "scripts").glob("asr_evaluation_*.py")),
                ROOT / "runtime-source/source-inventory.json",
                ROOT / "runtime-source/installed-runtime-first.txt",
                ROOT / "runtime-source/passwd",
                ROOT / "runtime-source/group",
                *sorted((PROJECT / "tests").glob("test_asr_evaluation_*.py")),
            ]
        },
    )
    save_bytes(output / "freeze.json", (json.dumps(frozen, indent=2) + "\n").encode())
    before = core_snapshot()
    save_bytes(
        output / "core-before.json", (json.dumps(before, indent=2) + "\n").encode()
    )
    metadata, stdout, stderr = run_worker(sandbox_command(candidate, model), request)
    save_bytes(output / "worker.stdout.jsonl", stdout)
    save_bytes(output / "worker.stderr.log", stderr)
    events = [json.loads(line) for line in stdout.splitlines()]
    after = core_snapshot()
    assert all(
        before[key] == after[key] for key in ["pid", "start_ticks", "command_sha256"]
    )
    for path, expected in frozen["source_sha256"].items():
        assert digest(PROJECT / path) == expected
    assert digest(corpus_path) == frozen["corpus_sha256"]
    result = dict(
        description="Actual offline one-candidate observation; no quality or selection inferred from process exit alone.",
        candidate=candidate,
        mode=mode,
        process=metadata,
        events=events,
        core_before=before,
        core_after=after,
        freeze_sha256=digest(output / "freeze.json"),
        observation_complete=metadata["exit_code"] == 0
        and not metadata["timed_out"]
        and [event["event"] for event in events].count("ready") == 1
        and [event["event"] for event in events].count("complete") == 1,
        selection=None,
    )
    if mode == "predict":
        result["metrics"] = score(
            corpus["cases"],
            [event for event in events if event["event"] == "prediction"],
        )
    save_bytes(
        output / "result.json",
        (json.dumps(result, indent=2, ensure_ascii=False) + "\n").encode(),
    )
    logger.info(
        "asr_candidate_evaluation_saved candidate=%s mode=%s exit_code=%d selected_models=0",
        candidate,
        mode,
        metadata["exit_code"],
    )


def main():
    """Accept only a nominated candidate and exclusive owned output directory for qualification or a single actual comparison run."""
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--candidate", choices=["qwen3-asr-0.6b", "whisper-small-ct2"], required=True
    )
    parser.add_argument(
        "--mode", choices=["imports", "load", "smoke", "predict"], required=True
    )
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    evaluate(arguments.candidate, arguments.mode, arguments.output)


if __name__ == "__main__":
    main()
