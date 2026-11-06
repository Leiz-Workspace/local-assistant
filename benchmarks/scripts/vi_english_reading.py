"""Restore English terms in the owner-preferred speech path and own a small existing-weight comparison."""

import argparse
import base64
import html
import asyncio
import hashlib
import json
import logging
import os
import subprocess
import time
from dataclasses import asdict, replace

from benchmarks.scripts import vi_speech_quality as quality
from benchmarks.scripts.vi_speech_text import render_speech
from src.application.services.web_fetch_tasks import finish_owned, spawn_owned

LOGGER = logging.getLogger(__name__)
ROOT = quality.assets.ROOT / "english-reading-first"
CASES = (
    ("english-01", "Bạn muốn học Python hay dùng API của ứng dụng?"),
    ("english-02", "Chị đang kiểm tra Python; API sẽ sẵn sàng sau ít phút."),
    ("english-03", "Python giúp xử lý dữ liệu; API kết nối các ứng dụng."),
    ("english-04", "Chị sẽ nhắc bạn lúc 09:15 ngày 14/11; sau đó cùng kiểm tra API."),
)
PROBE_SOURCE = '''"""Inspect English phonemes and tokenizer coverage without loading neural weights."""
import json,logging,sys
from pathlib import Path
from sea_g2p import Normalizer,G2P
from tokenizers import Tokenizer
logging.basicConfig(level=logging.INFO)
request=sys.stdin.buffer.read(32769)
if len(request)>32768:raise ValueError("english_probe_bound")
texts=json.loads(request)
if type(texts) is not list or len(texts)!=8:raise ValueError("english_probe_count")
n,g=Normalizer(lang="vi"),G2P(lang="vi")
t=Tokenizer.from_file("/approved-tokenizer.json")
unknown=t.token_to_id("<|unk|>")
references={"Python":g.convert("<en>python</en>",punc_norm=False),"API":g.convert("<en>a p i</en>",punc_norm=False)}
rows=[]
for text in texts:
 if type(text) is not str or len(text.encode())>512:raise ValueError("english_probe_text")
 normalized=n.normalize(text,punc_norm=False)
 phonemes=g.convert(normalized,punc_norm=False)
 ids=t.encode(phonemes,add_special_tokens=False).ids
 required=[term for term in references if term in text]
 rows.append(dict(speech_text=text,normalized=normalized,phonemes=phonemes,unknown_tokens=ids.count(unknown),english_references_present={term:references[term] in phonemes for term in required}))
with Path("/output/frontend.json").open("x") as stream:
 json.dump(dict(description="English frontend/tokenizer probe only; no neural weights or inference.",references=references,rows=rows,model_calls=0),stream,ensure_ascii=False,indent=2)
 stream.write("\\n")
logging.info("english_frontend_probe_complete rows=%d model_calls=0",len(rows))
'''


def render_english(text):
    """Keep accepted date/clause edits while removing only the experimental Vietnamese term substitutions."""
    started = time.perf_counter()
    previous = render_speech(text, "clauses")
    edits = tuple(edit for edit in previous.edits if edit.kind != "lexicon")
    cursor, parts = 0, []
    for edit in edits:
        parts.extend((text[cursor : edit.start], edit.spoken))
        cursor = edit.end
    parts.append(text[cursor:])
    speech = "".join(parts)
    result = replace(
        previous,
        speech_text=speech,
        speech_sha256=hashlib.sha256(speech.encode()).hexdigest(),
        policy="clauses_english",
        policy_version="vi-english-research-1",
        edits=edits,
        render_seconds=time.perf_counter() - started,
    )
    LOGGER.info(
        "english_speech_rendered edits=%d source_sha256=%s speech_sha256=%s",
        len(edits),
        result.source_sha256,
        result.speech_sha256,
    )
    return result


def rows():
    """Fix eight first-attempt voice/case slots without selecting a voice from observed outcomes."""
    return [
        dict(
            id=f"{label}-{identity}",
            case=identity,
            voice=voice,
            profile="clauses",
            render=asdict(render_english(text)),
            status="UNATTEMPTED",
        )
        for label, voice in quality.VOICES
        for identity, text in CASES
    ]


