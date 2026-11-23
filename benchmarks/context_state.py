"""Measure the opt-in working state (HAR-009-C1): B2 stale cases with and without state, and multi-window dialogues."""

import argparse
import asyncio
import hashlib
import json
import logging
import time
from pathlib import Path

import httpx

from apps.api.runtime.presets import build_generation_params, calculate_budget
from apps.harness.inference import ProductInference
from benchmarks import context_budget as budget_module
from benchmarks.context_retention import median, observed, presence, score
from benchmarks.har008 import ROOT, save_json
from benchmarks.harness_resources import ResourceSampler, process_memory
from benchmarks.harness_stream_timing import TimingError, measure
from src.application.ports.inference import InferenceFailure
from src.application.services.context_reduction import ContextError

LOGGER = logging.getLogger(__name__)
MAX_TOKENS = 512
TEMPERATURE = 0.7
QUESTION_PAIR = 200
DROP_PAIRS = 32
BOUND = 256
ARMS_A = (
    ("legacy", None),
    ("budget", dict(mode="token-budget")),
    ("budget_state", dict(mode="token-budget", working_state=True)),
)
ARMS_B = (
    ("legacy", None),
    ("budget_drop", dict(mode="token-budget")),
    ("budget_state", dict(mode="token-budget", working_state=True)),
)
SOURCES = (
    "benchmarks/context_state.py",
    "benchmarks/context_budget.py",
    "benchmarks/context_retention.py",
    "benchmarks/harness_stream_timing.py",
    "benchmarks/harness_resources.py",
    "src/application/services/context_composer.py",
    "src/application/services/context_reduction.py",
    "src/application/services/working_state.py",
    "src/application/services/conversation_context.py",
    "apps/harness/inference.py",
    "apps/cli/main.py",
    "apps/api/runtime/presets.py",
    "configs/models.yaml",
)


def long_case(
    identifier, kind, language, targets, question, required, forbidden, evidence
):
    """Build one 200-pair dialogue: fixed targets, short fillers elsewhere, the question as pair 200's user message."""
    pool = budget_module.SHORT_FILLER[language]
    offset = sum(map(ord, identifier)) % len(pool)
    pairs = []
    for number in range(1, QUESTION_PAIR):
        if number in targets:
            pairs.append(targets[number])
        else:
            pairs.append(pool[(offset + number) % len(pool)])
    suffix = (
        " Trả lời ngắn gọn trong một dòng."
        if language == "vi"
        else " Answer in one short line."
    )
    return dict(
        id=identifier,
        part="B",
        kind=kind,
        regime="multiwindow",
        language=language,
        target_turns=sorted(targets),
        pairs=pairs,
        question=question + suffix,
        required=required,
        forbidden=forbidden,
        evidence=evidence,
    )


def multiwindow_corpus():
    """Return six frozen 200-pair cases whose targets all lie in pairs the client drops before the question."""
    return [
        long_case(
            "mw-decision-region",
            "keyed_decision_update",
            "en",
            {
                3: (
                    "Decision[db-region]: the reporting database runs in Frankfurt.",
                    "Noted: Frankfurt.",
                ),
                70: (
                    "Decision[db-region]: the reporting database moves to Warsaw.",
                    "Updated: Warsaw.",
                ),
            },
            "Which city does the reporting database run in now?",
            [["Warsaw"]],
            ["Frankfurt"],
            ["Warsaw"],
        ),
        long_case(
            "mw-rule-invoice",
            "early_rule",
            "en",
            {
                2: (
                    "Rule: every invoice number uses the prefix INV-ACME- followed by the number.",
                    "Understood.",
                ),
                199: (
                    "The new invoice for the printer lease is number 5521.",
                    "Logged: invoice 5521.",
                ),
            },
            "Give the full number of the new invoice for the printer lease.",
            [["INV-ACME-5521"]],
            [],
            ["INV-ACME-", "number 5521"],
        ),
        long_case(
            "mw-todo-open",
            "todo_closed",
            "en",
            {
                5: (
                    "Todo[backup]: verify the nightly backup restore.",
                    "Added to the list.",
                ),
                40: (
                    "Todo[cert]: renew the portal TLS certificate.",
                    "Added to the list.",
                ),
                90: ("Done[backup]: the nightly restore was verified.", "Closed."),
            },
            "Which tracked task is still open? Name only that task.",
            [["certificate"]],
            ["backup"],
            ["TLS certificate"],
        ),
        long_case(
            "mw-goal-vi",
            "goal",
            "vi",
            {
                1: (
                    "Mục tiêu: chuyển dịch vụ báo cáo sang Postgres 17 trước tháng Ba.",
                    "Đã ghi nhận mục tiêu.",
                )
            },
            "Mục tiêu của dự án hiện tại là gì?",
            [["Postgres 17"]],
            [],
            ["Postgres 17"],
        ),
        long_case(
            "mw-decision-vi",
            "keyed_decision_update",
            "vi",
            {
                4: ("Quyết định[máy-chủ]: đặt máy chủ chính ở Hà Nội.", "Đã ghi."),
                80: (
                    "Quyết định[máy-chủ]: chuyển máy chủ chính vào Đà Nẵng.",
                    "Đã cập nhật.",
                ),
            },
            "Máy chủ chính hiện đặt ở thành phố nào?",
            [["Đà Nẵng"]],
            ["Hà Nội"],
            ["Đà Nẵng"],
        ),
        long_case(
            "mw-unmarked-control",
            "unmarked_fact",
            "en",
            {
                3: (
                    "Which port does the Lynx metrics agent listen on?",
                    "The Lynx metrics agent listens on port 9464.",
                )
            },
            "Which port does the Lynx metrics agent listen on?",
            [["9464"]],
            [],
            ["9464"],
        ),
    ]


