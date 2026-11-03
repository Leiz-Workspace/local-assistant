"""Own a sixteen-clip paired reference-conditioning diagnostic on existing Vietnamese TTS weights."""

import argparse
import asyncio
import base64
import html
import json
import logging
import os
import subprocess
import time

from benchmarks.scripts import vi_english_reading as english
from src.application.services.web_fetch_tasks import finish_owned, spawn_owned

LOGGER = logging.getLogger(__name__)
Q = english.quality
ROOT = Q.assets.ROOT / "api-reference-first"
MODES = ("with_reference", "without_reference")
CASES = (
    ("letter-a", "A.", "Ei"),
    ("api-spaced", "API.", "Ei–Pi–Ai, chuỗi từng chữ"),
    ("api-compact", "API.", "Ei–Pi–Ai, chuỗi từ điển"),
    ("api-context", "Chị sẽ kiểm tra API.", "Chị sẽ kiểm tra Ei–Pi–Ai."),
)

PROBE = '''"""Verify exact English phonemes and token roundtrips without neural weights."""
import json,logging,sys
from pathlib import Path
from sea_g2p import Normalizer,G2P
from tokenizers import Tokenizer
logging.basicConfig(level=logging.INFO)
raw=sys.stdin.buffer.read(16385)
if len(raw)>16384:raise ValueError("reference_probe_bound")
request=json.loads(raw)
if len(request)!=4:raise ValueError("reference_probe_count")
n,g=Normalizer(lang="vi"),G2P(lang="vi")
t=Tokenizer.from_file("/approved-tokenizer.json")
reference_api=g.convert("<en>a p i</en>",punc_norm=False)
reference_a=reference_api.split()[0]
if reference_a!="ˈeɪ":raise ValueError("reference_english_A")
rows=[]
for case in request:
 normalized=n.normalize(case["text"],punc_norm=False)
 native_phonemes=g.convert(normalized,punc_norm=False)
 phonemes=reference_a+"." if case["id"]=="letter-a" else reference_api+"." if case["id"]=="api-spaced" else native_phonemes
 ids=t.encode(phonemes,add_special_tokens=False).ids
 decoded=t.decode(ids,skip_special_tokens=False)
 needed=reference_a if case["id"]=="letter-a" else native_phonemes if case["id"]=="api-compact" else reference_api
 if needed not in phonemes or t.token_to_id("<|unk|>") in ids or decoded!=phonemes:raise ValueError("reference_probe_english_or_roundtrip")
 rows.append(dict(id=case["id"],source_text=case["text"],normalized=normalized,native_g2p_phonemes=native_phonemes,phonemes=phonemes,token_ids=ids,decoded=decoded,unknown_tokens=0))
with Path("/output/frontend.json").open("x") as stream:
 json.dump(dict(description="English minimal-control frontend; no neural forwards.",rows=rows,reference_a=reference_a,reference_api=reference_api,model_calls=0),stream,ensure_ascii=False,indent=2)
 stream.write("\\n")
logging.info("reference_probe_complete rows=4 neural_calls=0")
'''


def verify_previous():
    """Verify all nineteen prior research files without changing any previously accepted processing."""
    previous = english.verify_preferred_code()
    latest = json.loads((english.ROOT / "execution-freeze.json").read_text())[
        "source_sha256"
    ]
    for name, expected in latest.items():
        if Q.assets.digest(Q.assets.PROJECT / name) != expected:
            raise ValueError("english_operator_changed")
    LOGGER.info(
        "reference_predecessors_verified preferred=10 older=7 english=%d", len(latest)
    )
    return dict(preferred=previous, english=latest)


def native_command(output, mode):
    """Reuse the original isolated CPU namespace with only a new bounded reference-control worker."""
    if mode not in MODES:
        raise ValueError("reference_mode")
    command = Q.command(output, "raw")
    index = command.index("--remount-ro")
    command[index:index] = [
        "--ro-bind",
        str(Q.assets.PROJECT / "benchmarks/scripts/vi_api_reference_worker.py"),
        "/app/reference_worker.py",
    ]
    command[-2:] = ["/app/reference_worker.py", mode]
    return command


