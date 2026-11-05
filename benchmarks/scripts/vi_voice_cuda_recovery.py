"""Recover six original-PCM native turns using retained exact Qwen CUDA quality, preserving the failed first experiment."""

import argparse
import asyncio
import json
import logging
import time
from pathlib import Path

from benchmarks.scripts import vi_voice_cuda_check as cuda

LOGGER = logging.getLogger(__name__)
ROOT = cuda.PROJECT / "data/backups/d74-cuda-root-guard-confirmation-first"
ADR = "docs/ADR/172-cuda-original-source-binding-recovery.md"
SOURCES = (
    "benchmarks/scripts/vi_voice_cuda_recovery.py",
    "benchmarks/tests/test_vi_voice_cuda_recovery.py",
)
CANDIDATE = "qwen3-asr-0.6b"


def validate_quality(value):
    """Require complete bilingual byte-exact Qwen text evidence without reclassifying failed or unknown lanes."""
    if (
        value.get("candidate") != CANDIDATE
        or value.get("passed") is not True
        or type(value.get("exact_text_matches")) is not int
        or value["exact_text_matches"] != 40
        or not cuda.quality_pass(value["cpu"], value["gpu"])
    ):
        raise ValueError("cuda_recovery_retained_quality")
    cpu, gpu = value["cpu"]["cases"], value["gpu"]["cases"]
    if (
        len(cpu) != 40
        or len(gpu) != 40
        or len({x["id"] for x in cpu}) != 40
        or [x["id"] for x in cpu] != [x["id"] for x in gpu]
        or any(
            a["status"] != "ok"
            or b["status"] != "ok"
            or a["prediction"] != b["prediction"]
            for a, b in zip(cpu, gpu, strict=True)
        )
    ):
        raise ValueError("cuda_recovery_quality_rows")
    LOGGER.info("cuda_recovery_quality_verified exact=40")


def retained_quality(first=cuda.ROOT):
    """Bind retained quality to the actual unchanged worker, source hashes and retired first execution."""
    first = Path(first)
    freeze = json.loads((first / "execution-freeze.json").read_text())
    snapshot = first / "executed-source"
    changed = {
        cuda.SOURCES[1],
        cuda.SOURCES[3],
        cuda.resident.SOURCES[1],
        cuda.resident.SOURCES[3],
    }
    for name, digest in freeze["source_sha256"].items():
        if cuda.original.assets.digest(snapshot / name) != digest:
            raise ValueError("cuda_recovery_first_source_snapshot")
        if (
            name not in changed
            and cuda.original.assets.digest(cuda.PROJECT / name) != digest
        ):
            raise ValueError("cuda_recovery_inference_source_changed")
    cuda.old.verify_snapshot(freeze["previous_sha256"])
    cuda.old.verify_snapshot(freeze["asr_checkpoint_sha256"])
    first_result = json.loads((first / "result.json").read_text())
    if (
        first_result.get("failure") != "VoiceError"
        or first_result.get("baseline_preserved") is not True
        or first_result.get("calls") != dict(asr=1, core=0, tts=0)
    ):
        raise ValueError("cuda_recovery_first_failure_scope")
    quality_path = first / "quality" / (CANDIDATE + "-result.json")
    value = json.loads(quality_path.read_text())
    validate_quality(value)
    expected_ids = {x["id"] for x in freeze["quality_sources"]}
    if expected_ids != {x["id"] for x in value["gpu"]["cases"]}:
        raise ValueError("cuda_recovery_original_quality_inputs")
    LOGGER.info("cuda_recovery_first_evidence_verified")
    return value, cuda.original.assets.digest(quality_path)


class Ledger(cuda.resident.Ledger):
    """Limit this explicit recovery to four first attempts per downstream stage."""

    def admit(self, kind, identity):
        """Consume an attempt before dispatch with no retry refund or access to another native lane."""
        if kind not in self.counts or self.counts[kind] >= 4:
            raise ValueError("cuda_recovery_call_budget")
        super().admit(kind, identity)