def history(pairs):
    """Flatten (user, assistant) pairs into alternating chat messages."""
    rows = []
    for user, assistant in pairs:
        rows += [
            dict(role="user", content=user),
            dict(role="assistant", content=assistant),
        ]
    return rows


async def client_requests(inference, item, policy):
    """Replay the CLI window rule and return the final request and its policy, carrying state through real compositions."""
    pairs = item["pairs"]
    if policy is None:
        return (
            history(pairs)[-22:] + [dict(role="user", content=item["question"])],
            None,
            [],
            None,
        )
    start, offset, carried, drops = 0, 0, [], []
    for request in range(1, QUESTION_PAIR + 1):
        if 2 * (request - 1 - start) >= BOUND:
            if policy.get("working_state"):
                window = history(pairs[start : request - 2]) + [
                    dict(role="user", content=pairs[request - 2][0])
                ]
                body = {
                    **policy,
                    "carried_state": [
                        entry for entry in carried if entry["turn"] <= offset
                    ],
                    "history_offset": offset,
                }
                _, _, report = await inference.prepare(
                    window, preset="fast", max_tokens=MAX_TOKENS, history_policy=body
                )
                carried = report["history_policy"]["working_state"]["items"]
            start, offset = start + DROP_PAIRS, offset + DROP_PAIRS
            drops.append(request)
    final = dict(policy)
    if policy.get("working_state"):
        final.update(
            carried_state=[entry for entry in carried if entry["turn"] <= offset],
            history_offset=offset,
        )
    messages = history(pairs[start:]) + [dict(role="user", content=item["question"])]
    return messages, final, drops, offset


def expectations_b(item, arm, plan):
    """Return design violations for the multi-window part."""
    problems = []
    retained_targets = [
        turn for turn in item["target_turns"] if turn > plan["history_offset"]
    ]
    if arm != "legacy" and plan["history_offset"] != 96:
        problems.append("client_did_not_drop_three_windows")
    if (
        arm == "budget_state"
        and item["kind"] != "unmarked_fact"
        and not plan["carried_items"]
    ):
        problems.append("state_arm_carries_nothing")
    if item["kind"] != "early_rule" and retained_targets:
        problems.append("target_still_inside_the_final_window")
    return problems


def schedule(specs):
    """Rotate arm order per case so no arm always runs first."""
    plan = []
    for index, group in enumerate(specs):
        plan.extend(group[index % len(group) :] + group[: index % len(group)])
    return plan


