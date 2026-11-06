"""Own a fixed broader-context Truc Ly validation while retaining all accepted source and pronunciation policies."""

import argparse
import asyncio
import base64
import html
import json
import logging
import os
import subprocess
import time
from dataclasses import asdict

from benchmarks.scripts import vi_us_terms_trial as previous
from benchmarks.scripts.vi_truc_ly_validation_worker import validate_entries
from src.application.services.web_fetch_tasks import finish_owned, spawn_owned

LOGGER = logging.getLogger(__name__)
Q = previous.Q
ROOT = Q.assets.ROOT / "truc-ly-validation-first"
SOURCES = (
    "benchmarks/scripts/vi_truc_ly_validation_worker.py",
    "benchmarks/scripts/vi_truc_ly_validation.py",
    "benchmarks/tests/test_vi_truc_ly_validation.py",
)
CASES = (
    dict(
        id="en-i",
        group="EN",
        text="I think this is the right answer.",
        terms={},
        api=0,
        refs=["think", "this", "right"],
        pieces=[],
        initial_i=True,
        hint="I đọc ai; think/this, right và accent Mỹ",
    ),
    dict(
        id="en-contrasts",
        group="EN",
        text="Please say ship, sheep, right, and light in that order.",
        terms={},
        api=0,
        refs=["ship", "sheep", "right", "light"],
        pieces=[],
        initial_i=False,
        hint="Phân biệt ship/sheep và right/light",
    ),
    dict(
        id="en-question",
        group="EN",
        text="Are you ready to use Python on this server?",
        terms={"python": 1, "server": 1},
        api=0,
        refs=[],
        pieces=[],
        initial_i=False,
        hint="Python/server và ngữ điệu câu hỏi",
    ),
    dict(
        id="en-github",
        group="EN",
        text="I saved the file on GitHub, and the browser is ready.",
        terms={"github": 1},
        api=0,
        refs=[],
        pieces=[],
        initial_i=True,
        hint="I, GitHub/browser và độ tự nhiên cả câu",
    ),
    dict(
        id="mixed-api",
        group="MIXED",
        text="Bạn có thể gọi API bằng Python trên server này không?",
        terms={"python": 1, "server": 1},
        api=1,
        refs=[],
        pieces=[],
        initial_i=False,
        hint="Chuyển Việt–Anh, Python/API/server và câu hỏi",
    ),
    dict(
        id="mixed-dev",
        group="MIXED",
        text="Bạn muốn xem mã GitHub hay chạy ứng dụng bằng Docker?",
        terms={"github": 1},
        api=0,
        refs=[],
        pieces=[],
        initial_i=False,
        hint="GitHub/Docker trong câu Việt, giữ chất giọng",
    ),
    dict(
        id="mixed-time",
        group="MIXED",
        text="Hẹn bạn lúc 09:15 ngày 14/11/2026; bạn muốn nhận thông báo qua API không?",
        terms={},
        api=1,
        refs=[],
        pieces=[
            "chín giờ mười lăm phút",
            "ngày mười bốn tháng mười một",
            "hai nghìn không trăm hai mươi sáu",
        ],
        initial_i=False,
        hint="09:15 ngày14/11/2026, ngắt câu và API",
    ),
    dict(
        id="vi-numbers",
        group="VI",
        text="Đơn hàng có 12 sản phẩm, mỗi sản phẩm giá 125000 đồng.",
        terms={},
        api=0,
        refs=[],
        pieces=["mười hai", "một trăm hai mươi lăm nghìn"],
        initial_i=False,
        hint="12 sản phẩm,125000đồng và nhịp đọc",
    ),
    dict(
        id="vi-context",
        group="VI",
        text="Chương XI nói về xi măng; chương VI nói về hành vi vi phạm.",
        terms={},
        api=0,
        refs=[],
        pieces=["chương mười một", "xi măng", "chương sáu", "hành vi vi phạm"],
        initial_i=False,
        hint="XI/xi măng và VI/vi phạm trong hai mệnh đề",
    ),
    dict(
        id="vi-natural",
        group="VI",
        text="Chị đã lưu bản ghi, bạn có muốn nghe lại trước khi tiếp tục không?",
        terms={},
        api=0,
        refs=[],
        pieces=[],
        initial_i=False,
        hint="Độ tự nhiên tiếng Việt và câu hỏi",
    ),
)