def verify_preferred_code():
    """Require the accepted comparison's ten original files and the seven older operators to remain unchanged."""
    frozen = json.loads((quality.ROOT / "execution-freeze.json").read_text())[
        "source_sha256"
    ]
    for name, expected in frozen.items():
        if quality.assets.digest(quality.assets.PROJECT / name) != expected:
            raise ValueError("preferred_processing_code_changed")
    quality.verify_retained_operators()
    LOGGER.info("preferred_processing_verified files=%d", len(frozen))
    return frozen


def probe_command(output):
    """Expose only the approved text tokenizer, public SDK and probe program without model weights or network."""
    command = quality.command(output, "raw", probe=True)
    insertion = command.index("--remount-ro")
    tokenizer = (
        quality.assets.ROOT
        / "models/models--pnnbao-ump--VieNeu-TTS-v3-Turbo/snapshots/61b85e3d937fbbacb387714180e8182823512523/onnx_update/tokenizer.json"
    )
    command[insertion:insertion] = [
        "--ro-bind",
        str(tokenizer),
        "/approved-tokenizer.json",
    ]
    start = command.index("/venv/bin/python")
    return command[:start] + ["/venv/bin/python", "-c", PROBE_SOURCE]


def probe(root=ROOT):
    """Run one bounded model-free English frontend diagnostic with preserved process and output evidence."""
    root.mkdir(mode=0o700)
    directory = root / "probe"
    directory.mkdir(mode=0o700)
    output = directory / "native"
    output.mkdir(mode=0o700)
    request = json.dumps(
        [row["render"]["speech_text"] for row in rows()], ensure_ascii=False
    ).encode()
    (directory / "request.json").write_bytes(request)
    command = probe_command(output)
    quality.assets.publish(
        directory / "launch.json",
        dict(
            description="One English phoneme/tokenizer inspection, no neural inference or weights.",
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
                        quality.lifecycle.rss_bytes(pid)
                        for pid in quality.lifecycle.process_tree(process.pid)
                    ),
                )
                if peak > 2 * quality.lifecycle.GIB or time.monotonic() - started > 60:
                    raise ValueError("english_probe_rss_or_wall")
                quality.assets.budget(quality.assets.ROOT)
                time.sleep(0.05)
            if process.returncode:
                raise ValueError("english_probe_failed")
        finally:
            quality.assets.terminate(process)
            quality.assets.publish(
                directory / "retirement.json",
                dict(
                    description="Joined model-free English probe.",
                    returncode=process.returncode,
                    peak_sampled_rss_bytes=peak,
                    wall_seconds=time.monotonic() - started,
                    model_calls=0,
                ),
            )
    result = json.loads((output / "frontend.json").read_text())
    if len(result["rows"]) != 8 or any(
        row["unknown_tokens"] or not all(row["english_references_present"].values())
        for row in result["rows"]
    ):
        raise ValueError("english_frontend_or_tokenizer_failed")
    return result


