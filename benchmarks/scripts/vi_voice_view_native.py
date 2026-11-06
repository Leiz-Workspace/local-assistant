"""Conditionally verify eight real-model voice turns with the qualified detector copy and unchanged reading workflow."""

import argparse
import asyncio
import json
import logging
import os
import signal
import time
from pathlib import Path
from uuid import uuid4

from benchmarks.scripts import vi_voice_peak_check as study
from benchmarks.scripts import vi_workflow_reading_native as reading
from benchmarks.scripts.vi_voice_detector_view import ViewObservation
from benchmarks.scripts.vi_voice_detector_peak import ViewDetector
from benchmarks.scripts.vi_voice_presence import WholeClipASR
from src.application.services.web_fetch_tasks import finish_owned, spawn_owned

LOGGER = logging.getLogger(__name__)
old = study.old
original = old.prior
PROJECT = study.PROJECT
ROOT = PROJECT / "data/backups/d74-detector-view-native-first"
SOURCES = (
    "benchmarks/scripts/vi_voice_view_native.py",
    "benchmarks/tests/test_vi_voice_view_native.py",
)
ADR = "docs/ADR/168-qualified-detector-native-voice-check.md"


class Ledger(original.Ledger):
    """Consume at most four actual ASR/CORE/TTS calls while negative turns must stop before all three."""

    def admit(self, kind, identity):
        """Count before dispatch and never refund or retry a dependency request."""
        if kind not in self.counts or self.counts[kind] >= 4 or identity in self.seen:
            raise ValueError("view_native_budget_or_duplicate")
        super().admit(kind, identity)


def matrix(packet):
    """Declare two original ASR candidates and four fixed original sources before observing any new turn."""
    sources = [x for x in packet["workflow_sources"] if not x["expected_no_answer"]][
        :2
    ] + [x for x in packet["workflow_sources"] if x["expected_no_answer"]]
    if len(sources) != 4:
        raise ValueError("view_native_source_count")
    return [
        dict(
            id=f"view-turn-{i:02d}",
            asr=asr,
            source=row["id"],
            expected_no_answer=row["expected_no_answer"],
            status="UNATTEMPTED",
        )
        for i, (asr, row) in enumerate(
            ((a, r) for a in ("whisper-small-ct2", "qwen3-asr-0.6b") for r in sources)
        )
    ]


class NativeViewBackend:
    """Own a single offline VAD namespace with exact scope/view binding and joined cancellation."""

    def __init__(self, slot, samples, expected, deadline, core_pid):
        """Bind one first detector request before any ASR/TTS workers can load."""
        self.slot, self.samples, self.expected, self.deadline, self.core_pid = (
            slot,
            samples,
            expected,
            deadline,
            core_pid,
        )
        self.used = False
        LOGGER.info("voice_native_view_backend_initialized first_attempt_only=True")

    async def observe(self, view):
        """Run one original Silero smoke request on the verified view, then retire it before ASR admission."""
        if (
            self.used
            or view.waveform_sha256 != self.expected["waveform_sha256"]
            or view.sample_count != self.expected["sample_count"]
        ):
            raise ValueError("view_native_capability_or_view")
        if (
            original.assets.digest(self.samples / self.expected["filename"])
            != view.waveform_sha256
        ):
            raise ValueError("view_native_input_changed")
        self.used = True
        directory = self.slot / "vad"
        directory.mkdir(mode=0o700)
        if any(
            w.process is not None and w.process.returncode is None
            for w in original.WORKERS
        ):
            raise ValueError("view_native_vad_requires_no_asr_tts_worker")
        headroom = old.require_headroom()
        request = old.worker_request("smoke", [self.expected])
        command = old.replace_mount(
            old.sandbox(), old.VAD_ROOT / "samples", self.samples
        )
        old.publish(
            directory / "launch.json",
            dict(
                description="One CPU offline3GiB VAD view before ASR/TTS, original settings.",
                command=command,
                MemAvailable_bytes=headroom["MemAvailable_bytes"],
                actual_address_space_cap_bytes=3 * 1024**3,
                request=request,
            ),
        )
        process = await asyncio.create_subprocess_exec(
            *command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=True,
            env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"},
        )
        old.publish(
            directory / "identity.json",
            dict(description="Exact owned VAD namespace process.", pid=process.pid),
        )
        actor = spawn_owned(process.communicate(json.dumps(request).encode()))
        started = time.monotonic()
        peak = 0
        failure = None
        stdout = stderr = b""
        try:
            while not actor.done():
                await asyncio.wait({actor}, timeout=0.025)
                rss = sum(
                    original.rss_bytes(pid)
                    for pid in original.process_tree(process.pid)
                )
                peak = max(peak, rss)
                core_rss = sum(
                    original.rss_bytes(pid)
                    for pid in original.process_tree(self.core_pid)
                )
                if (
                    time.monotonic() > min(self.deadline, started + 180)
                    or rss + core_rss > 8 * 1024**3
                ):
                    raise ValueError("view_native_vad_resource_or_deadline")
            stdout, stderr = await actor
        except BaseException as error:
            failure = type(error).__name__
            if process.returncode is None:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            stdout, stderr = await finish_owned(actor)
            raise
        finally:
            old.save_bytes(directory / "stdout.jsonl", stdout)
            old.save_bytes(directory / "stderr.log", stderr)
            old.publish(
                directory / "retirement.json",
                dict(
                    description="Joined exact VAD child before admission can retire or ASR can start.",
                    pid=process.pid,
                    exit_code=process.returncode,
                    reaped=process.returncode is not None,
                    failure=failure,
                    wall_seconds=time.monotonic() - started,
                    sampled_peak_RSS_RAM_bytes=peak,
                ),
            )
        if process.returncode or len(stdout) > 2 * 1024**2 or len(stderr) > 8 * 1024**2:
            raise ValueError("view_native_vad_failed")
        events = [json.loads(line) for line in stdout.splitlines()]
        event = old.validate_events([self.expected], events, reverse=False)[
            self.expected["id"]
        ]
        LOGGER.info("voice_native_view_observed source_bound=True")
        return ViewObservation(
            view.waveform_sha256,
            view.sample_count,
            tuple((x["start"], x["end"]) for x in event["segments"]),
        )