def source_packet():
    """Render the fixed corpus through the exact original English/date/clause renderer with stable trace fields."""
    rows = []
    old_texts = {case["text"] for case in previous.CASES}
    for case in CASES:
        if case["text"] in old_texts:
            raise ValueError("truc_validation_reused_sentence")
        rendered = previous.english.render_english(case["text"])
        rows.append(
            dict(
                id=case["id"],
                group=case["group"],
                source_text=case["text"],
                rendered_text=rendered.speech_text,
                source_sha256=rendered.source_sha256,
                rendered_sha256=rendered.speech_sha256,
                render_edits=[asdict(edit) for edit in rendered.edits],
                expected_terms=case["terms"],
                expected_api=case["api"],
                references=case["refs"],
                required_pieces=case["pieces"],
                initial_i=case["initial_i"],
                question=case["text"].endswith("?"),
                hint=case["hint"],
            )
        )
    LOGGER.info("truc_validation_sources_rendered cases=10")
    return rows


def packet(frontend):
    """Bind the actual no-weights probe to declared source/rendered semantics before native execution."""
    rows = frontend.get("rows", [])
    if (
        frontend.get("model_calls") != 0
        or frontend.get("voice") != "Trúc Ly"
        or len(rows) != 10
    ):
        raise ValueError("truc_validation_probe_binding")
    expected = source_packet()
    for row, source in zip(rows, expected, strict=True):
        if any(row.get(key) != value for key, value in source.items()):
            raise ValueError("truc_validation_render_or_corpus_drift")
    if len({row["rendered_text"] for row in rows}) != 10:
        raise ValueError("truc_validation_ambiguous_rendered_input")
    validate_entries(rows)
    LOGGER.info(
        "truc_validation_packet_bound cases=10 inner_chunks=%d",
        sum(len(row["phone_plans"]) for row in rows),
    )
    return [dict(row, voice="Trúc Ly", status="UNATTEMPTED") for row in rows]


def verify_previous():
    """Require all thirty-seven previous research files and the accepted term panel to remain unchanged."""
    previous.verify_previous()
    freeze = json.loads((previous.ROOT / "execution-freeze.json").read_text())
    for name, sha in freeze["source_sha256"].items():
        if Q.assets.digest(Q.assets.PROJECT / name) != sha:
            raise ValueError("truc_validation_old_source_changed")
    receipt = json.loads(
        (Q.assets.PROJECT / "docs/evidence/d74-us-terms-result.json").read_text()
    )
    for name, sha in receipt["private_sha256"].items():
        if Q.assets.digest(previous.ROOT / name) != sha:
            raise ValueError("truc_validation_old_evidence_changed")
    actual = json.loads((previous.ROOT / "campaign-result.json").read_text())
    selected = next(row for row in actual["pairs"] if row["id"] == "truc-ly-python-vi")
    binding = selected["us"]["native"]["prosody_trace"]["voice_binding"]
    LOGGER.info("truc_validation_prior_verified research_files=37")
    return binding


def command(output, probe=False, frontend=None, expected_sha=None):
    """Reuse original CPU isolation and mount the frozen read-only validation packet only for neural execution."""
    args = previous.command(output, "us", probe)
    mounts = [
        "--ro-bind",
        str(Q.assets.PROJECT / SOURCES[0]),
        "/app/benchmarks/scripts/vi_truc_ly_validation_worker.py",
    ]
    if not probe:
        if frontend is None or expected_sha is None or len(expected_sha) != 64:
            raise ValueError("truc_validation_packet_mount_required")
        mounts.extend(["--ro-bind", str(frontend), "/approved-validation.json"])
    index = args.index("--remount-ro")
    args[index:index] = mounts
    start = args.index("/venv/bin/python")
    return (
        args[:start]
        + [
            "/venv/bin/python",
            "/app/benchmarks/scripts/vi_truc_ly_validation_worker.py",
        ]
        + (["--probe"] if probe else ["--run", expected_sha])
    )


