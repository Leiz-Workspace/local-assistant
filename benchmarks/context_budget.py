"""Measure retention under real token pressure for the token-budget history policy against legacy and compaction (HAR-009-B2)."""

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
from benchmarks.context_retention import median, observed, presence, score
from benchmarks.har008 import ROOT, save_json
from benchmarks.harness_resources import ResourceSampler, process_memory
from benchmarks.harness_stream_timing import TimingError, measure
from src.application.ports.inference import InferenceFailure
from src.application.services.context_reduction import (
    ContextError,
    input_limit,
)
from src.infrastructure.context_archive import ContextArchive

LOGGER = logging.getLogger(__name__)
LONG_PAIRS = 16
SHORT_PAIRS = 40
LOG_LINES = 96
MAX_TOKENS = 512
TEMPERATURE = 0.7
ARMS = (
    ("legacy", None),
    ("budget", dict(mode="token-budget")),
    ("compact", dict(mode="extractive-compact")),
)
SOURCES = (
    "benchmarks/context_budget.py",
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
SERVICES = ("ledger", "billing", "search", "mailer", "assets", "reports")
SHORT_FILLER = {
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
            "Suggest a short greeting for the newsletter.",
            "Try 'Hello again, everyone!'",
        ),
        (
            "Which colour is calmer for a poster, blue or orange?",
            "Blue usually reads as calmer.",
        ),
    ),
    "vi": (
        (
            "Gợi ý tên cho buổi ăn trưa của nhóm nhé.",
            "Bạn có thể dùng tên 'Bàn Thứ Sáu'.",
        ),
        (
            "Tiêu đề slide nên dùng phông chữ gì?",
            "Phông không chân giúp tiêu đề dễ đọc.",
        ),
        ("Nhắc tôi tưới cây trong văn phòng.", "Đã ghi lại lời nhắc cá nhân."),
        (
            "Máy pha cà phê tầng hai đã sửa chưa?",
            "Tôi không có thông tin về máy pha cà phê.",
        ),
        ("Gợi ý một lời chào ngắn cho bản tin.", "Thử dùng 'Chào cả nhà!'."),
        (
            "Màu nào dịu mắt hơn cho áp phích, xanh lam hay cam?",
            "Xanh lam thường dịu mắt hơn.",
        ),
    ),
}


def log_block(identifier, number, language):
    """Return one long deterministic synthetic worker log pair that carries no target fact."""
    state = sum(map(ord, identifier)) * 131 + number * 977
    lines = []
    service = SERVICES[(state + number) % len(SERVICES)]
    for index in range(LOG_LINES):
        state = (state * 1103515245 + 12345) % 2147483648
        lines.append(
            f"{8 + index // 60:02d}:{index % 60:02d}:{state % 60:02d} INFO {SERVICES[state % 6]}-worker "
            f"job={1000 + state % 900} rows={100 + state % 800} ms={10 + state % 89} status=ok"
        )
    if language == "vi":
        intro = f"Đây là nhật ký worker {service} của lô {number}, chưa cần xử lý, chỉ lưu để tham khảo:\n"
        reply = f"Đã nhận nhật ký lô {number}; chưa cần làm gì."
    else:
        intro = f"Here is the {service} worker log from batch {number}; nothing to act on, keep it for reference:\n"
        reply = f"Received the batch {number} log; no action is needed."
    return intro + "\n".join(lines), reply


def case(
    identifier, kind, regime, language, targets, question, required, forbidden, evidence
):
    """Build one dialogue with fixed target pairs, long log fillers (long regime) or short fillers (short regime)."""
    pairs = LONG_PAIRS if regime == "long" else SHORT_PAIRS
    pool = SHORT_FILLER[language]
    offset = sum(map(ord, identifier)) % len(pool)
    history, filler = [], 0
    for number in range(1, pairs + 1):
        if number in targets:
            user, assistant = targets[number]
        elif regime == "long":
            user, assistant = log_block(identifier, number, language)
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
        regime=regime,
        language=language,
        target_turns=sorted(targets),
        messages=history + [dict(role="user", content=question + suffix)],
        required=required,
        forbidden=forbidden,
        evidence=evidence,
    )


