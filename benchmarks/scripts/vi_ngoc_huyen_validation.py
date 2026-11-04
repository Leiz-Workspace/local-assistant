"""Own one matched Ngoc Huyen context evaluation without modifying the accepted Truc Ly experiment."""

import argparse
import asyncio
import json
import logging
import os
import time

from benchmarks.scripts import vi_truc_ly_validation as retained
from benchmarks.scripts.vi_ngoc_huyen_validation_worker import VOICE, validate_packet
from src.application.services.web_fetch_tasks import finish_owned, spawn_owned

LOGGER = logging.getLogger(__name__)
Q = retained.Q
ROOT = Q.assets.ROOT / "ngoc-huyen-validation-first"
SOURCES = (
    "benchmarks/scripts/vi_ngoc_huyen_validation_worker.py",
    "benchmarks/scripts/vi_ngoc_huyen_validation.py",
    "benchmarks/tests/test_vi_ngoc_huyen_validation.py",
)
AUTHORITY = "docs/evidence/d74-ngoc-validation-authorization.json"


def packet_rows(frontend):
    """Reuse exact measured Truc Ly source/rendered/chunk/phone plans, changing only the declared preset."""
    rows = [dict(row, voice=VOICE) for row in retained.packet(frontend)]
    validate_packet(dict(voice=VOICE, rows=rows))
    LOGGER.info(
        "ngoc_validation_matched_packet cases=10 chunks=%d",
        sum(len(row["phone_plans"]) for row in rows),
    )
    return rows


def verify_previous():
    """Preserve all forty previous research files, genuine audio and accepted Truc Ly disposition."""
    retained.verify_previous()
    public = json.loads(
        (Q.assets.PROJECT / "docs/evidence/d74-truc-validation-result.json").read_text()
    )
    for name, sha in public["source_sha256"].items():
        if Q.assets.digest(Q.assets.PROJECT / name) != sha:
            raise ValueError("ngoc_validation_old_source_changed")
    for name, sha in public["private_sha256"].items():
        if Q.assets.digest(retained.ROOT / name) != sha:
            raise ValueError("ngoc_validation_old_evidence_changed")
    previous = json.loads((retained.previous.ROOT / "campaign-result.json").read_text())
    row = next(row for row in previous["pairs"] if row["id"] == "ngoc-huyen-python-vi")
    binding = row["us"]["native"]["prosody_trace"]["voice_binding"]
    LOGGER.info("ngoc_validation_previous_preserved research_files=40")
    return binding


def prepare(root=ROOT):
    """Create one exclusive packet from verified original frontend observations without another probe or model call."""
    verify_previous()
    frontend = retained.ROOT / "probe/native/frontend.json"
    rows = packet_rows(json.loads(frontend.read_text()))
    root.mkdir(mode=0o700)
    Q.assets.publish(
        root / "approved-packet.json",
        dict(
            description="Exact retained ten-case frontend plans reused explicitly; only the existing voice changes.",
            voice=VOICE,
            original_frontend_sha256=Q.assets.digest(frontend),
            rows=rows,
        ),
    )
    LOGGER.info("ngoc_validation_prepared neural_calls=0 new_probe_calls=0")


def read_packet(root):
    """Reject changed source semantics or plans by comparing the prepared packet with original measured observations."""
    packet = json.loads((root / "approved-packet.json").read_text())
    frontend = retained.ROOT / "probe/native/frontend.json"
    if packet.get("original_frontend_sha256") != Q.assets.digest(frontend):
        raise ValueError("ngoc_validation_frontend_binding")
    rows = validate_packet(packet)
    if rows != packet_rows(json.loads(frontend.read_text())):
        raise ValueError("ngoc_validation_matched_plan_drift")
    return rows


def command(output, frontend, expected_sha):
    """Reuse the original offline CPU namespace and mount only the new voice-specific worker and SHA-bound packet."""
    args = retained.command(output, frontend=frontend, expected_sha=expected_sha)
    index = args.index("--remount-ro")
    args[index:index] = [
        "--ro-bind",
        str(Q.assets.PROJECT / SOURCES[0]),
        "/app/benchmarks/scripts/vi_ngoc_huyen_validation_worker.py",
    ]
    start = args.index("/venv/bin/python")
    args[start + 1] = "/app/benchmarks/scripts/vi_ngoc_huyen_validation_worker.py"
    return args