def probe(root=ROOT):
    """Run one original-SDK frontend inspection without weights and preserve observations even if semantic checks fail."""
    root.mkdir(mode=0o700)
    directory = root / "probe"
    directory.mkdir(mode=0o700)
    output = directory / "native"
    output.mkdir(mode=0o700)
    raw = json.dumps(source_packet(), ensure_ascii=False).encode()
    (directory / "request.json").write_bytes(raw)
    args = command(output, probe=True)
    Q.assets.publish(
        directory / "launch.json",
        dict(
            description="Original SDK frontend for new Truc Ly contexts, no weights or inference.",
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
                    raise ValueError("truc_validation_probe_resource")
                Q.assets.budget(Q.assets.ROOT)
                time.sleep(0.05)
            if process.returncode:
                raise ValueError("truc_validation_probe_failed")
        finally:
            Q.assets.terminate(process)
            Q.assets.publish(
                directory / "retirement.json",
                dict(
                    description="Joined original-SDK no-weights probe.",
                    returncode=process.returncode,
                    peak_sampled_rss_bytes=peak,
                    wall_seconds=time.monotonic() - started,
                    model_calls=0,
                ),
            )
    front = json.loads((output / "frontend.json").read_text())
    packet(front)
    return front


def verify_native(row, native, directory, expected_voice):
    """Require exact ordered probe plans, EOS/frame bounds, chunk hashes and the previously measured voice binding."""
    trace = native["prosody_trace"]
    plans = row["phone_plans"]
    if (
        trace.get("validation_case") != row["id"]
        or trace.get("validation_plans") != plans
        or trace.get("voice_binding") != expected_voice
        or trace.get("term_mode") != "us"
    ):
        raise ValueError("truc_validation_native_plan_or_voice")
    if (
        trace["chunks"] != row["chunks"]
        or trace["gaps"] != row["gaps"]
        or trace["phonemes"] != [p["us"] for p in plans]
        or len(native["chunks"]) != len(plans)
        or len(trace["native_chunk_sha256"]) != len(plans)
    ):
        raise ValueError("truc_validation_native_order")
    if native["generation_complete"] is not True:
        raise ValueError("truc_validation_incomplete")
    for index, (group, plan) in enumerate(zip(native["chunks"], plans, strict=True)):
        if group["eos"] is not True or not 1 <= group["frames"] <= plan["shared_cap"]:
            raise ValueError("truc_validation_chunk_eos_or_cap")
        raw = (directory / f"{row['id']}-chunk-{index}.f32").read_bytes()
        if Q.lifecycle.sha(raw) != trace["native_chunk_sha256"][index]:
            raise ValueError("truc_validation_chunk_hash")
    LOGGER.info(
        "truc_validation_native_verified case=%s chunks=%d", row["id"], len(plans)
    )


class ValidationWorker(Q.QualityWorker):
    """Retain original owned CPU lifecycle while binding a fixed validation packet SHA at readiness."""

    def __init__(self, frontend, sha, directory, deadline):
        """Bind the exact preflight artifact before creating any process."""
        super().__init__("clauses", directory, deadline)
        self.frontend, self.packet_sha = frontend, sha

    async def start(self):
        """Load under original headroom/affinity guards and require the exact packet in the ready event."""
        if (
            self.process is not None
            or Q.lifecycle.mem_available() < 14 * Q.lifecycle.GIB
            or not {0, 1} <= os.sched_getaffinity(0)
        ):
            self.failure = "truc_validation_worker_preflight"
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
                description="One CPU Truc Ly validation worker with the frozen probe mounted read-only.",
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
                description="Exact owned Truc Ly validation worker.",
                pid=self.process.pid,
            ),
        )
        Q.lifecycle.WORKERS.add(self)
        try:
            self.ready = await self.receive()
            if (
                self.ready.get("event") != "ready"
                or self.ready.get("candidate") != "turbo"
                or self.ready.get("profile") != "truc-validation"
                or self.ready.get("packet_sha256") != self.packet_sha
            ):
                raise ValueError("truc_validation_ready_packet")
        except BaseException as error:
            self.failure = type(error).__name__ + ":" + str(error)
            await finish_owned(spawn_owned(self.close(force=True)))
            raise
        LOGGER.info("truc_validation_worker_ready")
        return self