def corpus():
    """Return the twelve frozen cases: eight long-turn cases under token pressure and four many-short-turn cases."""
    return [
        case(
            "long-fact-kestrel",
            "early_fact",
            "long",
            "en",
            {
                2: (
                    "For the Kestrel migration, which database snapshot is the rollback point?",
                    "The Kestrel rollback point is snapshot S-731; S-732 was a failed copy and must not be used.",
                )
            },
            "Which snapshot is the Kestrel rollback point?",
            [["S-731"]],
            ["S-732"],
            ["S-731"],
        ),
        case(
            "long-fact-sonca",
            "early_fact",
            "long",
            "vi",
            {
                3: (
                    "Dự án Sơn Ca lưu mã nguồn ở kho nào?",
                    "Dự án Sơn Ca lưu mã nguồn ở kho R-552; R-553 là kho thử nghiệm cũ, không dùng nữa.",
                )
            },
            "Dự án Sơn Ca đang lưu mã nguồn ở kho nào?",
            [["R-552"]],
            ["R-553"],
            ["R-552"],
        ),
        case(
            "long-marked-heron",
            "marked_constraint",
            "long",
            "en",
            {
                1: (
                    "Rule: every Heron incident ticket ID uses the prefix HRN- followed by the incident number; the old INC- prefix is retired.",
                    "Understood: Heron incident tickets use the HRN- prefix, never INC-.",
                ),
                15: (
                    "The new Heron incident is incident 8812, a cache outage.",
                    "Logged: Heron incident 8812, cache outage.",
                ),
            },
            "Give the full ticket ID for the new Heron incident.",
            [["HRN-8812"]],
            ["INC-8812"],
            ["HRN-", "incident 8812"],
        ),
        case(
            "long-marked-bocau",
            "marked_constraint",
            "long",
            "vi",
            {
                1: (
                    "Quy tắc: mọi thời lượng bảo trì của dự án Bồ Câu phải ghi bằng phút, không dùng giờ.",
                    "Đã ghi nhận: thời lượng bảo trì của Bồ Câu ghi bằng phút.",
                ),
                15: (
                    "Đợt bảo trì Bồ Câu tuần này kéo dài hai giờ rưỡi.",
                    "Đã ghi: đợt bảo trì Bồ Câu tuần này kéo dài hai giờ rưỡi.",
                ),
            },
            "Ghi thời lượng đợt bảo trì Bồ Câu tuần này theo đúng quy định.",
            [["150 phút"]],
            ["2,5 giờ", "2.5 giờ", "2 giờ 30"],
            ["bằng phút", "hai giờ rưỡi"],
        ),
        case(
            "long-unmarked-osprey",
            "unmarked_constraint",
            "long",
            "en",
            {
                1: (
                    "For Osprey, write every date as YYYY-MM-DD in all answers.",
                    "Got it: Osprey dates use YYYY-MM-DD.",
                ),
                15: (
                    "The Osprey go-live moved to the fourth of March 2027.",
                    "Noted: Osprey go-live on the fourth of March 2027.",
                ),
            },
            "Write the Osprey go-live date in the required format.",
            [["2027-03-04"]],
            ["04/03/2027", "03/04/2027", "March 4"],
            ["YYYY-MM-DD", "fourth of March 2027"],
        ),
        case(
            "long-unmarked-chimse",
            "unmarked_constraint",
            "long",
            "vi",
            {
                1: (
                    "Với dự án Chim Sẻ, mã yêu cầu mua hàng phải viết theo dạng MH-CS- và đủ bốn chữ số.",
                    "Đã rõ: mã mua hàng của Chim Sẻ có dạng MH-CS- và bốn chữ số.",
                ),
                15: (
                    "Yêu cầu mua hàng mới của Chim Sẻ là số 315, mua màn hình.",
                    "Đã ghi: yêu cầu mua hàng số 315 của Chim Sẻ, mua màn hình.",
                ),
            },
            "Viết mã đầy đủ của yêu cầu mua hàng mới của Chim Sẻ.",
            [["MH-CS-0315"]],
            [],
            ["MH-CS-", "số 315"],
        ),
        case(
            "long-stale-hydra",
            "stale_marked_rule",
            "long",
            "en",
            {
                1: (
                    "Decision: Hydra production deploys go out on Tuesdays.",
                    "Noted: Hydra production deploys go out on Tuesdays.",
                ),
                6: (
                    "Change of plan for Hydra: production deploys move to Thursdays from now on.",
                    "Updated: Hydra production deploys now go out on Thursdays.",
                ),
            },
            "On which weekday do Hydra production deploys go out now?",
            [["Thursday"]],
            ["Tuesday"],
            ["Thursdays"],
        ),
        case(
            "long-stale-daibang",
            "stale_marked_rule",
            "long",
            "vi",
            {
                1: (
                    "Quyết định: máy chủ chính của dự án Đại Bàng đặt ở Hà Nội.",
                    "Đã ghi nhận: máy chủ chính của Đại Bàng đặt ở Hà Nội.",
                ),
                6: (
                    "Thay đổi cho dự án Đại Bàng: máy chủ chính đã chuyển vào Đà Nẵng.",
                    "Đã cập nhật: máy chủ chính của Đại Bàng giờ ở Đà Nẵng.",
                ),
            },
            "Máy chủ chính của dự án Đại Bàng hiện đặt ở đâu?",
            [["Đà Nẵng"]],
            ["Hà Nội"],
            ["Đà Nẵng"],
        ),
        case(
            "short-fact-lynx",
            "early_fact",
            "short",
            "en",
            {
                2: (
                    "Which port does the Lynx metrics agent listen on?",
                    "The Lynx metrics agent listens on port 9464; port 9465 belongs to the retired exporter.",
                )
            },
            "Which port does the Lynx metrics agent use?",
            [["9464"]],
            ["9465"],
            ["9464"],
        ),
        case(
            "short-fact-hoami",
            "early_fact",
            "short",
            "vi",
            {
                2: (
                    "Phiên bản ổn định hiện tại của dự án Họa Mi là bản nào?",
                    "Phiên bản ổn định của Họa Mi là V-3.8; V-3.9 vẫn đang thử nghiệm.",
                )
            },
            "Họa Mi đang dùng phiên bản ổn định nào?",
            [["V-3.8", "3.8"]],
            ["V-3.9", "3.9"],
            ["V-3.8"],
        ),
        case(
            "short-contradiction-mantis",
            "contradiction",
            "short",
            "en",
            {
                3: (
                    "What is the Mantis API rate limit?",
                    "The Mantis API rate limit is 300 requests per minute.",
                ),
                25: (
                    "Correction for Mantis: the API rate limit was lowered.",
                    "Updated: the Mantis API rate limit is now 120 requests per minute.",
                ),
            },
            "What is the current Mantis API rate limit?",
            [["120"]],
            ["300"],
            ["120 requests"],
        ),
        case(
            "short-unfinished-puffin",
            "unfinished_citation",
            "short",
            "en",
            {
                4: (
                    "Where are we on the Puffin data export?",
                    "The Puffin export is half done: orders are exported; the refunds table still needs exporting under ticket T-5307.",
                )
            },
            "What is still left for the Puffin export, and which ticket tracks it?",
            [["refunds"], ["T-5307"]],
            [],
            ["refunds", "T-5307"],
        ),
    ]


