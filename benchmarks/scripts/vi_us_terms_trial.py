"""Own a bounded paired US-term study with original Python baselines and explicit identical-input controls."""

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
from pathlib import Path

from benchmarks.scripts import vi_english_reading as english
from benchmarks.scripts import vi_xi_context as previous
from benchmarks.scripts.vi_us_terms_worker import CASES, phone_plan
from src.application.services.web_fetch_tasks import finish_owned, spawn_owned

LOGGER = logging.getLogger(__name__)
Q = previous.Q
ROOT = Q.assets.ROOT / "us-terms-first"
SOURCES = (
    "benchmarks/scripts/vi_us_terms_worker.py",
    "benchmarks/scripts/vi_us_terms_trial.py",
    "benchmarks/tests/test_vi_us_terms_worker.py",
    "benchmarks/tests/test_vi_us_terms_trial.py",
)
ROLES = ("baseline", "us")
COMPLETE = {"NATIVE_COMPLETE", "RETAINED_COMPLETE", "SHARED_CONTROL_COMPLETE"}


def verify_previous():
    """Preserve thirty-three prior research files and every previously accepted or rejected output."""
    previous.verify_previous()
    frozen = json.loads((previous.ROOT / "execution-freeze.json").read_text())
    for name, sha in frozen["source_sha256"].items():
        if Q.assets.digest(Q.assets.PROJECT / name) != sha:
            raise ValueError("us_terms_prior_source_changed")
    receipt = json.loads(
        (Q.assets.PROJECT / "docs/evidence/d74-xi-context-result.json").read_text()
    )
    for name, sha in receipt["private_sha256"].items():
        if Q.assets.digest(previous.ROOT / name) != sha:
            raise ValueError("us_terms_prior_result_changed")
    LOGGER.info("us_terms_prior_verified files=33")


def command(output, role="baseline", probe=False):
    """Expose only approved CPU assets plus the new worker and frozen API function."""
    if role not in ROLES:
        raise ValueError("us_terms_role")
    args = english.probe_command(output) if probe else Q.command(output, "clauses")
    index = args.index("--remount-ro")
    mounts = []
    for name in ("vi_us_terms_worker.py", "vi_api_stress_worker.py"):
        mounts.extend(
            [
                "--ro-bind",
                str(Q.assets.PROJECT / "benchmarks/scripts" / name),
                "/app/benchmarks/scripts/" + name,
            ]
        )
    args[index:index] = mounts
    start = args.index("/venv/bin/python")
    return args[:start] + [
        "/venv/bin/python",
        "/app/benchmarks/scripts/vi_us_terms_worker.py",
        "--probe" if probe else role,
    ]


