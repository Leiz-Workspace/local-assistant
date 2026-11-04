"""Qualify fixed detector peak normalization on retained failures plus a separately frozen fresh bilingual control group."""

import argparse
import asyncio
import json
import logging
import time
from dataclasses import asdict
from pathlib import Path

import numpy as np

from benchmarks.scripts import vi_voice_view_check as first
from benchmarks.scripts import vi_voice_detector_peak as peak

LOGGER = logging.getLogger(__name__)
old = first.old
PROJECT = first.PROJECT
ROOT = PROJECT / "data/backups/d74-detector-peak-v2-first"
SOURCES = (
    "benchmarks/scripts/vi_voice_detector_peak.py",
    "benchmarks/scripts/vi_voice_peak_check.py",
    "benchmarks/tests/test_vi_voice_detector_peak.py",
    "benchmarks/tests/test_vi_voice_peak_check.py",
)
ADR = "docs/ADR/169-fixed-detector-peak-normalization-and-fresh-controls.md"


def load_audio(root, row):
    """Read exact original PCM from either the immutable first study or this new fixed control group."""
    return first.load_audio(first.ROOT if row["origin"] == "gain32" else root, row)


def prepare(root=ROOT):
    """Freeze147rows, including20previously unused source utterances and their quiet derivatives, before native loading."""
    root = Path(root)
    root.mkdir(mode=0o700, exist_ok=False)
    for name in ("samples", "rows"):
        (root / name).mkdir(mode=0o700)
    original = old.previous_snapshot()
    for directory in (
        old.ROOT,
        first.ROOT,
        PROJECT / "data/backups/d74-detector-view-first",
    ):
        for path in directory.rglob("*"):
            if path.is_file():
                original[str(path.relative_to(PROJECT))] = old.prior.assets.digest(path)
    previous = json.loads((first.ROOT / "execution-freeze.json").read_text())
    original.update(previous["source_sha256"])
    rows = [dict(x, origin="gain32") for x in previous["rows"]]
    audios = {x["id"]: first.load_audio(first.ROOT, x) for x in rows}
    corpus_path = PROJECT / "data/backups/d68-asr-evaluation/prepared/corpus.json"
    original[str(corpus_path.relative_to(PROJECT))] = old.prior.assets.digest(
        corpus_path
    )
    corpus = json.loads(corpus_path.read_text())["cases"]
    used = {x["parent"] for x in rows if x["kind"] == "disjoint_original_speech"}
    d72 = json.loads((old.CORPUS_ROOT / "corpus.json").read_text())["cases"]
    excluded = {
        (x.get("language"), x.get("sentence_id"))
        for x in d72
        if x.get("sentence_id") is not None
    }
    parents = []

    def add(identity, audio, kind, language, expected=True, parent=None):
        """Declare one fixed fresh-case capability without any model feedback or reference-text input."""
        rows.append(
            dict(
                id=identity,
                origin="fresh",
                group="fresh",
                kind=kind,
                language=language,
                expected_speech=expected,
                parent=parent,
                sample_count=audio.sample_count,
                waveform_sha256=old.sha(old.floats(audio)),
                audio={k: v for k, v in asdict(audio).items() if k != "pcm_s16le"},
            )
        )
        audios[identity] = audio

    for lang in ("vi_vn", "en_us"):
        selected = [
            x
            for x in corpus
            if x["kind"] == "independent_public_speech"
            and x["language"] == lang
            and x["id"] not in used
            and (lang, x["sentence_id"]) not in excluded
        ][:10]
        if len(selected) != 10:
            raise ValueError("peak_fresh_source_coverage")
        for i, x in enumerate(selected):
            raw = Path(x["waveform_path"]).read_bytes()
            if old.sha(raw) != x["waveform_sha256"]:
                raise ValueError("peak_source_changed")
            original[str(Path(x["waveform_path"]).relative_to(PROJECT))] = old.sha(raw)
            audio = old.prior.NativeAudioNormalizer().normalize(
                old.prior.pcm_wave(raw, 16000)
            )
            identity = f"fresh-{lang[:2]}-{i:02d}"
            add(identity, audio, "fresh_original_speech", lang[:2], parent=x["id"])
            parents.append((identity, audio, lang[:2]))
    for identity, audio, lang in parents:
        raw = (
            np.rint(
                np.frombuffer(audio.pcm_s16le, dtype="<i2").astype(np.float64) * 0.03
            )
            .astype("<i2")
            .tobytes()
        )
        add(
            identity + "-quiet",
            first.derived(audio, raw, "fresh-gain0.03:"),
            "derived_quiet_recording",
            lang,
            parent=identity,
        )
    rng = np.random.default_rng(20261105)
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
            f"fresh-negative-{i}",
            audio,
            "authored_no_speech",
            "vi" if i % 2 else "en",
            expected=False,
        )
    for lang in ("vi", "en"):
        identity, audio, _ = next(x for x in parents if x[2] == lang)
        raw = b"\0\0" * 16000 + audio.pcm_s16le + b"\0\0" * 16000
        add(
            "fresh-padded-" + lang,
            first.derived(audio, raw, "fresh-padded:"),
            "padded_repeat",
            lang,
            parent=identity,
        )
    if len(rows) != 147 or len({x["id"] for x in rows}) != 147:
        raise ValueError("peak_panel_coverage")
    requests = {}
    for row in rows:
        audio = audios[row["id"]]
        if row["origin"] == "fresh":
            old.save_bytes(
                root / "samples" / ("raw-" + row["id"] + ".f32"), old.floats(audio)
            )
        view = peak.detector_view(audio)
        request = dict(
            id="peak-" + row["id"],
            filename="peak-" + row["id"] + ".f32",
            sample_count=audio.sample_count,
            waveform_sha256=view.waveform_sha256,
        )
        if (
            sum(p.stat().st_size for p in root.rglob("*") if p.is_file())
            + len(view.waveform_f32)
            > 128 * 1024**2
        ):
            raise ValueError("peak_disk_cap")
        old.save_bytes(root / "samples" / request["filename"], view.waveform_f32)
        row["gain"] = view.gain
        row["view_sha256"] = view.waveform_sha256
        requests[row["id"]] = request
    batches = []
    for group in ("regression", "validation", "fresh", "repair"):
        subset = [x for x in rows if x["group"] == group]
        if len(subset) != (6 if group == "repair" else 47):
            raise ValueError("peak_group_coverage")
        for chunk in [[x] for x in subset] if group == "repair" else [subset]:
            batches.append([requests[x["id"]] for x in chunk])
    old.publish(
        root / "execution-freeze.json",
        dict(
            description="Second fixed candidate, peak0.5 detector-only normalization with mathematical PCM gain bound16384. Prior99of100FAIL retained; fresh group selected before outcomes.",
            policy=peak.POLICY,
            rows=rows,
            batches=batches,
            source_sha256={
                n: old.prior.assets.digest(PROJECT / n) for n in (*SOURCES, ADR)
            },
            previous_sha256=original,
            before=old.prior.local_state(),
            limits=dict(
                workers=9,
                observations=288,
                retries=0,
                asr=0,
                core=0,
                tts=0,
                wall_seconds=900,
                root_bytes=128 * 1024**2,
            ),
            pass_criteria="All147fixed coarse presence labels correct,132speech admitted/15negative rows refused; all source/lifecycle/guard gates. Includes derivative/repeated sources, not147independent recordings.",
        ),
    )
    LOGGER.info("voice_peak_scope_frozen rows=147 workers=9 observations=288")


