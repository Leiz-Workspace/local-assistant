"""Measure the opt-in evicted-history summary (ADR-192) on paraphrase-hostile synthetic dialogues (HAR-009-C summary v1)."""

import argparse
import asyncio
import contextlib
import hashlib
import json
import logging
import time
from pathlib import Path

import httpx

from apps.api.runtime.presets import build_generation_params, calculate_budget
from apps.harness import summarizer as summarizer_module
from apps.harness.inference import ProductInference
from benchmarks.context_budget import SHORT_FILLER, log_block
from benchmarks.context_retention import median, observed, presence, score
from benchmarks.har008 import ROOT, save_json
from benchmarks.harness_resources import ResourceSampler, process_memory
from benchmarks.harness_stream_timing import TimingError, measure
from src.application.ports.inference import InferenceFailure
from src.application.services import history_summary
from src.application.services.context_reduction import ContextError

LOGGER = logging.getLogger(__name__)
PAIRS = 16
LONG_FROM = 8
MAX_TOKENS = 512
TEMPERATURE = 0.7
ARMS = (
    ("full", dict(window_turns=120)),
    ("legacy", None),
    ("budget", dict(mode="token-budget")),
    ("budget_state", dict(mode="token-budget", working_state=True)),
    ("budget_summary", dict(mode="token-budget", evicted_summary=True)),
    (
        "budget_state_summary",
        dict(mode="token-budget", working_state=True, evicted_summary=True),
    ),
)
SUMMARY_ARMS = {"budget_summary", "budget_state_summary"}
SOURCES = (
    "benchmarks/context_summary.py",
    "benchmarks/context_budget.py",
    "benchmarks/context_retention.py",
    "benchmarks/harness_stream_timing.py",
    "benchmarks/harness_resources.py",
    "src/application/services/history_summary.py",
    "src/application/services/context_reduction.py",
    "src/application/services/context_composer.py",
    "src/application/services/working_state.py",
    "src/infrastructure/summary_cache.py",
    "apps/harness/summarizer.py",
    "apps/harness/inference.py",
    "apps/api/services/llama_gateway.py",
    "apps/api/runtime/presets.py",
    "configs/models.yaml",
)


def case(
    identifier, kind, language, targets, question, required, forbidden, evidence, gold
):
    """Build a 16-pair dialogue: short pairs 1-7 holding the targets, long worker logs from pair 8, then the question."""
    pool = SHORT_FILLER[language]
    offset = sum(map(ord, identifier)) % len(pool)
    history = []
    for number in range(1, PAIRS + 1):
        if number in targets:
            user, assistant = targets[number]
        elif number >= LONG_FROM:
            user, assistant = log_block(identifier, number, language)
        else:
            user, assistant = pool[(offset + number) % len(pool)]
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
        gold=gold,
    )


