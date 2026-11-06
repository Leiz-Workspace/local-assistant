"""Own a bounded paired TTS-only reading/prosody comparison without changing models or product routes."""

import argparse
import asyncio
import json
import logging
import os
import re
import subprocess
import time
from dataclasses import asdict

from benchmarks.scripts import vi_voice_campaign as lifecycle
from benchmarks.scripts import vi_voice_preparation as assets
from benchmarks.scripts.vi_speech_text import render_speech
from src.application.services.web_fetch_tasks import finish_owned, spawn_owned

LOGGER = logging.getLogger(__name__)
ROOT = assets.ROOT / "reading-quality-first"
PROFILES = ("raw", "reading", "clauses")
VOICES = (("truc-ly", "Trúc Ly"), ("ngoc-huyen", "Ngọc Huyền"))
CASES = (
    ("reading-01", "Cuộc hẹn bắt đầu lúc 09:15 ngày 14/11."),
    ("reading-02", "Chị sẽ nhắc bạn lúc 00:05 ngày 29/02/2028."),
    ("reading-03", "Lịch mới bắt đầu lúc 21:30 vào ngày 31/12/2026."),
    ("reading-04", "Bạn muốn học Python hay dùng API của ứng dụng?"),
    ("reading-05", "Chị đang kiểm tra Python; API sẽ sẵn sàng sau ít phút."),
    ("reading-06", "Tệp đã lưu; hãy kiểm tra bản sao trước khi đóng cửa sổ."),
    ("reading-07", "Chị hiểu. Bạn muốn nhận thông báo sáng mai hay chiều nay?"),
    ("reading-08", "Bạn đồng ý chứ?"),
)


def verify_retained_operators():
    """Require all seven retained research files to match the still-unapproved original recovery plan."""
    plan = json.loads(
        (
            assets.PROJECT
            / "docs/evidence/d74-adr155-proposed-workflow-recovery-20261103.json"
        ).read_text()
    )
    for name, expected in plan["operator_sha256"].items():
        if assets.digest(assets.PROJECT / name) != expected:
            raise ValueError("retained_operator_changed")
    LOGGER.info(
        "retained_research_operators_verified files=%d", len(plan["operator_sha256"])
    )
    return plan["operator_sha256"]


def command(output, profile, probe=False):
    """Reuse the original sealed CPU namespace while binding the new worker and removing unused audio/ASR mounts."""
    if profile not in PROFILES:
        raise ValueError("quality_profile")
    original = lifecycle.namespace("turbo", output)
    result, index = [], 0
    removed = {
        "/samples",
        "/app/scripts/asr_evaluation_worker.py",
        "/app/scripts/tts_evaluation_worker.py",
        "/app/scripts/tts_waveform.py",
    }
    if probe:
        removed |= {"/model", "/hf/hub"}
    while index < len(original):
        if original[index] == "--ro-bind":
            host, guest = original[index + 1 : index + 3]
            if guest not in removed:
                result.extend(original[index : index + 3])
            index += 3
        else:
            result.append(original[index])
            index += 1
    insertion = result.index("--remount-ro")
    mounts = []
    for name in [
        "vi_voice_worker.py",
        "vi_speech_worker.py",
        "vi_speech_text.py",
        "vi_speech_prosody.py",
    ]:
        mounts.extend(
            [
                "--ro-bind",
                str(assets.PROJECT / "benchmarks/scripts" / name),
                "/app/benchmarks/scripts/" + name,
            ]
        )
    result[insertion:insertion] = mounts
    result[-2:] = ["/app/benchmarks/scripts/vi_speech_worker.py", profile]
    if probe:
        result.append("--probe")
    return result


