"""Verify existing Roman/Vietnamese context reading and Python controls without modifying speech policies."""

import argparse
import asyncio
import base64
import html
import json
import logging
import os
import subprocess
import time

from benchmarks.scripts import vi_api_stress_trial as previous
from src.application.services.web_fetch_tasks import finish_owned, spawn_owned

LOGGER = logging.getLogger(__name__)
Q = previous.Q
ROOT = Q.assets.ROOT / "roman-context-first"
CASES = (
    (
        "lower-word",
        "Hành vi vi phạm này cần được kiểm tra.",
        "hành vi vi phạm này cần được kiểm tra.",
        "vi phạm, không phải sáu phạm",
    ),
    (
        "upper-word",
        "VI PHẠM là cụm từ tiếng Việt.",
        "vi phạm là cụm từ tiếng việt.",
        "vi phạm dù viết hoa",
    ),
    ("roman-six", "Chương VI có sáu mục.", "chương sáu có sáu mục.", "chương sáu"),
    (
        "roman-mixed",
        "CHƯƠNG VI nói về hành vi vi phạm.",
        "chương sáu nói về hành vi vi phạm.",
        "chương sáu; hành vi vi phạm",
    ),
    (
        "roman-other",
        "Chương IV và chương IX cần được đọc lại.",
        "chương bốn và chương chín cần được đọc lại.",
        "frontend only: bốn và chín",
    ),
    (
        "identifier",
        "Mã định danh VI phải được giữ nguyên.",
        None,
        "observation only; owner has not specified identifier spelling",
    ),
    (
        "python-context",
        "Bạn muốn học Python hay dùng API của ứng dụng?",
        None,
        "retained mixed-language audio; Python still unacceptable",
    ),
    (
        "python-tag",
        "Bạn muốn học <en>python</en> hay dùng API của ứng dụng?",
        None,
        "frontend-only equivalence control",
    ),
    (
        "python-english",
        "I write code in Python every day.",
        None,
        "Python in a full English sentence; diagnostic, not a fix",
    ),
)
AUDIBLE = frozenset(
    {"lower-word", "upper-word", "roman-six", "roman-mixed", "python-english"}
)
SOURCES = (
    "benchmarks/scripts/vi_roman_context.py",
    "benchmarks/tests/test_vi_roman_context.py",
)
PROBE = '''"""Inspect actual existing clause normalization/G2P/tokenization without weights or added reading rules."""
import json,logging,sys
from pathlib import Path
from sea_g2p import Normalizer,G2P
from tokenizers import Tokenizer
from benchmarks.scripts.vi_speech_prosody import preserving_chunks
from vieneu_utils.core_utils import split_into_sentences,pack_sentences_into_chunks,_classify_gap,max_expected_frames
logging.basicConfig(level=logging.INFO)
request=sys.stdin.buffer.read(16385)
cases=json.loads(request)
if len(request)>16384 or len(cases)!=9:raise ValueError("context_probe_bound")
n,g=Normalizer(lang="vi"),G2P(lang="vi")
t=Tokenizer.from_file("/approved-tokenizer.json")
rows=[]
for identity,text,expected,hint in cases:
 normalized=n.normalize(text,punc_norm=False)
 chunks,gaps=preserving_chunks(text,n.normalize,split_into_sentences,pack_sentences_into_chunks,_classify_gap)
 phones=[g.convert(chunk,punc_norm=False) for chunk in chunks]
 for ph in phones:
  ids=t.encode(ph,add_special_tokens=False).ids
  if t.token_to_id("<|unk|>") in ids or t.decode(ids,skip_special_tokens=False)!=ph:raise ValueError("context_unknown_or_roundtrip")
 rows.append(dict(id=identity,source_text=text,normalized=normalized,chunks=chunks,gaps=gaps,phonemes=phones,frame_caps=[min(300,max_expected_frames(ph)) for ph in phones],unknown_tokens=0))
with Path("/output/frontend.json").open("x") as stream:
 json.dump(dict(description="Original contextual readings and token roundtrip; no new normalization rule or neural inference.",rows=rows,model_calls=0,python_reference=g.convert("<en>python</en>",punc_norm=False)),stream,ensure_ascii=False,indent=2)
 stream.write("\\n")
logging.info("context_frontend_complete cases=9 model_calls=0")
'''


def verify_previous():
    """Preserve twenty-nine prior research files, accepted API evidence and original model/audio artifacts."""
    previous.verify_previous()
    frozen = json.loads((previous.ROOT / "execution-freeze.json").read_text())
    for name, expected in frozen["source_sha256"].items():
        if Q.assets.digest(Q.assets.PROJECT / name) != expected:
            raise ValueError("context_prior_api_source_changed")
    receipt = json.loads(
        (Q.assets.PROJECT / "docs/evidence/d74-api-stress-result.json").read_text()
    )
    for name, expected in receipt["private_sha256"].items():
        if Q.assets.digest(previous.ROOT / name) != expected:
            raise ValueError("context_prior_api_evidence_changed")
    LOGGER.info("context_prior_research_verified files=29")