def probe(root=ROOT):
    """Run one model-free four-case token/phoneme audit under the existing namespace and limits."""
    root.mkdir(mode=0o700, exist_ok=True)
    directory = root / "accepted-probe"
    directory.mkdir(mode=0o700)
    output = directory / "native"
    output.mkdir(mode=0o700)
    command = english.probe_command(output)
    command[-1] = PROBE
    request = json.dumps(
        [dict(id=identity, text=text) for identity, text, _ in CASES],
        ensure_ascii=False,
    ).encode()
    (directory / "request.json").write_bytes(request)
    Q.assets.publish(
        directory / "launch.json",
        dict(
            description="One model-free reference diagnostic; approved tokenizer only, no neural weights.",
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
                    raise ValueError("reference_probe_rss_or_wall")
                Q.assets.budget(Q.assets.ROOT)
                time.sleep(0.05)
            if process.returncode:
                raise ValueError("reference_probe_failed")
        finally:
            Q.assets.terminate(process)
            Q.assets.publish(
                directory / "retirement.json",
                dict(
                    description="Joined model-free reference probe.",
                    returncode=process.returncode,
                    peak_sampled_rss_bytes=peak,
                    wall_seconds=time.monotonic() - started,
                    model_calls=0,
                ),
            )
    return json.loads((output / "frontend.json").read_text())


class ReferenceWorker(Q.lifecycle.Worker):
    """Reuse tested original request/guard/retirement behavior with an explicit reference-condition startup."""

    def __init__(self, mode, directory, deadline):
        """Bind one fixed ablation with unchanged model and resource authority."""
        super().__init__("turbo", directory, deadline)
        self.mode = mode

    async def start(self):
        """Load exactly one owned sealed CPU runtime under retained headroom and readiness binding."""
        if (
            self.process is not None
            or Q.lifecycle.mem_available() < 14 * Q.lifecycle.GIB
            or not {0, 1} <= os.sched_getaffinity(0)
        ):
            self.failure = "reference_preflight"
            raise ValueError(self.failure)
        self.directory.mkdir(mode=0o700)
        output = self.directory / "native"
        output.mkdir(mode=0o700)
        self.started = time.monotonic()
        self.log = (self.directory / "stderr.log").open("xb")
        command = native_command(output, self.mode)
        Q.assets.publish(
            self.directory / "launch.json",
            dict(
                description="One retained-model reference condition; no retry.",
                command=command,
                available_ram=Q.lifecycle.mem_available(),
            ),
        )
        self.process = await asyncio.create_subprocess_exec(
            *command,
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
                description="Exact owned reference worker process.",
                pid=self.process.pid,
            ),
        )
        Q.lifecycle.WORKERS.add(self)
        try:
            self.ready = await self.receive()
            if (
                self.ready.get("event") != "ready"
                or self.ready.get("candidate") != "turbo"
                or self.ready.get("mode") != self.mode
            ):
                raise ValueError("reference_ready_binding")
        except BaseException as error:
            self.failure = type(error).__name__ + ":" + str(error)
            await finish_owned(spawn_owned(self.close(force=True)))
            raise
        LOGGER.info("reference_worker_ready mode=%s", self.mode)
        return self


def packet(frontend):
    """Declare every case/voice/ref-condition slot with identical phonemes and visible unattempted outcomes."""
    if len(frontend["rows"]) != 4 or {row["id"] for row in frontend["rows"]} != {
        row[0] for row in CASES
    }:
        raise ValueError("reference_frontend_coverage")
    if (
        frontend.get("reference_a") != "ˈeɪ"
        or frontend.get("reference_api") != "ˈeɪ pˈiː ˈaɪ"
    ):
        raise ValueError("reference_english_target")
    lookup = {row["id"]: row for row in frontend["rows"]}
    for identity, text, _ in CASES:
        row = lookup[identity]
        needed = (
            frontend["reference_a"]
            if identity == "letter-a"
            else row["native_g2p_phonemes"]
            if identity == "api-compact"
            else frontend["reference_api"]
        )
        if (
            row["source_text"] != text
            or row["decoded"] != row["phonemes"]
            or row["unknown_tokens"] != 0
            or needed not in row["phonemes"]
        ):
            raise ValueError("reference_frontend_binding")
    return [
        dict(
            id=f"{mode}-{label}-{identity}",
            case=identity,
            voice=voice,
            mode=mode,
            source_text=text,
            expected_spoken=expected,
            phonemes=lookup[identity]["phonemes"],
            status="UNATTEMPTED",
        )
        for mode in MODES
        for label, voice in Q.VOICES
        for identity, text, expected in CASES
    ]


def verify_pairs(rows):
    """Require identical actual speaker anchors and text tokens across all eight paired ablations."""
    if len(rows) != 16 or any(
        row["status"] != "NATIVE_COMPLETE_AWAITING_OWNER_REVIEW" for row in rows
    ):
        raise ValueError("reference_pair_coverage")
    for identity, _, _ in CASES:
        for _, voice in Q.VOICES:
            pair = [
                row for row in rows if row["case"] == identity and row["voice"] == voice
            ]
            if len(pair) != 2 or {row["mode"] for row in pair} != set(MODES):
                raise ValueError("reference_pair_identity")
            left, right = [row["native"]["reference_trace"] for row in pair]
            for key in [
                "phonemes",
                "token_ids",
                "speaker_embedding_sha256",
                "projected_anchor_sha256",
                "prompt_text_ids",
            ]:
                if left[key] != right[key]:
                    raise ValueError("reference_pair_changed_" + key)
            for row in pair:
                trace = row["native"]["reference_trace"]
                enabled = row["mode"] == "with_reference"
                if (
                    trace["use_ref_codes"] is not enabled
                    or (trace["reference_rows"] > 0) is not enabled
                ):
                    raise ValueError("reference_pair_audio_condition")
    LOGGER.info("reference_pairs_verified pairs=8 identical_speaker_and_text=True")


async def run(root=ROOT):
    """Execute one frozen sixteen-call paired ablation, stopping on first failure without promoting a condition."""
    if (root / "execution-freeze.json").exists():
        raise ValueError("reference_trial_already_attempted")
    authority = Q.assets.PROJECT / "docs/evidence/d74-api-reference-authorization.json"
    if json.loads(authority.read_text()).get("authorized") is not True:
        raise ValueError("reference_authorization")
    predecessors = verify_previous()
    Q.lifecycle.prepared_integrity(Q.assets.ROOT)
    original = Q.lifecycle.verify_originals()
    before = Q.lifecycle.local_state()
    frontend = root / "accepted-probe/native/frontend.json"
    rows = packet(json.loads(frontend.read_text()))
    files = [
        *Q.assets.PROJECT.glob("benchmarks/scripts/vi_api_reference_*.py"),
        *Q.assets.PROJECT.glob("benchmarks/tests/test_vi_api_reference_*.py"),
    ]
    hashes = {str(p.relative_to(Q.assets.PROJECT)): Q.assets.digest(p) for p in files}
    software = json.loads((root / "software-verification.json").read_text())
    if software["status"] != "PASS" or software["source_sha256"] != hashes:
        raise ValueError("reference_software_freeze")
    Q.assets.publish(
        root / "execution-freeze.json",
        dict(
            description="New same-model paired reference conditioning diagnostic; no production/voice adoption.",
            source_sha256=hashes,
            predecessors=predecessors,
            authority_sha256=Q.assets.digest(authority),
            frontend_sha256=Q.assets.digest(frontend),
            software=software,
            before=before,
            preserved=original,
            rows=rows,
            limits=dict(
                tts_calls=16,
                asr_calls=0,
                core_calls=0,
                retries=0,
                AS_gib=8,
                tts_sampled_RSS_gib=2,
                aggregate_gib=8,
                headroom_gib=14,
                parent_root_gib=8,
                wall_seconds=600,
            ),
        ),
    )
    deadline, attempts = time.monotonic() + 600, 0
    Q.lifecycle.FAILURES.clear()
    watchdog = asyncio.create_task(
        Q.lifecycle.monitor_campaign(Q.assets.ROOT, deadline, asyncio.current_task())
    )
    result = dict(
        description="Reference-condition acoustic diagnostic; correct tokens and different audio are not English-pronunciation PASS.",
        status="STARTED",
        rows=rows,
    )
    try:
        for mode in MODES:
            worker = ReferenceWorker(mode, root / mode, deadline)
            try:
                await worker.start()
                for row in (row for row in rows if row["mode"] == mode):
                    if attempts >= 16:
                        raise ValueError("reference_call_ceiling")
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
                        or trace["use_ref_codes"] != (mode == "with_reference")
                    ):
                        raise ValueError("reference_actual_input_binding")
                    row.update(
                        status="NATIVE_COMPLETE_AWAITING_OWNER_REVIEW", native=value
                    )
            finally:
                await finish_owned(
                    spawn_owned(worker.close(force=bool(worker.failure)))
                )
        verify_pairs(rows)
        result["status"] = "PAIRED_DIAGNOSTIC_COMPLETE_QUALITY_UNVERIFIED"
    except BaseException as error:
        result["status"], result["error"] = (
            "STOPPED_NO_RETRY",
            type(error).__name__ + ":" + str(error),
        )
        LOGGER.exception("reference_diagnostic_stopped")
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
            asr_calls=0,
            core_calls=0,
            unattempted=sum(row["status"] == "UNATTEMPTED" for row in rows),
            after=after,
            baseline_restored=after == before,
            preserved_after=Q.lifecycle.verify_originals(),
            owner_ratings=None,
            model_selection=None,
            physical_first_audible="UNVERIFIED",
        )
        if after != before:
            result["status"] = "STOPPED_BASELINE_CHANGED"
        Q.assets.publish(root / "campaign-result.json", result)
    return result


