"""Use complete carrier sentences for a separately frozen API reference diagnostic without relaxing caps."""

import argparse
import asyncio
import base64
import html
import json
import logging
import os
import subprocess
import time

from benchmarks.scripts import vi_api_reference_trial as original
from src.application.services.web_fetch_tasks import finish_owned, spawn_owned

LOGGER = logging.getLogger(__name__)
Q = original.Q
ROOT = original.ROOT / "context-followup"
CASES = (
    ("vi-carrier", "Chị sẽ hướng dẫn cách gọi API ngay bây giờ."),
    ("english-carrier", "Please say A, P, I."),
)
PROBE = '''"""Validate full-sentence English controls without neural weights or relaxed frame limits."""
import json,logging,sys
from pathlib import Path
from sea_g2p import Normalizer,G2P
from tokenizers import Tokenizer
from vieneu_utils.core_utils import syllable_count,max_expected_frames
logging.basicConfig(level=logging.INFO)
raw=sys.stdin.buffer.read(16385)
if len(raw)>16384:raise ValueError("context_probe_bound")
request=json.loads(raw)
if len(request)!=2:raise ValueError("context_probe_count")
n,g=Normalizer(lang="vi"),G2P(lang="vi")
t=Tokenizer.from_file("/approved-tokenizer.json")
ref=g.convert("<en>a p i</en>",punc_norm=False)
rows=[]
for case in request:
 normalized=n.normalize(case["text"],punc_norm=False)
 ph=g.convert("<en>please say</en>",punc_norm=False)+" "+ref+"." if case["id"]=="english-carrier" else g.convert(normalized,punc_norm=False)
 ids=t.encode(ph,add_special_tokens=False).ids
 decoded=t.decode(ids,skip_special_tokens=False)
 syllables=syllable_count(ph)
 cap=max_expected_frames(ph)
 if ref not in ph or decoded!=ph or t.token_to_id("<|unk|>") in ids or syllables<=4 or cap<=13:raise ValueError("context_frontend_or_micro_utterance")
 rows.append(dict(id=case["id"],source_text=case["text"],normalized=normalized,phonemes=ph,token_ids=ids,decoded=decoded,syllables=syllables,original_frame_cap=cap,unknown_tokens=0))
with Path("/output/frontend.json").open("x") as stream:
 json.dump(dict(description="Two new carrier controls, unchanged original duration-dependent frame cap; no neural calls.",rows=rows,reference_api=ref,model_calls=0),stream,ensure_ascii=False,indent=2)
 stream.write("\\n")
logging.info("context_probe_complete model_calls=0")
'''


def predecessors():
    """Preserve the stopped first cohort and enforce its remaining actual-request budget."""
    result = json.loads((original.ROOT / "campaign-result.json").read_text())
    if result["status"] != "STOPPED_NO_RETRY" or result["tts_attempts"] + 8 > 16:
        raise ValueError("context_prior_disposition_or_budget")
    frozen = json.loads((original.ROOT / "execution-freeze.json").read_text())
    for name, expected in frozen["source_sha256"].items():
        if Q.assets.digest(Q.assets.PROJECT / name) != expected:
            raise ValueError("original_reference_operator_changed")
    original.verify_previous()
    LOGGER.info(
        "context_predecessors_verified prior_attempts=%d followup_ceiling=8 total_ceiling=16",
        result["tts_attempts"],
    )
    return result


