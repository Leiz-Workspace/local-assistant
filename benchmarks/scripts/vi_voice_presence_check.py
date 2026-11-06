"""Measure a research whole-clip gate using unchanged Silero, retained bilingual sources and explicitly derived quiet controls."""

import argparse
import asyncio
import hashlib
import json
import logging
import os
import signal
import subprocess
import time
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import numpy as np

from benchmarks.scripts import vi_voice_campaign as prior
from benchmarks.scripts.vi_voice_presence import (
    POLICY,
    VAD_MODEL,
    SpeechPresence,
    WholeClipASR,
)
from scripts.asr_evaluation_corpus import save_bytes
from scripts.tts_local_review import require_headroom
from scripts.vad_evaluation import ROOT as VAD_ROOT
from scripts.vad_evaluation import sandbox, verify_provision, worker_request
from scripts.vad_evaluation_worker import validate_segments
from scripts.voice_vad_comparison import ROOT as CORPUS_ROOT
from scripts.voice_vad_comparison import replace_mount
from src.application.ports.audio import NormalizedAudio
from src.application.ports.voice import VoiceTranscript
from src.application.services.voice_pipeline import (
    VoiceError,
    VoicePipeline,
    normalized,
)

LOGGER = logging.getLogger(__name__)
PROJECT = prior.PROJECT
ROOT = PROJECT / "data/backups/d74-whole-clip-presence-first"
SOURCES = (
    "benchmarks/scripts/vi_voice_presence.py",
    "benchmarks/scripts/vi_voice_presence_check.py",
    "benchmarks/tests/test_vi_voice_presence.py",
    "benchmarks/tests/test_vi_voice_presence_check.py",
)
ADR = "docs/ADR/166-whole-clip-presence-with-original-pcm.md"


def sha(raw):
    """Fingerprint bounded complete bytes without recording their audio or text content in logs."""
    return hashlib.sha256(raw).hexdigest()


def publish(path, value):
    """Publish immutable private first receipts using the existing exclusive writer."""
    prior.assets.publish(path, value)


def previous_snapshot():
    """Bind tracked code/configuration and retained prior voice evidence without reading private owner edits."""
    names = subprocess.check_output(
        [
            "git",
            "ls-files",
            "src",
            "apps",
            "tests",
            "scripts",
            "benchmarks",
            "configs",
            "pyproject.toml",
            "uv.lock",
        ],
        cwd=PROJECT,
        text=True,
    ).splitlines()
    native = prior.ROOT / "workflow-reading-native-first"
    paths = [PROJECT / name for name in names]
    paths.extend(
        path
        for directory in (native, CORPUS_ROOT)
        for path in directory.rglob("*")
        if path.is_file() and not path.is_symlink()
    )
    paths.extend(
        PROJECT / name
        for name in (
            "docs/evidence/d74-workflow-reading-native-result.json",
            "docs/evidence/d74-workflow-reading-native-authorization.json",
            "docs/ADR/165-reading-aware-native-voice-workflow-validation.md",
        )
    )
    paths.extend(path for path in (VAD_ROOT / "official").iterdir() if path.is_file())
    result = {
        str(path.relative_to(PROJECT)): prior.assets.digest(path) for path in paths
    }
    LOGGER.info("voice_presence_previous_snapshot files=%d", len(result))
    return result


def verify_snapshot(expected):
    """Refuse any mutation of prior sources or measured artifacts rather than overwriting the first record."""
    for name, digest in expected.items():
        if prior.assets.digest(PROJECT / name) != digest:
            raise ValueError("presence_previous_changed")
    LOGGER.info("voice_presence_previous_preserved files=%d", len(expected))


def floats(audio):
    """Represent complete normalized PCM exactly as the original ASR input without trimming or gain changes."""
    return (
        (
            np.frombuffer(audio.pcm_s16le, dtype="<i2").astype(np.float32)
            / np.float32(32768)
        )
        .astype("<f4")
        .tobytes()
    )