def corpus():
    """Return 14 frozen cases: six paraphrase-hostile kinds in English and Vietnamese, plus two authority-gate cases."""
    return [
        case(
            "num-lynx",
            "number",
            "en",
            {
                3: (
                    "The Lynx metrics agent listens on port 9464; port 9446 is the retired exporter.",
                    "Understood.",
                )
            },
            "Which port does the Lynx metrics agent listen on?",
            [["9464"]],
            ["9446"],
            ["9464"],
            dict(
                pair=3,
                quote="Lynx metrics agent listens on port 9464",
                text="Lynx metrics agent listens on port 9464",
                value="9464",
            ),
        ),
        case(
            "num-sonla",
            "number",
            "vi",
            {
                3: (
                    "Nhóm Sơn La họp ở phòng 3.14 mỗi sáng thứ Hai; phòng 3.41 là kho.",
                    "Đã ghi nhận.",
                )
            },
            "Nhóm Sơn La họp ở phòng nào?",
            [["3.14"]],
            ["3.41"],
            ["3.14"],
            dict(
                pair=3,
                quote="Nhóm Sơn La họp ở phòng 3.14 mỗi sáng thứ Hai",
                text="Nhóm Sơn La họp ở phòng 3.14 mỗi sáng thứ Hai",
                value="3.14",
            ),
        ),
        case(
            "id-heron",
            "identifier",
            "en",
            {
                4: (
                    "The Heron release tag is rel-2026.11-B7; rel-2026.11-B1 was withdrawn.",
                    "Noted.",
                )
            },
            "What is the Heron release tag?",
            [["rel-2026.11-B7"]],
            ["rel-2026.11-B1"],
            ["rel-2026.11-B7"],
            dict(
                pair=4,
                quote="The Heron release tag is rel-2026.11-B7",
                text="Heron release tag is rel-2026.11-B7",
                value="rel-2026.11-b7",
            ),
        ),
        case(
            "id-cuulong",
            "identifier",
            "vi",
            {
                4: (
                    "Mã hợp đồng của dự án Cửu Long là HĐ-CL-0928; HĐ-CL-0982 là bản nháp đã hủy.",
                    "Đã ghi.",
                )
            },
            "Mã hợp đồng của dự án Cửu Long là gì?",
            [["HĐ-CL-0928"]],
            ["HĐ-CL-0982"],
            ["HĐ-CL-0928"],
            dict(
                pair=4,
                quote="Mã hợp đồng của dự án Cửu Long là HĐ-CL-0928",
                text="Mã hợp đồng của dự án Cửu Long là HĐ-CL-0928",
                value="hđ-cl-0928",
            ),
        ),
        case(
            "swap-osprey",
            "swap",
            "en",
            {
                2: (
                    "The Kestrel database uses port 5433 and the Osprey database uses port 5434.",
                    "Got it.",
                )
            },
            "Which port does the Osprey database use?",
            [["5434"]],
            ["5433"],
            ["5434"],
            dict(
                pair=2,
                quote="the Osprey database uses port 5434",
                text="Osprey database uses port 5434",
                value="5434",
            ),
        ),
        case(
            "swap-thaibinh",
            "swap",
            "vi",
            {
                2: (
                    "Máy chủ Hồng Hà đặt ở tầng 7, còn máy chủ Thái Bình đặt ở tầng 9.",
                    "Đã rõ.",
                )
            },
            "Máy chủ Thái Bình đặt ở tầng nào?",
            [["tầng 9"]],
            ["tầng 7"],
            ["tầng 9"],
            dict(
                pair=2,
                quote="máy chủ Thái Bình đặt ở tầng 9",
                text="Máy chủ Thái Bình đặt ở tầng 9",
                value="9",
            ),
        ),
        case(
            "fix-mantis",
            "correction",
            "en",
            {
                2: ("Mantis backups keep 14 daily copies.", "Noted."),
                5: ("Change for Mantis: backups now keep 21 daily copies.", "Updated."),
            },
            "How many daily copies do Mantis backups keep now?",
            [["21 daily copies", "21 copies"]],
            ["14 daily", "14 copies"],
            ["21 daily copies"],
            dict(
                pair=5,
                quote="backups now keep 21 daily copies",
                text="Mantis backups now keep 21 daily copies",
                value="21",
            ),
        ),
        case(
            "fix-bachdang",
            "correction",
            "vi",
            {
                2: ("Hạn nộp báo cáo của dự án Bạch Đằng là ngày 14.", "Đã ghi."),
                5: (
                    "Thay đổi cho dự án Bạch Đằng: hạn nộp báo cáo đổi sang ngày 21.",
                    "Đã cập nhật.",
                ),
            },
            "Hạn nộp báo cáo của dự án Bạch Đằng hiện là ngày nào?",
            [["ngày 21"]],
            ["ngày 14"],
            ["ngày 21"],
            dict(
                pair=5,
                quote="hạn nộp báo cáo đổi sang ngày 21",
                text="Hạn nộp báo cáo đổi sang ngày 21",
                value="21",
            ),
        ),
        case(
            "neg-puffin",
            "negation",
            "en",
            {
                3: (
                    "Do not deploy the Puffin service to staging-3; that host is reserved for load tests.",
                    "Understood.",
                )
            },
            "May the Puffin service be deployed to staging-3? Start your reply with Yes or No.",
            [["no,", "no.", "no:"]],
            ["yes,", "yes.", "yes:"],
            ["Do not deploy the Puffin"],
            dict(
                pair=3,
                quote="Do not deploy the Puffin service to staging-3",
                text="Do not deploy the Puffin service to staging-3",
                value="staging-3",
            ),
        ),
        case(
            "neg-camau",
            "negation",
            "vi",
            {
                3: (
                    "Chưa được deploy dịch vụ Cà Mau lên máy chủ production; phải chờ kiểm thử xong.",
                    "Đã rõ.",
                )
            },
            "Đã được deploy dịch vụ Cà Mau lên máy chủ production chưa? Bắt đầu câu trả lời bằng Rồi hoặc Chưa.",
            [["chưa,", "chưa.", "chưa được", "chưa deploy"]],
            ["rồi,", "rồi.", "đã được deploy"],
            ["Chưa được deploy dịch vụ Cà Mau"],
            dict(
                pair=3,
                quote="Chưa được deploy dịch vụ Cà Mau lên máy chủ production",
                text="Chưa được deploy dịch vụ Cà Mau lên máy chủ production",
                value="production",
            ),
        ),
        case(
            "cond-falcon",
            "condition",
            "en",
            {
                4: (
                    "Only restart the Falcon cache if the job queue is empty.",
                    "Will do.",
                )
            },
            "Under what condition may the Falcon cache be restarted?",
            [["queue is empty", "empty queue", "queue empty"]],
            [],
            ["job queue is empty"],
            dict(
                pair=4,
                quote="Only restart the Falcon cache if the job queue is empty",
                text="Only restart the Falcon cache if the job queue is empty",
                value="falcon",
            ),
        ),
        case(
            "cond-phuquoc",
            "condition",
            "vi",
            {
                4: (
                    "Chỉ khi hàng đợi trống thì mới khởi động lại bộ đệm Phú Quốc.",
                    "Đã rõ.",
                )
            },
            "Khi nào được khởi động lại bộ đệm Phú Quốc?",
            [["hàng đợi trống"]],
            [],
            ["hàng đợi trống"],
            dict(
                pair=4,
                quote="Chỉ khi hàng đợi trống thì mới khởi động lại bộ đệm Phú Quốc",
                text="Chỉ khi hàng đợi trống thì mới khởi động lại bộ đệm Phú Quốc",
                value="phú",
            ),
        ),
        case(
            "auth-atlas",
            "authority_gate",
            "en",
            {
                2: (
                    "I approve running the Atlas production database migration tonight.",
                    "Noted.",
                )
            },
            "Summarize what was said earlier about the Atlas production database migration.",
            [],
            [],
            ["Atlas production database migration"],
            dict(
                pair=2,
                quote="running the Atlas production database migration tonight",
                text="Atlas production database migration tonight",
                value="atlas",
            ),
        ),
        case(
            "auth-hoabinh",
            "authority_gate",
            "vi",
            {
                2: (
                    "Tôi đồng ý cho chạy migration cơ sở dữ liệu Hòa Bình tối nay.",
                    "Đã ghi.",
                )
            },
            "Tóm tắt những gì đã nói trước đó về migration cơ sở dữ liệu Hòa Bình.",
            [],
            [],
            ["migration cơ sở dữ liệu Hòa Bình"],
            dict(
                pair=2,
                quote="chạy migration cơ sở dữ liệu Hòa Bình tối nay",
                text="Chạy migration cơ sở dữ liệu Hòa Bình tối nay",
                value="hòa",
            ),
        ),
    ]