def authorization():
    """Require the exact approved voice/budgets and unchanged decision/feedback bindings before neural execution."""
    path = Q.assets.PROJECT / AUTHORITY
    receipt = json.loads(path.read_text())
    if (
        receipt.get("authorized") is not True
        or receipt.get("voice") != VOICE
        or receipt.get("tts_ceiling") != 10
        or receipt.get("inner_chunks_ceiling") != 16
        or receipt.get("retries") != 0
    ):
        raise ValueError("ngoc_validation_authorization")
    for name, sha in receipt["bindings"].items():
        if Q.assets.digest(Q.assets.PROJECT / name) != sha:
            raise ValueError("ngoc_validation_authority_drift")
    LOGGER.info("ngoc_validation_authority_verified")
    return path


class ValidationWorker(Q.QualityWorker):
    """Reuse owned resource/request/retirement behavior with explicit Ngoc Huyen readiness binding."""

    def __init__(self, frontend, sha, directory, deadline):
        """Bind the exact frozen packet while preserving all original CPU worker limits."""
        super().__init__("clauses", directory, deadline)
        self.frontend, self.packet_sha = frontend, sha

    async def start(self):
        """Load under original headroom/affinity guards and require the exact packet in the ready event."""
        if (
            self.process is not None
            or Q.lifecycle.mem_available() < 14 * Q.lifecycle.GIB
            or not {0, 1} <= os.sched_getaffinity(0)
        ):
            self.failure = "ngoc_validation_worker_preflight"
            raise ValueError(self.failure)
        self.directory.mkdir(mode=0o700)
        output = self.directory / "native"
        output.mkdir(mode=0o700)
        self.started = time.monotonic()
        self.log = (self.directory / "stderr.log").open("xb")
        args = command(output, frontend=self.frontend, expected_sha=self.packet_sha)
        Q.assets.publish(
            self.directory / "launch.json",
            dict(
                description="One CPU Ngoc Huyen validation worker with the frozen probe mounted read-only.",
                command=args,
                available_ram=Q.lifecycle.mem_available(),
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
        Q.assets.publish(
            self.directory / "process-identity.json",
            dict(
                description="Exact owned Ngoc Huyen validation worker.",
                pid=self.process.pid,
            ),
        )
        Q.lifecycle.WORKERS.add(self)
        try:
            self.ready = await self.receive()
            if (
                self.ready.get("event") != "ready"
                or self.ready.get("candidate") != "turbo"
                or self.ready.get("profile") != "ngoc-validation"
                or self.ready.get("voice") != VOICE
                or self.ready.get("packet_sha256") != self.packet_sha
            ):
                raise ValueError("ngoc_validation_ready_packet")
        except BaseException as error:
            self.failure = type(error).__name__ + ":" + str(error)
            await finish_owned(spawn_owned(self.close(force=True)))
            raise
        LOGGER.info("ngoc_validation_worker_ready")
        return self


async def run(root=ROOT):
    """Make at most ten first Ngoc Huyen attempts, preserving the first error and every unattempted slot."""
    if (root / "execution-freeze.json").exists():
        raise ValueError("ngoc_validation_already_attempted")
    authority = authorization()
    binding = verify_previous()
    Q.lifecycle.prepared_integrity(Q.assets.ROOT)
    originals = Q.lifecycle.verify_originals()
    before = Q.lifecycle.local_state()
    if before["native_pids"]:
        raise ValueError("ngoc_validation_baseline_busy")
    rows = read_packet(root)
    frontend = root / "approved-packet.json"
    sha = Q.assets.digest(frontend)
    hashes = {name: Q.assets.digest(Q.assets.PROJECT / name) for name in SOURCES}
    software = json.loads((root / "software-verification.json").read_text())
    if software.get("status") != "PASS" or software.get("source_sha256") != hashes:
        raise ValueError("ngoc_validation_software_binding")
    Q.assets.publish(
        root / "execution-freeze.json",
        dict(
            description="Single matched Ngoc Huyen evaluation; retained Truc Ly evidence/policy stays immutable.",
            source_sha256=hashes,
            authority_sha256=Q.assets.digest(authority),
            packet_sha256=sha,
            software=software,
            before=before,
            originals=originals,
            expected_voice_binding=binding,
            rows=rows,
            planned_inner_chunks=sum(len(row["phone_plans"]) for row in rows),
            limits=dict(
                tts=10,
                inner_chunks=16,
                retries=0,
                asr=0,
                core=0,
                wall_seconds=120,
                AS_gib=8,
                RSS_gib=2,
                headroom_gib=14,
            ),
        ),
    )
    deadline = time.monotonic() + 120
    Q.lifecycle.FAILURES.clear()
    worker = ValidationWorker(frontend, sha, root / "worker", deadline)
    watchdog = asyncio.create_task(
        Q.lifecycle.monitor_campaign(Q.assets.ROOT, deadline, asyncio.current_task())
    )
    attempts, chunks = 0, 0
    result = dict(
        description="Actual first Ngoc Huyen outcomes on the preserved corpus; no invented listening labels.",
        voice=VOICE,
        rows=rows,
        status="STARTED",
    )
    try:
        await worker.start()
        for row in rows:
            if attempts >= 10 or chunks + len(row["phone_plans"]) > 16:
                raise ValueError("ngoc_validation_budget")
            attempts += 1
            row["status"] = "ATTEMPTED"
            native = await worker.call(
                dict(
                    op="synthesize",
                    id=row["id"],
                    text=row["rendered_text"],
                    voice=VOICE,
                )
            )
            row["native"] = native
            chunks += len(native["chunks"])
            retained.verify_native(row, native, root / "worker/native", binding)
            row["status"] = "NATIVE_COMPLETE_AWAITING_OWNER_REVIEW"
        result["status"] = "NGOC_CONTEXTS_COMPLETE_ACOUSTIC_UNVERIFIED"
    except BaseException as error:
        result.update(
            status="STOPPED_NO_RETRY", error=type(error).__name__ + ":" + str(error)
        )
        LOGGER.exception("ngoc_validation_stopped")
        for row in rows:
            if row["status"] == "ATTEMPTED":
                row["status"] = "FAILED_OR_CANCELLED"
    finally:
        await finish_owned(spawn_owned(worker.close(force=bool(worker.failure))))
        watchdog.cancel()
        await asyncio.gather(watchdog, return_exceptions=True)
        after = Q.lifecycle.local_state()
        result.update(
            tts_attempts=attempts,
            completed_inner_chunks=chunks,
            unattempted=sum(row["status"] == "UNATTEMPTED" for row in rows),
            asr_calls=0,
            core_calls=0,
            retries=0,
            after=after,
            baseline_restored=after == before,
            originals_after=Q.lifecycle.verify_originals(),
            owner_ratings=None,
            model_selection=None,
            physical_first_audible="UNVERIFIED",
        )
        if after != before:
            result["status"] = "STOPPED_BASELINE_CHANGED"
        Q.assets.publish(root / "campaign-result.json", result)
    return result


def render_review(rows, audio, group=None):
    """Reuse tested media-only rendering with truthful Ngoc Huyen labels and unchanged genuine WAV bytes."""
    if any(row.get("voice") != VOICE for row in rows):
        raise ValueError("ngoc_validation_review_voice")
    return (
        retained.render_review(rows, audio, group)
        .replace("Trúc Ly", VOICE)
        .replace("Truc Ly", "Ngoc Huyen")
    )


def publish_review(root=ROOT):
    """Verify each completed native observation and retain all ten slots before grouped local media publication."""
    result = json.loads((root / "campaign-result.json").read_text())
    binding = json.loads((root / "execution-freeze.json").read_text())[
        "expected_voice_binding"
    ]
    audio = {}
    for row in result["rows"]:
        if row["status"] == "NATIVE_COMPLETE_AWAITING_OWNER_REVIEW":
            Q.lifecycle.read_native(root / "worker/native", row["id"], row["native"])
            retained.verify_native(row, row["native"], root / "worker/native", binding)
            audio[row["id"]] = (
                root / "worker/native" / (row["id"] + ".wav")
            ).read_bytes()
    directory = root / "review"
    directory.mkdir(mode=0o700)
    pages = {}
    for name, group in [
        ("index", None),
        ("english", "EN"),
        ("mixed", "MIXED"),
        ("vietnamese", "VI"),
    ]:
        p = directory / (name + ".html")
        with p.open("xb") as stream:
            stream.write(render_review(result["rows"], audio, group).encode())
        pages[name] = dict(file=p.name, sha256=Q.assets.digest(p))
    Q.assets.publish(
        directory / "index.json",
        dict(
            description="Same ten context slots, authentic Ngoc Huyen WAVs and explicit missing outcomes; no acoustic ratings.",
            voice=VOICE,
            pages=pages,
            audio={key: Q.lifecycle.sha(raw) for key, raw in audio.items()},
            owner_ratings=None,
        ),
    )
    Q.assets.budget(Q.assets.ROOT)
    LOGGER.info("ngoc_validation_review_published native=%d slots=10", len(audio))


def main():
    """Prepare one matched packet, execute it once or publish genuine complete local media."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "run", "review"))
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    os.umask(0o077)
    if args.action == "prepare":
        prepare()
    elif args.action == "review":
        publish_review()
    elif asyncio.run(run())["status"] != "NGOC_CONTEXTS_COMPLETE_ACOUSTIC_UNVERIFIED":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
