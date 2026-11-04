"""Compare fixed raw and gain-only detector views on regression and disjoint bilingual controls without model changes."""

import argparse
import asyncio
import json
import logging
import time
from dataclasses import asdict, replace
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import numpy as np

from benchmarks.scripts import vi_voice_presence_check as old
from benchmarks.scripts.vi_voice_detector_view import (
    POLICY,
    ViewDetector,
    ViewObservation,
    detector_view,
)
from benchmarks.scripts.vi_voice_presence import WholeClipASR
from src.application.ports.voice import VoiceTranscript
from src.application.ports.audio import NormalizedAudio
from src.application.services.voice_pipeline import VoiceError, VoicePipeline

LOGGER = logging.getLogger(__name__)
PROJECT = old.PROJECT
ROOT = PROJECT / "data/backups/d74-detector-view-storage-corrected-first"
SOURCES = (
    "benchmarks/scripts/vi_voice_detector_view.py",
    "benchmarks/scripts/vi_voice_view_check.py",
    "benchmarks/tests/test_vi_voice_detector_view.py",
    "benchmarks/tests/test_vi_voice_view_check.py",
)
ADR = "docs/ADR/167-detector-only-fixed-gain-comparison.md"


def derived(audio, raw, label):
    """Describe an explicit new authored control without mutating its retained parent PCM."""
    return replace(
        audio,
        source_sha256=old.sha(label.encode() + raw),
        pcm_sha256=old.sha(raw),
        pcm_s16le=raw,
        sample_count=len(raw) // 2,
        source_sample_count=len(raw) // 2,
    )