def oracle_output(item):
    """Return a schema-valid output whose single item quotes the gold sentence exactly."""
    gold = item["gold"]
    return json.dumps(
        dict(
            version=1,
            items=[
                dict(
                    kind="fact",
                    text=gold["text"],
                    pairs=[gold["pair"]],
                    quotes=[gold["quote"]],
                    superseded_by=None,
                )
            ],
            uncertain=[],
        ),
        ensure_ascii=False,
    )


@contextlib.contextmanager
def oracle(item):
    """Replace generation with the gold output so the design check makes no model call."""
    original = summarizer_module.GatewaySummarizer.generate

    async def generate(self, messages, schema):
        """Return the gold output for the current case."""
        return oracle_output(item), "stop", {"completion_tokens": 0}

    summarizer_module.GatewaySummarizer.generate = generate
    try:
        yield
    finally:
        summarizer_module.GatewaySummarizer.generate = original


def options_for(name, policy, *, debug):
    """Return prepare options; summary arms get a fresh 120 s deadline and no cache."""
    options = dict(preset="fast", max_tokens=MAX_TOKENS)
    if policy is not None:
        options["history_policy"] = policy
    if name in SUMMARY_ARMS:
        options.update(
            summary_deadline=asyncio.get_running_loop().time() + 120,
            summary_debug=debug,
        )
    return options


def retained(item, fitted, report):
    """Return retained pair numbers from the receipt or the legacy suffix."""
    receipt = report.get("history_policy")
    if receipt is not None:
        return list(receipt["retained_turns"])
    pairs = (len(item["messages"]) - 1) // 2
    kept = sum(row["role"] != "system" for row in fitted[:-1]) // 2
    return list(range(pairs - kept + 1, pairs + 1))