def probe(root=ROOT):
    """Run the fixed nine-case model-free inspection once under the existing no-weights namespace."""
    root.mkdir(mode=0o700, exist_ok=True)
    directory = root / "probe"
    directory.mkdir(mode=0o700)
    output = directory / "native"
    output.mkdir(mode=0o700)
    request = json.dumps(CASES, ensure_ascii=False).encode()
    (directory / "request.json").write_bytes(request)
    args = previous.previous.original.english.probe_command(output)
    args[-1] = PROBE
    Q.assets.publish(
        directory / "launch.json",
        dict(
            description="Original context frontend only, no weights/network.",
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
                    raise ValueError("context_probe_resource")
                Q.assets.budget(Q.assets.ROOT)
                time.sleep(0.05)
            if process.returncode:
                raise ValueError("context_probe_failed")
        finally:
            Q.assets.terminate(process)
            Q.assets.publish(
                directory / "retirement.json",
                dict(
                    description="Joined no-weights context probe.",
                    returncode=process.returncode,
                    peak_sampled_rss_bytes=peak,
                    wall_seconds=time.monotonic() - started,
                    model_calls=0,
                ),
            )
    return json.loads((output / "frontend.json").read_text())


def packet(frontend):
    """Validate explicit reading targets and freeze ten native slots without adding Roman conversion rules."""
    entries = frontend.get("rows", [])
    if (
        frontend.get("model_calls") != 0
        or len(entries) != len(CASES)
        or {r["id"] for r in entries} != {c[0] for c in CASES}
    ):
        raise ValueError("context_frontend_coverage")
    lookup = {r["id"]: r for r in entries}
    for identity, text, expected, hint in CASES:
        entry = lookup[identity]
        if (
            entry["source_text"] != text
            or entry["unknown_tokens"] != 0
            or (expected is not None and entry["normalized"] != expected)
        ):
            raise ValueError("context_expected_reading_or_source")
        if identity in AUDIBLE and (
            len(entry["chunks"]) != 1
            or entry["gaps"]
            or len(entry["phonemes"]) != 1
            or len(entry["frame_caps"]) != 1
        ):
            raise ValueError("context_single_chunk_required")
    if (
        lookup["python-context"]["phonemes"] != lookup["python-tag"]["phonemes"]
        or frontend["python_reference"] != "pˈaɪθən"
        or not all(
            frontend["python_reference"] in " ".join(lookup[key]["phonemes"])
            for key in ("python-context", "python-tag", "python-english")
        )
    ):
        raise ValueError("context_python_reference_or_tag_equivalence")
    rows = [
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
    LOGGER.info(
        "context_packet_bound native_slots=10 frontend_cases=9 unambiguous_roman_targets=5"
    )
    return rows


def verify_native(row, native, directory):
    """Require actual old worker traces to match the frozen context and genuine chunk bytes."""
    observed, expected = native["prosody_trace"], row["frontend"]
    if (
        any(observed[key] != expected[key] for key in ("chunks", "gaps", "phonemes"))
        or len(native["chunks"]) != 1
    ):
        raise ValueError("context_native_provenance")
    if (
        not native["generation_complete"]
        or native["chunks"][0]["eos"] is not True
        or native["chunks"][0]["frames"] > expected["frame_caps"][0]
    ):
        raise ValueError("context_native_completeness_or_cap")
    raw = (directory / f"{row['id']}-chunk-0.f32").read_bytes()
    if Q.lifecycle.sha(raw) != observed["native_chunk_sha256"][0]:
        raise ValueError("context_native_chunk_hash")
    LOGGER.info("context_native_verified id=%s", row["id"])


async def run(root=ROOT):
    """Generate ten original-policy controls once with no retries, retaining first failures and joined cleanup."""
    if (root / "execution-freeze.json").exists():
        raise ValueError("context_already_attempted")
    authority = Q.assets.PROJECT / "docs/evidence/d74-roman-context-authorization.json"
    if json.loads(authority.read_text()).get("authorized") is not True:
        raise ValueError("context_authorization")
    verify_previous()
    Q.lifecycle.prepared_integrity(Q.assets.ROOT)
    originals = Q.lifecycle.verify_originals()
    before = Q.lifecycle.local_state()
    if before["native_pids"]:
        raise ValueError("context_baseline_busy")
    frontend = root / "probe/native/frontend.json"
    rows = packet(json.loads(frontend.read_text()))
    hashes = {name: Q.assets.digest(Q.assets.PROJECT / name) for name in SOURCES}
    software = json.loads((root / "software-verification.json").read_text())
    if software.get("status") != "PASS" or software.get("source_sha256") != hashes:
        raise ValueError("context_software_binding")
    Q.assets.publish(
        root / "execution-freeze.json",
        dict(
            description="Existing context behavior only, ten fixed requests, no reading/model/policy changes.",
            source_sha256=hashes,
            authority_sha256=Q.assets.digest(authority),
            frontend_sha256=Q.assets.digest(frontend),
            software=software,
            before=before,
            originals=originals,
            rows=rows,
            limits=dict(
                tts=10,
                inner_chunks=10,
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
        description="Existing context controls, no acoustic quality labels.",
        rows=rows,
        status="STARTED",
    )
    try:
        await worker.start()
        for row in rows:
            if attempts >= 10 or chunks >= 10:
                raise ValueError("context_budget")
            attempts += 1
            row["status"] = "ATTEMPTED"
            native = await worker.call(
                dict(
                    op="synthesize",
                    id=row["id"],
                    voice=row["voice"],
                    text=row["source_text"],
                )
            )
            row["native"] = native
            chunks += len(native["chunks"])
            verify_native(row, native, root / "worker/native")
            row["status"] = "NATIVE_COMPLETE_AWAITING_OWNER_REVIEW"
        result["status"] = "CONTEXT_CONTROLS_COMPLETE_ACOUSTIC_UNVERIFIED"
    except BaseException as error:
        result.update(
            status="STOPPED_NO_RETRY", error=type(error).__name__ + ":" + str(error)
        )
        LOGGER.exception("context_stopped")
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


def render_review(rows, audio, references):
    """Keep all context slots and label old Python/API examples as retained different-context references."""
    if (
        len(rows) != 10
        or len({r["id"] for r in rows}) != 10
        or set(audio) - {r["id"] for r in rows}
    ):
        raise ValueError("context_review_coverage")
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
    for identity, content in references.items():
        cards.append(
            "<article><h2>Clip cũ giữ nguyên — "
            + html.escape(identity)
            + '</h2><p>Bạn muốn học Python hay dùng API của ứng dụng?</p><p>API đã được xác nhận đọc đúng trên bộ trước; Python vẫn chưa đạt. Đây là tham chiếu khác ngữ cảnh so với câu tiếng Anh mới, không phải bằng chứng sửa Python.</p><audio controls preload="none" src="data:audio/wav;base64,'
            + base64.b64encode(content).decode()
            + '"></audio></article>'
        )
    return (
        """<!doctype html>
<!-- Purpose: Local Roman/Vietnamese context and English Python listening controls, no recording or uploads. -->
<html lang="vi"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; media-src data:; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<title>D74 — vi phạm và chương VI</title><style>body{max-width:950px;margin:30px auto;padding:0 20px;font:16px/1.6 system-ui;background:#f8fafb;color:#18232b}article{background:white;padding:18px;margin:16px 0;border:1px solid #ccd6dd}audio{width:100%}h2{font-size:19px}</style>
<h1>vi phạm / Chương VI / Python</h1><p>Đang kiểm tra cách đọc hiện có, không thêm luật chuyển VI thành số và không thay model.
Chữ vi trong vi phạm cần giữ là vi; Chương VI cần đọc chương sáu. Nhận xét theo mã câu và giọng nếu nghe sai.</p>
<p>Python trong câu tiếng Anh là control ngữ cảnh mới, chưa phải bản sửa. API và ngày/giờ đã được chấp nhận theo phạm vi trước giữ nguyên. Trang không thu microphone hoặc gửi dữ liệu ra ngoài.</p>"""
        + "".join(cards)
        + "\n</html>\n"
    )


def publish_review(root=ROOT):
    """Verify genuine current WAVs and untouched prior Python/API examples before creating local media."""
    rows = json.loads((root / "campaign-result.json").read_text())["rows"]
    audio, references = {}, {}
    for row in rows:
        if row["status"] == "NATIVE_COMPLETE_AWAITING_OWNER_REVIEW":
            directory = root / "worker/native"
            Q.lifecycle.read_native(directory, row["id"], row["native"])
            verify_native(row, row["native"], directory)
            audio[row["id"]] = (directory / (row["id"] + ".wav")).read_bytes()
    old = json.loads((previous.ROOT / "campaign-result.json").read_text())["rows"]
    for row in old:
        if row["case"] == "english-01":
            directory = previous.ROOT / "worker/native"
            Q.lifecycle.read_native(directory, row["id"], row["native"])
            references[row["id"]] = (directory / (row["id"] + ".wav")).read_bytes()
    directory = root / "review"
    directory.mkdir(mode=0o700)
    with (directory / "index.html").open("xb") as stream:
        stream.write(render_review(rows, audio, references).encode())
    Q.assets.publish(
        directory / "index.json",
        dict(
            description="Ten declared native context slots and two unchanged prior mixed Python/API references, no acoustic labels.",
            page_sha256=Q.assets.digest(directory / "index.html"),
            audio={k: Q.lifecycle.sha(v) for k, v in audio.items()},
            references={k: Q.lifecycle.sha(v) for k, v in references.items()},
            owner_ratings=None,
        ),
    )
    Q.assets.budget(Q.assets.ROOT)
    LOGGER.info(
        "context_review_published native=%d references=%d", len(audio), len(references)
    )


def main():
    """Run only the explicit model-free probe, one frozen context study or retained-media publication."""
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
        asyncio.run(run())["status"] != "CONTEXT_CONTROLS_COMPLETE_ACOUSTIC_UNVERIFIED"
    ):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