def summarize(rows):
    """Aggregate strict, stale and presence per part and arm, plus paired changes against legacy."""
    out = {}
    for part in ("A", "B"):
        part_rows = [row for row in rows if row["part"] == part]
        arms = sorted({row["arm"] for row in part_rows})
        by_arm = {}
        for arm in arms:
            arm_rows = [row for row in part_rows if row["arm"] == arm]
            complete = [row for row in arm_rows if row["status"] == "COMPLETE"]
            kinds = {}
            for row in complete:
                kinds.setdefault(row["kind"], [0, 0])
                kinds[row["kind"]][1] += 1
                kinds[row["kind"]][0] += row["score"]["strict"]
            by_arm[arm] = dict(
                attempts=len(arm_rows),
                complete=len(complete),
                strict=sum(row["score"]["strict"] for row in complete),
                stale=sum(bool(row["score"]["stale"]) for row in complete),
                present=sum(bool(row.get("present")) for row in arm_rows),
                by_kind={kind: f"{ok}/{total}" for kind, (ok, total) in kinds.items()},
                median_input_tokens=median(observed(complete, "input_tokens")),
                max_input_tokens=max(observed(complete, "input_tokens"), default=None),
                median_prepare_seconds=median(observed(complete, "prepare_seconds")),
                median_first_text_seconds=median(
                    observed(complete, "first_text_seconds")
                ),
                median_total_seconds=median(observed(complete, "total_seconds")),
            )
        legacy = {
            row["case_id"]: row
            for row in part_rows
            if row["arm"] == "legacy" and row["status"] == "COMPLETE"
        }
        paired = {}
        for arm in arms:
            if arm == "legacy":
                continue
            gains, regressions = [], []
            for row in part_rows:
                if (
                    row["arm"] != arm
                    or row["status"] != "COMPLETE"
                    or row["case_id"] not in legacy
                ):
                    continue
                base = legacy[row["case_id"]]["score"]["strict"]
                if row["score"]["strict"] and not base:
                    gains.append(row["case_id"])
                if base and not row["score"]["strict"]:
                    regressions.append(row["case_id"])
            paired[arm] = dict(gains_vs_legacy=gains, regressions_vs_legacy=regressions)
        out[part] = dict(by_arm=by_arm, paired=paired)
    return out


async def design(inference):
    """Compose every attempt with the native tokenizer only and collect placements, final requests and violations."""
    specs, plan, violations = [], [], []
    for item in budget_module.corpus():
        group = []
        for arm, policy in ARMS_A:
            options = dict(preset="fast", max_tokens=MAX_TOKENS)
            if policy is not None:
                options["history_policy"] = policy
            _, fitted, report = await inference.prepare(item["messages"], **options)
            retained = budget_module.retained_turns(item, fitted, report)
            receipt = report.get("history_policy") or {}
            entry = dict(
                part="A",
                case_id=item["id"],
                arm=arm,
                retained_turns=retained,
                input_tokens=report["input_tokens"],
                present=presence(fitted, item),
                newer_related=[
                    e["turn"]
                    for e in receipt.get("selection", [])
                    if e["reason"] == "newer_related"
                ],
            )
            plan.append(entry)
            if (
                arm == "budget_state"
                and item["kind"] == "stale_marked_rule"
                and not {1, 6} <= set(retained)
            ):
                violations.append(
                    dict(
                        case_id=item["id"],
                        arm=arm,
                        problem="state_arm_lost_rule_or_correction",
                    )
                )
            if arm in {"legacy", "budget"}:
                for problem in budget_module.expectations(item, arm, retained):
                    violations.append(
                        dict(case_id=item["id"], arm=arm, problem=problem)
                    )
            group.append(
                dict(
                    part="A",
                    item=item,
                    arm=arm,
                    messages=item["messages"],
                    policy=policy,
                )
            )
        specs.append(group)
    for item in multiwindow_corpus():
        group = []
        for arm, policy in ARMS_B:
            messages, final, drops, offset = await client_requests(
                inference, item, policy
            )
            options = dict(preset="fast", max_tokens=MAX_TOKENS)
            if final is not None:
                options["history_policy"] = final
            _, fitted, report = await inference.prepare(messages, **options)
            entry = dict(
                part="B",
                case_id=item["id"],
                arm=arm,
                history_offset=offset,
                drops_before_requests=drops,
                carried_items=len((final or {}).get("carried_state", ())),
                input_tokens=report["input_tokens"],
                present=presence(fitted, item),
                messages=len(messages),
            )
            plan.append(entry)
            if arm != "legacy":
                for problem in expectations_b(item, arm, entry):
                    violations.append(
                        dict(case_id=item["id"], arm=arm, problem=problem)
                    )
            group.append(
                dict(part="B", item=item, arm=arm, messages=messages, policy=final)
            )
        specs.append(group)
    return specs, plan, violations