def prepare(root=ROOT):
    """Freeze 47 retained inputs and six predeclared full-recording attenuation controls before any inference."""
    root = Path(root)
    root.mkdir(mode=0o700, exist_ok=False)
    (root / "samples").mkdir(mode=0o700)
    (root / "pcm").mkdir(mode=0o700)
    original = previous_snapshot()
    corpus = json.loads((CORPUS_ROOT / "corpus.json").read_text())
    cases, audios = [], {}
    if len(corpus["cases"]) != 47:
        raise ValueError("presence_corpus_count")
    for row in corpus["cases"]:
        raw = Path(row["waveform_path"]).read_bytes()
        if sha(raw) != row["waveform_sha256"] or len(raw) != row["sample_count"] * 4:
            raise ValueError("presence_source_changed")
        audio = prior.NativeAudioNormalizer().normalize(prior.pcm_wave(raw, 16000))
        identity = row["id"]
        audios[identity] = audio
        cases.append(
            dict(
                id=identity,
                filename=identity + ".f32",
                kind=row["kind"],
                language=row["language"][:2],
                expected_speech=row["kind"] != "authored_no_speech",
                original_waveform_sha256=sha(raw),
                waveform_sha256=sha(floats(audio)),
                sample_count=audio.sample_count,
                audio={k: v for k, v in asdict(audio).items() if k != "pcm_s16le"},
            )
        )
    original_freeze = json.loads((prior.ROOT / "execution-freeze.json").read_text())[
        "input_conversion"
    ]
    for identity, binding in original_freeze.items():
        if sha(floats(audios[identity])) != binding["request"]["waveform_sha256"]:
            raise ValueError("presence_D74_exact_input_changed")
    for language in ("vi", "en"):
        source = next(
            row
            for row in cases
            if row["language"] == language
            and row["kind"] == "independent_public_speech"
        )
        original_audio = audios[source["id"]]
        for label, gain in (("half", 0.5), ("tenth", 0.1), ("three-percent", 0.03)):
            identity = "quiet-" + language + "-" + label
            pcm = (
                np.rint(
                    np.frombuffer(original_audio.pcm_s16le, dtype="<i2").astype(
                        np.float64
                    )
                    * gain
                )
                .astype("<i2")
                .tobytes()
            )
            audio = NormalizedAudio(
                sha(b"derived-full-recording-quiet-v1:" + pcm),
                sha(pcm),
                pcm,
                original_audio.sample_count,
                "pcm_s16le",
                16000,
                1,
                original_audio.sample_count,
                1,
                16000,
                0,
            )
            audios[identity] = audio
            cases.append(
                dict(
                    id=identity,
                    filename=identity + ".f32",
                    kind="derived_quiet_recording",
                    language=language,
                    expected_speech=True,
                    parent=source["id"],
                    gain=gain,
                    waveform_sha256=sha(floats(audio)),
                    sample_count=audio.sample_count,
                    audio={k: v for k, v in asdict(audio).items() if k != "pcm_s16le"},
                )
            )
    if len(cases) != 53 or len({x["id"] for x in cases}) != 53:
        raise ValueError("presence_panel_count")
    for row in cases:
        save_bytes(root / "samples" / row["filename"], floats(audios[row["id"]]))
        save_bytes(root / "pcm" / (row["id"] + ".s16le"), audios[row["id"]].pcm_s16le)
    freeze = dict(
        description="Preregistered existing47recordings converted through original PCM port plus6derived full-recording gains; no new independent holdout or fine-grained quiet-word labels.",
        policy=POLICY,
        cases=cases,
        original_source_sha256=original,
        source_sha256={
            name: prior.assets.digest(PROJECT / name) for name in (*SOURCES, ADR)
        },
        prior_D74_exact_inputs=len(original_freeze),
        limits=dict(
            workers=7,
            observations=100,
            asr=0,
            core=0,
            tts=0,
            retries=0,
            worker_wall=180,
            total_wall=900,
            root_bytes=128 * 1024**2,
            headroom_bytes=14 * 1024**3,
            virtual_bytes=3 * 1024**3,
        ),
        before=prior.local_state(),
    )
    publish(root / "execution-freeze.json", freeze)
    LOGGER.info("voice_presence_panel_frozen originals=47 derived_quiet=6")
    return freeze