def expectations(item, arm, retained):
    """Return design violations: each regime must place its targets inside or outside an arm's window as intended."""
    problems = []
    if item["regime"] == "short":
        if arm == "legacy" and retained != list(
            range(SHORT_PAIRS - 10, SHORT_PAIRS + 1)
        ):
            problems.append("legacy_short_window_is_not_the_last_eleven_pairs")
        if arm == "budget" and retained != list(range(1, SHORT_PAIRS + 1)):
            problems.append("budget_short_regime_did_not_keep_everything")
        return problems
    if arm == "legacy":
        if any(number <= 4 for number in retained):
            problems.append("legacy_long_window_reaches_the_early_targets")
        if item["kind"] == "stale_marked_rule" and 6 not in retained:
            problems.append("legacy_long_window_lost_the_correction")
    if arm == "budget":
        if 6 in retained:
            problems.append("budget_long_window_reaches_the_correction_pair")
        marked = item["kind"] in {"marked_constraint", "stale_marked_rule"}
        if (1 in retained) != marked:
            problems.append("budget_marker_retention_differs_from_design")
    return problems


def schedule(cases):
    """Assign a cyclic arm order per case so no arm always runs first or last."""
    plan = []
    for index, item in enumerate(cases):
        rotated = ARMS[index % len(ARMS) :] + ARMS[: index % len(ARMS)]
        plan.extend((item, name, policy) for name, policy in rotated)
    return plan


