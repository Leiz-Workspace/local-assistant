"""Own one four-request API stress comparison against exact preserved clause-path audio."""

import argparse
import asyncio
import base64
import html
import json
import logging
import os
import subprocess
import time

from benchmarks.scripts import vi_api_context_followup as previous
from benchmarks.scripts.vi_api_stress_worker import SOURCE, TARGET
from src.application.services.web_fetch_tasks import finish_owned, spawn_owned

LOGGER = logging.getLogger(__name__)
Q = previous.Q
ROOT = Q.assets.ROOT / "api-stress-first"
CASES = tuple(
    row
    for row in previous.original.english.CASES
    if row[0] in {"english-01", "english-04"}
)
SOURCES = (
    "benchmarks/scripts/vi_api_stress_worker.py",
    "benchmarks/scripts/vi_api_stress_trial.py",
    "benchmarks/tests/test_vi_api_stress_worker.py",
    "benchmarks/tests/test_vi_api_stress_trial.py",
)


def verify_previous():
    """Preserve all twenty-five earlier research files and every failed/refused experiment."""
    previous.predecessors()
    frozen = json.loads((previous.ROOT / "execution-freeze.json").read_text())
    for name, expected in frozen["source_sha256"].items():
        if Q.assets.digest(Q.assets.PROJECT / name) != expected:
            raise ValueError("api_stress_predecessor_changed")
    old = json.loads(
        (Q.assets.PROJECT / "docs/evidence/d74-english-reading-result.json").read_text()
    )
    for name, expected in old["private_sha256"].items():
        if Q.assets.digest(previous.original.english.ROOT / name) != expected:
            raise ValueError("api_stress_prior_english_evidence_changed")
    LOGGER.info("api_stress_predecessors_verified files=25")


def packet():
    """Bind four exact prior English sentences and voices without changing their original speech renderer."""
    old = json.loads(
        (previous.original.english.ROOT / "campaign-result.json").read_text()
    )["rows"]
    selected = []
    for label, voice in Q.VOICES:
        for case, text in CASES:
            identity = f"{label}-{case}"
            baseline = next(row for row in old if row["id"] == identity)
            rendered = previous.original.english.render_english(text)
            if (
                baseline["voice"] != voice
                or baseline["render"]["speech_text"] != rendered.speech_text
            ):
                raise ValueError("api_stress_baseline_text_or_voice")
            Q.lifecycle.read_native(
                previous.original.english.ROOT / "worker/native",
                identity,
                baseline["native"],
            )
            selected.append(
                dict(
                    id=identity,
                    case=case,
                    voice=voice,
                    source_text=text,
                    speech_text=rendered.speech_text,
                    baseline=baseline["native"],
                    status="UNATTEMPTED",
                )
            )
    LOGGER.info("api_stress_baselines_bound count=4")
    return selected


def command(output, probe=False):
    """Retain the original CPU isolation while mounting only the new stress worker and optional text tokenizer."""
    args = (
        previous.original.english.probe_command(output)
        if probe
        else Q.command(output, "clauses")
    )
    index = args.index("--remount-ro")
    args[index:index] = [
        "--ro-bind",
        str(Q.assets.PROJECT / SOURCES[0]),
        "/app/benchmarks/scripts/vi_api_stress_worker.py",
    ]
    start = args.index("/venv/bin/python")
    return args[:start] + [
        "/venv/bin/python",
        "/app/benchmarks/scripts/vi_api_stress_worker.py",
        "--probe" if probe else "api-stress",
    ]