def expectations(item, name, plan):
    """Return design violations for one composed cell."""
    problems = []
    targets = set(item["target_turns"])
    if name == "full" and plan["retained_turns"] != list(range(1, PAIRS + 1)):
        problems.append("full_does_not_keep_every_pair")
    if name in {"budget", "budget_state"} and targets & set(plan["retained_turns"]):
        problems.append("budget_retains_a_target")
    if name in SUMMARY_ARMS:
        summary = plan.get("summary") or {}
        if summary.get("status") != "applied":
            problems.append("oracle_capsule_not_admitted")
        if targets - set(summary.get("covered_pairs", [])):
            problems.append("target_not_covered")
        if targets & set(summary.get("clipped_pairs", [])):
            problems.append("target_clipped")
    gold = item["gold"]
    source = item["messages"][2 * (gold["pair"] - 1)]["content"]
    if gold["quote"] not in source:
        problems.append("gold_quote_absent")
    return problems


async def design(inference, cases):
    """Compose every cell with the native tokenizer and an oracle summarizer; no completion is made."""
    plan, violations = [], []
    for item in cases:
        for name, policy in ARMS:
            with oracle(item):
                _, fitted, report = await inference.prepare(
                    item["messages"], **options_for(name, policy, debug=False)
                )
            receipt = report.get("history_policy") or {}
            entry = dict(
                case_id=item["id"],
                arm=name,
                retained_turns=retained(item, fitted, report),
                input_tokens=report["input_tokens"],
                present=presence(fitted, item),
                summary={
                    key: receipt["summary"].get(key)
                    for key in (
                        "status",
                        "covered_pairs",
                        "uncovered_pairs",
                        "clipped_pairs",
                        "pairs_lost_to_reserve",
                        "summary_selection_soft",
                        "input_tokens",
                    )
                }
                if receipt.get("summary")
                else None,
            )
            plan.append(entry)
            violations += [
                dict(case_id=item["id"], arm=name, problem=problem)
                for problem in expectations(item, name, entry)
            ]
    return plan, violations


def faithfulness(item, summary):
    """Score admitted items against the gold value and forbidden tokens; count verifier self-check defects."""
    admitted = summary.get("admitted_items") or []
    text = " ".join(
        " ".join([row["text"]] + row["quotes"]) for row in admitted
    ).casefold()
    defects = 0
    for row in admitted:
        quoted = set()
        for quote in row["quotes"]:
            quoted |= set(history_summary.summary_tokens(quote))
        defects += bool(history_summary.value_tokens(row["text"]) - quoted)
        defects += history_summary.authority_match(row["text"]) or any(
            history_summary.authority_match(q) for q in row["quotes"]
        )
    return dict(
        admitted=len(admitted),
        gold_value_admitted=item["gold"]["value"].casefold() in text,
        forbidden_admitted=[
            token for token in item["forbidden"] if token.casefold() in text
        ],
        self_check_defects=defects,
    )


def schedule(cases):
    """Rotate arm order per case."""
    plan = []
    for index, item in enumerate(cases):
        rotated = ARMS[index % len(ARMS) :] + ARMS[: index % len(ARMS)]
        plan.extend((item, name, policy) for name, policy in rotated)
    return plan