def probe(root=ROOT):
    """Inspect all six declared paired plans in one original no-weights namespace."""
    root.mkdir(mode=0o700, exist_ok=True)
    directory = root / "probe"
    directory.mkdir(mode=0o700)
    output = directory / "native"
    output.mkdir(mode=0o700)
    request = json.dumps(CASES, ensure_ascii=False).encode()
    (directory / "request.json").write_bytes(request)
    args = command(output, probe=True)
    Q.assets.publish(
        directory / "launch.json",
        dict(
            description="US term phone/cap/roundtrip proof only, no model weights or neural calls.",
            command=args,
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
            process.stdin.write(request)
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
                    raise ValueError("us_terms_probe_resource")
                Q.assets.budget(Q.assets.ROOT)
                time.sleep(0.05)
            if process.returncode:
                raise ValueError("us_terms_probe_failed")
        finally:
            Q.assets.terminate(process)
            Q.assets.publish(
                directory / "retirement.json",
                dict(
                    description="Joined no-weights US term probe.",
                    returncode=process.returncode,
                    peak_sampled_rss_bytes=peak,
                    wall_seconds=time.monotonic() - started,
                    model_calls=0,
                ),
            )
    return json.loads((output / "frontend.json").read_text())


def packet(frontend):
    """Freeze twelve exact pairs, four old baselines and four non-generated identical-input candidates."""
    if (
        frontend.get("model_calls") != 0
        or len(frontend.get("rows", [])) != 6
        or {r["id"] for r in frontend["rows"]} != {c["id"] for c in CASES}
    ):
        raise ValueError("us_terms_frontend_coverage")
    lookup = {r["id"]: r for r in frontend["rows"]}
    pairs = []
    for label, voice in Q.VOICES:
        for case in CASES:
            entry = lookup[case["id"]]
            plan = entry["phone_plan"]
            if (
                entry["source_text"] != case["text"]
                or entry["unknown_tokens"] != 0
                or len(entry["chunks"]) != 1
                or entry["gaps"]
            ):
                raise ValueError("us_terms_frontend_binding")
            caps = {
                plan["baseline"]: plan["baseline_original_cap"],
                plan["us"]: plan["us_original_cap"],
            }
            if phone_plan(plan["raw"], case, lambda phones: caps[phones]) != plan:
                raise ValueError("us_terms_edit_or_cap_proof")
            identity = f"{label}-{case['id']}"
            row = dict(
                id=identity,
                case=case["id"],
                voice=voice,
                source_text=case["text"],
                frontend=entry,
                baseline=dict(status="UNATTEMPTED", artifact_id="baseline-" + identity),
                us=dict(
                    status="SHARED_CONTROL_PENDING"
                    if plan["same_input"]
                    else "UNATTEMPTED",
                    artifact_id="us-" + identity,
                ),
            )
            pairs.append(row)
    LOGGER.info("us_terms_packet_bound pairs=12 logical_slots=24")
    return pairs


def bind_retained(pairs):
    """Reuse exact prior Python audio only when source, actual phones, gaps and cap match this comparison."""
    for row in pairs:
        if row["case"] not in {"python-vi", "python-en"}:
            continue
        label = row["id"].split("-", 2)[:2]
        label = "-".join(label)
        root = Q.assets.ROOT / (
            "api-stress-first" if row["case"] == "python-vi" else "roman-context-first"
        )
        identity = label + (
            "-english-01" if row["case"] == "python-vi" else "-python-english"
        )
        old = next(
            r
            for r in json.loads((root / "campaign-result.json").read_text())["rows"]
            if r["id"] == identity
        )
        entry = row["frontend"]
        plan = entry["phone_plan"]
        trace = old["native"]["prosody_trace"]
        cap = (
            old["frontend"]["api_stress"][0]["frame_cap"]
            if row["case"] == "python-vi"
            else old["frontend"]["frame_caps"][0]
        )
        if (
            old.get("source_text") != row["source_text"]
            or old["voice"] != row["voice"]
            or trace["chunks"] != entry["chunks"]
            or trace["gaps"] != entry["gaps"]
            or trace["phonemes"] != [plan["baseline"]]
            or cap != plan["shared_cap"]
        ):
            raise ValueError("us_terms_retained_baseline_binding")
        Q.lifecycle.read_native(root / "worker/native", identity, old["native"])
        row["baseline"].update(
            status="RETAINED_COMPLETE",
            artifact_id=identity,
            directory=str(root / "worker/native"),
            native=old["native"],
            voice_binding_provenance="Retained preset/source pins; no retrospective speaker hash measurement",
        )
    LOGGER.info("us_terms_retained_baselines_bound count=4")


def verify_native(row, role, native, directory, identity):
    """Require actual phones/cap/voice audit to match the probe and new paired speaker/reference hashes."""
    plan = row["frontend"]["phone_plan"]
    trace = native["prosody_trace"]
    expected = dict(
        id=identity,
        frontend=dict(
            chunks=row["frontend"]["chunks"],
            gaps=row["frontend"]["gaps"],
            phonemes=[plan[role]],
            frame_caps=[plan["shared_cap"]],
        ),
    )
    previous.previous.verify_native(expected, native, directory)
    if (
        trace["us_terms"] != plan
        or trace["term_mode"] != role
        or set(trace["voice_binding"]) != {"speaker_sha256", "reference_codes_sha256"}
    ):
        raise ValueError("us_terms_native_policy_binding")
    other = row["baseline"]
    if (
        role == "us"
        and other["status"] == "NATIVE_COMPLETE"
        and trace["voice_binding"] != other["native"]["prosody_trace"]["voice_binding"]
    ):
        raise ValueError("us_terms_new_pair_voice_changed")
    LOGGER.info("us_terms_native_pair_verified id=%s role=%s", row["id"], role)


class TermsWorker(Q.QualityWorker):
    """Retain original owned lifecycle/resource guards with one explicit US-term role per worker."""

    def __init__(self, role, directory, deadline):
        """Bind one immutable baseline or candidate role."""
        super().__init__("clauses", directory, deadline)
        self.role = role

    async def start(self):
        """Admit a CPU load only under the original headroom/affinity and verified role entry point."""
        if (
            self.process is not None
            or Q.lifecycle.mem_available() < 14 * Q.lifecycle.GIB
            or not {0, 1} <= os.sched_getaffinity(0)
        ):
            self.failure = "us_terms_worker_preflight"
            raise ValueError(self.failure)
        self.directory.mkdir(mode=0o700)
        output = self.directory / "native"
        output.mkdir(mode=0o700)
        self.started = time.monotonic()
        self.log = (self.directory / "stderr.log").open("xb")
        args = command(output, self.role)
        Q.assets.publish(
            self.directory / "launch.json",
            dict(
                description="One original CPU worker with a fixed term role and unchanged reference policy.",
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
            dict(description="Exact owned term-role worker.", pid=self.process.pid),
        )
        Q.lifecycle.WORKERS.add(self)
        try:
            self.ready = await self.receive()
            if (
                self.ready.get("event") != "ready"
                or self.ready.get("candidate") != "turbo"
                or self.ready.get("profile") != "us-terms"
                or self.ready.get("mode") != self.role
            ):
                raise ValueError("us_terms_ready_binding")
        except BaseException as error:
            self.failure = type(error).__name__ + ":" + str(error)
            await finish_owned(spawn_owned(self.close(force=True)))
            raise
        LOGGER.info("us_terms_worker_ready role=%s", self.role)
        return self


def share_controls(pairs):
    """Reuse completed unchanged-input controls explicitly without claiming another model call or improvement."""
    for row in pairs:
        if (
            row["us"]["status"] == "SHARED_CONTROL_PENDING"
            and row["baseline"]["status"] in COMPLETE
        ):
            row["us"] = dict(
                copy.deepcopy(row["baseline"]),
                status="SHARED_CONTROL_COMPLETE",
                shared_from="baseline",
            )
    LOGGER.info(
        "us_terms_identical_controls_shared count=%d",
        sum(r["us"]["status"] == "SHARED_CONTROL_COMPLETE" for r in pairs),
    )


async def run(root=ROOT):
    """Execute only the frozen unique requests, stopping the entire paired study at the first failure."""
    if (root / "execution-freeze.json").exists():
        raise ValueError("us_terms_already_attempted")
    authority = Q.assets.PROJECT / "docs/evidence/d74-us-terms-authorization.json"
    if json.loads(authority.read_text()).get("authorized") is not True:
        raise ValueError("us_terms_authorization")
    verify_previous()
    Q.lifecycle.prepared_integrity(Q.assets.ROOT)
    originals = Q.lifecycle.verify_originals()
    before = Q.lifecycle.local_state()
    if before["native_pids"]:
        raise ValueError("us_terms_baseline_busy")
    frontend = root / "probe/native/frontend.json"
    pairs = packet(json.loads(frontend.read_text()))
    bind_retained(pairs)
    planned = sum(
        row[role]["status"] == "UNATTEMPTED" for row in pairs for role in ROLES
    )
    if planned > 20:
        raise ValueError("us_terms_preregistered_budget")
    hashes = {name: Q.assets.digest(Q.assets.PROJECT / name) for name in SOURCES}
    software = json.loads((root / "software-verification.json").read_text())
    if software.get("status") != "PASS" or software.get("source_sha256") != hashes:
        raise ValueError("us_terms_software_binding")
    Q.assets.publish(
        root / "execution-freeze.json",
        dict(
            description="Exact twelve pairs with retained baselines and explicitly shared identical controls; only unique first attempts dispatched.",
            source_sha256=hashes,
            authority_sha256=Q.assets.digest(authority),
            frontend_sha256=Q.assets.digest(frontend),
            software=software,
            before=before,
            originals=originals,
            pairs=pairs,
            planned_native_requests=planned,
            limits=dict(
                tts=20,
                inner_chunks=20,
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
    workers = []
    attempts, chunks = 0, 0
    watchdog = asyncio.create_task(
        Q.lifecycle.monitor_campaign(Q.assets.ROOT, deadline, asyncio.current_task())
    )
    result = dict(
        description="US term paired results; no owner acoustic ratings inferred.",
        pairs=pairs,
        status="STARTED",
    )
    try:
        for role in ROLES:
            worker = TermsWorker(role, root / role, deadline)
            workers.append(worker)
            await worker.start()
            for row in pairs:
                info = row[role]
                if info["status"] != "UNATTEMPTED":
                    continue
                if attempts >= 20 or chunks >= 20:
                    raise ValueError("us_terms_native_budget")
                attempts += 1
                info["status"] = "ATTEMPTED"
                native = await worker.call(
                    dict(
                        op="synthesize",
                        id=info["artifact_id"],
                        text=row["source_text"],
                        voice=row["voice"],
                    )
                )
                info["native"] = native
                chunks += len(native["chunks"])
                verify_native(
                    row, role, native, root / role / "native", info["artifact_id"]
                )
                info.update(
                    status="NATIVE_COMPLETE", directory=str(root / role / "native")
                )
            await finish_owned(spawn_owned(worker.close(force=bool(worker.failure))))
            workers.remove(worker)
            share_controls(pairs)
        result["status"] = "US_TERM_PAIRS_COMPLETE_ACOUSTIC_UNVERIFIED"
    except BaseException as error:
        result.update(
            status="STOPPED_NO_RETRY", error=type(error).__name__ + ":" + str(error)
        )
        LOGGER.exception("us_terms_stopped")
        for row in pairs:
            for role in ROLES:
                if row[role]["status"] == "ATTEMPTED":
                    row[role]["status"] = "FAILED_OR_CANCELLED"
    finally:
        for worker in workers:
            await finish_owned(spawn_owned(worker.close(force=bool(worker.failure))))
        watchdog.cancel()
        await asyncio.gather(watchdog, return_exceptions=True)
        share_controls(pairs)
        after = Q.lifecycle.local_state()
        result.update(
            tts_attempts=attempts,
            completed_inner_chunks=chunks,
            planned_native_requests=planned,
            unattempted_native=sum(
                r[role]["status"] == "UNATTEMPTED" for r in pairs for role in ROLES
            ),
            logical_complete=sum(
                r[role]["status"] in COMPLETE for r in pairs for role in ROLES
            ),
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


def render_review(pairs, audio, voice=None):
    """Render twelve before/after rows with one player for unchanged controls and explicit missing outcomes."""
    if len(pairs) != 12 or len({r["id"] for r in pairs}) != 12:
        raise ValueError("us_terms_review_coverage")
    if voice is not None and voice not in {name for _, name in Q.VOICES}:
        raise ValueError("us_terms_review_voice")
    cards = []
    for row in pairs:
        if voice is not None and row["voice"] != voice:
            continue
        cells = []
        for role, title in [("baseline", "Bản hiện có"), ("us", "Bản thử Anh–Mỹ")]:
            info = row[role]
            content = audio.get((row["id"], role))
            if info["status"] == "SHARED_CONTROL_COMPLETE":
                player = "<p>Đầu vào phát âm giữ nguyên; dùng chung clip bên trái, không tạo lại một bản giống đầu vào.</p>"
            elif content is not None:
                player = (
                    '<audio controls preload="none" src="data:audio/wav;base64,'
                    + base64.b64encode(content).decode()
                    + '"></audio>'
                )
            else:
                player = (
                    "<p>Chưa có clip hoàn chỉnh: "
                    + html.escape(info["status"])
                    + "</p>"
                )
            cells.append("<section><h3>" + title + "</h3>" + player + "</section>")
        cards.append(
            "<article><h2>"
            + html.escape(row["id"] + " — " + row["voice"])
            + "</h2><p>"
            + html.escape(row["source_text"])
            + '</p><div class="pair">'
            + "".join(cells)
            + "</div></article>"
        )
    return (
        """<!doctype html>
<!-- Purpose: Local same-text US term comparison with exact original controls, no microphone or network. -->
<html lang="vi"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; media-src data:; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<title>D74 — Python và các từ tiếng Anh</title><style>body{max-width:1100px;margin:30px auto;padding:0 20px;font:16px/1.6 system-ui;background:#f8fafb;color:#18232b}article{background:white;padding:18px;margin:16px 0;border:1px solid #ccd6dd}.pair{display:grid;grid-template-columns:1fr 1fr;gap:20px}audio{width:100%}h2{font-size:19px}h3{font-size:17px}@media(max-width:750px){.pair{grid-template-columns:1fr}}</style>
<h1>Python, Docker, GitHub, browser, server và database</h1><p>So sánh cùng câu và giọng: phát âm Anh–Mỹ có đúng hơn không, giọng còn giống và tự nhiên không? Với câu chứa API, nghe lại API có còn đúng không.</p><p>Chỉ thử thay Python, GitHub và server; Docker/browser giữ đầu vào cũ làm đối chứng. Database giữ đầu vào cũ trong câu có server nhưng âm thanh cả câu vẫn có thể thay đổi. Bản thử chưa được chấp nhận. Không đổi model hoặc phát lại bộ thử bị chê.</p><p>Trang không thu microphone hoặc gửi dữ liệu ra ngoài. Một số clip Python bên trái được lấy nguyên từ bộ trước.</p>"""
        + "".join(cards)
        + "\n</html>\n"
    )


def publish_review(root=ROOT):
    """Verify exact new and retained native media before creating the twelve-pair local review."""
    pairs = json.loads((root / "campaign-result.json").read_text())["pairs"]
    audio = {}
    for row in pairs:
        for role in ROLES:
            info = row[role]
            if (
                info["status"] not in COMPLETE
                or info["status"] == "SHARED_CONTROL_COMPLETE"
            ):
                continue
            directory = (
                Q.assets.PROJECT / info["directory"]
                if not os.path.isabs(info["directory"])
                else Path(info["directory"])
            )
            Q.lifecycle.read_native(directory, info["artifact_id"], info["native"])
            if info["status"] == "NATIVE_COMPLETE":
                verify_native(row, role, info["native"], directory, info["artifact_id"])
            audio[(row["id"], role)] = (
                directory / (info["artifact_id"] + ".wav")
            ).read_bytes()
    directory = root / "review"
    directory.mkdir(mode=0o700)
    with (directory / "index.html").open("xb") as f:
        f.write(render_review(pairs, audio).encode())
    pages = {}
    for label, voice in Q.VOICES:
        path = directory / (label + ".html")
        with path.open("xb") as f:
            f.write(render_review(pairs, audio, voice).encode())
        pages[label] = dict(file=path.name, sha256=Q.assets.digest(path))
    Q.assets.publish(
        directory / "index.json",
        dict(
            description="Twelve logical pairs and two smaller voice pages, no duplicate generation for unchanged controls, exact retained/new WAVs.",
            page_sha256=Q.assets.digest(directory / "index.html"),
            voice_pages=pages,
            audio={
                key[0] + ":" + key[1]: Q.lifecycle.sha(value)
                for key, value in audio.items()
            },
            owner_ratings=None,
        ),
    )
    Q.assets.budget(Q.assets.ROOT)
    LOGGER.info("us_terms_review_published players=%d pairs=12", len(audio))


def main():
    """Run explicit probe, one frozen paired study or retained-media publication with audit logging."""
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
    elif asyncio.run(run())["status"] != "US_TERM_PAIRS_COMPLETE_ACOUSTIC_UNVERIFIED":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