def run_probe(root=ROOT, texts=None, probe_name="probe"):
    """Execute a single bounded, model-free diagnostic before freezing native evaluation inputs."""
    if not re.fullmatch(r"[a-z][a-z0-9-]{0,60}", probe_name):
        raise ValueError("probe_name")
    root.mkdir(mode=0o700, exist_ok=True)
    directory = root / probe_name
    directory.mkdir(mode=0o700)
    output = directory / "native"
    output.mkdir(mode=0o700)
    selected = [text for _, text in CASES] if texts is None else texts
    request = json.dumps(selected, ensure_ascii=False).encode()
    (directory / "request.json").write_bytes(request)
    args = command(output, "raw", probe=True)
    assets.publish(
        directory / "launch.json",
        dict(
            description="One model-free offline SDK probe; no model mounts or inference.",
            command=args,
        ),
    )
    started, peak = time.monotonic(), 0
    with (
        (directory / "stdout.jsonl").open("xb") as stdout,
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
            process.stdin.write(request)
            process.stdin.close()
            while process.poll() is None:
                peak = max(
                    peak,
                    sum(
                        lifecycle.rss_bytes(pid)
                        for pid in lifecycle.process_tree(process.pid)
                    ),
                )
                if peak > 2 * lifecycle.GIB or time.monotonic() - started > 60:
                    raise ValueError("probe_rss_or_wall")
                assets.budget(assets.ROOT)
                time.sleep(0.05)
            if process.returncode:
                raise ValueError("probe_failed")
        finally:
            assets.terminate(process)
            assets.publish(
                directory / "retirement.json",
                dict(
                    description="Model-free probe lifecycle; native TTS calls0.",
                    returncode=process.returncode,
                    peak_sampled_rss_bytes=peak,
                    wall_seconds=time.monotonic() - started,
                    model_calls=0,
                ),
            )
    rows = json.loads((output / "normalizer-probe.json").read_text())
    if len(rows["rows"]) != 3 * len(selected) or rows["model_calls"] != 0:
        raise ValueError("probe_coverage")
    return rows


class QualityWorker(lifecycle.Worker):
    """Reuse tested bounded request/retirement behavior with an independently mounted quality-profile worker."""

    def __init__(self, profile, directory, deadline):
        """Bind one fixed profile with the original root-wide resource caps."""
        super().__init__("turbo", directory, deadline)
        self.profile = profile

    async def start(self):
        """Own one explicit profile startup without altering the original campaign operator or SDK source."""
        if (
            self.process is not None
            or lifecycle.mem_available() < 14 * lifecycle.GIB
            or not {0, 1} <= os.sched_getaffinity(0)
        ):
            self.failure = "quality_worker_preflight"
            raise ValueError(self.failure)
        self.directory.mkdir(mode=0o700)
        output = self.directory / "native"
        output.mkdir(mode=0o700)
        self.started = time.monotonic()
        self.log = (self.directory / "stderr.log").open("xb")
        args = command(output, self.profile)
        assets.publish(
            self.directory / "launch.json",
            dict(
                description="Owner-authorized TTS-only quality comparison; original CPU assets, no retry.",
                command=args,
                available_ram=lifecycle.mem_available(),
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
        assets.publish(
            self.directory / "process-identity.json",
            dict(description="Exact owned profile process.", pid=self.process.pid),
        )
        lifecycle.WORKERS.add(self)
        try:
            self.ready = await self.receive()
            if (
                self.ready.get("event") != "ready"
                or self.ready.get("candidate") != "turbo"
                or self.ready.get("profile") != self.profile
            ):
                raise ValueError("quality_ready_binding")
            LOGGER.info("quality_worker_ready profile=%s", self.profile)
        except BaseException as error:
            self.failure = type(error).__name__ + ":" + str(error)
            await finish_owned(spawn_owned(self.close(force=True)))
            raise
        return self


def packet_rows():
    """Preregister all48 paired requests, original display text and independent speech-rendering traces."""
    rows = []
    for profile in PROFILES:
        for label, voice in VOICES:
            for identity, text in CASES:
                rendered = render_speech(text, profile)
                rows.append(
                    dict(
                        id=f"{profile}-{label}-{identity}",
                        case=identity,
                        voice=voice,
                        profile=profile,
                        render=asdict(rendered),
                        status="UNATTEMPTED",
                    )
                )
    return rows


async def run(root=ROOT):
    """Run one frozen48-call TTS-only panel under the existing caps and retain every first failure."""
    if (root / "execution-freeze.json").exists():
        raise ValueError("quality_campaign_already_attempted")
    authorization = json.loads(
        (
            assets.PROJECT
            / "docs/evidence/d74-reading-quality-owner-authorization.json"
        ).read_text()
    )
    if authorization.get("authorized") is not True:
        raise ValueError("quality_authorization_required")
    retained = verify_retained_operators()
    lifecycle.prepared_integrity(assets.ROOT)
    preserved = lifecycle.verify_originals()
    before = lifecycle.local_state()
    rows = packet_rows()
    code_paths = [
        *assets.PROJECT.glob("benchmarks/scripts/vi_speech_*.py"),
        *assets.PROJECT.glob("benchmarks/tests/test_vi_speech_*.py"),
    ]
    hashes = {str(p.relative_to(assets.PROJECT)): assets.digest(p) for p in code_paths}
    software = json.loads((root / "software-verification.json").read_text())
    if software["status"] != "PASS" or software["operator_sha256"] != hashes:
        raise ValueError("quality_software_freeze")
    probe_path = root / "sentence-preserving-probe/native/normalizer-probe.json"
    if not probe_path.is_file():
        raise ValueError("quality_probe_required")
    assets.publish(
        root / "execution-freeze.json",
        dict(
            description="One new paired quality panel, not ADR155 recovery or product activation.",
            authorization_sha256=assets.digest(
                assets.PROJECT
                / "docs/evidence/d74-reading-quality-owner-authorization.json"
            ),
            source_sha256=hashes,
            retained_operator_sha256=retained,
            probe_sha256=assets.digest(probe_path),
            software=software,
            before=before,
            preserved=preserved,
            rows=rows,
            limits=dict(
                tts_calls=48,
                asr_calls=0,
                core_calls=0,
                retries=0,
                wall_seconds=1800,
                worker_wall_seconds=600,
                address_space_gib=8,
                tts_sampled_rss_gib=2,
                aggregate_sampled_rss_gib=8,
                available_ram_gib=14,
                root_gib=8,
            ),
        ),
    )
    deadline, attempts = time.monotonic() + 1800, 0
    lifecycle.FAILURES.clear()
    watchdog = asyncio.create_task(
        lifecycle.monitor_campaign(assets.ROOT, deadline, asyncio.current_task())
    )
    result = dict(
        description="Paired reading/prosody native outputs for owner review; no model choice or physical timing PASS.",
        status="STARTED",
        rows=rows,
    )
    try:
        for profile in PROFILES:
            worker = QualityWorker(profile, root / ("profile-" + profile), deadline)
            try:
                await worker.start()
                for row in (r for r in rows if r["profile"] == profile):
                    if attempts >= 48:
                        raise ValueError("quality_call_ceiling")
                    row["status"] = "ATTEMPTED"
                    attempts += 1
                    native = await worker.call(
                        dict(
                            op="synthesize",
                            id=row["id"],
                            text=row["render"]["speech_text"],
                            voice=row["voice"],
                        )
                    )
                    row.update(
                        status="NATIVE_COMPLETE_AWAITING_OWNER_REVIEW", native=native
                    )
            finally:
                await finish_owned(
                    spawn_owned(worker.close(force=bool(worker.failure)))
                )
        result["status"] = "NATIVE_PANEL_COMPLETE_QUALITY_UNVERIFIED"
    except BaseException as error:
        result["status"], result["error"] = (
            "STOPPED_NO_RETRY",
            type(error).__name__ + ":" + str(error),
        )
        LOGGER.exception("speech_quality_campaign_stopped")
        for row in rows:
            if row["status"] == "ATTEMPTED":
                row["status"] = "FAILED_OR_CANCELLED"
    finally:
        watchdog.cancel()
        await asyncio.gather(watchdog, return_exceptions=True)
        for worker in list(lifecycle.WORKERS):
            await finish_owned(spawn_owned(worker.close(force=True)))
        after = lifecycle.local_state()
        result.update(
            tts_attempts=attempts,
            asr_calls=0,
            core_calls=0,
            unattempted=sum(row["status"] == "UNATTEMPTED" for row in rows),
            after=after,
            baseline_restored=before == after,
            preserved_after=lifecycle.verify_originals(),
            owner_ratings=None,
            physical_first_audible="UNVERIFIED",
            model_selection=None,
        )
        if before != after:
            result["status"] = "STOPPED_BASELINE_CHANGED"
        assets.publish(root / "campaign-result.json", result)
    return result


def main():
    """Expose separate model-free probing and the single authorized paired native panel."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("probe", "run"))
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    os.umask(0o077)
    if args.action == "probe":
        run_probe()
    else:
        result = asyncio.run(run())
        if result["status"] != "NATIVE_PANEL_COMPLETE_QUALITY_UNVERIFIED":
            raise SystemExit(1)


if __name__ == "__main__":
    main()