def load_audio(root, row):
    """Reconstruct only exact immutable normalized PCM capabilities from the prepared finite panel."""
    raw = (Path(root) / "pcm" / (row["id"] + ".s16le")).read_bytes()
    result = NormalizedAudio(pcm_s16le=raw, **row["audio"])
    normalized(result)
    if sha(floats(result)) != row["waveform_sha256"]:
        raise ValueError("presence_pcm_float_binding")
    return result


def validate_events(cases, events, *, reverse):
    """Reconcile genuine complete VAD coverage, exact PCM and recurrence replay before using any decision."""
    if [x.get("event") for x in events].count("ready") != 1 or [
        x.get("event") for x in events
    ].count("complete") != 1:
        raise ValueError("presence_vad_lifecycle")
    ready = next(x for x in events if x["event"] == "ready")
    if ready.get("execution", {}).get("providers") != [
        "CPUExecutionProvider"
    ] or ready.get("logical_CPU_affinity") != [0, 1]:
        raise ValueError("presence_vad_execution")
    observations = [x for x in events if x.get("event") == "observation"]
    expected = [
        (p, row)
        for p, rows in (
            [("forward", cases), ("reverse", list(reversed(cases)))]
            if reverse
            else [("qualification", cases)]
        )
        for row in rows
    ]
    if len(observations) != len(expected):
        raise ValueError("presence_vad_coverage")
    result = {}
    for event, (pass_name, row) in zip(observations, expected, strict=True):
        if (
            event.get("pass_name"),
            event.get("id"),
            event.get("status"),
            event.get("waveform_sha256"),
            event.get("sample_count"),
            event.get("source_samples_modified"),
            event.get("external_recording_resets"),
        ) != (
            pass_name,
            row["id"],
            "ok",
            row["waveform_sha256"],
            row["sample_count"],
            False,
            1,
        ):
            raise ValueError("presence_vad_binding")
        if (
            event["source_samples_modified"] is not False
            or type(event["external_recording_resets"]) is not int
        ):
            raise ValueError("presence_vad_metadata")
        validate_segments(event["segments"], row["sample_count"])
        probabilities = np.asarray(event["window_probabilities"], dtype="<f4")
        if (
            len(probabilities) != (row["sample_count"] + 511) // 512
            or not np.isfinite(probabilities).all()
            or np.any((probabilities < 0) | (probabilities > 1))
            or sha(probabilities.tobytes()) != event["probability_sha256"]
        ):
            raise ValueError("presence_vad_probabilities")
        if pass_name == "reverse":
            if any(
                event[key] != result[row["id"]][key]
                for key in ("segments", "probability_sha256")
            ):
                raise ValueError("presence_vad_replay")
        else:
            result[row["id"]] = event
    LOGGER.info(
        "voice_presence_native_events_verified cases=%d observations=%d",
        len(cases),
        len(observations),
    )
    return result


def run_vad(root, identity, request, *, timeout=180):
    """Own one unchanged offline VAD worker and retain first outputs even after timeout or interruption."""
    directory = Path(root) / identity
    directory.mkdir(mode=0o700)
    publish(directory / "request.json", request)
    headroom = require_headroom()
    command = replace_mount(sandbox(), VAD_ROOT / "samples", Path(root) / "samples")
    publish(
        directory / "launch.json",
        dict(
            description="Original Silero v5 CPU worker, unchanged thresholds and resource caps.",
            command=command,
            preflight=headroom,
        ),
    )
    started = time.monotonic()
    process = subprocess.Popen(
        command,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
        env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"},
    )
    timed_out = False
    interrupted = False
    stdout, stderr = b"", b""
    try:
        stdout, stderr = process.communicate(
            json.dumps(request).encode(), timeout=timeout
        )
    except BaseException as error:
        timed_out = isinstance(error, subprocess.TimeoutExpired)
        interrupted = not timed_out
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
        stdout, stderr = process.communicate(timeout=10)
        if interrupted:
            raise
    finally:
        save_bytes(directory / "stdout.jsonl", stdout)
        save_bytes(directory / "stderr.log", stderr)
        receipt = dict(
            description="Owned VAD process retirement; no retry.",
            pid=process.pid,
            exit_code=process.returncode,
            timed_out=timed_out,
            interrupted=interrupted,
            reaped=process.poll() is not None,
            wall_seconds=time.monotonic() - started,
        )
        publish(directory / "process.json", receipt)
        LOGGER.info(
            "voice_presence_worker_retired worker=%s exit=%s",
            identity,
            process.returncode,
        )
    if (
        process.returncode
        or timed_out
        or len(stdout) > 2 * 1024**2
        or len(stderr) > 8 * 1024**2
    ):
        raise ValueError("presence_vad_worker_failed")
    return [json.loads(line) for line in stdout.splitlines()], receipt


