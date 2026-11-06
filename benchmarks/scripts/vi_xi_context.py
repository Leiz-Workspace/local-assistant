"""Verify existing XI/xi-mang readings using unchanged SDK and retained native worker boundaries."""

import argparse
import asyncio
import base64
import html
import json
import logging
import os
import subprocess
import time

from benchmarks.scripts import vi_roman_context as previous
from src.application.services.web_fetch_tasks import finish_owned, spawn_owned

LOGGER = logging.getLogger(__name__)
Q = previous.Q
ROOT = Q.assets.ROOT / "xi-context-first"
CASES = (
    (
        "xi-word",
        "Xi măng được dùng để xây nhà.",
        "xi măng được dùng để xây nhà.",
        "xi măng, không phải mười một măng",
    ),
    (
        "xi-uppercase",
        "XI MĂNG được dùng để xây nhà.",
        "xi măng được dùng để xây nhà.",
        "xi măng dù viết hoa",
    ),
    (
        "roman-eleven",
        "Chương XI có mười một mục.",
        "chương mười một có mười một mục.",
        "chương mười một",
    ),
    (
        "xi-mixed",
        "Chương XI nói về xi măng và cách sử dụng.",
        "chương mười một nói về xi măng và cách sử dụng.",
        "chương mười một, sau đó xi măng",
    ),
    (
        "xi-uppercase-mixed",
        "CHƯƠNG XI nói về XI MĂNG.",
        "chương mười một nói về xi măng.",
        "mười một và xi măng trong cùng câu viết hoa",
    ),
    ("identifier", "Mã sản phẩm XI cần được giữ nguyên.", None, "observation only"),
    ("bare", "XI.", None, "observation only"),
    (
        "noncanonical",
        "Chương IIX không phải ký hiệu chuẩn.",
        None,
        "observation only; malformed Roman notation",
    ),
    ("lower-identifier", "Tên biến xi không phải số La Mã.", None, "observation only"),
)
AUDIBLE = frozenset({"xi-word", "roman-eleven", "xi-mixed"})
SOURCES = (
    "benchmarks/scripts/vi_xi_context.py",
    "benchmarks/tests/test_vi_xi_context.py",
)


def verify_previous():
    """Preserve all thirty-one previous research files and the complete VI-context observations."""
    previous.verify_previous()
    freeze = json.loads((previous.ROOT / "execution-freeze.json").read_text())
    for name, sha in freeze["source_sha256"].items():
        if Q.assets.digest(Q.assets.PROJECT / name) != sha:
            raise ValueError("xi_previous_source_changed")
    receipt = json.loads(
        (Q.assets.PROJECT / "docs/evidence/d74-roman-context-result.json").read_text()
    )
    for name, sha in receipt["private_sha256"].items():
        if Q.assets.digest(previous.ROOT / name) != sha:
            raise ValueError("xi_previous_evidence_changed")
    LOGGER.info("xi_previous_verified files=31")