def render_page(rows, audio):
    """Display all sixteen controlled slots with paired audio, expected English reading and no remote capabilities."""
    if (
        len(rows) != 16
        or len({row["id"] for row in rows}) != len(rows)
        or set(audio) - {row["id"] for row in rows}
    ):
        raise ValueError("reference_review_coverage")
    cards = []
    for identity, text, expected in CASES:
        for _, voice in Q.VOICES:
            cells = []
            for mode, label in [
                ("with_reference", "Có đoạn tham chiếu preset"),
                (
                    "without_reference",
                    "Không dùng đoạn tham chiếu, cùng đặc trưng người nói",
                ),
            ]:
                row = next(
                    row
                    for row in rows
                    if row["case"] == identity
                    and row["voice"] == voice
                    and row["mode"] == mode
                )
                content = audio.get(row["id"])
                player = (
                    "<p>Chưa có clip hoàn chỉnh: " + html.escape(row["status"]) + "</p>"
                    if content is None
                    else '<audio controls preload="none" src="data:audio/wav;base64,'
                    + base64.b64encode(content).decode("ascii")
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
                + " — Cần nghe: "
                + html.escape(expected)
                + '</p><div class="pair">'
                + "".join(cells)
                + "</div></article>"
            )
    return (
        """<!doctype html>
<!-- Purpose: Compare sixteen unchanged native reference-conditioning diagnostics locally without capture or network. -->
<html lang="vi"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; media-src data:; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<title>D74 — Kiểm tra chữ A và API</title><style>body{max-width:1100px;margin:30px auto;padding:0 20px;font:16px/1.6 system-ui;background:#f8fafb;color:#18232b}article{padding:20px;margin:20px 0;background:white;border:1px solid #ccd6dd;border-radius:10px}.pair{display:grid;grid-template-columns:1fr 1fr;gap:20px}audio{width:100%}h2{font-size:21px}h3{font-size:16px}@media(max-width:750px){.pair{grid-template-columns:1fr}}</style>
<h1>D74 — Chữ A và API</h1><p>Chữ A cần đọc “Ei”; API cần đọc “Ei–Pi–Ai”. Mỗi hàng giữ cùng phoneme và người nói, chỉ đổi việc dùng đoạn tham chiếu preset.
Đây là thử nghiệm, chưa chọn cách mới hoặc khẳng định đã sửa lỗi. Kiểm tra cả phát âm, rè/run và chất giọng có thay đổi không.</p><p>Phần giờ/ngày và ngắt câu đã được bạn xác nhận giữ nguyên ở bộ trước. Trang này không thu âm, upload hoặc kết nối mạng.</p>
"""
        + "".join(cards)
        + "\n</html>\n"
    )


def publish_review(root=ROOT):
    """Verify native outputs and save the paired page without inventing audio for failed/unattempted slots."""
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
            description="Paired reference diagnostics, original native WAV bytes; owner labels not invented.",
            audio=index,
            page_sha256=Q.assets.digest(directory / "index.html"),
            owner_ratings=None,
        ),
    )
    Q.assets.budget(Q.assets.ROOT)
    LOGGER.info(
        "reference_review_published native_audio=%d declared_slots=16", len(audio)
    )
    return directory / "index.html"


def main():
    """Expose separate model-free, one-shot native and local artifact actions for the authorized diagnostic."""
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
        asyncio.run(run())["status"] != "PAIRED_DIAGNOSTIC_COMPLETE_QUALITY_UNVERIFIED"
    ):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