def observed_calls(root):
    """Count actual retained native observations, marking malformed logs unknown instead of inventing planned totals."""
    count = 0
    try:
        for path in Path(root).glob("worker-*/stdout.jsonl"):
            for line in path.read_bytes().splitlines():
                count += json.loads(line).get("event") == "observation"
    except (ValueError, TypeError, AttributeError):
        return None
    LOGGER.info("voice_presence_native_observations_counted observations=%d", count)
    return count


async def replay_pipeline(row, audio, event):
    """Exercise the original pipeline with real VAD evidence and explicitly synthetic downstream sentinels."""
    calls = []
    owner = uuid4()

    async def detect(who, value):
        """Rebind already measured native presence evidence to this exact owner and unchanged PCM."""
        if value is not audio:
            raise ValueError("presence_replay_audio_changed")
        return SpeechPresence(
            who,
            value.source_sha256,
            value.pcm_sha256,
            value.sample_count,
            value.first_pts,
            value.time_base_num,
            value.time_base_den,
            VAD_MODEL,
            tuple((x["start"], x["end"]) for x in event["segments"]),
        )

    async def transcribe(who, value, language):
        """Record exact whole-clip forwarding without making an ASR accuracy or new inference claim."""
        if value is not audio:
            raise ValueError("presence_forwarded_audio_changed")
        calls.append("asr_sentinel")
        return VoiceTranscript(
            who, value.source_sha256, value.pcm_sha256, language, "", "asr-sentinel"
        )

    async def forbidden(**kwargs):
        """Refuse any CORE/TTS dispatch in this VAD-only measurement protocol."""
        raise ValueError("presence_unplanned_model_call")

    adapter = WholeClipASR(
        detector=SimpleNamespace(detect=detect),
        asr=SimpleNamespace(transcribe=transcribe),
        asr_model="asr-sentinel",
    )
    pipeline = VoicePipeline(
        asr=adapter,
        llm=SimpleNamespace(complete=forbidden),
        tts=SimpleNamespace(synthesize=forbidden),
        asr_model="asr-sentinel",
        llm_model="core-sentinel",
        tts_model="tts-sentinel",
    )
    try:
        await pipeline.complete(owner, audio, row["language"], explicit_submission=True)
        raise ValueError("presence_replay_must_end_before_core")
    except VoiceError as error:
        if error.code != "no_speech":
            raise
    finally:
        await pipeline.shutdown()
        await adapter.shutdown()
    expected = ["asr_sentinel"] if event["segments"] else []
    if calls != expected:
        raise ValueError("presence_pipeline_sentinel_coverage")
    LOGGER.info(
        "voice_presence_pipeline_replayed accepted=%s actual_asr_calls=0",
        bool(event["segments"]),
    )
    return dict(
        id=row["id"],
        expected_speech=row["expected_speech"],
        accepted=bool(event["segments"]),
        kind=row["kind"],
        language=row["language"],
        asr_sentinel_calls=len(calls),
        actual_asr_calls=0,
        core_calls=0,
        tts_calls=0,
        full_pcm_preserved=True,
        original_clock_preserved=True,
        detector_seconds=event["wall_seconds"],
    )


