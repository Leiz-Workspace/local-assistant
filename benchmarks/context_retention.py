"""Measure answer retention, context presence and cost of the explicit history policies on frozen synthetic dialogues (HAR-009-B1)."""

import argparse
import asyncio
import hashlib
import json
import logging
import time
from pathlib import Path
from uuid import uuid4

import httpx

from apps.api.runtime.presets import build_generation_params, calculate_budget
from apps.harness.inference import ProductInference
from benchmarks.har008 import ROOT, save_json
from benchmarks.harness_resources import ResourceSampler, process_memory
from benchmarks.harness_stream_timing import TimingError, measure
from src.application.ports.inference import InferenceFailure
from src.application.services.context_reduction import ContextError, encode
from src.infrastructure.context_archive import ContextArchive

LOGGER = logging.getLogger(__name__)
PAIRS = 16
MAX_TOKENS = 512
TEMPERATURE = 0.7
ARMS = (
    ("full", dict(window_turns=PAIRS)),
    ("legacy", None),
    ("window3", dict(window_turns=3)),
    ("window3_pin1", dict(window_turns=3, pinned_turns=[1])),
    ("compact3", dict(mode="extractive-compact", window_turns=3)),
)
SOURCES = (
    "benchmarks/context_retention.py",
    "benchmarks/harness_stream_timing.py",
    "benchmarks/harness_resources.py",
    "src/application/services/context_composer.py",
    "src/application/services/context_reduction.py",
    "src/application/services/conversation_context.py",
    "src/infrastructure/context_archive.py",
    "apps/harness/inference.py",
    "apps/api/runtime/presets.py",
    "configs/models.yaml",
)
FILLER = {
    "en": (
        (
            "Can you suggest a name for the team lunch vote?",
            "How about 'Friday Table'?",
        ),
        (
            "What font should the slide titles use?",
            "A plain sans-serif keeps titles readable.",
        ),
        ("Remind me to water the office plants.", "Noted as a personal reminder."),
        (
            "Is the coffee machine on floor two fixed?",
            "I have no information about the coffee machine.",
        ),
        (
            "Draft a friendly welcome line for new interns.",
            "Welcome aboard, we are glad you are here!",
        ),
        (
            "Which day suits the quarterly picnic?",
            "Saturdays usually work best for picnics.",
        ),
        ("Give me a synonym for 'quick'.", "Rapid."),
        (
            "How long should a stand-up meeting last?",
            "Around fifteen minutes is common.",
        ),
        ("Suggest a colour for the onboarding poster.", "A calm teal would fit."),
        (
            "What is a polite way to decline a meeting?",
            "Thank you for the invite; I cannot attend this one.",
        ),
        (
            "Recommend a short stretching routine.",
            "Neck rolls, shoulder shrugs and a standing forward bend.",
        ),
        ("Name a good board game for six people.", "Codenames works well for six."),
        ("How do I say 'thank you' in Japanese?", "Arigatou gozaimasu."),
        (
            "Suggest a title for the holiday newsletter.",
            "'Winter Notes from the Team'.",
        ),
        ("What snack goes well with tea?", "Shortbread biscuits are a classic choice."),
        ("Write a two-word motto for the hackathon.", "Build boldly."),
    ),
    "vi": (
        (
            "Gợi ý tên cho cuộc bình chọn quán ăn trưa của nhóm?",
            "Có thể gọi là 'Bàn Thứ Sáu'.",
        ),
        (
            "Tiêu đề slide nên dùng phông chữ gì?",
            "Phông không chân giúp tiêu đề dễ đọc.",
        ),
        (
            "Nhắc tôi tưới cây trong văn phòng nhé.",
            "Đã ghi lại như một lời nhắc cá nhân.",
        ),
        (
            "Máy pha cà phê tầng hai đã sửa chưa?",
            "Tôi không có thông tin về máy pha cà phê.",
        ),
        (
            "Viết một câu chào thân thiện cho thực tập sinh mới.",
            "Chào mừng bạn, rất vui được làm việc cùng bạn!",
        ),
        ("Ngày nào hợp cho buổi dã ngoại hằng quý?", "Thứ Bảy thường thuận tiện nhất."),
        ("Cho tôi một từ cùng nghĩa với 'nhanh'.", "Mau."),
        ("Một buổi họp đứng nên kéo dài bao lâu?", "Khoảng mười lăm phút là phổ biến."),
        ("Gợi ý màu cho áp phích chào đón nhân viên mới.", "Màu xanh ngọc dịu sẽ hợp."),
        (
            "Cách lịch sự để từ chối một cuộc họp?",
            "Cảm ơn lời mời, lần này tôi không tham dự được.",
        ),
        (
            "Gợi ý vài động tác giãn cơ ngắn.",
            "Xoay cổ, nhún vai và cúi người về trước.",
        ),
        ("Trò chơi bàn cờ nào hợp cho sáu người?", "Codenames chơi sáu người rất vui."),
        ("'Cảm ơn' trong tiếng Nhật nói thế nào?", "Arigatou gozaimasu."),
        ("Gợi ý tiêu đề cho bản tin dịp lễ.", "'Ghi chép mùa đông của cả nhóm'."),
        ("Món ăn vặt nào hợp với trà?", "Bánh quy bơ là lựa chọn quen thuộc."),
        ("Viết khẩu hiệu hai chữ cho hackathon.", "Dám làm."),
    ),
}


