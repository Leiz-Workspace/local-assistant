"""Measure fixed resident CPU voice profiles with the qualified detector, original decoding and complete auditable outputs."""

import argparse
import asyncio
import itertools
import json
import logging
import math
import os
import time
from pathlib import Path
from uuid import uuid4

from benchmarks.scripts import vi_voice_view_native as previous
from benchmarks.scripts import vi_workflow_reading_native as reading
from benchmarks.scripts.vi_voice_detector_peak import ViewDetector, detector_view
from benchmarks.scripts.vi_voice_detector_view import ViewObservation
from benchmarks.scripts.vi_voice_presence import WholeClipASR
from benchmarks.scripts.vi_voice_resident_worker import ROLE_MODELS, ROLE_POLICIES
from src.application.services.web_fetch_tasks import finish_owned, spawn_owned

LOGGER = logging.getLogger(__name__)
old = previous.old
original = previous.original
PROJECT = previous.PROJECT
ROOT = PROJECT / "data/backups/d74-resident-cpu-first"
WORKER = "benchmarks/scripts/vi_voice_resident_worker.py"
SOURCES = (
    WORKER,
    "benchmarks/scripts/vi_voice_resident_check.py",
    "benchmarks/tests/test_vi_voice_resident_worker.py",
    "benchmarks/tests/test_vi_voice_resident_check.py",
)
ADR = "docs/ADR/170-resident-voice-cpu-latency-comparison.md"


def latency_gates(rows):
    """Evaluate the declared maximum on every complete speech case, never averages or fast negative refusals."""
    result = []
    for asr, threads in itertools.product(
        ("whisper-small-ct2", "qwen3-asr-0.6b"), (2, 4, 8)
    ):
        group = [x for x in rows if x["asr"] == asr and x["threads"] == threads]
        speech = [x for x in group if not x["expected_no_answer"]]
        negatives = [x for x in group if x["expected_no_answer"]]
        times = [x.get("buffered_latency_seconds") for x in speech]
        valid = (
            len(group) == 6
            and len(speech) == 4
            and len(negatives) == 2
            and all(x["status"] == "COMPLETE_PCM" for x in speech)
            and all(x["status"] == "CORRECT_NO_SPEECH" for x in negatives)
            and all(
                type(x) in (float, int) and math.isfinite(x) and x > 0 for x in times
            )
        )
        result.append(
            dict(
                asr=asr,
                threads=threads,
                speech_cases=len(speech),
                negative_cases=len(negatives),
                complete_coverage=valid,
                maximum_complete_pcm_seconds=max(times) if valid else None,
                compute_proxy_within4=valid and max(times) <= 4,
                physical_first_audible="UNVERIFIED",
                quality_parity="SEPARATE_AUDIT",
            )
        )
    LOGGER.info("resident_latency_gates_evaluated model_selection=False")
    return result


def matrix(packet):
    """Freeze all36slots before inference, lower-memory ASR first with2/4/8CPUprofiles and all six sources."""
    rows = [
        dict(
            id=f"resident-turn-{i:02d}",
            asr=asr,
            threads=threads,
            source=source["id"],
            expected_no_answer=source["expected_no_answer"],
            status="UNATTEMPTED",
        )
        for i, (asr, threads, source) in enumerate(
            itertools.product(
                ("whisper-small-ct2", "qwen3-asr-0.6b"),
                (2, 4, 8),
                packet["workflow_sources"],
            )
        )
    ]
    if len(rows) != 36 or sum(x["expected_no_answer"] for x in rows) != 12:
        raise ValueError("resident_matrix")
    return rows