async def run(
    inference,
    output,
    *,
    pid,
    sampler_factory=ResourceSampler,
    preflight=process_memory,
    clock=time.monotonic,
):
    """Check the design with the tokenizer, freeze, then run every attempt once without retries."""
    output = Path(output)
    native = preflight(pid)
    output.mkdir(mode=0o700, parents=False, exist_ok=False)
    specs, plan, violations = await design(inference)
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
        description="HAR-009-C1 frozen working-state benchmark: B2 corpus with and without state (part A) and six 200-pair multi-window dialogues (part B); first outcomes only.",
        corpus_a=budget_module.corpus(),
        corpus_b=multiwindow_corpus(),
        arms_a=[dict(name=name, history_policy=policy) for name, policy in ARMS_A],
        arms_b=[dict(name=name, history_policy=policy) for name, policy in ARMS_B],
        client_rule=dict(
            bound_messages=BOUND, drop_pairs=DROP_PAIRS, legacy_keeps_messages=22
        ),
        options=dict(
            preset="fast",
            max_tokens=MAX_TOKENS,
            temperature=TEMPERATURE,
            stream=True,
            retries=0,
        ),
        composition_plan=plan,
        native_process=native,
        source_sha256={
            name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
            for name in SOURCES
        },
        analysis=dict(
            primary="strict answer success per arm in each part",
            secondary=[
                "stale answers",
                "facts present in the composed input",
                "results per kind",
                "paired gains and regressions against legacy",
                "input tokens, prepare, first text and total seconds",
                "sampled CORE RSS and GPU peaks",
            ],
            design_expectations=[
                "part A: legacy and budget placements as in B2; budget_state keeps pairs 1 and 6 in both stale cases",
                "part B: state and drop arms end at history_offset 96 after three client drops; no target except the invoice detail remains in the final window; the state arm carries items",
            ],
            adoption="none: measurement only; default or adoption decisions stay with the owner",
        ),
    )
    save_json(output / "frozen-inputs.json", frozen)
    frozen_sha256 = hashlib.sha256(
        (output / "frozen-inputs.json").read_bytes()
    ).hexdigest()
    rows = []
    for attempt, spec in enumerate(schedule(specs), start=1):
        item = spec["item"]
        row = dict(
            attempt=attempt,
            part=spec["part"],
            case_id=item["id"],
            kind=item["kind"],
            language=item["language"],
            arm=spec["arm"],
            status="INCOMPLETE",
        )
        options = dict(preset="fast", max_tokens=MAX_TOKENS)
        if spec["policy"] is not None:
            options["history_policy"] = spec["policy"]
        started = clock()
        try:
            gateway, fitted, report = await inference.prepare(
                spec["messages"], **options
            )
        except (InferenceFailure, ContextError) as error:
            row.update(
                status="PREPARE_FAILED", error=getattr(error, "code", "prepare_failed")
            )
            rows.append(row)
            save_json(output / f"{attempt:02d}-result.json", row)
            continue
        receipt = report.get("history_policy") or {}
        row.update(
            prepare_seconds=round(clock() - started, 6),
            input_tokens=report["input_tokens"],
            present=presence(fitted, item),
            working_state_summary=receipt.get("working_state_summary"),
            selection=receipt.get("selection"),
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
    expected = sum(len(group) for group in specs)
    result = dict(
        schema_version=1,
        status="COMPLETE"
        if len(rows) == expected and all(row["status"] == "COMPLETE" for row in rows)
        else "INCOMPLETE",
        frozen_sha256=frozen_sha256,
        attempts=len(rows),
        retries=0,
        summary=summarize(rows),
        native_calls=sum(
            row["status"] in {"COMPLETE", "STREAM_FAILED"} for row in rows
        ),
        semantic_quality_claim="controlled synthetic retention only; not general conversation quality",
    )
    save_json(output / "summary.json", result)
    LOGGER.info("context_state_closed attempts=%d", len(rows))
    return result, rows


def main():
    """Run one exclusive campaign against the already loaded approved CORE process."""
    parser = argparse.ArgumentParser(
        description="HAR-009-C1 frozen working-state benchmark."
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