async def run(root=ROOT):
    """Generate exactly eight new English-preserving candidates without repeating or changing the accepted path."""
    if (root / "execution-freeze.json").exists():
        raise ValueError("english_trial_already_attempted")
    authorization = json.loads(
        (
            quality.assets.PROJECT
            / "docs/evidence/d74-english-reading-authorization.json"
        ).read_text()
    )
    if authorization.get("authorized") is not True:
        raise ValueError("english_trial_authorization")
    retained = verify_preferred_code()
    quality.lifecycle.prepared_integrity(quality.assets.ROOT)
    preserved = quality.lifecycle.verify_originals()
    before = quality.lifecycle.local_state()
    packet = rows()
    files = [
        quality.assets.PROJECT / "benchmarks/scripts/vi_english_reading.py",
        quality.assets.PROJECT / "benchmarks/tests/test_vi_english_reading.py",
    ]
    hashes = {
        str(path.relative_to(quality.assets.PROJECT)): quality.assets.digest(path)
        for path in files
    }
    software = json.loads((root / "software-verification.json").read_text())
    if software.get("status") != "PASS" or software.get("operator_sha256") != hashes:
        raise ValueError("english_software_freeze")
    frontend = root / "probe/native/frontend.json"
    if not frontend.is_file():
        raise ValueError("english_probe_required")
    probe_result = json.loads(frontend.read_text())
    if len(probe_result["rows"]) != 8 or any(
        row["unknown_tokens"] or not all(row["english_references_present"].values())
        for row in probe_result["rows"]
    ):
        raise ValueError("english_frontend_gate")
    if [item.get("speech_text") for item in probe_result["rows"]] != [
        row["render"]["speech_text"] for row in packet
    ]:
        raise ValueError("english_probe_input_changed")
    quality.assets.publish(
        root / "execution-freeze.json",
        dict(
            description="New input-only English-preserving variant; retained accepted renderer/prosody code and samples remain immutable.",
            source_sha256=hashes,
            preferred_code_sha256=retained,
            authorization_sha256=quality.assets.digest(
                quality.assets.PROJECT
                / "docs/evidence/d74-english-reading-authorization.json"
            ),
            software=software,
            frontend_sha256=quality.assets.digest(frontend),
            before=before,
            preserved=preserved,
            rows=packet,
            limits=dict(
                tts_calls=8,
                asr_calls=0,
                core_calls=0,
                retries=0,
                wall_seconds=600,
                worker_as_gib=8,
                tts_sampled_rss_gib=2,
                headroom_gib=14,
                parent_root_gib=8,
            ),
        ),
    )
    deadline, attempts = time.monotonic() + 600, 0
    quality.lifecycle.FAILURES.clear()
    watchdog = asyncio.create_task(
        quality.lifecycle.monitor_campaign(
            quality.assets.ROOT, deadline, asyncio.current_task()
        )
    )
    worker = quality.QualityWorker("clauses", root / "worker", deadline)
    result = dict(
        description="New English-preserving candidates, not a pass for pronunciation or API buzz.",
        status="STARTED",
        rows=packet,
    )
    try:
        await worker.start()
        for row in packet:
            if attempts >= 8:
                raise ValueError("english_call_ceiling")
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
            row.update(status="NATIVE_COMPLETE_AWAITING_OWNER_REVIEW", native=native)
        result["status"] = "ENGLISH_CANDIDATES_COMPLETE_QUALITY_UNVERIFIED"
    except BaseException as error:
        result["status"], result["error"] = (
            "STOPPED_NO_RETRY",
            type(error).__name__ + ":" + str(error),
        )
        LOGGER.exception("english_trial_stopped")
        for row in packet:
            if row["status"] == "ATTEMPTED":
                row["status"] = "FAILED_OR_CANCELLED"
    finally:
        await finish_owned(spawn_owned(worker.close(force=bool(worker.failure))))
        watchdog.cancel()
        await asyncio.gather(watchdog, return_exceptions=True)
        after = quality.lifecycle.local_state()
        result.update(
            tts_attempts=attempts,
            asr_calls=0,
            core_calls=0,
            unattempted=sum(row["status"] == "UNATTEMPTED" for row in packet),
            after=after,
            baseline_restored=before == after,
            preserved_after=quality.lifecycle.verify_originals(),
            owner_ratings=None,
            model_selection=None,
            physical_first_audible="UNVERIFIED",
        )
        if after != before:
            result["status"] = "STOPPED_BASELINE_CHANGED"
        quality.assets.publish(root / "campaign-result.json", result)
    return result