def summarize(rows, cases):
    """Aggregate first outcomes per arm, kind and regime, plus paired gains and regressions against legacy."""
    by_arm = {}
    for name, _ in ARMS:
        arm_rows = [row for row in rows if row["arm"] == name]
        complete = [row for row in arm_rows if row["status"] == "COMPLETE"]
        groups = {}
        for item in cases:
            groups.setdefault(item["kind"], [0, 0])
            groups.setdefault("regime:" + item["regime"], [0, 0])
        for row in complete:
            for key in (row["kind"], "regime:" + row["regime"]):
                groups[key][1] += 1
                groups[key][0] += row["score"]["strict"]
        by_arm[name] = dict(
            attempts=len(arm_rows),
            complete=len(complete),
            strict=sum(row["score"]["strict"] for row in complete),
            stale=sum(bool(row["score"]["stale"]) for row in complete),
            present=sum(
                row["present"] for row in arm_rows if row.get("present") is not None
            ),
            strict_when_present=sum(
                row["score"]["strict"] for row in complete if row["present"]
            ),
            by_group={key: f"{ok}/{total}" for key, (ok, total) in groups.items()},
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
        gains, regressions = [], []
        for row in rows:
            if (
                row["arm"] != name
                or row["status"] != "COMPLETE"
                or row["case_id"] not in legacy
            ):
                continue
            base = legacy[row["case_id"]]["score"]["strict"]
            if row["score"]["strict"] and not base:
                gains.append(row["case_id"])
            if base and not row["score"]["strict"]:
                regressions.append(row["case_id"])
        paired[name] = dict(gains_vs_legacy=gains, regressions_vs_legacy=regressions)
    return dict(by_arm=by_arm, paired=paired)


def options_for(policy, store, owner):
    """Return prepare options for one arm, binding compaction to a real owner-scoped RAM archive."""
    options = dict(preset="fast", max_tokens=MAX_TOKENS)
    if policy is not None:
        options["history_policy"] = policy
    if policy is not None and policy.get("mode") == "extractive-compact":
        options["archive"] = lambda raw: store.put(owner, raw)
    return options


def retained_turns(item, fitted, report):
    """Read retained pairs from the policy receipt, or count the legacy whole-turn suffix that survived."""
    receipt = report.get("history_policy")
    if receipt is not None:
        return list(receipt["retained_turns"])
    pairs = (len(item["messages"]) - 1) // 2
    kept = sum(row["role"] != "system" for row in fitted[:-1]) // 2
    return list(range(pairs - kept + 1, pairs + 1))


async def design(inference, cases):
    """Compose every case under every arm with the native tokenizer only, and report placement violations."""
    owner, store = uuid4(), ContextArchive()
    plan, violations = [], []
    try:
        for item in cases:
            for name, policy in ARMS:
                _, fitted, report = await inference.prepare(
                    item["messages"], **options_for(policy, store, owner)
                )
                retained = retained_turns(item, fitted, report)
                problems = expectations(item, name, retained)
                plan.append(
                    dict(
                        case_id=item["id"],
                        arm=name,
                        retained_turns=retained,
                        input_tokens=report["input_tokens"],
                        present=presence(fitted, item),
                    )
                )
                violations += [
                    dict(case_id=item["id"], arm=name, problem=problem)
                    for problem in problems
                ]
    finally:
        store.close()
    return plan, violations


async def run(
    inference,
    output,
    *,
    pid,
    sampler_factory=ResourceSampler,
    preflight=process_memory,
    clock=time.monotonic,
):
    """Check the design with the tokenizer, freeze inputs, then run every case once per arm without retries."""
    output = Path(output)
    native = preflight(pid)
    cases = corpus()
    output.mkdir(mode=0o700, parents=False, exist_ok=False)
    plan, violations = await design(inference, cases)
    if violations:
        result = dict(
            schema_version=1,
            status="DESIGN_INVALID",
            violations=violations,
            plan=plan,
            native_calls=0,
        )
        save_json(output / "design-invalid.json", result)
        return result, []
    soft = int(input_limit("fast", MAX_TOKENS) * 0.8)
    frozen = dict(
        schema_version=1,
        description="HAR-009-B2 frozen paired token-pressure benchmark: twelve synthetic dialogues, three history arms, first outcomes only.",
        corpus=cases,
        arms=[dict(name=name, history_policy=policy) for name, policy in ARMS],
        options=dict(
            preset="fast",
            max_tokens=MAX_TOKENS,
            temperature=TEMPERATURE,
            stream=True,
            retries=0,
        ),
        budgets=dict(
            hard_input_limit=input_limit("fast", MAX_TOKENS), soft_input_limit=soft
        ),
        composition_plan=plan,
        native_process=native,
        source_sha256={
            name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
            for name in SOURCES
        },
        analysis=dict(
            primary="strict answer success per arm over 12 cases",
            secondary=[
                "stale or distractor answers",
                "source facts present in the composed input, and strict success when present",
                "results per item kind and per regime (long turns under token pressure, many short turns)",
                "paired gains and regressions against legacy",
                "input tokens",
                "prepare seconds",
                "first text and total seconds",
                "sampled CORE RSS and GPU peaks",
            ],
            design_expectations=[
                "short regime: legacy keeps exactly pairs 30-40 and budget keeps all forty pairs",
                "long regime: legacy never reaches pairs 1-4 and keeps the pair-6 correction in the stale cases",
                "long regime: budget never reaches pair 6 and keeps pair 1 only when its user message is marked",
            ],
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
                regime=item["regime"],
                language=item["language"],
                arm=name,
                status="INCOMPLETE",
            )
            started = clock()
            try:
                gateway, fitted, report = await inference.prepare(
                    item["messages"], **options_for(policy, store, owner)
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
                retained_turns=retained_turns(item, fitted, report),
                history_policy=report.get("history_policy"),
            )
            plan_budget = calculate_budget(
                preset="fast",
                input_tokens=report["input_tokens"],
                requested_max_tokens=MAX_TOKENS,
            )
            payload = build_generation_params(plan_budget)
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
                    resources = telemetry.report()
                    row["resources"] = dict(
                        status=resources["status"],
                        sampled_peak_rss_kib=resources["sampled_peak_rss_kib"],
                        sampled_peak_gpu_process_mib=resources[
                            "sampled_peak_gpu_process_mib"
                        ],
                        samples=len(resources["samples"]),
                    )
            rows.append(row)
            save_json(output / f"{attempt:02d}-result.json", row)
        result = dict(
            schema_version=1,
            status="COMPLETE"
            if len(rows) == len(cases) * len(ARMS)
            and all(row["status"] == "COMPLETE" for row in rows)
            else "INCOMPLETE",
            frozen_sha256=frozen_sha256,
            attempts=len(rows),
            retries=0,
            summary=summarize(rows, cases),
            native_calls=sum(
                row["status"] in {"COMPLETE", "STREAM_FAILED"} for row in rows
            ),
            semantic_quality_claim="controlled synthetic retention under token pressure only; not general conversation quality",
        )
        save_json(output / "summary.json", result)
        return result, rows
    finally:
        archived = len(store.entries)
        store.close()
        LOGGER.info(
            "context_budget_closed attempts=%d archived=%d", len(rows), archived
        )


def main():
    """Run one exclusive campaign against the already loaded approved CORE process."""
    parser = argparse.ArgumentParser(
        description="HAR-009-B2 frozen paired token-pressure benchmark."
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
                summary=result.get("summary"),
                violations=result.get("violations"),
            ),
            ensure_ascii=False,
        )
    )
    return 0 if result["status"] == "COMPLETE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