async def run(root=ROOT):
    """Generate ten frozen new contexts once, with at most sixteen original chunks and first-failure stopping."""
    if (root / "execution-freeze.json").exists():
        raise ValueError("truc_validation_already_attempted")
    authority = (
        Q.assets.PROJECT / "docs/evidence/d74-truc-validation-authorization.json"
    )
    if json.loads(authority.read_text()).get("authorized") is not True:
        raise ValueError("truc_validation_authorization")
    binding = verify_previous()
    Q.lifecycle.prepared_integrity(Q.assets.ROOT)
    originals = Q.lifecycle.verify_originals()
    before = Q.lifecycle.local_state()
    if before["native_pids"]:
        raise ValueError("truc_validation_baseline_busy")
    frontend = root / "probe/native/frontend.json"
    rows = packet(json.loads(frontend.read_text()))
    sha = Q.assets.digest(frontend)
    hashes = {name: Q.assets.digest(Q.assets.PROJECT / name) for name in SOURCES}
    software = json.loads((root / "software-verification.json").read_text())
    if software.get("status") != "PASS" or software.get("source_sha256") != hashes:
        raise ValueError("truc_validation_software_binding")
    Q.assets.publish(
        root / "execution-freeze.json",
        dict(
            description="New contexts only, original Truc Ly/US/API/date/clause policy, declared corpus/semantic checks before neural calls.",
            source_sha256=hashes,
            authority_sha256=Q.assets.digest(authority),
            frontend_sha256=sha,
            software=software,
            before=before,
            originals=originals,
            expected_voice_binding=binding,
            rows=rows,
            planned_inner_chunks=sum(len(r["phone_plans"]) for r in rows),
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
        description="Broader Truc Ly context outputs with no invented owner listening labels.",
        rows=rows,
        status="STARTED",
    )
    try:
        await worker.start()
        for row in rows:
            if attempts >= 10 or chunks + len(row["phone_plans"]) > 16:
                raise ValueError("truc_validation_budget")
            attempts += 1
            row["status"] = "ATTEMPTED"
            native = await worker.call(
                dict(
                    op="synthesize",
                    id=row["id"],
                    text=row["rendered_text"],
                    voice="Trúc Ly",
                )
            )
            row["native"] = native
            chunks += len(native["chunks"])
            verify_native(row, native, root / "worker/native", binding)
            row["status"] = "NATIVE_COMPLETE_AWAITING_OWNER_REVIEW"
        result["status"] = "TRUC_CONTEXTS_COMPLETE_ACOUSTIC_UNVERIFIED"
    except BaseException as error:
        result.update(
            status="STOPPED_NO_RETRY", error=type(error).__name__ + ":" + str(error)
        )
        LOGGER.exception("truc_validation_stopped")
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
            unattempted=sum(r["status"] == "UNATTEMPTED" for r in rows),
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
    """Keep every declared slot and genuine audio in grouped, script-free listening pages."""
    if (
        len(rows) != 10
        or len({r["id"] for r in rows}) != 10
        or set(audio) - {r["id"] for r in rows}
        or group not in {None, "EN", "MIXED", "VI"}
    ):
        raise ValueError("truc_validation_review_coverage")
    cards = []
    for row in rows:
        if group is not None and row["group"] != group:
            continue
        raw = audio.get(row["id"])
        player = (
            '<audio controls preload="none" src="data:audio/wav;base64,'
            + base64.b64encode(raw).decode()
            + '"></audio>'
            if raw is not None
            else "<p>Chưa có clip hoàn chỉnh: " + html.escape(row["status"]) + "</p>"
        )
        cards.append(
            "<article><h2>"
            + html.escape(row["id"] + " — Trúc Ly")
            + "</h2><p>"
            + html.escape(row["source_text"])
            + "</p><p>Cần kiểm tra: "
            + html.escape(row["hint"])
            + "</p>"
            + player
            + "</article>"
        )
    return (
        """<!doctype html>
<!-- Purpose: Local broader-context Truc Ly validation; original audio, no recording, scripts or network. -->
<html lang="vi"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; media-src data:; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<title>D74 — Trúc Ly trong câu mới</title><style>body{max-width:950px;margin:30px auto;padding:0 20px;font:16px/1.6 system-ui;background:#f8fafb;color:#18232b}article{background:white;padding:18px;margin:16px 0;border:1px solid #ccd6dd}audio{width:100%}h2{font-size:19px}</style>
<h1>Trúc Ly — tiếng Anh, câu Việt–Anh và tiếng Việt</h1><p>Bộ câu mới giữ cách xử lý đã thử trước. Kiểm tra phát âm/accent Mỹ, độ tự nhiên, ngắt câu và chất giọng có còn giống bản bạn thích không.</p><p>Chú ý I, ship/sheep, right/light; API/Python/server/GitHub; ngày giờ, tiền và VI/XI. Bộ mới chưa được chấm đạt. Trang không thu microphone hoặc gửi dữ liệu ra ngoài.</p>"""
        + "".join(cards)
        + "\n</html>\n"
    )


def publish_review(root=ROOT):
    """Independently verify completed output before publishing full and smaller language-group pages."""
    result = json.loads((root / "campaign-result.json").read_text())
    binding = json.loads((root / "execution-freeze.json").read_text())[
        "expected_voice_binding"
    ]
    rows = result["rows"]
    audio = {}
    for row in rows:
        if row["status"] == "NATIVE_COMPLETE_AWAITING_OWNER_REVIEW":
            Q.lifecycle.read_native(root / "worker/native", row["id"], row["native"])
            verify_native(row, row["native"], root / "worker/native", binding)
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
        with p.open("xb") as f:
            f.write(render_review(rows, audio, group).encode())
        pages[name] = dict(file=p.name, sha256=Q.assets.digest(p))
    Q.assets.publish(
        directory / "index.json",
        dict(
            description="Ten new Truc Ly slots and authentic completed WAVs; grouped pages preserve failures/missing outcomes, no quality ratings.",
            pages=pages,
            audio={key: Q.lifecycle.sha(value) for key, value in audio.items()},
            owner_ratings=None,
        ),
    )
    Q.assets.budget(Q.assets.ROOT)
    LOGGER.info("truc_validation_review_published native=%d slots=10", len(audio))


def main():
    """Run only an explicit no-weights probe, one frozen validation or original-media review publication."""
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
    elif asyncio.run(run())["status"] != "TRUC_CONTEXTS_COMPLETE_ACOUSTIC_UNVERIFIED":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