def command(role, output, manifest, manifest_sha, threads, samples):
    """Bind fixed original models/runtimes and only the requested CPU profile inside owned offline namespaces."""
    if threads not in (2, 4, 8) or (role == "vad" and threads != 2):
        raise ValueError("resident_command_threads")
    if role == "turbo":
        args = reading.prepared.command(output, manifest, manifest_sha)
    elif role == "vad":
        args = old.replace_mount(old.sandbox(), old.VAD_ROOT / "samples", samples)
        args = ["/usr/bin/taskset", "--cpu-list", "0,1"] + args
    else:
        args = original.namespace(role, output)
    args = list(args)
    index = args.index("--cpu-list") + 1
    args[index] = ",".join(str(x) for x in range(threads))
    for index, value in enumerate(args):
        if (
            value
            in (
                "OMP_NUM_THREADS",
                "MKL_NUM_THREADS",
                "OPENBLAS_NUM_THREADS",
                "NUMBA_NUM_THREADS",
                "RAYON_NUM_THREADS",
            )
            and index
            and args[index - 1] == "--setenv"
        ):
            args[index + 1] = str(threads)
        if (
            role == "vad"
            and value == "PYTHONPATH"
            and index
            and args[index - 1] == "--setenv"
        ):
            args[index + 1] = "/app:/official"
    mounts = []
    for name in (
        WORKER,
        "benchmarks/scripts/vi_voice_worker.py",
        "scripts/vad_evaluation_worker.py",
    ):
        mounts += ["--ro-bind", str(PROJECT / name), "/app/" + name]
    if role != "turbo":
        mounts += ["--ro-bind", str(manifest), "/approved-workflow.json"]
    index = args.index("--remount-ro")
    args[index:index] = mounts
    index = args.index("/venv/bin/python")
    return args[:index] + ["/venv/bin/python", "/app/" + WORKER, manifest_sha]


class Worker(original.Worker):
    """Reuse original aggregate/log/deadline guards while starting one declared resident CPU-stage capability."""

    def __init__(
        self,
        role,
        directory,
        deadline,
        core_pid,
        scope_path,
        threads,
        samples,
        *,
        root=ROOT,
    ):
        """Bind fixed identity, CPU allocation and immutable per-worker scope before any process exists."""
        super().__init__(role, directory, deadline, root=Path(root), core_pid=core_pid)
        self.scope_path, self.threads, self.samples_path = scope_path, threads, samples
        self.scope_sha = original.assets.digest(scope_path)

    async def start(self):
        """Load one resident stage after unchanged host-memory preflight and verify actual readiness/settings."""
        if (
            self.process is not None
            or original.mem_available() < 14 * original.GIB
            or not set(range(self.threads)) <= os.sched_getaffinity(0)
        ):
            raise ValueError("resident_worker_preflight")
        self.directory.mkdir(mode=0o700)
        output = self.directory / "native"
        output.mkdir(mode=0o700)
        self.started = time.monotonic()
        self.log = (self.directory / "stderr.log").open("xb")
        try:
            args = command(
                self.candidate,
                output,
                self.scope_path,
                self.scope_sha,
                self.threads,
                self.samples_path,
            )
            old.publish(
                self.directory / "launch.json",
                dict(
                    description="Resident original CPU-stage launch with explicit allocation; original memory caps.",
                    command=args,
                    MemAvailable_bytes=original.mem_available(),
                    cpu_threads=self.threads,
                ),
            )
            self.process = await asyncio.create_subprocess_exec(
                *args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=self.log,
                start_new_session=True,
                limit=65537,
                env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"},
            )
            original.WORKERS.add(self)
            old.publish(
                self.directory / "process-identity.json",
                dict(
                    description="Exact owned resident stage identity.",
                    pid=self.process.pid,
                ),
            )
            self.ready = await self.receive()
            execution = self.ready.get("execution", {})
            if (
                self.ready.get("event") != "ready"
                or self.ready.get("candidate") != self.candidate
                or self.ready.get("manifest_sha256") != self.scope_sha
                or execution.get("cpu_threads") != self.threads
                or execution.get("logical_CPU_affinity") != list(range(self.threads))
            ):
                raise ValueError("resident_ready_binding")
            if self.candidate == "turbo" and (
                self.ready.get("profile") != "workflow-reading"
                or self.ready.get("voice") != "Trúc Ly"
            ):
                raise ValueError("resident_voice_binding")
        except BaseException as error:
            self.failure = type(error).__name__ + ":" + str(error)
            original.FAILURES.append(self.failure)
            if self.process is not None:
                await finish_owned(spawn_owned(self.close(force=True)))
            else:
                self.log.close()
            raise
        LOGGER.info(
            "resident_worker_ready role=%s threads=%d", self.candidate, self.threads
        )
        return self

    async def detect(self, message):
        """Admit one source-bound VAD operation without pretending it is an ASR or synthesis request."""
        if (
            self.candidate != "vad"
            or self.busy
            or self.process is None
            or self.process.returncode is not None
        ):
            raise ValueError("resident_vad_busy_or_closed")
        self.busy = True
        try:
            old.publish(
                self.directory / (message["id"] + "-request.json"),
                dict(
                    description="One first detector-copy request, without source labels.",
                    **message,
                ),
            )
            self.process.stdin.write(json.dumps(message).encode() + b"\n")
            await self.process.stdin.drain()
            result = await self.receive()
            if (result.get("event"), result.get("id"), result.get("operation")) != (
                "result",
                message["id"],
                "detect",
            ):
                raise ValueError("resident_vad_result")
            return result["vad"]
        except BaseException as error:
            self.failure = type(error).__name__ + ":" + str(error)
            original.FAILURES.append(self.failure)
            await finish_owned(spawn_owned(self.close(force=True)))
            raise
        finally:
            self.busy = False