def probe(root=ROOT):
    """Reuse the exact existing no-weights probe program with the fixed nine-case XI packet."""
    root.mkdir(mode=0o700)
    directory = root / "probe"
    directory.mkdir(mode=0o700)
    output = directory / "native"
    output.mkdir(mode=0o700)
    request = json.dumps(CASES, ensure_ascii=False).encode()
    (directory / "request.json").write_bytes(request)
    args = previous.previous.previous.original.english.probe_command(output)
    args[-1] = previous.PROBE
    Q.assets.publish(
        directory / "launch.json",
        dict(
            description="Existing no-weights context probe, XI corpus, no reading-rule changes.",
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
                    raise ValueError("xi_probe_resource")
                Q.assets.budget(Q.assets.ROOT)
                time.sleep(0.05)
            if process.returncode:
                raise ValueError("xi_probe_failed")
        finally:
            Q.assets.terminate(process)
            Q.assets.publish(
                directory / "retirement.json",
                dict(
                    description="Joined no-weights XI inspection.",
                    returncode=process.returncode,
                    peak_sampled_rss_bytes=peak,
                    wall_seconds=time.monotonic() - started,
                    model_calls=0,
                ),
            )
    return json.loads((output / "frontend.json").read_text())


def packet(frontend):
    """Require five context-dependent targets without scoring ambiguous identifiers or malformed numerals."""
    rows = frontend.get("rows", [])
    if (
        frontend.get("model_calls") != 0
        or len(rows) != 9
        or {r["id"] for r in rows} != {r[0] for r in CASES}
    ):
        raise ValueError("xi_frontend_coverage")
    lookup = {r["id"]: r for r in rows}
    for identity, text, expected, hint in CASES:
        row = lookup[identity]
        if (
            row["source_text"] != text
            or row["unknown_tokens"]
            or (expected is not None and row["normalized"] != expected)
        ):
            raise ValueError("xi_context_expected_reading_or_source")
        if identity in AUDIBLE and (
            len(row["chunks"]) != 1
            or row["gaps"]
            or len(row["phonemes"]) != 1
            or len(row["frame_caps"]) != 1
        ):
            raise ValueError("xi_single_chunk_required")
    result = [
        dict(
            id=f"{label}-{identity}",
            case=identity,
            voice=voice,
            source_text=text,
            expected_reading=hint,
            frontend=lookup[identity],
            status="UNATTEMPTED",
        )
        for label, voice in Q.VOICES
        for identity, text, expected, hint in CASES
        if identity in AUDIBLE
    ]
    LOGGER.info("xi_packet_bound frontend=9 expected_matches=5 native=6")
    return result


async def run(root=ROOT):
    """Own exactly six original-policy XI controls with first-failure stopping and inherited cleanup."""
    if (root / "execution-freeze.json").exists():
        raise ValueError("xi_already_attempted")
    authority = Q.assets.PROJECT / "docs/evidence/d74-xi-context-authorization.json"
    if json.loads(authority.read_text()).get("authorized") is not True:
        raise ValueError("xi_authorization")
    verify_previous()
    Q.lifecycle.prepared_integrity(Q.assets.ROOT)
    originals = Q.lifecycle.verify_originals()
    before = Q.lifecycle.local_state()
    if before["native_pids"]:
        raise ValueError("xi_native_baseline_busy")
    frontend = root / "probe/native/frontend.json"
    rows = packet(json.loads(frontend.read_text()))
    hashes = {name: Q.assets.digest(Q.assets.PROJECT / name) for name in SOURCES}
    software = json.loads((root / "software-verification.json").read_text())
    if software.get("status") != "PASS" or software.get("source_sha256") != hashes:
        raise ValueError("xi_software_binding")
    Q.assets.publish(
        root / "execution-freeze.json",
        dict(
            description="Six XI controls, original worker/model/normalizer/phonemizer unchanged.",
            source_sha256=hashes,
            authority_sha256=Q.assets.digest(authority),
            frontend_sha256=Q.assets.digest(frontend),
            software=software,
            before=before,
            originals=originals,
            rows=rows,
            limits=dict(
                tts=6,
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
    worker = Q.QualityWorker("clauses", root / "worker", deadline)
    watchdog = asyncio.create_task(
        Q.lifecycle.monitor_campaign(Q.assets.ROOT, deadline, asyncio.current_task())
    )
    attempts, chunks = 0, 0
    result = dict(
        description="Existing XI-context observations, not new acoustic quality labels.",
        rows=rows,
        status="STARTED",
    )
    try:
        await worker.start()
        for row in rows:
            if attempts >= 6 or chunks >= 6:
                raise ValueError("xi_budget")
            attempts += 1
            row["status"] = "ATTEMPTED"
            native = await worker.call(
                dict(
                    op="synthesize",
                    id=row["id"],
                    text=row["source_text"],
                    voice=row["voice"],
                )
            )
            row["native"] = native
            chunks += len(native["chunks"])
            previous.verify_native(row, native, root / "worker/native")
            row["status"] = "NATIVE_COMPLETE_AWAITING_OWNER_REVIEW"
        result["status"] = "XI_CONTROLS_COMPLETE_ACOUSTIC_UNVERIFIED"
    except BaseException as error:
        result.update(
            status="STOPPED_NO_RETRY", error=type(error).__name__ + ":" + str(error)
        )
        LOGGER.exception("xi_stopped")
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


def render_review(rows, audio):
    """Show all six XI slots with authentic local audio and no invented successful missing outputs."""
    if (
        len(rows) != 6
        or len({r["id"] for r in rows}) != 6
        or set(audio) - {r["id"] for r in rows}
    ):
        raise ValueError("xi_review_coverage")
    cards = []
    for row in rows:
        content = audio.get(row["id"])
        player = (
            '<audio controls preload="none" src="data:audio/wav;base64,'
            + base64.b64encode(content).decode()
            + '"></audio>'
            if content is not None
            else "<p>Chưa có clip hoàn chỉnh: " + html.escape(row["status"]) + "</p>"
        )
        cards.append(
            "<article><h2>"
            + html.escape(row["id"] + " — " + row["voice"])
            + "</h2><p>"
            + html.escape(row["source_text"])
            + "</p><p>Cần kiểm tra: "
            + html.escape(row["expected_reading"])
            + "</p>"
            + player
            + "</article>"
        )
    return (
        """<!doctype html>
<!-- Purpose: Local unchanged-policy XI and xi mang listening checks, no microphone or uploads. -->
<html lang="vi"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; media-src data:; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<title>D74 — XI và xi măng</title><style>body{max-width:950px;margin:30px auto;padding:0 20px;font:16px/1.6 system-ui;background:#f8fafb;color:#18232b}article{background:white;padding:18px;margin:16px 0;border:1px solid #ccd6dd}audio{width:100%}h2{font-size:19px}</style>
<h1>XI và xi măng</h1><p>Chương XI cần đọc chương mười một; xi măng vẫn là xi măng. Các mẫu dùng nguyên model, giọng và cách đọc hiện có, không thêm luật thay XI bằng số. Bộ VI/vi đã được bạn xác nhận giữ nguyên.</p><p>Đây là kiểm tra XI, chưa phải bản sửa phát âm tiếng Anh. Trang không thu microphone hoặc gửi dữ liệu ra ngoài.</p>"""
        + "".join(cards)
        + "\n</html>\n"
    )


def publish_review(root=ROOT):
    """Verify completed WAVs and original context trace before publishing the six-slot local page."""
    rows = json.loads((root / "campaign-result.json").read_text())["rows"]
    audio = {}
    for row in rows:
        if row["status"] == "NATIVE_COMPLETE_AWAITING_OWNER_REVIEW":
            directory = root / "worker/native"
            Q.lifecycle.read_native(directory, row["id"], row["native"])
            previous.verify_native(row, row["native"], directory)
            audio[row["id"]] = (directory / (row["id"] + ".wav")).read_bytes()
    directory = root / "review"
    directory.mkdir(mode=0o700)
    with (directory / "index.html").open("xb") as stream:
        stream.write(render_review(rows, audio).encode())
    Q.assets.publish(
        directory / "index.json",
        dict(
            description="Six unchanged-policy XI slots and authentic available audio; no owner listening labels.",
            page_sha256=Q.assets.digest(directory / "index.html"),
            audio={k: Q.lifecycle.sha(v) for k, v in audio.items()},
            owner_ratings=None,
        ),
    )
    Q.assets.budget(Q.assets.ROOT)
    LOGGER.info("xi_review_published native=%d slots=6", len(audio))


def main():
    """Run explicit probe, one frozen XI study or original-media publication without changing speech policies."""
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
    elif asyncio.run(run())["status"] != "XI_CONTROLS_COMPLETE_ACOUSTIC_UNVERIFIED":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