async def replay(row, audio, event):
    """Reuse the already tested original gate projection while selecting only the fixed v2 detector adapter."""
    from types import SimpleNamespace
    from uuid import uuid4
    from benchmarks.scripts.vi_voice_detector_view import ViewObservation
    from benchmarks.scripts.vi_voice_presence import WholeClipASR
    from src.application.ports.voice import VoiceTranscript
    from src.application.services.voice_pipeline import VoiceError, VoicePipeline

    traces = []
    calls = []

    async def observe(view):
        """Bind one measured native result to the exact fixed-peak copy before projecting source identity."""
        if view.waveform_sha256 != event["waveform_sha256"]:
            raise ValueError("peak_native_binding")
        return ViewObservation(
            view.waveform_sha256,
            audio.sample_count,
            tuple((x["start"], x["end"]) for x in event["segments"]),
        )

    async def audit(trace):
        """Retain redacted source/view/clock metadata before any original audio forwarding."""
        traces.append(trace)

    async def transcribe(owner, value, language):
        """Count only an explicit sentinel while verifying identical original audio identity."""
        if value is not audio:
            raise ValueError("peak_original_pcm_changed")
        calls.append(True)
        return VoiceTranscript(
            owner, value.source_sha256, value.pcm_sha256, language, "", "asr-sentinel"
        )

    gate = WholeClipASR(
        detector=peak.ViewDetector(SimpleNamespace(observe=observe), audit),
        asr=SimpleNamespace(transcribe=transcribe),
        asr_model="asr-sentinel",
    )
    pipeline = VoicePipeline(
        asr=gate,
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
        raise ValueError("peak_unplanned_completion")
    except VoiceError as error:
        if error.code != "no_speech":
            raise
    finally:
        await pipeline.shutdown()
        await gate.shutdown()
    if len(traces) != 1 or len(calls) != int(bool(event["segments"])):
        raise ValueError("peak_sentinel_or_audit")
    LOGGER.info("voice_peak_pipeline_replayed original_pcm_preserved=True")
    return dict(trace=traces[0], asr_sentinel_calls=len(calls))


def execute(root=ROOT):
    """Run the nine preregistered workers once and retain all first failures without a third normalization choice."""
    root = Path(root)
    f = json.loads((root / "execution-freeze.json").read_text())
    software = json.loads((root / "software-verification.json").read_text())
    if software.get("status") != "PASS" or software.get("source_sha256") != {
        n: f["source_sha256"][n] for n in SOURCES
    }:
        raise ValueError("peak_software_gate")
    for n, h in f["source_sha256"].items():
        if old.prior.assets.digest(PROJECT / n) != h:
            raise ValueError("peak_source_drift")
    old.verify_snapshot(f["previous_sha256"])
    old.verify_provision()
    if old.prior.local_state() != f["before"]:
        raise ValueError("peak_baseline_changed")
    old.publish(
        root / "run-start.json",
        dict(description="One fixed peak-v2 scope, consumed even if it fails."),
    )
    started = time.monotonic()
    failure = None
    observations = {}
    try:
        for i, batch in enumerate(f["batches"]):
            if (
                time.monotonic() - started >= 900
                or sum(p.stat().st_size for p in root.rglob("*") if p.is_file())
                > 128 * 1024**2
            ):
                raise ValueError("peak_resource_cap")
            for x in batch:
                if (
                    old.prior.assets.digest(root / "samples" / x["filename"])
                    != x["waveform_sha256"]
                ):
                    raise ValueError("peak_input_drift")
            request = old.worker_request(
                "predict" if len(batch) == 47 else "smoke", batch
            )
            events, _ = old.run_vad(
                root,
                f"worker-{i:02d}",
                request,
                timeout=min(180, 900 - (time.monotonic() - started)),
            )
            observations.update(
                old.validate_events(batch, events, reverse=len(batch) == 47)
            )
        rows = []
        for x in f["rows"]:
            audio = load_audio(root, x)
            view = peak.detector_view(audio)
            event = observations["peak-" + x["id"]]
            if (
                view.waveform_sha256 != x["view_sha256"]
                or event["waveform_sha256"] != view.waveform_sha256
            ):
                raise ValueError("peak_projection_drift")
            outcome = dict(
                id=x["id"],
                group=x["group"],
                kind=x["kind"],
                language=x["language"],
                expected_speech=x["expected_speech"],
                boost_accepted=bool(event["segments"]),
                gain=view.gain,
                **asyncio.run(replay(x, audio, event)),
            )
            rows.append(outcome)
            old.publish(
                root / "rows" / (x["id"] + ".json"),
                dict(
                    description="Native v2 detector result and explicit downstream sentinel; not neural ASR/CORE/TTS.",
                    **outcome,
                ),
            )
        correct = sum(x["boost_accepted"] == x["expected_speech"] for x in rows)
        old.publish(
            root / "quality.json",
            dict(
                description="Fixed147case v2qualification, including20fresh source utterances and inherited quiet labels.",
                status="LOCAL_DETECTOR_GATES_PASS"
                if correct == 147
                else "LOCAL_DETECTOR_GATES_FAIL",
                boost_correct=correct,
                total=147,
                rows=rows,
                actual_neural_asr_core_tts_calls=0,
                product_activation=False,
            ),
        )
    except BaseException as error:
        failure = type(error).__name__
        raise
    finally:
        after = old.prior.local_state()
        old.verify_snapshot(f["previous_sha256"])
        old.publish(
            root / "retirement.json",
            dict(
                description="Joined v2native observation scope; prior99of100FAIL unchanged.",
                failure=failure,
                observations=old.observed_calls(root),
                after=after,
                baseline_preserved=after == f["before"],
                wall_seconds=time.monotonic() - started,
                retries=0,
            ),
        )
    LOGGER.info("voice_peak_comparison_complete correct=%d total=147", correct)


def main():
    """Prepare or execute the separately fixed v2research scope with no model or service changes."""
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