async def run(root=ROOT):
    """Execute one fixed native-only repair after verifying retained quality and source-tested recovery software."""
    root = Path(root)
    all_sources = (*SOURCES, *cuda.SOURCES, *cuda.resident.SOURCES)
    hashes = {n: cuda.original.assets.digest(cuda.PROJECT / n) for n in all_sources}
    software = json.loads((root / "software-verification.json").read_text())
    if software.get("status") != "PASS" or software.get("source_sha256") != hashes:
        raise ValueError("cuda_recovery_software_gate")
    for name in (ADR, cuda.ADR, cuda.resident.ADR):
        hashes[name] = cuda.original.assets.digest(cuda.PROJECT / name)
    quality, quality_sha = retained_quality()
    preserved = cuda.old.previous_snapshot()
    for directory in (
        cuda.ROOT,
        cuda.resident.ROOT,
        cuda.resident.previous.ROOT,
        cuda.PROJECT / "data/backups/d74-cuda-source-binding-recovery-first",
    ):
        for path in directory.rglob("*"):
            if path.is_file():
                preserved[str(path.relative_to(cuda.PROJECT))] = (
                    cuda.original.assets.digest(path)
                )
    binding, _ = cuda.resident.reading.verify_previous()
    cuda.original.verify_originals()
    cuda.original.verify_models()
    cuda.original.verify_runtime_snapshot()
    cuda.old.verify_provision()
    before = cuda.original.local_state()
    if before["native_pids"]:
        raise ValueError("cuda_recovery_existing_core")
    for name in ("results", "manifests", "samples"):
        (root / name).mkdir(mode=0o700)
    packet = json.loads(cuda.original.assets.PACKET.read_text())
    sources = cuda.original.retained_sources(cuda.original.ROOT, packet)
    rows = [
        dict(
            id=f"cuda-recovery-{i:02d}",
            asr=CANDIDATE,
            threads=8,
            source=x["id"],
            expected_no_answer=x["expected_no_answer"],
            status="UNATTEMPTED",
            asr_execution="cuda",
        )
        for i, x in enumerate(packet["workflow_sources"])
    ]
    if len(rows) != 6 or sum(x["expected_no_answer"] for x in rows) != 2:
        raise ValueError("cuda_recovery_matrix")
    expected = {}
    for identity, value in sources.items():
        view = cuda.resident.detector_view(value["audio"])
        filename = identity + ".f32"
        cuda.old.save_bytes(root / "samples" / filename, view.waveform_f32)
        expected[identity] = dict(
            filename=filename,
            sample_count=view.sample_count,
            waveform_sha256=view.waveform_sha256,
        )
        source_path = cuda.original.ROOT / "samples" / filename
        if (
            cuda.original.assets.digest(source_path)
            != value["request"]["waveform_sha256"]
        ):
            raise ValueError("cuda_recovery_source_mount_preflight")
    cuda.old.publish(
        root / "execution-freeze.json",
        dict(
            description="One fixed source-binding recovery; reuse exact40 Qwen quality, never rerun failed Whisper.",
            source_sha256=hashes,
            previous_sha256=preserved,
            before=before,
            retained_quality_sha256=quality_sha,
            rows=rows,
            limits=dict(
                vad=6,
                asr=4,
                core=4,
                tts=4,
                readiness_asr=1,
                retries=0,
                wall_seconds=900,
            ),
        ),
    )
    scope_sha = cuda.original.assets.digest(root / "execution-freeze.json")
    monitor = cuda.Monitor()
    ledger = Ledger(root)
    started = time.monotonic()
    failure = None
    factory = cuda.resident.Worker
    cuda.original.FAILURES.clear()

    def selected(role, *args, **kwargs):
        """Use only the qualified original Qwen CUDA worker and unchanged resident VAD/TTS implementations."""
        return (
            cuda.Worker(role, *args, monitor=monitor, **kwargs)
            if role == CANDIDATE
            else factory(role, *args, **kwargs)
        )

    cuda.resident.Worker = selected
    try:
        await cuda.resident.workflow(
            root, rows, sources, ledger, started + 900, binding, scope_sha, expected
        )
    except BaseException as error:
        failure = type(error).__name__
        raise
    finally:
        cuda.resident.Worker = factory
        monitor.close()
        after = cuda.original.local_state()
        cuda.old.verify_snapshot(preserved)
        cuda.original.verify_originals()
        complete = all(
            x["status"]
            == ("CORRECT_NO_SPEECH" if x["expected_no_answer"] else "COMPLETE_PCM")
            for x in rows
        )
        maximum = (
            max(
                x["buffered_latency_seconds"]
                for x in rows
                if not x["expected_no_answer"]
            )
            if complete
            else None
        )
        accepted = (
            complete
            and maximum <= 4
            and quality["passed"]
            and failure is None
            and not cuda.original.FAILURES
            and before == after
            and ledger.counts == dict(asr=4, core=4, tts=4)
        )
        cuda.old.publish(
            root / "result.json",
            dict(
                description="First six-turn original-source CUDA recovery; actual speaker/product acceptance remains separate.",
                status="LOCAL_BUFFERED_COMPUTE_PASS" if accepted else "NOT_PASS",
                rows=rows,
                calls=ledger.counts,
                failure=failure,
                guard_failures=cuda.original.FAILURES,
                maximum_complete_pcm_seconds=maximum,
                retained_quality_sha256=quality_sha,
                baseline_preserved=before == after,
                after=after,
                wall_seconds=time.monotonic() - started,
                physical_first_audible="UNVERIFIED",
                product_activation=False,
            ),
        )
    LOGGER.info("cuda_recovery_completed")


def main():
    """Dispatch only the fixed source-tested recovery without changing application or shared services."""
    argparse.ArgumentParser(description=__doc__).parse_args()
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run())


if __name__ == "__main__":
    main()