async def workflow(root, rows, sources, ledger, deadline, binding, scope_sha, expected):
    """Verify fixed complete positive turns and negative early exits without changing model or voice selection."""
    core_dir = root / "results/core"
    core_dir.mkdir(mode=0o700)
    server = original.OwnedServer("core", core_dir)
    try:
        await server.start()
        for row in rows:
            slot = root / "results" / row["id"]
            slot.mkdir(mode=0o700)

            async def factory(directory, until, pid):
                """Load one original fixed Truc Ly reading worker with a one-request manifest."""
                return await reading.reading_worker(
                    root, directory, until, pid, scope_sha, 1
                )

            service, asr, tts = reading.make_service(
                row["asr"],
                "turbo",
                "fresh",
                None,
                None,
                slot,
                sources[row["source"]],
                ledger,
                deadline,
                server.process.pid,
                factory,
                binding,
            )
            backend = NativeViewBackend(
                slot,
                root / "samples",
                expected[row["source"]],
                deadline,
                server.process.pid,
            )

            async def audit(trace):
                """Retain exact detector-view to original-source provenance before ASR sees audio."""
                old.publish(
                    slot / "detector-view.json",
                    dict(
                        description="Original PCM and detector-only view binding; no transcript or raw audio.",
                        **trace,
                    ),
                )

            gate = WholeClipASR(
                detector=ViewDetector(backend, audit), asr=asr, asr_model=row["asr"]
            )
            service.asr = gate
            row["status"] = "ATTEMPTED"
            try:
                result = await service.complete(
                    uuid4(),
                    sources[row["source"]]["audio"],
                    "vi",
                    explicit_submission=True,
                )
                row.update(
                    status="NEGATIVE_REPLY_FAIL"
                    if row["expected_no_answer"]
                    else "COMPLETE_PCM",
                    stage_seconds=result.stage_seconds,
                    buffered_latency_seconds=result.buffered_latency_seconds,
                    physical_first_audible="UNVERIFIED",
                )
            except asyncio.CancelledError:
                row["status"] = "CANCELLED"
                raise
            except Exception as error:
                row.update(
                    status="CORRECT_NO_SPEECH"
                    if getattr(error, "code", None) == "no_speech"
                    and row["expected_no_answer"]
                    else "FAILED",
                    error_class=type(error).__name__,
                    code=getattr(error, "code", None),
                )
                if (
                    original.FAILURES
                    or any(w.failure for w in (asr.worker, tts.worker) if w is not None)
                    or getattr(error, "code", None) not in ("no_speech",)
                ):
                    raise
            finally:
                await finish_owned(spawn_owned(service.shutdown()))
                await finish_owned(spawn_owned(gate.shutdown()))
                for adapter in (asr, tts):
                    if adapter.worker is not None:
                        await finish_owned(
                            spawn_owned(
                                adapter.worker.close(force=bool(adapter.worker.failure))
                            )
                        )
                old.publish(
                    slot / "result.json",
                    dict(
                        description="First native gated voice turn; no physical latency certification.",
                        **row,
                    ),
                )
            if server.failure or time.monotonic() > deadline:
                raise ValueError("view_native_core_or_wall")
            original.assets.budget(root, limit=8 * 1024**3)
            LOGGER.info(
                "voice_native_gated_turn_finished id=%s status=%s",
                row["id"],
                row["status"],
            )
    finally:
        await finish_owned(spawn_owned(server.stop()))
        old.publish(
            core_dir / "retirement.json",
            dict(
                description="Original owned CORE32K lifecycle retired without shared-service changes.",
                **server.receipt(),
            ),
        )