def case(identifier, kind, language, targets, question, required, forbidden, evidence):
    """Build one dialogue: fixed target pairs at declared turns, fillers elsewhere, current question last."""
    pool = FILLER[language]
    offset = sum(map(ord, identifier)) % len(pool)
    history, filler = [], 0
    for number in range(1, PAIRS + 1):
        if number in targets:
            user, assistant = targets[number]
        else:
            user, assistant = pool[(offset + filler) % len(pool)]
            filler += 1
        history += [
            dict(role="user", content=user),
            dict(role="assistant", content=assistant),
        ]
    suffix = (
        " Trả lời ngắn gọn trong một dòng."
        if language == "vi"
        else " Answer in one short line."
    )
    return dict(
        id=identifier,
        kind=kind,
        language=language,
        target_turns=sorted(targets),
        messages=history + [dict(role="user", content=question + suffix)],
        required=required,
        forbidden=forbidden,
        evidence=evidence,
    )


def corpus():
    """Return the twelve frozen synthetic cases: three per item type, one Vietnamese case per type."""
    return [
        case(
            "early-fact-atlas",
            "early_fact",
            "en",
            {
                2: (
                    "For Atlas release 2.4, which restore snapshot do we use?",
                    "Atlas release 2.4 uses restore snapshot G-17. Snapshot G-18 is reserved for release 2.5.",
                )
            },
            "Which restore snapshot does Atlas release 2.4 use?",
            [["G-17"]],
            ["G-18"],
            ["G-17"],
        ),
        case(
            "early-fact-kestrel",
            "early_fact",
            "en",
            {
                2: (
                    "What is the staging VPN gateway for the Kestrel team?",
                    "Kestrel staging traffic goes through gateway gw-kestrel-04; gw-kestrel-07 is decommissioned.",
                )
            },
            "Which VPN gateway does Kestrel staging use?",
            [["gw-kestrel-04"]],
            ["gw-kestrel-07"],
            ["gw-kestrel-04"],
        ),
        case(
            "early-fact-danang",
            "early_fact",
            "vi",
            {
                2: (
                    "Mã kho dự phòng của chi nhánh Đà Nẵng là gì?",
                    "Chi nhánh Đà Nẵng dùng kho dự phòng KDN-52; kho KDN-58 đã đóng.",
                )
            },
            "Chi nhánh Đà Nẵng dùng mã kho dự phòng nào?",
            [["KDN-52"]],
            ["KDN-58"],
            ["KDN-52"],
        ),
        case(
            "constraint-orion",
            "pinned_constraint",
            "en",
            {
                1: (
                    "Project rules for Orion: ticket IDs must use the prefix OPS-; the old prefix TCK- is retired.",
                    "Understood: Orion ticket IDs use OPS-, never TCK-.",
                ),
                15: (
                    "The database migration got ticket number 4471.",
                    "Noted: the database migration is ticket number 4471.",
                ),
            },
            "Write the full Orion ticket ID for the database migration.",
            [["OPS-4471"]],
            ["TCK-4471"],
            ["prefix OPS-", "4471"],
        ),
        case(
            "constraint-vega",
            "pinned_constraint",
            "en",
            {
                1: (
                    "House style for the Vega report: every duration must be written in minutes, never in hours.",
                    "Understood: Vega durations are always written in minutes.",
                ),
                15: (
                    "The Vega backup window lasts two and a half hours.",
                    "Noted the Vega backup window duration.",
                ),
            },
            "State the Vega backup window duration following the Vega house style.",
            [["150"]],
            ["hour"],
            ["written in minutes", "two and a half hours"],
        ),
        case(
            "constraint-saomai",
            "pinned_constraint",
            "vi",
            {
                1: (
                    "Quy ước dự án Sao Mai: số tiền luôn ghi bằng đồng Việt Nam (VND), không dùng đô la.",
                    "Đã hiểu: dự án Sao Mai ghi số tiền bằng VND, không dùng đô la.",
                ),
                15: (
                    "Chi phí thuê máy chủ tháng này của Sao Mai là 4.200.000.",
                    "Đã ghi nhận chi phí thuê máy chủ tháng này.",
                ),
            },
            "Ghi chi phí thuê máy chủ tháng này theo quy ước dự án Sao Mai.",
            [["4.200.000", "4200000", "4,200,000"], ["VND", "đồng"]],
            ["USD", "$", "đô la"],
            ["(VND)", "4.200.000"],
        ),
        case(
            "contradiction-lynx",
            "contradiction",
            "en",
            {
                3: (
                    "Which build does the Lynx kiosk run?",
                    "Lynx kiosks run build 7.2.9.",
                ),
                12: (
                    "Update: the Lynx kiosks were upgraded today.",
                    "Recorded: Lynx kiosks now run build 7.3.2.",
                ),
            },
            "Which build do the Lynx kiosks run now?",
            [["7.3.2"]],
            ["7.2.9"],
            ["7.3.2"],
        ),
        case(
            "contradiction-heron",
            "contradiction",
            "en",
            {
                3: (
                    "Where do the Heron nightly reports go?",
                    "Heron nightly reports are sent to channel #ops-heron.",
                ),
                12: (
                    "Change of plan for the Heron nightly reports.",
                    "From now on Heron nightly reports go to channel #data-heron.",
                ),
            },
            "Which channel receives the Heron nightly reports now?",
            [["data-heron"]],
            ["ops-heron"],
            ["#data-heron"],
        ),
        case(
            "contradiction-haiau",
            "contradiction",
            "vi",
            {
                3: (
                    "Phòng họp cố định của nhóm Hải Âu là phòng nào?",
                    "Nhóm Hải Âu họp ở phòng P-304.",
                ),
                12: (
                    "Cập nhật lịch họp của nhóm Hải Âu.",
                    "Từ tuần này nhóm Hải Âu chuyển sang họp ở phòng P-512.",
                ),
            },
            "Hiện nay nhóm Hải Âu họp ở phòng nào?",
            [["P-512"]],
            ["P-304"],
            ["P-512"],
        ),
        case(
            "unfinished-falcon",
            "unfinished_citation",
            "en",
            {
                4: (
                    "What is the status of the Falcon billing migration?",
                    "Per ticket T-4821: the invoices table is migrated; still remaining: rebuild index idx_invoice_date.",
                )
            },
            "For the Falcon billing migration, what work is still remaining, and which ticket records it?",
            [["idx_invoice_date"], ["T-4821"]],
            [],
            ["idx_invoice_date", "T-4821"],
        ),
        case(
            "unfinished-pelican",
            "unfinished_citation",
            "en",
            {
                4: (
                    "Where are we with the Pelican search upgrade?",
                    "Per ticket T-5306: the analyzer is deployed; still remaining: reindex collection pelican_docs.",
                )
            },
            "For the Pelican search upgrade, what work is still remaining, and which ticket records it?",
            [["pelican_docs"], ["T-5306"]],
            [],
            ["pelican_docs", "T-5306"],
        ),
        case(
            "unfinished-bocau",
            "unfinished_citation",
            "vi",
            {
                4: (
                    "Tiến độ chuyển đổi hệ thống lương Bồ Câu thế nào?",
                    "Theo phiếu T-6190: đã chuyển xong bảng nhân sự; còn lại: đối soát bảng thưởng quý 3.",
                )
            },
            "Việc chuyển đổi hệ thống lương Bồ Câu còn lại việc gì và phiếu nào ghi nhận?",
            [["T-6190"], ["thưởng"]],
            [],
            ["T-6190", "bảng thưởng"],
        ),
    ]