def execute(root=ROOT):
    """Run at most seven VAD workers once, preserve failures and audit all original bytes after cleanup."""
    root = Path(root)
    freeze = json.loads((root / "execution-freeze.json").read_text())
    software = json.loads((root / "software-verification.json").read_text())
    for name, expected in freeze["source_sha256"].items():
        if prior.assets.digest(PROJECT / name) != expected:
            raise ValueError("presence_source_freeze_drift")
    if software.get("status") != "PASS" or software.get("source_sha256") != {
        name: freeze["source_sha256"][name] for name in SOURCES
    }:
        raise ValueError("presence_software_gate")
    publish(
        root / "run-start.json",
        dict(
            description="One first VAD-only attempt; finite scope consumed even if it fails.",
            execution_freeze_sha256=prior.assets.digest(root / "execution-freeze.json"),
        ),
    )
    cases = freeze["cases"]
    if len(cases) != 53 or len({x["id"] for x in cases}) != 53:
        raise ValueError("presence_case_count")
    verify_snapshot(freeze["original_source_sha256"])
    verify_provision()
    if prior.local_state() != freeze["before"]:
        raise ValueError("presence_baseline_changed")
    rows = []
    workers = []
    started = time.monotonic()
    failure = None
    try:
        for row in cases:
            audio = load_audio(root, row)
            if (root / "samples" / row["filename"]).read_bytes() != floats(audio):
                raise ValueError("presence_input_changed")
        batches = [cases[:47]] + [[row] for row in cases[47:]]
        for index, batch in enumerate(batches):
            if time.monotonic() - started > 900:
                raise ValueError("presence_wall_limit")
            if (
                sum(p.stat().st_size for p in root.rglob("*") if p.is_file())
                > 128 * 1024**2
            ):
                raise ValueError("presence_disk_limit")
            request = worker_request("predict" if index == 0 else "smoke", batch)
            events, process = run_vad(
                root,
                f"worker-{index}",
                request,
                timeout=min(180, max(0.001, 900 - (time.monotonic() - started))),
            )
            workers.append(process)
            mapped = validate_events(batch, events, reverse=index == 0)
            for row in batch:
                result = asyncio.run(
                    replay_pipeline(row, load_audio(root, row), mapped[row["id"]])
                )
                rows.append(result)
                publish(
                    root / (row["id"] + "-result.json"),
                    dict(
                        description="Native VAD plus synthetic downstream pipeline sentinel; not a native ASR/CORE/TTS turn.",
                        **result,
                    ),
                )
    except BaseException as error:
        failure = type(error).__name__
        raise
    finally:
        after = prior.local_state()
        preserved = False
        try:
            verify_snapshot(freeze["original_source_sha256"])
            preserved = True
        finally:
            publish(
                root / "result.json",
                dict(
                    description="First whole-clip presence observation; original D74 failures remain immutable and no product gate is enabled.",
                    status="OBSERVATIONS_COMPLETE_NOT_PRODUCT_QUALIFIED"
                    if failure is None
                    and len(rows) == 53
                    and preserved
                    and after == freeze["before"]
                    else "FAILED_OR_INCOMPLETE",
                    rows=rows,
                    workers=workers,
                    failure=failure,
                    unattempted=[
                        row["id"]
                        for row in cases
                        if row["id"] not in {x["id"] for x in rows}
                    ],
                    prior_bytes_preserved=preserved,
                    baseline_preserved=after == freeze["before"],
                    after=after,
                    actual_calls=dict(
                        vad_observations=observed_calls(root),
                        asr=0,
                        core=0,
                        tts=0,
                    ),
                    retries=0,
                    wall_seconds=time.monotonic() - started,
                    product_activation=False,
                    physical_latency_measured=False,
                ),
            )
    LOGGER.info(
        "voice_presence_measurement_complete observations=100 rows=53 product_qualified=False"
    )


def main():
    """Prepare or execute one bounded research panel without downloads, model choice or shared-service actions."""
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
