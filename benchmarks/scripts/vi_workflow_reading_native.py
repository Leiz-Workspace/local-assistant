"""Own one authorized48-slot real-model voice validation with the fixed accepted reading bridge and original assets."""

import argparse
import asyncio
import itertools
import json
import logging
import os
import time
from dataclasses import asdict
from pathlib import Path
from uuid import uuid4

from benchmarks.scripts import vi_voice_campaign as original
from benchmarks.scripts import vi_workflow_reading_check as prepared
from benchmarks.scripts.vi_workflow_reading_bridge import (
    ReadingResearchTTS,
    compose_workflow,
)
from benchmarks.scripts.vi_workflow_reading_policy import MODEL, POLICY, VOICE
from src.application.services.voice_pipeline import VoicePipeline
from src.application.services.web_fetch_tasks import finish_owned, spawn_owned

LOGGER = logging.getLogger(__name__)
ROOT = original.ROOT / "workflow-reading-native-first"
SOURCES = (
    "benchmarks/scripts/vi_workflow_reading_native.py",
    "benchmarks/tests/test_vi_workflow_reading_native.py",
)
AUTHORITY = "docs/evidence/d74-workflow-reading-native-authorization.json"


def verify_previous():
    """Require52prior research files and all preparation/native evidence to remain byte-identical."""
    prepared.verify_previous()
    receipt = json.loads(
        (
            original.PROJECT / "docs/evidence/d74-workflow-reading-preparation.json"
        ).read_text()
    )
    for name, sha in receipt["final_source_sha256"].items():
        if original.assets.digest(original.PROJECT / name) != sha:
            raise ValueError("reading_workflow_dependency_changed")
    for name, sha in receipt["private_sha256"].items():
        if original.assets.digest(prepared.ROOT / name) != sha:
            raise ValueError("reading_workflow_preparation_changed")
    binding = json.loads(
        (prepared.previous.retained.retained.ROOT / "execution-freeze.json").read_text()
    )["expected_voice_binding"]
    LOGGER.info("reading_workflow_dependencies_verified research_files=52")
    return binding, receipt["final_source_sha256"]


def authority():
    """Require the exact owner-authorized native matrix and unchanged decision/evidence bindings before dispatch."""
    path = original.PROJECT / AUTHORITY
    value = json.loads(path.read_text())
    if (
        value.get("authorized") is not True
        or value.get("slots") != 48
        or value.get("policy") != POLICY
        or value.get("limits")
        != dict(
            asr=48,
            core=48,
            tts=48,
            optional_recovery_core=2,
            retries=0,
            wall_seconds=3600,
        )
    ):
        raise ValueError("reading_workflow_native_authority")
    for name, sha in value["bindings"].items():
        if original.assets.digest(original.PROJECT / name) != sha:
            raise ValueError("reading_workflow_authority_drift")
    LOGGER.info("reading_workflow_native_authority_verified")
    return path


def matrix(packet):
    """Freeze all48new slots in declared lower-RAM-first order without selecting a model or dropping later failures."""
    rows = [
        dict(
            id=f"reading-turn-{index:02d}",
            asr=asr,
            tts=tts,
            state=state,
            source=case["id"],
            expected_no_answer=case["expected_no_answer"],
            status="UNATTEMPTED",
            reading_policy=POLICY if tts == "turbo" else "original-piper",
        )
        for index, (asr, tts, state, case) in enumerate(
            itertools.product(
                ("whisper-small-ct2", "qwen3-asr-0.6b"),
                ("turbo", "piper-vi"),
                ("fresh", "resident"),
                packet["workflow_sources"],
            )
        )
    ]
    if len(rows) != 48 or len({row["id"] for row in rows}) != 48:
        raise ValueError("reading_workflow_matrix_coverage")
    LOGGER.info("reading_workflow_matrix_declared slots=48 order=lower_RAM_first")
    return rows


class Ledger(original.Ledger):
    """Retain immutable attempt records while limiting each workflow dependency to48first calls."""

    def admit(self, kind, identity):
        """Consume a first attempt before dispatch, without the older standalone TTS allowance."""
        if kind not in self.counts or identity in self.seen or self.counts[kind] >= 48:
            raise ValueError("reading_workflow_call_ceiling_or_duplicate")
        super().admit(kind, identity)


