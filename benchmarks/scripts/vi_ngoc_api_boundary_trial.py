"""Own one same-text Ngoc Huyen API grouping comparison while preserving all previous voices and evidence."""

import argparse
import asyncio
import base64
import copy
import html
import json
import logging
import os
import subprocess
import time

from benchmarks.scripts import vi_ngoc_huyen_validation as retained
from benchmarks.scripts.vi_ngoc_api_boundary_worker import (
    SELECTED,
    SOURCE,
    TARGET,
    VOICE,
    compact_plan,
)
from src.application.services.web_fetch_tasks import finish_owned, spawn_owned

LOGGER = logging.getLogger(__name__)
Q = retained.Q
ROOT = Q.assets.ROOT / "ngoc-api-boundary-first"
SOURCES = (
    "benchmarks/scripts/vi_ngoc_api_boundary_worker.py",
    "benchmarks/scripts/vi_ngoc_api_boundary_trial.py",
    "benchmarks/tests/test_vi_ngoc_api_boundary.py",
)
AUTHORITY = "docs/evidence/d74-ngoc-api-boundary-authorization.json"


def verify_previous():
    """Rehash all43previous research files and retained native artifacts without modifying a first outcome."""
    binding = retained.verify_previous()
    result = json.loads(
        (Q.assets.PROJECT / "docs/evidence/d74-ngoc-validation-result.json").read_text()
    )
    for name, sha in result["source_sha256"].items():
        if Q.assets.digest(Q.assets.PROJECT / name) != sha:
            raise ValueError("api_boundary_previous_source_changed")
    for name, sha in result["private_sha256"].items():
        if Q.assets.digest(retained.ROOT / name) != sha:
            raise ValueError("api_boundary_previous_artifact_changed")
    LOGGER.info("api_boundary_previous_verified research_files=43")
    return binding


def baseline():
    """Read and verify the immutable actual Ngoc Huyen mixed-api baseline rather than regenerating it."""
    result = json.loads((retained.ROOT / "campaign-result.json").read_text())
    row = next(row for row in result["rows"] if row["id"] == SELECTED)
    Q.lifecycle.read_native(retained.ROOT / "worker/native", SELECTED, row["native"])
    LOGGER.info("api_boundary_baseline_verified id=%s", SELECTED)
    return row


def command(output, frontend=None, expected_sha=None, probe=False):
    """Mount the new worker under original CPU isolation, exposing no model weights to a probe."""
    if probe:
        args = retained.retained.command(output, probe=True)
        extras = [retained.SOURCES[0], SOURCES[0]]
    else:
        args = retained.command(output, frontend, expected_sha)
        extras = [SOURCES[0]]
    mounts = []
    for name in extras:
        mounts.extend(["--ro-bind", str(Q.assets.PROJECT / name), "/app/" + name])
    index = args.index("--remount-ro")
    args[index:index] = mounts
    args[args.index("/venv/bin/python") + 1] = "/app/" + SOURCES[0]
    return args


def compile_packet(original, observed):
    """Bind exactly one two-space edit to the original packet and measured dictionary/cap/token observations."""
    rows = copy.deepcopy(original["rows"])
    selected = next(row for row in rows if row["id"] == SELECTED)
    if (
        observed.get("selected_id") != SELECTED
        or observed.get("model_calls") != 0
        or observed.get("unknown_tokens") != 0
        or observed.get("native_dictionary") != TARGET + "."
        or observed.get("original_row") != selected
    ):
        raise ValueError("api_boundary_probe_binding")
    planned = observed["candidate_plan"]
    expected = compact_plan(
        selected["phone_plans"][0], lambda text: planned["us_original_cap"]
    )
    if (
        planned != expected
        or SOURCE in planned["us"]
        or planned["us"].count(TARGET) != 1
    ):
        raise ValueError("api_boundary_candidate_drift")
    selected["phone_plans"] = [planned]
    packet = dict(
        copy.deepcopy(original),
        rows=rows,
        selected_id=SELECTED,
        description="One compact API candidate, nine original metadata rows never admitted for synthesis.",
    )
    retained.validate_packet(packet)
    return packet