def probe(root=ROOT):
    """Inspect new carrier phonemes and original frame caps without any neural model execution."""
    root.mkdir(mode=0o700)
    directory = root / "probe"
    directory.mkdir(mode=0o700)
    out = directory / "native"
    out.mkdir(mode=0o700)
    command = original.english.probe_command(out)
    command[-1] = PROBE
    request = json.dumps(
        [dict(id=identity, text=text) for identity, text in CASES], ensure_ascii=False
    ).encode()
    (directory / "request.json").write_bytes(request)
    Q.assets.publish(
        directory / "launch.json",
        dict(
            description="New carrier frontend only; no resubmitted failed short-letter control.",
            command=command,
        ),
    )
    started, peak = time.monotonic(), 0
    with (
        (directory / "stdout.log").open("xb") as stdout,
        (directory / "stderr.log").open("xb") as stderr,
    ):
        process = subprocess.Popen(
            command,
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
                    raise ValueError("context_probe_rss_or_wall")
                Q.assets.budget(Q.assets.ROOT)
                time.sleep(0.05)
            if process.returncode:
                raise ValueError("context_probe_failed")
        finally:
            Q.assets.terminate(process)
            Q.assets.publish(
                directory / "retirement.json",
                dict(
                    description="Joined model-free carrier probe.",
                    returncode=process.returncode,
                    peak_sampled_rss_bytes=peak,
                    wall_seconds=time.monotonic() - started,
                    model_calls=0,
                ),
            )
    return json.loads((out / "frontend.json").read_text())


def packet(frontend):
    """Freeze eight separate carrier slots and reject unchanged micro-controls or mismatched source bindings."""
    if len(frontend["rows"]) != 2 or frontend.get("reference_api") != "ˈeɪ pˈiː ˈaɪ":
        raise ValueError("context_frontend_coverage")
    lookup = {row["id"]: row for row in frontend["rows"]}
    for identity, text in CASES:
        row = lookup.get(identity, {})
        if (
            row.get("source_text") != text
            or row.get("decoded") != row.get("phonemes")
            or row.get("syllables", 0) <= 4
            or row.get("original_frame_cap", 0) <= 13
            or row.get("unknown_tokens") != 0
            or frontend["reference_api"] not in row.get("phonemes", "")
        ):
            raise ValueError("context_frontend_binding")
    return [
        dict(
            id=f"{mode}-{label}-{identity}",
            case=identity,
            source_text=text,
            voice=voice,
            mode=mode,
            phonemes=lookup[identity]["phonemes"],
            status="UNATTEMPTED",
        )
        for mode in original.MODES
        for label, voice in Q.VOICES
        for identity, text in CASES
    ]


def verify_pairs(rows):
    """Check exact four-pair speaker and actual text invariants independently of changed reference rows."""
    if len(rows) != 8 or any(
        row["status"] != "NATIVE_COMPLETE_AWAITING_OWNER_REVIEW" for row in rows
    ):
        raise ValueError("context_pair_coverage")
    for identity, _ in CASES:
        for _, voice in Q.VOICES:
            pair = [
                row for row in rows if row["case"] == identity and row["voice"] == voice
            ]
            if len(pair) != 2 or {row["mode"] for row in pair} != set(original.MODES):
                raise ValueError("context_pair_identity")
            a, b = [row["native"]["reference_trace"] for row in pair]
            for key in [
                "phonemes",
                "token_ids",
                "speaker_embedding_sha256",
                "projected_anchor_sha256",
                "prompt_text_ids",
            ]:
                if a[key] != b[key]:
                    raise ValueError("context_pair_changed_" + key)
            for row in pair:
                trace = row["native"]["reference_trace"]
                enabled = row["mode"] == "with_reference"
                if (
                    trace["use_ref_codes"] is not enabled
                    or (trace["reference_rows"] > 0) is not enabled
                ):
                    raise ValueError("context_pair_reference_binding")


async def run(root=ROOT):
    """Run at most eight new carrier requests within the retained sixteen-request actual budget, never retrying failed inputs."""
    if (root / "execution-freeze.json").exists():
        raise ValueError("context_already_attempted")
    authority = Q.assets.PROJECT / "docs/evidence/d74-api-context-authorization.json"
    if json.loads(authority.read_text()).get("authorized") is not True:
        raise ValueError("context_authorization")
    prior = predecessors()
    Q.lifecycle.prepared_integrity(Q.assets.ROOT)
    preserved = Q.lifecycle.verify_originals()
    before = Q.lifecycle.local_state()
    frontend = root / "probe/native/frontend.json"
    rows = packet(json.loads(frontend.read_text()))
    files = [
        Q.assets.PROJECT / "benchmarks/scripts/vi_api_context_followup.py",
        Q.assets.PROJECT / "benchmarks/tests/test_vi_api_context_followup.py",
    ]
    hashes = {
        str(path.relative_to(Q.assets.PROJECT)): Q.assets.digest(path) for path in files
    }
    software = json.loads((root / "software-verification.json").read_text())
    if software["status"] != "PASS" or software["source_sha256"] != hashes:
        raise ValueError("context_software_freeze")
    Q.assets.publish(
        root / "execution-freeze.json",
        dict(
            description="New carrier cohort after stopped short-letter control; original16declared rows/failure remain unchanged. Actual combined request ceiling16.",
            source_sha256=hashes,
            prior_result_sha256=Q.assets.digest(original.ROOT / "campaign-result.json"),
            authority_sha256=Q.assets.digest(authority),
            frontend_sha256=Q.assets.digest(frontend),
            software=software,
            rows=rows,
            before=before,
            preserved=preserved,
            limits=dict(
                followup_tts=8,
                actual_combined_ceiling=16,
                asr_calls=0,
                core_calls=0,
                retries=0,
                wall_seconds=120,
                AS_gib=8,
                RSS_gib=2,
                headroom_gib=14,
                parent_root_gib=8,
            ),
        ),
    )
    deadline, attempts = time.monotonic() + 120, 0
    Q.lifecycle.FAILURES.clear()
    watchdog = asyncio.create_task(
        Q.lifecycle.monitor_campaign(Q.assets.ROOT, deadline, asyncio.current_task())
    )
    result = dict(
        description="New full-carrier cohort, no relabeling or retry of failed standalone A.",
        status="STARTED",
        rows=rows,
        prior_attempts=prior["tts_attempts"],
    )
    try:
        for mode in original.MODES:
            worker = original.ReferenceWorker(mode, root / mode, deadline)
            try:
                await worker.start()
                for row in (row for row in rows if row["mode"] == mode):
                    if attempts >= 8 or prior["tts_attempts"] + attempts >= 16:
                        raise ValueError("context_actual_budget")
                    attempts += 1
                    row["status"] = "ATTEMPTED"
                    value = await worker.call(
                        dict(
                            op="synthesize",
                            id=row["id"],
                            text=row["phonemes"],
                            voice=row["voice"],
                        )
                    )
                    trace = value["reference_trace"]
                    if (
                        trace["mode"] != mode
                        or trace["voice"] != row["voice"]
                        or trace["phonemes"] != row["phonemes"]
                    ):
                        raise ValueError("context_actual_binding")
                    row.update(
                        status="NATIVE_COMPLETE_AWAITING_OWNER_REVIEW", native=value
                    )
            finally:
                await finish_owned(
                    spawn_owned(worker.close(force=bool(worker.failure)))
                )
        verify_pairs(rows)
        result["status"] = "CARRIER_PAIRS_COMPLETE_QUALITY_UNVERIFIED"
    except BaseException as error:
        result["status"], result["error"] = (
            "STOPPED_NO_RETRY",
            type(error).__name__ + ":" + str(error),
        )
        LOGGER.exception("carrier_diagnostic_stopped")
        for row in rows:
            if row["status"] == "ATTEMPTED":
                row["status"] = "FAILED_OR_CANCELLED"
    finally:
        watchdog.cancel()
        await asyncio.gather(watchdog, return_exceptions=True)
        for worker in list(Q.lifecycle.WORKERS):
            await finish_owned(spawn_owned(worker.close(force=True)))
        after = Q.lifecycle.local_state()
        result.update(
            tts_attempts=attempts,
            combined_actual_attempts=prior["tts_attempts"] + attempts,
            asr_calls=0,
            core_calls=0,
            unattempted=sum(row["status"] == "UNATTEMPTED" for row in rows),
            after=after,
            baseline_restored=after == before,
            preserved_after=Q.lifecycle.verify_originals(),
            owner_ratings=None,
            model_selection=None,
        )
        if before != after:
            result["status"] = "STOPPED_BASELINE_CHANGED"
        Q.assets.publish(root / "campaign-result.json", result)
    return result


def render_page(rows, audio):
    """Display all eight carrier outcomes without hiding missing clips or implying pronunciation success."""
    if (
        len(rows) != 8
        or len({row["id"] for row in rows}) != 8
        or set(audio) - {row["id"] for row in rows}
    ):
        raise ValueError("context_review_coverage")
    cards = []
    for identity, text in CASES:
        for _, voice in Q.VOICES:
            cells = []
            for mode, label in [
                ("with_reference", "Có mã âm thanh tham chiếu"),
                ("without_reference", "Tắt mã tham chiếu, giữ đặc trưng người nói"),
            ]:
                row = next(
                    row
                    for row in rows
                    if row["case"] == identity
                    and row["voice"] == voice
                    and row["mode"] == mode
                )
                raw = audio.get(row["id"])
                player = (
                    "<p>Chưa có clip hoàn chỉnh: " + html.escape(row["status"]) + "</p>"
                    if raw is None
                    else '<audio controls preload="none" src="data:audio/wav;base64,'
                    + base64.b64encode(raw).decode("ascii")
                    + '"></audio>'
                )
                cells.append(
                    "<section><h3>"
                    + label
                    + "</h3><p>"
                    + html.escape(row["id"])
                    + "</p>"
                    + player
                    + "</section>"
                )
            cards.append(
                "<article><h2>"
                + html.escape(identity + " — " + voice)
                + "</h2><p>"
                + html.escape(text)
                + '</p><div class="pair">'
                + "".join(cells)
                + "</div></article>"
            )
    return (
        """<!doctype html>
<!-- Purpose: Local full-sentence API conditioning comparison; no recording, uploads or network. -->
<html lang="vi"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; media-src data:; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<title>D74 — Ei–Pi–Ai trong câu</title><style>body{max-width:1100px;margin:30px auto;padding:0 20px;background:#f8fafb;color:#18232b;font:16px/1.6 system-ui}article{background:white;padding:20px;margin:20px 0;border:1px solid #ccd6dd;border-radius:10px}.pair{display:grid;grid-template-columns:1fr 1fr;gap:20px}audio{width:100%}h2{font-size:20px}h3{font-size:17px}@media(max-width:750px){.pair{grid-template-columns:1fr}}</style>
<h1>D74 — API cần đọc Ei–Pi–Ai</h1><p>Mỗi hàng giữ cùng phoneme và đặc trưng người nói, chỉ đổi việc dùng mã âm thanh tham chiếu preset.
Nghe chữ A có thành Ei không, API còn rè/run không, và chất giọng có thay đổi không. Đây là mẫu chẩn đoán, chưa chọn cấu hình mới.</p>
<p>Bộ A đứng riêng trước đó đã dừng ở một clip thiếu dấu kết thúc; giữ nguyên lỗi, không tăng giới hạn hoặc phát bản cụt như bản đạt.
Các mẫu dưới đây là câu đầy đủ mới trong cohort riêng. Giờ/ngày/ngắt câu đã được bạn xác nhận vẫn giữ nguyên; không thu microphone hoặc kết nối mạng.</p>
"""
        + "".join(cards)
        + "\n</html>\n"
    )


def publish_review(root=ROOT):
    """Independently verify complete native carrier output before creating the local paired listening sheet."""
    rows = json.loads((root / "campaign-result.json").read_text())["rows"]
    audio = {}
    index = []
    for row in rows:
        if row["status"] != "NATIVE_COMPLETE_AWAITING_OWNER_REVIEW":
            continue
        directory = root / row["mode"] / "native"
        Q.lifecycle.read_native(directory, row["id"], row["native"])
        path = directory / (row["id"] + ".wav")
        audio[row["id"]] = path.read_bytes()
        index.append(dict(id=row["id"], sha256=Q.assets.digest(path)))
    directory = root / "review"
    directory.mkdir(mode=0o700)
    with (directory / "index.html").open("xb") as f:
        f.write(render_page(rows, audio).encode())
    Q.assets.publish(
        directory / "index.json",
        dict(
            description="Eight full-carrier slots including missing outcomes; unchanged native WAVs, no owner labels.",
            audio=index,
            page_sha256=Q.assets.digest(directory / "index.html"),
            owner_ratings=None,
        ),
    )
    Q.assets.budget(Q.assets.ROOT)
    LOGGER.info("context_review_published native_audio=%d slots=8", len(audio))
    return directory / "index.html"


def main():
    """Run one new carrier cohort or model-free/local artifact actions while retaining failed initial evidence."""
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
    elif asyncio.run(run())["status"] != "CARRIER_PAIRS_COMPLETE_QUALITY_UNVERIFIED":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