class ReadingWorker(original.Worker):
    """Use original owned CPU/resource lifecycle with an exact reading-policy manifest and CORE co-residency guard."""

    def __init__(self, directory, deadline, core_pid, manifest_path):
        """Bind only the fixed Turbo candidate and an already published read-only per-worker scope."""
        super().__init__("turbo", directory, deadline, core_pid=core_pid)
        self.manifest_path = manifest_path
        self.manifest_sha = original.assets.digest(manifest_path)

    async def start(self):
        """Load once under unchanged headroom/affinity caps and reject wrong readiness before admitting a request."""
        if (
            self.process is not None
            or original.mem_available() < 14 * original.GIB
            or not {0, 1} <= os.sched_getaffinity(0)
        ):
            self.failure = "reading_workflow_worker_preflight"
            original.FAILURES.append(self.failure)
            raise ValueError(self.failure)
        self.directory.mkdir(mode=0o700)
        output = self.directory / "native"
        output.mkdir(mode=0o700)
        self.started = time.monotonic()
        self.log = (self.directory / "stderr.log").open("xb")
        try:
            args = prepared.command(output, self.manifest_path, self.manifest_sha)
            original.assets.publish(
                self.directory / "launch.json",
                dict(
                    description="Fixed CPU Truc Ly reading worker with unchanged resource guards and scope SHA.",
                    command=args,
                    available_ram=original.mem_available(),
                    core_pid=self.core_pid,
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
            original.assets.publish(
                self.directory / "process-identity.json",
                dict(
                    description="Exact owned reading-policy namespace process.",
                    pid=self.process.pid,
                ),
            )
            original.WORKERS.add(self)
            self.ready = await self.receive()
            if (
                self.ready.get("event"),
                self.ready.get("candidate"),
                self.ready.get("profile"),
                self.ready.get("voice"),
                self.ready.get("reading_policy"),
                self.ready.get("manifest_sha256"),
            ) != (
                "ready",
                "turbo",
                "workflow-reading",
                VOICE,
                POLICY,
                self.manifest_sha,
            ):
                raise ValueError("reading_workflow_readiness_binding")
        except BaseException as error:
            self.failure = type(error).__name__ + ":" + str(error)
            original.FAILURES.append(self.failure)
            await finish_owned(spawn_owned(self.close(force=True)))
            if self.process is None:
                self.log.close()
            raise
        LOGGER.info("reading_workflow_worker_ready")
        return self


async def reading_worker(root, directory, deadline, core_pid, scope_sha, maximum):
    """Publish an exclusive one-or-six-request manifest before loading the fixed reading worker."""
    if maximum not in {1, 6}:
        raise ValueError("reading_workflow_worker_budget")
    path = root / "manifests" / (directory.parent.name + "-" + directory.name + ".json")
    original.assets.publish(
        path,
        dict(
            description="Per-worker capability for the owner-authorized reading-aware workflow, no model or voice selection.",
            native_authorized=True,
            policy=POLICY,
            model=MODEL,
            voice=VOICE,
            max_requests=maximum,
            scope_sha256=scope_sha,
        ),
    )
    return await ReadingWorker(directory, deadline, core_pid, path).start()


def make_service(
    asr,
    tts,
    state,
    resident_asr,
    resident_tts,
    slot,
    source,
    ledger,
    deadline,
    core_pid,
    worker_factory,
    binding,
):
    """Compose original ASR/CORE with either fixed reading-aware Truc Ly or the unchanged Piper control."""
    asr_adapter = original.ResearchASR(
        asr, resident_asr, slot, source, ledger, deadline, core_pid
    )
    core = original.ResearchCORE(slot, ledger)
    if tts == "turbo":
        backend = ReadingResearchTTS(
            resident_tts, slot, ledger, deadline, core_pid, worker_factory, binding
        )

        async def audit(trace):
            """Persist redacted original/spoken transform provenance before publishing a successful turn."""
            original.assets.publish(
                slot / "reading-transform.json",
                dict(
                    description="Verified original CORE answer to rendered speech mapping; raw content is not duplicated here.",
                    **asdict(trace),
                ),
            )

        service = compose_workflow(
            asr_adapter, core, backend, audit, asr_model=asr, timeout=180
        )
    else:
        backend = original.ResearchTTS(
            tts, resident_tts, slot, ledger, deadline, core_pid
        )
        service = VoicePipeline(
            asr=asr_adapter,
            llm=core,
            tts=backend,
            asr_model=asr,
            llm_model="qwen3.5-9b-core",
            tts_model=backend.model_id,
            timeout=180,
        )
    return service, asr_adapter, backend


async def workflow(root, sources, ledger, deadline, rows, scope_sha, binding):
    """Observe the frozen48slots without repair/retry and stop on first resource, provenance or worker failure."""
    core_dir = root / "results/core"
    core_dir.mkdir(mode=0o700)
    server = original.OwnedServer("core", core_dir)
    try:
        await server.start()
        for (asr, tts, state), group in itertools.groupby(
            rows, key=lambda row: (row["asr"], row["tts"], row["state"])
        ):
            resident_asr = resident_tts = None
            try:
                if state == "resident":
                    group_dir = root / "results" / f"resident-{asr}-{tts}"
                    group_dir.mkdir(mode=0o700)
                    resident_asr = await original.Worker(
                        asr, group_dir / "asr", deadline, core_pid=server.process.pid
                    ).start()
                    resident_tts = (
                        await reading_worker(
                            root,
                            group_dir / "tts",
                            deadline,
                            server.process.pid,
                            scope_sha,
                            6,
                        )
                        if tts == "turbo"
                        else await original.Worker(
                            tts,
                            group_dir / "tts",
                            deadline,
                            core_pid=server.process.pid,
                        ).start()
                    )
                for row in group:
                    if server.failure or time.monotonic() > deadline:
                        raise ValueError("reading_workflow_core_guard_or_wall")
                    slot = root / "results" / row["id"]
                    slot.mkdir(mode=0o700)

                    async def factory(directory, until, pid):
                        """Provide one exactly scoped cold reading worker without changing the selected model or voice."""
                        return await reading_worker(
                            root, directory, until, pid, scope_sha, 1
                        )

                    service, asr_adapter, tts_adapter = make_service(
                        asr,
                        tts,
                        state,
                        resident_asr,
                        resident_tts,
                        slot,
                        sources[row["source"]],
                        ledger,
                        deadline,
                        server.process.pid,
                        factory,
                        binding,
                    )
                    started = time.monotonic()
                    row["status"] = "ATTEMPTED"
                    try:
                        result = await service.complete(
                            uuid4(),
                            sources[row["source"]]["audio"],
                            "vi",
                            explicit_submission=True,
                        )
                        elapsed = time.monotonic() - started
                        row.update(
                            status="NEGATIVE_HALLUCINATION"
                            if row["expected_no_answer"]
                            else "COMPLETE_PCM_PROXY_ONLY",
                            buffered_latency_seconds=elapsed,
                            stage_seconds=result.stage_seconds,
                            complete_pcm_within_4s=elapsed <= 4,
                            physical_first_audible="UNVERIFIED",
                        )
                    except asyncio.CancelledError:
                        row.update(
                            status="CANCELLED",
                            elapsed_seconds=time.monotonic() - started,
                        )
                        raise
                    except Exception as error:
                        row.update(
                            status="CORRECT_NO_SPEECH"
                            if getattr(error, "code", None) == "no_speech"
                            and row["expected_no_answer"]
                            else "FAILED",
                            error_class=type(error).__name__,
                            code=getattr(error, "code", None),
                            elapsed_seconds=time.monotonic() - started,
                        )
                        if original.FAILURES or any(
                            worker.failure
                            for worker in (asr_adapter.worker, tts_adapter.worker)
                            if worker is not None
                        ):
                            raise ValueError(
                                "reading_workflow_native_failure_stops_admission"
                            ) from error
                    finally:
                        await finish_owned(spawn_owned(service.shutdown()))
                        for adapter in (asr_adapter, tts_adapter):
                            if adapter.owned and adapter.worker is not None:
                                await finish_owned(
                                    spawn_owned(
                                        adapter.worker.close(
                                            force=bool(adapter.worker.failure)
                                        )
                                    )
                                )
                        original.assets.publish(
                            slot / "result.json",
                            dict(
                                description="One immutable reading-aware workflow observation; complete PCM is not physical audibility.",
                                **row,
                            ),
                        )
                    LOGGER.info(
                        "reading_workflow_slot_finished id=%s status=%s",
                        row["id"],
                        row["status"],
                    )
            finally:
                for worker in (resident_asr, resident_tts):
                    if worker is not None:
                        await finish_owned(
                            spawn_owned(worker.close(force=bool(worker.failure)))
                        )
    finally:
        await finish_owned(spawn_owned(server.stop()))
        original.assets.publish(
            core_dir / "retirement.json",
            dict(
                description="Joined unchanged owned CORE lifecycle, no shared service restart.",
                **server.receipt(),
            ),
        )


async def run(root=ROOT):
    """Freeze the new scope, attempt its first real-model matrix once and preserve every outcome and cleanup result."""
    root = Path(root)
    if (root / "execution-freeze.json").exists():
        raise ValueError("reading_workflow_already_attempted")
    approved = authority()
    binding, dependencies = verify_previous()
    original.prepared_integrity(original.ROOT)
    originals = original.verify_originals()
    before = original.local_state()
    if before["native_pids"]:
        raise ValueError("reading_workflow_baseline_busy")
    original.verify_models()
    original.verify_runtime_snapshot()
    packet = json.loads(original.assets.PACKET.read_text())
    sources = original.retained_sources(original.ROOT, packet)
    rows = matrix(packet)
    hashes = {name: original.assets.digest(original.PROJECT / name) for name in SOURCES}
    software = json.loads((root / "software-verification.json").read_text())
    if software.get("status") != "PASS" or software.get("source_sha256") != hashes:
        raise ValueError("reading_workflow_software_binding")
    (root / "results").mkdir(mode=0o700)
    (root / "manifests").mkdir(mode=0o700)
    ledger = Ledger(root)
    original.assets.publish(
        root / "execution-freeze.json",
        dict(
            description="ADR165 new reading-aware native cohort; original ADR155 raw plan/approval/outcomes unchanged.",
            authority_sha256=original.assets.digest(approved),
            packet_sha256=original.assets.digest(original.assets.PACKET),
            source_sha256=hashes,
            dependencies_sha256=dependencies,
            software=software,
            originals=originals,
            before=before,
            expected_voice_binding=binding,
            rows=rows,
            limits=dict(
                asr=48,
                core=48,
                tts=48,
                optional_recovery_core=2,
                retries=0,
                wall_seconds=3600,
            ),
        ),
    )
    scope_sha = original.assets.digest(root / "execution-freeze.json")
    original.FAILURES.clear()
    started, actor = time.monotonic(), asyncio.current_task()
    deadline = started + 3600
    watchdog = asyncio.create_task(
        original.monitor_campaign(original.ROOT, deadline, actor)
    )
    result = dict(
        description="First native reading-aware workflow observations, no device first-audible or quality acceptance inferred.",
        status="STARTED",
        rows=rows,
    )
    try:
        await workflow(root, sources, ledger, deadline, rows, scope_sha, binding)
        result["status"] = "NATIVE_OBSERVATIONS_COMPLETE_PRODUCT_GATES_OPEN"
    except BaseException as error:
        result.update(
            status="STOPPED_NO_RETRY", error=type(error).__name__ + ":" + str(error)
        )
        LOGGER.exception("reading_workflow_stopped")
    finally:
        watchdog.cancel()
        await asyncio.gather(watchdog, return_exceptions=True)
        for worker in list(original.WORKERS):
            await finish_owned(spawn_owned(worker.close(force=True)))
        after = original.local_state()
        result.update(
            calls=ledger.counts,
            total_wall_seconds=time.monotonic() - started,
            state_after=after,
            baseline_restored=after == before,
            originals_after=original.verify_originals(),
            unattempted=sum(row["status"] == "UNATTEMPTED" for row in rows),
            guard_failures=list(original.FAILURES),
            physical_first_audible="UNVERIFIED",
            owner_voice_selection=None,
        )
        if after != before:
            result["status"] = "STOPPED_BASELINE_CHANGED"
        original.assets.publish(root / "campaign-result.json", result)
    return result


def main():
    """Require an explicit native action and owner-bound scope before any research model startup."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("run",))
    parser.parse_args()
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    os.umask(0o077)
    if (
        asyncio.run(run())["status"]
        != "NATIVE_OBSERVATIONS_COMPLETE_PRODUCT_GATES_OPEN"
    ):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