def probe(root=ROOT):
    """Run the same-text no-weights probe once with retained lifecycle and original resource limits."""
    root.mkdir(mode=0o700)
    directory = root / "probe"
    directory.mkdir(mode=0o700)
    output = directory / "native"
    output.mkdir(mode=0o700)
    texts = [
        previous.original.english.render_english(text).speech_text for _, text in CASES
    ]
    request = json.dumps(texts, ensure_ascii=False).encode()
    (directory / "request.json").write_bytes(request)
    args = command(output, probe=True)
    Q.assets.publish(
        directory / "launch.json",
        dict(
            description="Same-text stress probe only, no weights or network.",
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
                    raise ValueError("api_stress_probe_resource")
                Q.assets.budget(Q.assets.ROOT)
                time.sleep(0.05)
            if process.returncode:
                raise ValueError("api_stress_probe_failed")
        finally:
            Q.assets.terminate(process)
            Q.assets.publish(
                directory / "retirement.json",
                dict(
                    description="Joined model-free stress probe.",
                    returncode=process.returncode,
                    peak_sampled_rss_bytes=peak,
                    wall_seconds=time.monotonic() - started,
                    model_calls=0,
                ),
            )
    return json.loads((output / "frontend.json").read_text())


def bind_frontend(rows, frontend):
    """Require exact old chunks/gaps/phones and term-only edits before admitting any new neural request."""
    if frontend.get("model_calls") != 0 or len(frontend["rows"]) != 2:
        raise ValueError("api_stress_frontend_coverage")
    for row in rows:
        entry = next(
            item
            for item in frontend["rows"]
            if item["speech_text"] == row["speech_text"]
        )
        old = row["baseline"]["prosody_trace"]
        traces = entry["api_stress"]
        if (
            entry["chunks"] != old["chunks"]
            or entry["gaps"] != old["gaps"]
            or [trace["before"] for trace in traces] != old["phonemes"]
            or len(traces) != (1 if row["case"] == "english-01" else 2)
        ):
            raise ValueError("api_stress_old_chunk_provenance")
        if sum(trace["replacements"] for trace in traces) != 1:
            raise ValueError("api_stress_term_count")
        for trace in traces:
            if trace["after"] != trace["before"].replace(SOURCE, TARGET, 1) or len(
                trace["after"]
            ) != len(trace["before"]):
                raise ValueError("api_stress_nonterm_change")
        row["frontend"] = entry
    LOGGER.info("api_stress_frontend_bound requests=4 chunks=6")


class StressWorker(Q.QualityWorker):
    """Retain original owned request, resource monitoring and joined cleanup with a fixed new entry point."""

    async def start(self):
        """Load one CPU worker only after the unchanged headroom and affinity preflight."""
        if (
            self.process is not None
            or Q.lifecycle.mem_available() < 14 * Q.lifecycle.GIB
            or not {0, 1} <= os.sched_getaffinity(0)
        ):
            self.failure = "api_stress_worker_preflight"
            raise ValueError(self.failure)
        self.directory.mkdir(mode=0o700)
        output = self.directory / "native"
        output.mkdir(mode=0o700)
        self.started = time.monotonic()
        self.log = (self.directory / "stderr.log").open("xb")
        args = command(output)
        Q.assets.publish(
            self.directory / "launch.json",
            dict(
                description="One same-text stress worker, original CPU limits.",
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
                description="Exact owned same-text stress worker.", pid=self.process.pid
            ),
        )
        Q.lifecycle.WORKERS.add(self)
        try:
            self.ready = await self.receive()
            if (
                self.ready.get("event") != "ready"
                or self.ready.get("candidate") != "turbo"
                or self.ready.get("profile") != "api-stress"
            ):
                raise ValueError("api_stress_ready_binding")
        except BaseException as error:
            self.failure = type(error).__name__ + ":" + str(error)
            await finish_owned(spawn_owned(self.close(force=True)))
            raise
        LOGGER.info("api_stress_worker_ready")
        return self


def verify_native(row, native, directory):
    """Bind actual ordered chunks and term edits to the probe, preserving unchanged first date audio exactly."""
    actual, expected = native["prosody_trace"], row["frontend"]
    if (
        any(actual[key] != expected[key] for key in ("chunks", "gaps", "api_stress"))
        or actual["phonemes"] != [trace["after"] for trace in expected["api_stress"]]
        or len(native["chunks"]) != len(expected["chunks"])
    ):
        raise ValueError("api_stress_native_provenance")
    for index, trace in enumerate(expected["api_stress"]):
        raw = (directory / f"{row['id']}-chunk-{index}.f32").read_bytes()
        if Q.lifecycle.sha(raw) != actual["native_chunk_sha256"][index]:
            raise ValueError("api_stress_chunk_hash")
        if (
            trace["replacements"] == 0
            and actual["native_chunk_sha256"][index]
            != row["baseline"]["prosody_trace"]["native_chunk_sha256"][index]
        ):
            raise ValueError("api_stress_unchanged_date_audio_changed")
    LOGGER.info(
        "api_stress_native_verified id=%s chunks=%d", row["id"], len(native["chunks"])
    )


async def run(root=ROOT):
    """Execute one frozen four-request/six-chunk study, stopping on the first failure with no retry."""
    if (root / "execution-freeze.json").exists():
        raise ValueError("api_stress_already_attempted")
    authority = Q.assets.PROJECT / "docs/evidence/d74-api-stress-authorization.json"
    if json.loads(authority.read_text()).get("authorized") is not True:
        raise ValueError("api_stress_authorization")
    verify_previous()
    Q.lifecycle.prepared_integrity(Q.assets.ROOT)
    originals = Q.lifecycle.verify_originals()
    before = Q.lifecycle.local_state()
    if before["native_pids"]:
        raise ValueError("api_stress_native_baseline_busy")
    rows = packet()
    frontend = root / "probe/native/frontend.json"
    bind_frontend(rows, json.loads(frontend.read_text()))
    hashes = {name: Q.assets.digest(Q.assets.PROJECT / name) for name in SOURCES}
    software = json.loads((root / "software-verification.json").read_text())
    if software.get("status") != "PASS" or software.get("source_sha256") != hashes:
        raise ValueError("api_stress_software_freeze")
    Q.assets.publish(
        root / "execution-freeze.json",
        dict(
            description="Same old texts/voices/clause path, only API stresses change; no acoustic PASS.",
            source_sha256=hashes,
            authority_sha256=Q.assets.digest(authority),
            frontend_sha256=Q.assets.digest(frontend),
            software=software,
            before=before,
            originals=originals,
            rows=rows,
            limits=dict(
                tts=4,
                inner_chunks=6,
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
    worker = StressWorker("clauses", root / "worker", deadline)
    watchdog = asyncio.create_task(
        Q.lifecycle.monitor_campaign(Q.assets.ROOT, deadline, asyncio.current_task())
    )
    attempts, chunks = 0, 0
    result = dict(
        description="Same-text API stress outputs; subjective quality remains unverified.",
        rows=rows,
        status="STARTED",
    )
    try:
        await worker.start()
        for row in rows:
            if attempts >= 4 or chunks + len(row["frontend"]["chunks"]) > 6:
                raise ValueError("api_stress_request_or_chunk_ceiling")
            attempts += 1
            row["status"] = "ATTEMPTED"
            native = await worker.call(
                dict(
                    op="synthesize",
                    id=row["id"],
                    text=row["speech_text"],
                    voice=row["voice"],
                )
            )
            row["native"] = native
            chunks += len(native["chunks"])
            verify_native(row, native, root / "worker/native")
            row["status"] = "NATIVE_COMPLETE_AWAITING_OWNER_REVIEW"
        result["status"] = "STRESS_CANDIDATES_COMPLETE_QUALITY_UNVERIFIED"
    except BaseException as error:
        result.update(
            status="STOPPED_NO_RETRY", error=type(error).__name__ + ":" + str(error)
        )
        LOGGER.exception("api_stress_stopped")
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


def render_review(rows, candidate, baseline):
    """Show all four same-text slots and exact preserved controls without scripts or external resources."""
    if (
        len(rows) != 4
        or len({row["id"] for row in rows}) != 4
        or (set(candidate) | set(baseline)) - {row["id"] for row in rows}
    ):
        raise ValueError("api_stress_review_coverage")
    cards = []
    for row in rows:
        cells = []
        for title, audio in [
            ("Bản trước: giữ tiếng Anh", baseline.get(row["id"])),
            ("Bản thử: chỉ đổi trọng âm API", candidate.get(row["id"])),
        ]:
            player = (
                '<audio controls preload="none" src="data:audio/wav;base64,'
                + base64.b64encode(audio).decode()
                + '"></audio>'
                if audio is not None
                else "<p>Chưa có clip hoàn chỉnh: "
                + html.escape(row["status"])
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
<!-- Purpose: Exact old and new API stress comparison, local audio only, no microphone or uploads. -->
<html lang="vi"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; media-src data:; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<title>D74 — API cùng câu và giọng cũ</title><style>body{max-width:1100px;margin:30px auto;padding:0 20px;font:16px/1.6 system-ui;color:#18232b;background:#f8fafb}article{background:white;padding:20px;margin:20px 0;border:1px solid #ccd6dd}.pair{display:grid;grid-template-columns:1fr 1fr;gap:20px}audio{width:100%}h2{font-size:20px}h3{font-size:17px}@media(max-width:750px){.pair{grid-template-columns:1fr}}</style>
<h1>API — cùng câu, cùng giọng, chỉ đổi trọng âm</h1><p>Bên trái là clip cũ nguyên vẹn; bên phải chỉ đổi trọng âm API theo kiểu từ điển SDK. Giữ tham chiếu giọng, dấu hỏi, Python, ngày/giờ và ngắt câu. Chưa xác nhận Ei đúng hoặc hết rè/run.</p>
<p>So sánh API có đọc Ei–Pi–Ai, có rè/run, và cả câu có tự nhiên hơn không. Bộ thử bị chê trước vẫn lưu riêng, không được áp dụng. Trang không thu microphone hoặc gửi dữ liệu ra ngoài.</p>"""
        + "".join(cards)
        + "\n</html>\n"
    )


def publish_review(root=ROOT):
    """Verify original/native audio bytes before publishing a self-contained four-pair local review."""
    rows = json.loads((root / "campaign-result.json").read_text())["rows"]
    audio, baseline = {}, {}
    for row in rows:
        old = previous.original.english.ROOT / "worker/native"
        Q.lifecycle.read_native(old, row["id"], row["baseline"])
        baseline[row["id"]] = (old / (row["id"] + ".wav")).read_bytes()
        if row["status"] == "NATIVE_COMPLETE_AWAITING_OWNER_REVIEW":
            directory = root / "worker/native"
            Q.lifecycle.read_native(directory, row["id"], row["native"])
            verify_native(row, row["native"], directory)
            audio[row["id"]] = (directory / (row["id"] + ".wav")).read_bytes()
    directory = root / "review"
    directory.mkdir(mode=0o700)
    with (directory / "index.html").open("xb") as stream:
        stream.write(render_review(rows, audio, baseline).encode())
    Q.assets.publish(
        directory / "index.json",
        dict(
            description="Four exact retained baselines plus available same-text API stress candidates; no owner quality labels.",
            page_sha256=Q.assets.digest(directory / "index.html"),
            baseline={key: Q.lifecycle.sha(value) for key, value in baseline.items()},
            candidate={key: Q.lifecycle.sha(value) for key, value in audio.items()},
            owner_ratings=None,
        ),
    )
    Q.assets.budget(Q.assets.ROOT)
    LOGGER.info("api_stress_review_published baseline=4 candidates=%d", len(audio))


def main():
    """Run only explicit model-free probe, one frozen study or retained-media publication actions."""
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
        asyncio.run(run())["status"] != "STRESS_CANDIDATES_COMPLETE_QUALITY_UNVERIFIED"
    ):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