async def run(root=ROOT):
    """Run this new eight-turn scope only after every fixed detector comparison gate passes."""
    root = Path(root)
    quality = json.loads((study.ROOT / "quality.json").read_text())
    retirement = json.loads((study.ROOT / "retirement.json").read_text())
    if (
        quality.get("status") != "LOCAL_DETECTOR_GATES_PASS"
        or quality.get("boost_correct") != 147
        or quality.get("total") != 147
        or retirement.get("observations") != 288
        or not retirement.get("baseline_preserved")
        or retirement.get("failure") is not None
    ):
        raise ValueError("view_native_qualification_not_passed")
    software = json.loads((root / "software-verification.json").read_text())
    hashes = {
        name: old.prior.assets.digest(PROJECT / name)
        for name in (*SOURCES, *study.SOURCES, *study.first.SOURCES, ADR)
    }
    if software.get("status") != "PASS" or software.get("source_sha256") != hashes:
        raise ValueError("view_native_software_or_source_gate")
    study_freeze = json.loads((study.ROOT / "execution-freeze.json").read_text())
    for name, expected_hash in study_freeze["source_sha256"].items():
        if original.assets.digest(PROJECT / name) != expected_hash:
            raise ValueError("view_native_qualification_code_changed")
    old.verify_snapshot(study_freeze["previous_sha256"])
    binding, _ = reading.verify_previous()
    original.verify_originals()
    original.verify_models()
    original.verify_runtime_snapshot()
    old.verify_provision()
    before = original.local_state()
    if before["native_pids"]:
        raise ValueError("view_native_preexisting_core")
    packet = json.loads(original.assets.PACKET.read_text())
    sources = original.retained_sources(original.ROOT, packet)
    rows = matrix(packet)
    for name in ("results", "manifests", "samples"):
        (root / name).mkdir(mode=0o700)
    expected = {}
    for source in {x["source"] for x in rows}:
        view = study.peak.detector_view(sources[source]["audio"])
        filename = source + ".f32"
        old.save_bytes(root / "samples" / filename, view.waveform_f32)
        expected[source] = dict(
            id=source,
            filename=filename,
            sample_count=view.sample_count,
            waveform_sha256=view.waveform_sha256,
        )
    ledger = Ledger(root)
    original.FAILURES.clear()
    freeze = dict(
        description="New eight-turn native scope after exact detector qualification; previous48turn failures untouched.",
        source_sha256=hashes,
        quality_sha256=original.assets.digest(study.ROOT / "quality.json"),
        retirement_sha256=original.assets.digest(study.ROOT / "retirement.json"),
        rows=rows,
        expected=expected,
        before=before,
        limits=dict(turns=8, vad=8, asr=4, core=4, tts=4, retries=0, wall_seconds=900),
        scope_adr=ADR,
    )
    old.publish(root / "execution-freeze.json", freeze)
    started = time.monotonic()
    failure = None
    try:
        await workflow(
            root,
            rows,
            sources,
            ledger,
            started + 900,
            binding,
            original.assets.digest(root / "execution-freeze.json"),
            expected,
        )
    except BaseException as error:
        failure = type(error).__name__
        raise
    finally:
        after = original.local_state()
        status = (
            "LOCAL_NATIVE_NO_SPEECH_GATE_PASS"
            if failure is None
            and all(
                x["status"]
                == ("CORRECT_NO_SPEECH" if x["expected_no_answer"] else "COMPLETE_PCM")
                for x in rows
            )
            and ledger.counts == dict(asr=4, core=4, tts=4)
            and before == after
            else "FAILED_OR_INCOMPLETE"
        )
        old.publish(
            root / "result.json",
            dict(
                description="Actual8turn native qualification, not product/latency/semantic/quietASR acceptance.",
                status=status,
                rows=rows,
                calls=ledger.counts,
                failure=failure,
                guard_failures=original.FAILURES,
                after=after,
                baseline_preserved=before == after,
                wall_seconds=time.monotonic() - started,
                product_activation=False,
                physical_first_audible="UNVERIFIED",
            ),
        )
        original.verify_originals()
    LOGGER.info("voice_native_presence_check_complete status=%s", status)


def main():
    """Dispatch only the source-tested finite native check after local detector qualification succeeds."""
    logging.basicConfig(level=logging.INFO)
    argparse.ArgumentParser(description=__doc__).parse_args()
    asyncio.run(run())


if __name__ == "__main__":
    main()