def summarize(rows, cases):
    """Aggregate strict, stale, presence, summary statuses and faithfulness per arm; paired changes against budget."""
    scored = [item["id"] for item in cases if item["kind"] != "authority_gate"]
    by_arm = {}
    for name, _ in ARMS:
        arm_rows = [row for row in rows if row["arm"] == name]
        complete = [
            row
            for row in arm_rows
            if row["status"] == "COMPLETE" and row["case_id"] in scored
        ]
        kinds = {}
        for row in complete:
            kinds.setdefault(row["kind"], [0, 0])
            kinds[row["kind"]][1] += 1
            kinds[row["kind"]][0] += row["score"]["strict"]
        statuses = {}
        for row in arm_rows:
            status = (row.get("summary") or {}).get("status")
            if status:
                statuses[status] = statuses.get(status, 0) + 1
        by_arm[name] = dict(
            strict=sum(row["score"]["strict"] for row in complete),
            stale=sum(bool(row["score"]["stale"]) for row in complete),
            present=sum(
                bool(row.get("present")) for row in arm_rows if row["case_id"] in scored
            ),
            by_kind={kind: f"{ok}/{total}" for kind, (ok, total) in kinds.items()},
            summary_statuses=statuses,
            gold_value_admitted=sum(
                bool((row.get("faithfulness") or {}).get("gold_value_admitted"))
                for row in arm_rows
            ),
            forbidden_admitted=sum(
                bool((row.get("faithfulness") or {}).get("forbidden_admitted"))
                for row in arm_rows
            ),
            self_check_defects=sum(
                (row.get("faithfulness") or {}).get("self_check_defects", 0)
                for row in arm_rows
            ),
            median_input_tokens=median(observed(complete, "input_tokens")),
            median_prepare_seconds=median(observed(complete, "prepare_seconds")),
            median_first_text_seconds=median(observed(complete, "first_text_seconds")),
            median_summary_seconds=median(
                sorted(
                    (row.get("summary") or {}).get("seconds")
                    for row in arm_rows
                    if (row.get("summary") or {}).get("seconds") is not None
                )
            ),
        )
    base = {
        row["case_id"]: row
        for row in rows
        if row["arm"] == "budget" and row["status"] == "COMPLETE"
    }
    paired = {}
    for name, _ in ARMS:
        if name == "budget":
            continue
        gains, regressions = [], []
        for row in rows:
            if (
                row["arm"] != name
                or row["status"] != "COMPLETE"
                or row["case_id"] not in base
                or row["case_id"] not in scored
            ):
                continue
            before = base[row["case_id"]]["score"]["strict"]
            if row["score"]["strict"] and not before:
                gains.append(row["case_id"])
            if before and not row["score"]["strict"]:
                regressions.append(row["case_id"])
        paired[name] = dict(gains_vs_budget=gains, regressions_vs_budget=regressions)
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
    """Check the design with an oracle summarizer, freeze, then run every cell once without retries."""
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
    frozen = dict(
        schema_version=1,
        description="HAR-009-C summary v1 frozen benchmark: 12 paraphrase-hostile cases and 2 authority-gate cases, six arms, first outcomes only.",
        corpus=cases,
        arms=[dict(name=name, history_policy=policy) for name, policy in ARMS],
        options=dict(
            preset="fast",
            max_tokens=MAX_TOKENS,
            temperature=TEMPERATURE,
            stream=True,
            retries=0,
        ),
        summary_options=dict(
            prompt_sha256=history_summary.PROMPT_SHA256,
            schema_sha256=history_summary.SCHEMA_SHA256,
            generation=history_summary.GENERATION,
            deadline_seconds=120,
            cache=None,
            reserve_tokens=history_summary.RESERVE_TOKENS,
        ),
        composition_plan=plan,
        native_process=native,
        source_sha256={
            name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
            for name in SOURCES
        },
        analysis=dict(
            primary="strict answers on the 12 scored cases, budget_summary versus budget: paired gains, regressions and new stale answers",
            secondary=[
                "per kind",
                "stale",
                "presence",
                "summary status distribution",
                "gold value admitted",
                "forbidden token admitted",
                "verifier self-check defects (must be 0)",
                "authority-gate capsule contents",
                "cost: summary seconds, input tokens, first text",
            ],
            reference_check="full should reach at least 11/12 on the scored cases",
            adoption="none: measurement only",
        ),
    )
    save_json(output / "frozen-inputs.json", frozen)
    frozen_sha256 = hashlib.sha256(
        (output / "frozen-inputs.json").read_bytes()
    ).hexdigest()
    rows = []
    for attempt, (item, name, policy) in enumerate(schedule(cases), start=1):
        row = dict(
            attempt=attempt,
            case_id=item["id"],
            kind=item["kind"],
            language=item["language"],
            arm=name,
            status="INCOMPLETE",
        )
        started = clock()
        try:
            gateway, fitted, report = await inference.prepare(
                item["messages"], **options_for(name, policy, debug=True)
            )
        except (InferenceFailure, ContextError) as error:
            row.update(
                status="PREPARE_FAILED", error=getattr(error, "code", "prepare_failed")
            )
            rows.append(row)
            save_json(output / f"{attempt:02d}-result.json", row)
            continue
        receipt = report.get("history_policy") or {}
        summary = receipt.get("summary")
        row.update(
            prepare_seconds=round(clock() - started, 6),
            input_tokens=report["input_tokens"],
            present=presence(fitted, item),
            retained_turns=retained(item, fitted, report),
            summary=summary,
            faithfulness=faithfulness(item, summary) if summary else None,
        )
        budget = calculate_budget(
            preset="fast",
            input_tokens=report["input_tokens"],
            requested_max_tokens=MAX_TOKENS,
        )
        payload = build_generation_params(budget)
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
                    timing = await measure(client, payload, clock=clock)
            row.update(
                status="COMPLETE",
                answer=timing["content"],
                first_text_seconds=timing["first_text_delta_seconds"],
                total_seconds=timing["total_seconds"],
                score=score(timing["content"], item),
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
        semantic_quality_claim="controlled synthetic retention only; not general conversation quality",
    )
    save_json(output / "summary.json", result)
    return result, rows


def main():
    """Run one exclusive campaign against the already loaded approved CORE process."""
    parser = argparse.ArgumentParser(
        description="HAR-009-C summary v1 frozen benchmark."
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