def probe(root=ROOT):
    """Inspect exactly one candidate with the genuine SDK and tokenizer before any model or new synthesis."""
    verify_previous()
    original = json.loads((retained.ROOT / "approved-packet.json").read_text())
    row = next(row for row in original["rows"] if row["id"] == SELECTED)
    baseline()
    root.mkdir(mode=0o700)
    directory = root / "probe"
    directory.mkdir(mode=0o700)
    output = directory / "native"
    output.mkdir(mode=0o700)
    raw = json.dumps(row, ensure_ascii=False).encode()
    Q.assets.publish(
        directory / "request.json",
        dict(
            description="One unchanged retained normalized case for a no-weights dictionary-boundary probe.",
            row=row,
        ),
    )
    args = command(output, probe=True)
    Q.assets.publish(
        directory / "launch.json",
        dict(
            description="Offline model-free pinned G2P/tokenizer/cap inspection.",
            command=args,
            stdin_sha256=Q.lifecycle.sha(raw),
        ),
    )
    started, peak = time.monotonic(), 0
    with (
        (directory / "stdout.log").open("xb") as stdout,
        (directory / "stderr.log").open("xb") as stderr,
    ):
        process = subprocess.Popen(
            args,
            stdin=subprocess.PIPE,
            stdout=stdout,
            stderr=stderr,
            start_new_session=True,
            env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"},
        )
        try:
            process.stdin.write(raw)
            process.stdin.close()
            while process.poll() is None:
                peak = max(
                    peak,
                    sum(
                        Q.lifecycle.rss_bytes(pid)
                        for pid in Q.lifecycle.process_tree(process.pid)
                    ),
                )
                if peak > 2 * Q.lifecycle.GIB or time.monotonic() - started > 60:
                    raise ValueError("api_boundary_probe_resource")
                Q.assets.budget(Q.assets.ROOT)
                time.sleep(0.05)
            if process.returncode:
                raise ValueError("api_boundary_probe_failed")
        finally:
            Q.assets.terminate(process)
            Q.assets.publish(
                directory / "retirement.json",
                dict(
                    description="Joined no-weights probe, no native requests.",
                    returncode=process.returncode,
                    peak_sampled_rss_bytes=peak,
                    wall_seconds=time.monotonic() - started,
                    model_calls=0,
                ),
            )
    observed = json.loads((output / "frontend.json").read_text())
    packet = compile_packet(original, observed)
    Q.assets.publish(root / "approved-packet.json", packet)
    LOGGER.info("api_boundary_probe_complete candidate_requests=0")


def read_packet(root):
    """Rebuild the exact candidate from immutable old plans and the measured probe before model startup."""
    original = json.loads((retained.ROOT / "approved-packet.json").read_text())
    observed = json.loads((root / "probe/native/frontend.json").read_text())
    expected = compile_packet(original, observed)
    packet = json.loads((root / "approved-packet.json").read_text())
    if packet != expected:
        raise ValueError("api_boundary_packet_drift")
    return packet


def authorization():
    """Require one exact request under the source-backed decision and unchanged owner/evidence bindings."""
    path = Q.assets.PROJECT / AUTHORITY
    receipt = json.loads(path.read_text())
    if (
        receipt.get("authorized") is not True
        or receipt.get("voice") != VOICE
        or receipt.get("tts_ceiling") != 1
        or receipt.get("inner_chunks_ceiling") != 1
        or receipt.get("retries") != 0
    ):
        raise ValueError("api_boundary_authorization")
    for name, sha in receipt["bindings"].items():
        if Q.assets.digest(Q.assets.PROJECT / name) != sha:
            raise ValueError("api_boundary_authority_drift")
    return path


class BoundaryWorker(retained.ValidationWorker):
    """Retain owned CPU request/retirement behavior while requiring this exact one-case profile and packet."""

    async def start(self):
        """Load under original headroom/affinity guards and require the exact packet in the ready event."""
        if (
            self.process is not None
            or Q.lifecycle.mem_available() < 14 * Q.lifecycle.GIB
            or not {0, 1} <= os.sched_getaffinity(0)
        ):
            self.failure = "api_boundary_worker_preflight"
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
                or self.ready.get("profile") != "ngoc-api-boundary"
                or self.ready.get("voice") != VOICE
                or self.ready.get("packet_sha256") != self.packet_sha
            ):
                raise ValueError("api_boundary_ready_packet")
        except BaseException as error:
            self.failure = type(error).__name__ + ":" + str(error)
            await finish_owned(spawn_owned(self.close(force=True)))
            raise
        LOGGER.info("api_boundary_worker_ready")
        return self