def prepare(root=ROOT):
    """Freeze two47case groups plus six known quiet controls and both views before native observations."""
    root = Path(root)
    root.mkdir(mode=0o700, exist_ok=False)
    for name in ("samples", "rows"):
        (root / name).mkdir(mode=0o700)
    original = old.previous_snapshot()
    for directory in (old.ROOT, PROJECT / "data/backups/d74-detector-view-first"):
        for path in directory.rglob("*"):
            if path.is_file():
                original[str(path.relative_to(PROJECT))] = old.prior.assets.digest(path)
    for name in (
        "docs/evidence/d74-whole-clip-presence-result.json",
        "docs/ADR/166-whole-clip-presence-with-original-pcm.md",
    ):
        original[name] = old.prior.assets.digest(PROJECT / name)
    prior = json.loads((old.ROOT / "execution-freeze.json").read_text())
    rows = []
    audios = {}

    def add(identity, audio, *, group, kind, language, expected_speech, parent=None):
        """Retain exact original capability metadata while declaring one finite new panel row."""
        audios[identity] = audio
        rows.append(
            dict(
                id=identity,
                group=group,
                kind=kind,
                language=language,
                expected_speech=expected_speech,
                parent=parent,
                sample_count=audio.sample_count,
                waveform_sha256=old.sha(old.floats(audio)),
                audio={k: v for k, v in asdict(audio).items() if k != "pcm_s16le"},
            )
        )

    for index, row in enumerate(prior["cases"]):
        add(
            "reg-" + row["id"],
            old.load_audio(old.ROOT, row),
            group="regression" if index < 47 else "repair",
            kind="padded_repeat" if row["id"].startswith("padded-") else row["kind"],
            language=row["language"],
            expected_speech=row["expected_speech"],
            parent=row["id"],
        )
    corpus_path = PROJECT / "data/backups/d68-asr-evaluation/prepared/corpus.json"
    original[str(corpus_path.relative_to(PROJECT))] = old.prior.assets.digest(
        corpus_path
    )
    corpus = json.loads(corpus_path.read_text())
    d72 = json.loads((old.CORPUS_ROOT / "corpus.json").read_text())["cases"]
    excluded = {
        (x.get("language"), x.get("sentence_id"))
        for x in d72
        if x.get("sentence_id") is not None
    }
    parents = []
    for language in ("vi_vn", "en_us"):
        selected = [
            x
            for x in corpus["cases"]
            if x["kind"] == "independent_public_speech"
            and x["language"] == language
            and (language, x["sentence_id"]) not in excluded
        ][:10]
        if len(selected) != 10:
            raise ValueError("view_disjoint_validation_coverage")
        for index, row in enumerate(selected):
            raw = Path(row["waveform_path"]).read_bytes()
            if old.sha(raw) != row["waveform_sha256"]:
                raise ValueError("view_validation_source_changed")
            original[str(Path(row["waveform_path"]).relative_to(PROJECT))] = old.sha(
                raw
            )
            audio = old.prior.NativeAudioNormalizer().normalize(
                old.prior.pcm_wave(raw, 16000)
            )
            identity = f"validation-{language[:2]}-{index:02d}"
            add(
                identity,
                audio,
                group="validation",
                kind="disjoint_original_speech",
                language=language[:2],
                expected_speech=True,
                parent=row["id"],
            )
            parents.append((identity, audio, language[:2]))
    for identity, audio, language in parents:
        raw = (
            np.rint(
                np.frombuffer(audio.pcm_s16le, dtype="<i2").astype(np.float64) * 0.03
            )
            .astype("<i2")
            .tobytes()
        )
        add(
            identity + "-quiet",
            derived(audio, raw, "gain0.03:"),
            group="validation",
            kind="derived_quiet_recording",
            language=language,
            expected_speech=True,
            parent=identity,
        )
    rng = np.random.default_rng(20261104)
    signals = [
        np.zeros(48000),
        rng.normal(0, 0.02, 48000),
        rng.uniform(-0.05, 0.05, 48000),
        np.full(48000, -0.02),
        np.sin(np.arange(48000) * 2 * np.pi * 880 / 16000) * 0.03,
    ]
    for i, signal in enumerate(signals):
        audio = old.prior.NativeAudioNormalizer().normalize(
            old.prior.pcm_wave(signal.astype("<f4").tobytes(), 16000)
        )
        add(
            f"validation-negative-{i}",
            audio,
            group="validation",
            kind="authored_no_speech",
            language="vi" if i % 2 else "en",
            expected_speech=False,
        )
    for language in ("vi", "en"):
        identity, audio, _ = next(x for x in parents if x[2] == language)
        raw = b"\0\0" * 16000 + audio.pcm_s16le + b"\0\0" * 16000
        add(
            "validation-padded-" + language,
            replace(
                derived(audio, raw, "padded:"),
                first_pts=2500,
                time_base_num=1,
                time_base_den=1000,
            ),
            group="validation",
            kind="padded_repeat",
            language=language,
            expected_speech=True,
            parent=identity,
        )
    if len(rows) != 100 or len({x["id"] for x in rows}) != 100:
        raise ValueError("view_panel_count")
    requests = {}
    for row in rows:
        audio = audios[row["id"]]
        view = detector_view(audio)
        for variant, raw in (("raw", old.floats(audio)), ("boost", view.waveform_f32)):
            identity = variant + "-" + row["id"]
            filename = identity + ".f32"
            if (
                sum(p.stat().st_size for p in root.rglob("*") if p.is_file()) + len(raw)
                > 128 * 1024**2
            ):
                raise ValueError("view_prepared_disk_cap")
            old.save_bytes(root / "samples" / filename, raw)
            requests[identity] = dict(
                id=identity,
                filename=filename,
                sample_count=audio.sample_count,
                waveform_sha256=old.sha(raw),
            )
        row["gain"] = view.gain
        row["view_sha256"] = view.waveform_sha256
    batches = []
    for group in ("regression", "validation", "repair"):
        subset = [x for x in rows if x["group"] == group]
        if len(subset) != (6 if group == "repair" else 47):
            raise ValueError("view_group_count")
        chunks = [[x] for x in subset] if group == "repair" else [subset]
        for chunk in chunks:
            for variant in ("raw", "boost"):
                batch = [requests[variant + "-" + row["id"]] for row in chunk]
                batches.append(dict(variant=variant, group=group, requests=batch))
    if len(batches) != 16:
        raise ValueError("view_worker_budget")
    freeze = dict(
        description="Fixed boost-only peak0.5/maxgain32 study; raw controls, reused regression47/repair6 and20disjoint validation originals with20quiet derivatives/5authored negatives/2padded repeats. No independent human quiet labels.",
        policy=POLICY,
        rows=rows,
        batches=batches,
        source_sha256={
            n: old.prior.assets.digest(PROJECT / n) for n in (*SOURCES, ADR)
        },
        previous_sha256=original,
        before=old.prior.local_state(),
        limits=dict(
            workers=16,
            observations=388,
            retries=0,
            asr=0,
            core=0,
            tts=0,
            wall_seconds=900,
            root_bytes=128 * 1024**2,
        ),
        pass_criteria="All100boost rows must equal fixed expected speech-presence labels; zero negative admissions/false rejections, all provenance/lifecycle/resource gates valid; no product or latency PASS inferred.",
    )
    if sum(p.stat().st_size for p in root.rglob("*") if p.is_file()) > 128 * 1024**2:
        raise ValueError("view_prepared_disk_cap")
    old.publish(root / "execution-freeze.json", freeze)
    LOGGER.info("voice_view_panel_frozen rows=100 workers=16 observations=388")
    return freeze