class Backend:
    """Bind resident VAD results to exact prepared peak views without changing original ASR audio."""

    def __init__(self, worker, row, expected):
        """Create a one-call capability for this turn and fixed reference-free input."""
        self.worker, self.row, self.expected = worker, row, expected
        self.used = False

    async def observe(self, view):
        """Verify native full-source segmentation before allowing the existing peak adapter to rebind original identity."""
        if (
            self.used
            or view.waveform_sha256 != self.expected["waveform_sha256"]
            or view.sample_count != self.expected["sample_count"]
        ):
            raise ValueError("resident_detector_view_binding")
        self.used = True
        result = await self.worker.detect(
            dict(op="detect", id=self.row["id"] + "-vad", **self.expected)
        )
        if (
            result["waveform_sha256"] != view.waveform_sha256
            or result["sample_count"] != view.sample_count
            or result["source_samples_modified"] is not False
            or result["external_recording_resets"] != 1
        ):
            raise ValueError("resident_detector_native_binding")
        old.validate_segments(result["segments"], view.sample_count)
        LOGGER.info("resident_detector_verified full_source=True")
        return ViewObservation(
            view.waveform_sha256,
            view.sample_count,
            tuple((x["start"], x["end"]) for x in result["segments"]),
        )


class Ledger(original.Ledger):
    """Limit this fixed36turn cohort to24first downstream requests per model stage."""

    def admit(self, kind, identity):
        """Consume one attempt before dispatch with no retry or budget refund."""
        if kind not in self.counts or identity in self.seen or self.counts[kind] >= 24:
            raise ValueError("resident_call_budget")
        super().admit(kind, identity)