async def run(root=ROOT):
    """Attempt one new candidate once, retain failure without retry and join the original owned lifecycle."""
    if (root / "execution-freeze.json").exists():
        raise ValueError("api_boundary_already_attempted")
    authority = authorization()
    binding = verify_previous()
    Q.lifecycle.prepared_integrity(Q.assets.ROOT)
    originals = Q.lifecycle.verify_originals()
    before = Q.lifecycle.local_state()
    if before["native_pids"]:
        raise ValueError("api_boundary_baseline_busy")
    packet = read_packet(root)
    row = next(row for row in packet["rows"] if row["id"] == SELECTED)
    old = baseline()
    hashes = {name: Q.assets.digest(Q.assets.PROJECT / name) for name in SOURCES}
    software = json.loads((root / "software-verification.json").read_text())
    if software.get("status") != "PASS" or software.get("source_sha256") != hashes:
        raise ValueError("api_boundary_software_binding")
    frontend = root / "approved-packet.json"
    sha = Q.assets.digest(frontend)
    Q.assets.publish(
        root / "execution-freeze.json",
        dict(
            description="One dictionary-boundary candidate, one reused same-text Ngoc Huyen baseline; no Truc Ly tuning.",
            source_sha256=hashes,
            software=software,
            authority_sha256=Q.assets.digest(authority),
            packet_sha256=sha,
            probe_sha256=Q.assets.digest(root / "probe/native/frontend.json"),
            baseline=old,
            expected_voice_binding=binding,
            originals=originals,
            before=before,
            selected=row,
            limits=dict(
                tts=1,
                inner_chunks=1,
                retries=0,
                wall_seconds=60,
                AS_gib=8,
                RSS_gib=2,
                headroom_gib=14,
            ),
        ),
    )
    deadline = time.monotonic() + 60
    Q.lifecycle.FAILURES.clear()
    worker = BoundaryWorker(frontend, sha, root / "worker", deadline)
    watchdog = asyncio.create_task(
        Q.lifecycle.monitor_campaign(Q.assets.ROOT, deadline, asyncio.current_task())
    )
    result = dict(
        description="First outcome of a single Ngoc Huyen acronym grouping candidate; owner listening unknown.",
        baseline=old,
        candidate=row,
        status="STARTED",
        tts_attempts=0,
    )
    try:
        await worker.start()
        row["status"] = "ATTEMPTED"
        result["tts_attempts"] = 1
        native = await worker.call(
            dict(op="synthesize", id=SELECTED, text=row["rendered_text"], voice=VOICE)
        )
        row["native"] = native
        retained.retained.verify_native(row, native, root / "worker/native", binding)
        row["status"] = "NATIVE_COMPLETE_AWAITING_OWNER_REVIEW"
        result["status"] = "API_BOUNDARY_CANDIDATE_COMPLETE_ACOUSTIC_UNVERIFIED"
    except BaseException as error:
        result.update(
            status="STOPPED_NO_RETRY", error=type(error).__name__ + ":" + str(error)
        )
        row["status"] = (
            "FAILED_OR_CANCELLED" if result["tts_attempts"] else "UNATTEMPTED"
        )
        LOGGER.exception("api_boundary_stopped")
    finally:
        await finish_owned(spawn_owned(worker.close(force=bool(worker.failure))))
        watchdog.cancel()
        await asyncio.gather(watchdog, return_exceptions=True)
        after = Q.lifecycle.local_state()
        result.update(
            after=after,
            baseline_restored=after == before,
            originals_after=Q.lifecycle.verify_originals(),
            completed_inner_chunks=1
            if row["status"] == "NATIVE_COMPLETE_AWAITING_OWNER_REVIEW"
            else 0,
            unattempted=1 - result["tts_attempts"],
            retries=0,
            asr_calls=0,
            core_calls=0,
            owner_ratings=None,
            model_selection=None,
            physical_first_audible="UNVERIFIED",
        )
        if after != before:
            result["status"] = "STOPPED_BASELINE_CHANGED"
        Q.assets.publish(root / "campaign-result.json", result)
    return result