def load_audio(root, row):
    """Recover exact PCM from its dyadic raw-float representation and verify the original hash without duplicate storage."""
    raw = (Path(root) / "samples" / ("raw-" + row["id"] + ".f32")).read_bytes()
    if len(raw) != row["sample_count"] * 4 or old.sha(raw) != row["waveform_sha256"]:
        raise ValueError("view_original_float_changed")
    scaled = np.frombuffer(raw, dtype="<f4").astype(np.float64) * 32768
    rounded = np.rint(scaled)
    if (
        not np.isfinite(scaled).all()
        or np.any(scaled != rounded)
        or np.any((scaled < -32768) | (scaled > 32767))
    ):
        raise ValueError("view_pcm_not_exactly_representable")
    audio = NormalizedAudio(pcm_s16le=rounded.astype("<i2").tobytes(), **row["audio"])
    old.normalized(audio)
    LOGGER.info(
        "voice_view_original_pcm_recovered samples=%d hash_verified=True",
        audio.sample_count,
    )
    return audio


async def replay(row, audio, event):
    """Exercise native detector-view binding through the original ASR wrapper with an explicit synthetic sentinel."""
    calls = []
    traces = []

    async def observe(view):
        """Return only the native decision already verified against this exact normalized view."""
        if view.waveform_sha256 != event["waveform_sha256"]:
            raise ValueError("view_native_projection_changed")
        return ViewObservation(
            view.waveform_sha256,
            audio.sample_count,
            tuple((x["start"], x["end"]) for x in event["segments"]),
        )

    async def audit(trace):
        """Retain redacted source-to-view provenance before the gate can forward any original audio."""
        traces.append(trace)

    async def transcribe(owner, value, language):
        """Record exact full-audio forwarding without loading an ASR model or claiming recognition accuracy."""
        if value is not audio:
            raise ValueError("view_original_asr_audio_changed")
        calls.append("asr_sentinel")
        return VoiceTranscript(
            owner, value.source_sha256, value.pcm_sha256, language, "", "asr-sentinel"
        )

    adapter = WholeClipASR(
        detector=ViewDetector(SimpleNamespace(observe=observe), audit),
        asr=SimpleNamespace(transcribe=transcribe),
        asr_model="asr-sentinel",
    )
    pipeline = VoicePipeline(
        asr=adapter,
        llm=None,
        tts=None,
        asr_model="asr-sentinel",
        llm_model="core-sentinel",
        tts_model="tts-sentinel",
    )
    try:
        await pipeline.complete(
            uuid4(), audio, row["language"], explicit_submission=True
        )
        raise ValueError("view_unplanned_completion")
    except VoiceError as error:
        if error.code != "no_speech":
            raise
    finally:
        await pipeline.shutdown()
        await adapter.shutdown()
    if len(traces) != 1 or len(calls) != int(bool(event["segments"])):
        raise ValueError("view_sentinel_trace_missing")
    LOGGER.info("voice_view_pipeline_replayed full_pcm_preserved=True")
    return dict(trace=traces[0], asr_sentinel_calls=len(calls))