async def workflow(root, rows, sources, ledger, deadline, binding, scope_sha, expected):
    """Run all frozen groups with explicit readiness and joined per-group retirement; preserve first failures."""
    core_dir = root / "results/core"
    core_dir.mkdir(mode=0o700)
    server = original.OwnedServer("core", core_dir)
    try:
        await server.start()
        for (asr, threads), group in itertools.groupby(
            rows, key=lambda x: (x["asr"], x["threads"])
        ):
            group_dir = root / "results" / f"{asr}-cpu{threads}"
            group_dir.mkdir(mode=0o700)
            workers = []
            try:
                setup = time.monotonic()
                for role in ("vad", asr, "turbo"):
                    actual_threads = 2 if role == "vad" else threads
                    scope = root / "manifests" / f"{asr}-{threads}-{role}.json"
                    old.publish(
                        scope,
                        dict(
                            description="One fixed resident group capability, no product model selection.",
                            native_authorized=True,
                            role=role,
                            cpu_threads=actual_threads,
                            max_requests=6 if role == "vad" else 4,
                            scope_sha256=scope_sha,
                            policy=ROLE_POLICIES[role],
                            model=ROLE_MODELS[role],
                            voice=reading.VOICE if role == "turbo" else None,
                        ),
                    )
                    workers.append(
                        await Worker(
                            role,
                            group_dir / role,
                            deadline,
                            server.process.pid,
                            scope,
                            actual_threads,
                            root / "samples",
                            root=root,
                        ).start()
                    )
                vad, asr_worker, tts_worker = workers
                old.publish(
                    group_dir / "ready.json",
                    dict(
                        description="All three models ready before submission; no operator warmup requests or cached answers.",
                        setup_seconds=time.monotonic() - setup,
                        workers=[w.ready for w in workers],
                    ),
                )
                for row in group:
                    slot = root / "results" / row["id"]
                    slot.mkdir(mode=0o700)
                    service, asr_adapter, tts_adapter = reading.make_service(
                        asr,
                        "turbo",
                        "resident",
                        asr_worker,
                        tts_worker,
                        slot,
                        sources[row["source"]],
                        ledger,
                        deadline,
                        server.process.pid,
                        None,
                        binding,
                    )

                    async def audit(trace):
                        """Publish detector-copy provenance before the original complete audio can reach ASR."""
                        old.publish(
                            slot / "detector-view.json",
                            dict(
                                description="Qualified peak-copy to original PCM binding.",
                                **trace,
                            ),
                        )

                    gate = WholeClipASR(
                        detector=ViewDetector(
                            Backend(vad, row, expected[row["source"]]), audit
                        ),
                        asr=asr_adapter,
                        asr_model=asr,
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
                            status="NEGATIVE_HALLUCINATION"
                            if row["expected_no_answer"]
                            else "COMPLETE_PCM",
                            buffered_latency_seconds=result.buffered_latency_seconds,
                            stage_seconds=result.stage_seconds,
                            complete_pcm_within4=result.buffered_latency_seconds <= 4,
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
                            code=getattr(error, "code", None),
                            error_class=type(error).__name__,
                        )
                        if (
                            original.FAILURES
                            or any(w.failure for w in workers)
                            or getattr(error, "code", None) not in ("no_speech",)
                        ):
                            raise
                    finally:
                        await finish_owned(spawn_owned(service.shutdown()))
                        await finish_owned(spawn_owned(gate.shutdown()))
                        old.publish(
                            slot / "result.json",
                            dict(
                                description="First resident native observation; complete PCM is not speaker audibility.",
                                **row,
                            ),
                        )
                    if server.failure or time.monotonic() > deadline:
                        raise ValueError("resident_core_or_wall")
                    original.assets.budget(root, limit=8 * 1024**3)
                    LOGGER.info(
                        "resident_turn_finished id=%s status=%s",
                        row["id"],
                        row["status"],
                    )
            finally:
                for worker in reversed(workers):
                    await finish_owned(
                        spawn_owned(worker.close(force=bool(worker.failure)))
                    )
    finally:
        await finish_owned(spawn_owned(server.stop()))
        old.publish(
            core_dir / "retirement.json",
            dict(
                description="Joined original owned CORE after resident trial.",
                **server.receipt(),
            ),
        )