def render_pair(source, baseline_wav, candidate_wav, candidate_status):
    """Present only genuine retained/new audio with explicit missing outcomes and no active browser capabilities."""
    cards = []
    for label, raw in [
        ("Bản cũ — API đang bị báo đọc sai", baseline_wav),
        ("Thử mới — nhóm API liền theo dictionary", candidate_wav),
    ]:
        player = (
            (
                '<audio controls preload="none" src="data:audio/wav;base64,'
                + base64.b64encode(raw).decode()
                + '"></audio>'
            )
            if raw is not None
            else "<p>Chưa có clip hoàn chỉnh: " + html.escape(candidate_status) + "</p>"
        )
        cards.append("<article><h2>" + label + "</h2>" + player + "</article>")
    return (
        '<!doctype html>\n<!-- Purpose: Authentic same-sentence Ngoc Huyen API baseline/candidate listening, no scripts, recording or network. -->\n<html lang="vi"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src \'none\'; media-src data:; style-src \'unsafe-inline\'; base-uri \'none\'; form-action \'none\'">\n<title>Ngọc Huyền — API trước và sau</title><style>body{max-width:900px;margin:30px auto;padding:0 18px;font:16px/1.6 system-ui;background:#f8fafb;color:#18232b}article{padding:18px;background:white;border:1px solid #ccd6dd;margin:18px 0}audio{width:100%}</style><h1>Ngọc Huyền — một câu, hai cách nhóm API</h1><p>Cần nghe: API có thành Ei–Pi–Ai thay vì E–Pe–I/A–Pe–I không; có rè/run, đổi chất giọng hoặc làm hỏng Python/server và cả câu không? Bản thử chưa được chấm đạt.</p><p>'
        + html.escape(source)
        + "</p>"
        + "".join(cards)
        + "</html>\n"
    )


def publish_review(root=ROOT):
    """Reverify the original baseline and complete candidate before embedding their unchanged WAVs."""
    result = json.loads((root / "campaign-result.json").read_text())
    old, new = result["baseline"], result["candidate"]
    Q.lifecycle.read_native(retained.ROOT / "worker/native", SELECTED, old["native"])
    baseline_wav = (retained.ROOT / "worker/native" / (SELECTED + ".wav")).read_bytes()
    candidate_wav = None
    if new["status"] == "NATIVE_COMPLETE_AWAITING_OWNER_REVIEW":
        Q.lifecycle.read_native(root / "worker/native", SELECTED, new["native"])
        binding = json.loads((root / "execution-freeze.json").read_text())[
            "expected_voice_binding"
        ]
        retained.retained.verify_native(
            new, new["native"], root / "worker/native", binding
        )
        candidate_wav = (root / "worker/native" / (SELECTED + ".wav")).read_bytes()
    directory = root / "review"
    directory.mkdir(mode=0o700)
    page = directory / "index.html"
    with page.open("xb") as stream:
        stream.write(
            render_pair(
                old["source_text"], baseline_wav, candidate_wav, new["status"]
            ).encode()
        )
    Q.assets.publish(
        directory / "index.json",
        dict(
            description="One unchanged baseline and one genuine complete API-boundary candidate, or explicit failure.",
            page_sha256=Q.assets.digest(page),
            baseline_wav_sha256=Q.lifecycle.sha(baseline_wav),
            candidate_wav_sha256=Q.lifecycle.sha(candidate_wav)
            if candidate_wav
            else None,
            owner_ratings=None,
        ),
    )
    Q.assets.budget(Q.assets.ROOT)
    LOGGER.info(
        "api_boundary_review_published candidate_complete=%s", candidate_wav is not None
    )


def main():
    """Run one no-weights probe, one SHA-bound candidate or authentic paired media publication."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("probe", "run", "review"))
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    os.umask(0o077)
    if args.action == "probe":
        probe()
    elif args.action == "review":
        publish_review()
    elif (
        asyncio.run(run())["status"]
        != "API_BOUNDARY_CANDIDATE_COMPLETE_ACOUSTIC_UNVERIFIED"
    ):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