def execute(root=ROOT):
    """Consume one fixed paired comparison, retaining every first outcome without threshold tuning or retries."""
    root = Path(root)
    freeze = json.loads((root / "execution-freeze.json").read_text())
    software = json.loads((root / "software-verification.json").read_text())
    for n, h in freeze["source_sha256"].items():
        if old.prior.assets.digest(PROJECT / n) != h:
            raise ValueError("view_code_drift")
    if software.get("status") != "PASS" or software.get("source_sha256") != {
        n: freeze["source_sha256"][n] for n in SOURCES
    }:
        raise ValueError("view_software_gate")
    old.verify_snapshot(freeze["previous_sha256"])
    old.verify_provision()
    if old.prior.local_state() != freeze["before"]:
        raise ValueError("view_baseline_drift")
    old.publish(
        root / "run-start.json",
        dict(
            description="One finite paired comparison, consumed before native loading."
        ),
    )
    started = time.monotonic()
    observations = {}
    failure = None
    try:
        for i, batch in enumerate(freeze["batches"]):
            if time.monotonic() - started >= 900:
                raise ValueError("view_wall_cap")
            if (
                sum(p.stat().st_size for p in root.rglob("*") if p.is_file())
                > 128 * 1024**2
            ):
                raise ValueError("view_disk_cap")
            for row in batch["requests"]:
                if (
                    old.prior.assets.digest(root / "samples" / row["filename"])
                    != row["waveform_sha256"]
                ):
                    raise ValueError("view_model_input_changed")
            request = old.worker_request(
                "predict" if len(batch["requests"]) == 47 else "smoke",
                batch["requests"],
            )
            events, _ = old.run_vad(
                root,
                f"worker-{i:02d}",
                request,
                timeout=min(180, 900 - (time.monotonic() - started)),
            )
            observations.update(
                old.validate_events(
                    batch["requests"], events, reverse=len(batch["requests"]) == 47
                )
            )
        result = []
        for row in freeze["rows"]:
            audio = load_audio(root, row)
            view = detector_view(audio)
            if view.waveform_sha256 != row["view_sha256"] or view.gain != row["gain"]:
                raise ValueError("view_plan_changed")
            raw = observations["raw-" + row["id"]]
            boost = observations["boost-" + row["id"]]
            if (
                raw["waveform_sha256"] != old.sha(old.floats(audio))
                or boost["waveform_sha256"] != view.waveform_sha256
            ):
                raise ValueError("view_pair_binding")
            projected = asyncio.run(replay(row, audio, boost))
            outcome = dict(
                id=row["id"],
                group=row["group"],
                kind=row["kind"],
                language=row["language"],
                expected_speech=row["expected_speech"],
                raw_accepted=bool(raw["segments"]),
                boost_accepted=bool(boost["segments"]),
                gain=view.gain,
                **projected,
            )
            result.append(outcome)
            old.publish(
                root / "rows" / (row["id"] + ".json"),
                dict(
                    description="Paired native VAD and explicit synthetic downstream sentinel; original PCM remains unchanged.",
                    **outcome,
                ),
            )
        passed = all(x["boost_accepted"] == x["expected_speech"] for x in result)
        old.publish(
            root / "quality.json",
            dict(
                description="All predeclared100boost rows evaluated without selection or changed labels; local detector gate only.",
                status="LOCAL_DETECTOR_GATES_PASS"
                if passed
                else "LOCAL_DETECTOR_GATES_FAIL",
                rows=result,
                raw_correct=sum(
                    x["raw_accepted"] == x["expected_speech"] for x in result
                ),
                boost_correct=sum(
                    x["boost_accepted"] == x["expected_speech"] for x in result
                ),
                total=len(result),
                actual_neural_asr_core_tts_calls=0,
                product_activation=False,
            ),
        )
    except BaseException as error:
        failure = type(error).__name__
        raise
    finally:
        after = old.prior.local_state()
        old.verify_snapshot(freeze["previous_sha256"])
        old.publish(
            root / "retirement.json",
            dict(
                description="Paired VAD-only campaign retirement, all old evidence retained.",
                failure=failure,
                observations=old.observed_calls(root),
                baseline_preserved=after == freeze["before"],
                after=after,
                wall_seconds=time.monotonic() - started,
                retries=0,
            ),
        )
    LOGGER.info(
        "voice_view_comparison_complete local_gates_pass=%s product_activation=False",
        passed,
    )


def main():
    """Prepare or execute one fixed research scope without downloads, service changes or model adoption."""
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