def render_review(packet, audio, baseline):
    """Render eight candidate slots and only exact retained target baselines without modifying native bytes."""
    identities = {row["id"] for row in packet}
    if (
        len(packet) != 8
        or len(identities) != 8
        or (set(audio) | set(baseline)) - identities
    ):
        raise ValueError("english_review_coverage")
    cards = []
    for row in packet:
        cells = []
        for title, content in [
            ("Bản trước: âm tiết Việt", baseline.get(row["id"])),
            ("Bản mới: giữ tiếng Anh", audio.get(row["id"])),
        ]:
            if content is None:
                player = (
                    "<p>Không có bản đối chứng cùng câu.</p>"
                    if title.startswith("Bản trước")
                    else "<p>Chưa có clip hoàn chỉnh: "
                    + html.escape(row["status"])
                    + "</p>"
                )
            else:
                encoded = base64.b64encode(content).decode("ascii")
                player = (
                    '<audio controls preload="none" src="data:audio/wav;base64,'
                    + encoded
                    + '"></audio>'
                )
            cells.append("<section><h3>" + title + "</h3>" + player + "</section>")
        cards.append(
            "<article><h2>"
            + html.escape(row["id"] + " — " + row["voice"])
            + "</h2><p>"
            + html.escape(row["render"]["source_text"])
            + '</p><div class="pair">'
            + "".join(cells)
            + "</div></article>"
        )
    return (
        """<!doctype html>
<!-- Purpose: Local unchanged English-pronunciation candidates and retained exact baselines; no recording or network. -->
<html lang="vi"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; media-src data:; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<title>D74 — Kiểm tra Python và API</title>
<style>body{max-width:1000px;margin:30px auto;padding:0 20px;background:#f8fafb;color:#18232b;font:16px/1.6 system-ui}article{padding:20px;margin:20px 0;border:1px solid #ccd6dd;border-radius:10px;background:white}.pair{display:grid;grid-template-columns:1fr 1fr;gap:20px}audio{width:100%}h2{font-size:20px}h3{font-size:17px}@media(max-width:700px){.pair{grid-template-columns:1fr}}</style>
<h1>D74 — Python và API</h1><p>Bản mới giữ cách ngắt câu và đọc giờ/ngày bạn vừa thích; bỏ cách ghi âm tiết Việt cho Python/API.
Hai câu đầu có đối chứng lấy nguyên từ bộ trước. Hai câu sau là câu thử mới, không có đối chứng cùng câu.</p>
<p>Nghe xem Python đã giống tiếng Anh chưa; API có còn rè/run không. Chưa có kết luận rằng bản mới đã hết lỗi.
Bạn có thể gửi nhận xét theo mã câu và giọng trong chat. Trang không thu microphone hoặc gửi dữ liệu ra ngoài.</p>
"""
        + "".join(cards)
        + "\n</html>\n"
    )


def publish_review(root=ROOT):
    """Verify and embed new candidate audio beside four unchanged, exactly matched earlier preferred clips."""
    result = json.loads((root / "campaign-result.json").read_text())
    prior = json.loads((quality.ROOT / "campaign-result.json").read_text())["rows"]
    audio, baseline, index = {}, {}, []
    matched = {"english-01": "reading-04", "english-02": "reading-05"}
    for row in result["rows"]:
        if row["status"] == "NATIVE_COMPLETE_AWAITING_OWNER_REVIEW":
            directory = root / "worker/native"
            quality.lifecycle.read_native(directory, row["id"], row["native"])
            path = directory / (row["id"] + ".wav")
            audio[row["id"]] = path.read_bytes()
            index.append(
                dict(
                    id=row["id"],
                    role="new_candidate",
                    sha256=quality.assets.digest(path),
                )
            )
        if row["case"] in matched:
            old = next(
                item
                for item in prior
                if item["profile"] == "clauses"
                and item["case"] == matched[row["case"]]
                and item["voice"] == row["voice"]
            )
            if old["render"]["source_text"] != row["render"]["source_text"]:
                raise ValueError("english_baseline_text_mismatch")
            directory = quality.ROOT / "profile-clauses/native"
            quality.lifecycle.read_native(directory, old["id"], old["native"])
            path = directory / (old["id"] + ".wav")
            baseline[row["id"]] = path.read_bytes()
            index.append(
                dict(
                    id=row["id"],
                    role="retained_baseline",
                    old_id=old["id"],
                    sha256=quality.assets.digest(path),
                )
            )
    directory = root / "review"
    directory.mkdir(mode=0o700)
    with (directory / "index.html").open("xb") as stream:
        stream.write(render_review(result["rows"], audio, baseline).encode())
    quality.assets.publish(
        directory / "index.json",
        dict(
            description="Eight new English candidates and four retained exact baselines; no new subjective labels.",
            audio=index,
            page_sha256=quality.assets.digest(directory / "index.html"),
            owner_ratings=None,
        ),
    )
    quality.assets.budget(quality.assets.ROOT)
    LOGGER.info(
        "english_review_published new_audio=%d retained_baseline=%d",
        len(audio),
        len(baseline),
    )
    return directory / "index.html"


def main():
    """Run either model-free investigation or one bounded same-model English correction panel."""
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
    else:
        result = asyncio.run(run())
        if result["status"] != "ENGLISH_CANDIDATES_COMPLETE_QUALITY_UNVERIFIED":
            raise SystemExit(1)


if __name__ == "__main__":
    main()