async def run(root=ROOT):
    """Freeze and execute exactly one source-tested resident comparison with original model/evidence preservation."""
    root = Path(root)
    previous_result = json.loads((previous.ROOT / "result.json").read_text())
    if previous_result["status"] != "LOCAL_NATIVE_NO_SPEECH_GATE_PASS":
        raise ValueError("resident_previous_gate")
    software = json.loads((root / "software-verification.json").read_text())
    hashes = {n: original.assets.digest(PROJECT / n) for n in (*SOURCES, ADR)}
    if software.get("status") != "PASS" or software.get("source_sha256") != {
        n: hashes[n] for n in SOURCES
    }:
        raise ValueError("resident_software_gate")
    preserved = old.previous_snapshot()
    for path in previous.ROOT.rglob("*"):
        if path.is_file():
            preserved[str(path.relative_to(PROJECT))] = original.assets.digest(path)
    binding, _ = reading.verify_previous()
    original.verify_originals()
    original.verify_models()
    original.verify_runtime_snapshot()
    old.verify_provision()
    checkpoint_receipt = json.loads(
        (previous.ROOT / "asr-checkpoint-post-run.json").read_text()
    )
    checkpoints = checkpoint_receipt["sha256"]
    if len(checkpoints) != 14:
        raise ValueError("resident_checkpoint_coverage")
    for name, expected_hash in checkpoints.items():
        if original.assets.digest(PROJECT / name) != expected_hash:
            raise ValueError("resident_checkpoint_drift")
    before = original.local_state()
    if before["native_pids"]:
        raise ValueError("resident_existing_core")
    if not set(range(8)) <= os.sched_getaffinity(0):
        raise ValueError("resident_cpu_availability")
    cores = [
        Path(f"/sys/devices/system/cpu/cpu{i}/topology/core_id").read_text().strip()
        for i in range(8)
    ]
    if len(set(cores)) != 8:
        raise ValueError("resident_physical_core_topology")
    packet = json.loads(original.assets.PACKET.read_text())
    rows = matrix(packet)
    sources = original.retained_sources(original.ROOT, packet)
    for name in ("results", "manifests", "samples"):
        (root / name).mkdir(mode=0o700)
    expected = {}
    for source, value in sources.items():
        view = detector_view(value["audio"])
        filename = source + ".f32"
        old.save_bytes(root / "samples" / filename, view.waveform_f32)
        expected[source] = dict(
            filename=filename,
            sample_count=view.sample_count,
            waveform_sha256=view.waveform_sha256,
        )
    freeze = dict(
        description="Fixed resident36turn CPU2/4/8comparison; no cached transcript/answer/audio or changed models/decoding.",
        source_sha256=hashes,
        previous_sha256=preserved,
        before=before,
        rows=rows,
        expected=expected,
        core_ids=cores,
        asr_checkpoint_sha256=checkpoints,
        limits=dict(
            turns=36, vad=36, asr=24, core=24, tts=24, retries=0, wall_seconds=900
        ),
    )
    old.publish(root / "execution-freeze.json", freeze)
    ledger = Ledger(root)
    original.FAILURES.clear()
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
        old.verify_snapshot(preserved)
        original.verify_originals()
        old.publish(
            root / "result.json",
            dict(
                description="Complete first resident observations; quality/parity and physical acceptance separately audited.",
                status="OBSERVATIONS_COMPLETE"
                if failure is None
                and all(
                    x["status"] in ("COMPLETE_PCM", "CORRECT_NO_SPEECH") for x in rows
                )
                else "FAILED_OR_INCOMPLETE",
                rows=rows,
                latency_gates=latency_gates(rows),
                calls=ledger.counts,
                failure=failure,
                guard_failures=original.FAILURES,
                baseline_preserved=before == after,
                after=after,
                wall_seconds=time.monotonic() - started,
                product_activation=False,
                physical_first_audible="UNVERIFIED",
            ),
        )
    LOGGER.info("resident_comparison_complete")


def main():
    """Dispatch one fixed optional research scope without application/default or shared-service changes."""
    argparse.ArgumentParser(description=__doc__).parse_args()
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run())


if __name__ == "__main__":
    main()