def score(text, item):
    """Grade one first answer: every required group must match and no stale or distractor token may appear."""
    lowered = text.casefold()
    missing = [
        group
        for group in item["required"]
        if not any(option.casefold() in lowered for option in group)
    ]
    stale = [token for token in item["forbidden"] if token.casefold() in lowered]
    return dict(strict=not missing and not stale, missing=missing, stale=stale)


def presence(fitted, item):
    """Report whether every source fact needed to derive the answer appears in the composed native input."""
    text = encode(fitted).decode().casefold()
    return all(token.casefold() in text for token in item["evidence"])


def schedule(cases):
    """Assign a cyclic arm order per case so no arm always runs first or last."""
    plan = []
    for index, item in enumerate(cases):
        rotated = ARMS[index % len(ARMS) :] + ARMS[: index % len(ARMS)]
        plan.extend((item, name, policy) for name, policy in rotated)
    return plan


def median(data):
    """Return the upper median of finite sorted observations, or None when there are none."""
    return data[len(data) // 2] if data else None


def observed(rows, key):
    """Collect one sorted numeric observation across completed rows, skipping missing values."""
    return sorted(row[key] for row in rows if row.get(key) is not None)


def summarize(rows, cases):
    """Aggregate first outcomes per arm and type, plus paired gains and regressions against the legacy arm."""
    by_arm = {}
    for name, _ in ARMS:
        arm_rows = [row for row in rows if row["arm"] == name]
        complete = [row for row in arm_rows if row["status"] == "COMPLETE"]
        by_type = {}
        for item in cases:
            by_type.setdefault(item["kind"], [0, 0])
        for row in complete:
            kind = row["kind"]
            by_type[kind][1] += 1
            by_type[kind][0] += row["score"]["strict"]
        by_arm[name] = dict(
            attempts=len(arm_rows),
            complete=len(complete),
            strict=sum(row["score"]["strict"] for row in complete),
            stale=sum(bool(row["score"]["stale"]) for row in complete),
            present=sum(
                row["present"] for row in arm_rows if row.get("present") is not None
            ),
            by_type={kind: f"{ok}/{total}" for kind, (ok, total) in by_type.items()},
            median_input_tokens=median(observed(complete, "input_tokens")),
            max_input_tokens=max(observed(complete, "input_tokens"), default=None),
            median_prepare_seconds=median(observed(complete, "prepare_seconds")),
            median_first_text_seconds=median(observed(complete, "first_text_seconds")),
            median_total_seconds=median(observed(complete, "total_seconds")),
        )
    legacy = {
        row["case_id"]: row
        for row in rows
        if row["arm"] == "legacy" and row["status"] == "COMPLETE"
    }
    paired = {}
    for name, _ in ARMS:
        if name == "legacy":
            continue
        gains = regressions = 0
        for row in rows:
            if (
                row["arm"] != name
                or row["status"] != "COMPLETE"
                or row["case_id"] not in legacy
            ):
                continue
            base = legacy[row["case_id"]]["score"]["strict"]
            gains += row["score"]["strict"] and not base
            regressions += base and not row["score"]["strict"]
        paired[name] = dict(gains_vs_legacy=gains, regressions_vs_legacy=regressions)
    return dict(by_arm=by_arm, paired=paired)


async def run(
    inference,
    output,
    *,
    pid,
    sampler_factory=ResourceSampler,
    preflight=process_memory,
    clock=time.monotonic,
):
    """Freeze inputs, then run every case once per arm, retaining first outcomes without retries."""
    output = Path(output)
    native = preflight(pid)
    cases = corpus()
    output.mkdir(mode=0o700, parents=False, exist_ok=False)
    frozen = dict(
        schema_version=1,
        description="HAR-009-B1 frozen paired retention benchmark: twelve synthetic dialogues, five history arms, first outcomes only.",
        corpus=cases,
        arms=[dict(name=name, history_policy=policy) for name, policy in ARMS],
        options=dict(
            preset="fast",
            max_tokens=MAX_TOKENS,
            temperature=TEMPERATURE,
            stream=True,
            retries=0,
        ),
        native_process=native,
        source_sha256={
            name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
            for name in SOURCES
        },
        analysis=dict(
            primary="strict answer success per arm over 12 cases",
            secondary=[
                "stale or distractor answers",
                "source facts needed for the answer present in the composed input",
                "paired gains and regressions against legacy",
                "input tokens",
                "prepare seconds",
                "first text and total seconds",
                "sampled CORE RSS and GPU peaks",
            ],
            reference_check="arm full should reach at least 11/12 strict; otherwise model capability limits every arm",
            adoption="none: this benchmark measures; default or adoption decisions stay with the owner",
        ),
    )
    save_json(output / "frozen-inputs.json", frozen)
    frozen_sha256 = hashlib.sha256(
        (output / "frozen-inputs.json").read_bytes()
    ).hexdigest()
    owner, store = uuid4(), ContextArchive()
    rows = []
    try:
        for attempt, (item, name, policy) in enumerate(schedule(cases), start=1):
            row = dict(
                attempt=attempt,
                case_id=item["id"],
                kind=item["kind"],
                language=item["language"],
                arm=name,
                status="INCOMPLETE",
            )
            options = dict(preset="fast", max_tokens=MAX_TOKENS)
            if policy is not None:
                options["history_policy"] = policy
            if policy is not None and policy.get("mode") == "extractive-compact":
                options["archive"] = lambda raw: store.put(owner, raw)
            started = clock()
            try:
                gateway, fitted, report = await inference.prepare(
                    item["messages"], **options
                )
            except (InferenceFailure, ContextError) as error:
                row.update(
                    status="PREPARE_FAILED",
                    error=getattr(error, "code", "prepare_failed"),
                )
                rows.append(row)
                save_json(output / f"{attempt:02d}-result.json", row)
                continue
            row.update(
                prepare_seconds=round(clock() - started, 6),
                input_tokens=report["input_tokens"],
                present=presence(fitted, item),
                history_policy=report.get("history_policy"),
            )
            plan = calculate_budget(
                preset="fast",
                input_tokens=report["input_tokens"],
                requested_max_tokens=MAX_TOKENS,
            )
            payload = build_generation_params(plan)
            payload.update(
                model=gateway.model_id,
                messages=fitted,
                temperature=TEMPERATURE,
                stream=True,
            )
            save_json(output / f"{attempt:02d}-request.json", payload)
            telemetry = None
            try:
                with sampler_factory(
                    pid, expected_start=native["start_ticks"]
                ) as telemetry:
                    async with httpx.AsyncClient(
                        base_url=gateway.base_url,
                        transport=inference.transport,
                        timeout=gateway._timeout(),
                        trust_env=False,
                    ) as client:
                        receipt = await measure(client, payload, clock=clock)
                row.update(
                    status="COMPLETE",
                    answer=receipt["content"],
                    first_text_seconds=receipt["first_text_delta_seconds"],
                    total_seconds=receipt["total_seconds"],
                    score=score(receipt["content"], item),
                )
            except TimingError as error:
                row.update(
                    status="STREAM_FAILED",
                    partial=error.receipt.get("content", ""),
                    total_seconds=error.receipt.get("total_seconds"),
                )
            finally:
                if telemetry is not None and telemetry.thread is not None:
                    report_resources = telemetry.report()
                    row["resources"] = dict(
                        status=report_resources["status"],
                        sampled_peak_rss_kib=report_resources["sampled_peak_rss_kib"],
                        sampled_peak_gpu_process_mib=report_resources[
                            "sampled_peak_gpu_process_mib"
                        ],
                        samples=len(report_resources["samples"]),
                    )
            rows.append(row)
            save_json(output / f"{attempt:02d}-result.json", row)
        summary = summarize(rows, cases)
        result = dict(
            schema_version=1,
            status="COMPLETE"
            if len(rows) == len(cases) * len(ARMS)
            and all(row["status"] == "COMPLETE" for row in rows)
            else "INCOMPLETE",
            frozen_sha256=frozen_sha256,
            attempts=len(rows),
            retries=0,
            summary=summary,
            native_calls=sum(
                row["status"] in {"COMPLETE", "STREAM_FAILED"} for row in rows
            ),
            semantic_quality_claim="controlled synthetic retention only; not general conversation quality",
        )
        save_json(output / "summary.json", result)
        return result, rows
    finally:
        archived = len(store.entries)
        store.close()
        LOGGER.info(
            "context_retention_closed attempts=%d archived=%d", len(rows), archived
        )


def main():
    """Run one exclusive campaign against the already loaded approved CORE process."""
    parser = argparse.ArgumentParser(
        description="HAR-009-B1 frozen paired retention benchmark."
    )
    parser.add_argument("--pid", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    result, _ = asyncio.run(run(ProductInference(), args.output, pid=args.pid))
    print(
        json.dumps(
            dict(
                status=result["status"],
                attempts=result["attempts"],
                summary=result["summary"],
            ),
            ensure_ascii=False,
        )
    )
    return 0 if result["status"] == "COMPLETE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
