"""Measure fresh target-bound line/quote review outcomes against the unchanged generic source contract."""

import argparse
import hashlib
import json
import logging
import re
import time
from pathlib import Path
from uuid import UUID, uuid4

from apps.cli.client import ApiClient, DEFAULT_TOKEN, read_token
from benchmarks.har008 import ROOT, SKILLS, save_json, score_answer, unique_object
from benchmarks.har008_maintenance import task_text
from benchmarks.harness_resources import ResourceSampler, process_memory
from src.application.services.source_output_contract import NAME
from src.application.services.review_output_contract import (
    NAME as REVIEW_NAME,
    QUOTE_FIRST_NAME,
)

LOGGER = logging.getLogger(__name__)
CORPUS = ROOT / "benchmarks/fixtures/har008-l1-order-v1.json"
CATEGORIES = {"review-defect", "review-caller", "review-control"}
ARMS = (
    "generic_baseline",
    "generic_skill",
    "value_baseline",
    "value_skill",
    "quote_baseline",
    "quote_skill",
)


def load_panel(raw):
    """Reject ambiguous or unbounded input/oracles before any task is submitted or source fixture executed."""
    panel = json.loads(raw, object_pairs_hook=unique_object)
    if (
        type(panel) is not dict
        or set(panel) != {"description", "schema_version", "cases"}
        or type(panel["schema_version"]) is not int
        or panel["schema_version"] != 1
        or not isinstance(panel["description"], str)
        or type(panel["cases"]) is not list
        or len(panel["cases"]) != 12
    ):
        raise ValueError("invalid_maintenance_panel")
    seen = set()
    for case in panel["cases"]:
        if type(case) is not dict or set(case) != {
            "id",
            "read_start",
            "category",
            "skill",
            "sources",
            "target",
            "question",
            "value",
            "quote",
        }:
            raise ValueError("invalid_maintenance_case")
        if (
            type(case["id"]) is not str
            or re.fullmatch(r"[a-z][a-z0-9-]{0,63}", case["id"]) is None
            or case["id"] in seen
            or case["category"] not in CATEGORIES
            or case["skill"]
            != (
                "repo-review"
                if case["category"].startswith("review-")
                else "source-reader"
            )
        ):
            raise ValueError("invalid_maintenance_identity")
        seen.add(case["id"])
        if (
            type(case["sources"]) is not list
            or not 1 <= len(case["sources"]) <= 2
            or type(case["question"]) is not str
            or not 1 <= len(case["question"].encode()) <= 6000
        ):
            raise ValueError("invalid_maintenance_input")
        paths, quotes = set(), set()
        for source in case["sources"]:
            if (
                type(source) is not dict
                or set(source) != {"path", "text"}
                or type(source["path"]) is not str
                or re.fullmatch(r"[a-z][a-z0-9-]{0,90}\.(md|py)", source["path"])
                is None
                or source["path"] in paths
                or type(source["text"]) is not str
                or not 1 <= len(source["text"].encode()) <= 14000
                or "\r" in source["text"]
                or len(source["text"].splitlines()) > 100
            ):
                raise ValueError("invalid_maintenance_source")
            paths.add(source["path"])
            quotes.update(
                line.strip(" \t")
                for line in source["text"].splitlines()
                if line.strip(" \t")
            )
        if (
            len(quotes) > 128
            or sum(len(quote.encode()) for quote in quotes) > 16384
            or any(len(quote.encode()) > 1024 for quote in quotes)
        ):
            raise ValueError("maintenance_catalog_overflow")
        value = case["value"]
        if (
            type(value) not in {str, int, type(None)}
            or (type(value) is str and not 1 <= len(value) <= 256)
            or (type(value) is int and not -2147483648 <= value <= 2147483647)
        ):
            raise ValueError("invalid_maintenance_value")
        if value is None:
            if case["quote"] is not None:
                raise ValueError("invalid_maintenance_null")
        elif type(case["quote"]) is not str or case["quote"] not in quotes:
            raise ValueError("invalid_maintenance_quote")
        if type(case["read_start"]) is not int or not 1 <= case["read_start"] <= 100:
            raise ValueError("invalid_review_read_range")
        if case["skill"] == "repo-review":
            targets = [
                source for source in case["sources"] if source["path"] == case["target"]
            ]
            if len(targets) != 1:
                raise ValueError("missing_review_target")
            if case["read_start"] > len(targets[0]["text"].splitlines()) or (
                value is not None and value < case["read_start"]
            ):
                raise ValueError("oracle_outside_review_range")
            if value is not None and (
                type(value) is not int
                or not 1 <= value <= len(targets[0]["text"].splitlines())
                or targets[0]["text"].splitlines()[value - 1].strip(" \t")
                != case["quote"]
            ):
                raise ValueError("invalid_maintenance_review_line")
        elif case["target"] is not None:
            raise ValueError("unexpected_review_target")
    if any(
        sum(case["category"] == category for case in panel["cases"]) != 4
        for category in CATEGORIES
    ):
        raise ValueError("unbalanced_maintenance_panel")
    LOGGER.info("har008_q2_panel_validated cases=%d", len(seen))
    return panel["cases"]


def pair_valid(case, content):
    """Check raw number/quote membership against actual target lines, without consulting the gold finding."""
    try:
        answer = json.loads(content, object_pairs_hook=unique_object)
        if type(answer) is not dict or set(answer) != {"value", "quote"}:
            return False
        if answer["value"] is None:
            return answer["quote"] is None
        target = next(
            source for source in case["sources"] if source["path"] == case["target"]
        )
        lines = target["text"].splitlines()
        number = answer["value"]
        return (
            type(number) is int
            and case["read_start"] <= number <= len(lines)
            and lines[number - 1].strip(" \t") == answer["quote"]
        )
    except (ValueError, TypeError, KeyError, StopIteration):
        return False


def aggregate(rows, cases):
    """Report complete four-arm blocks, separate mechanics and semantics, and within-cohort discordance."""
    identifiers = {case["id"] for case in cases}
    keys = [(row["case_id"], row["arm"]) for row in rows]
    if len(keys) != len(set(keys)) or any(
        identifier not in identifiers or arm not in ARMS for identifier, arm in keys
    ):
        raise ValueError("invalid_outcome_set")
    totals = {}
    for arm in ARMS:
        selected = [row for row in rows if row["arm"] == arm]
        totals[arm] = {
            "attempts": len(selected),
            **{
                metric: sum(row["score"][metric] for row in selected)
                for metric in ("format", "value", "quote", "passed")
            },
            "contract_failures": sum(row["contract_failed"] for row in selected),
        }
    comparisons = {}
    for before, after in (
        (ARMS[0], ARMS[1]),
        (ARMS[2], ARMS[3]),
        (ARMS[0], ARMS[2]),
        (ARMS[1], ARMS[3]),
        (ARMS[4], ARMS[5]),
        (ARMS[0], ARMS[4]),
        (ARMS[1], ARMS[5]),
        (ARMS[2], ARMS[4]),
        (ARMS[3], ARMS[5]),
    ):
        pairs = []
        for identifier in identifiers:
            selected = {row["arm"]: row for row in rows if row["case_id"] == identifier}
            if before in selected and after in selected:
                pairs.append(
                    (
                        selected[before]["score"]["passed"],
                        selected[after]["score"]["passed"],
                    )
                )
        comparisons[before + "_to_" + after] = {
            "pairs": len(pairs),
            "gains": sum(not left and right for left, right in pairs),
            "regressions": sum(left and not right for left, right in pairs),
        }
    return {
        "expected_attempts": len(cases) * len(ARMS),
        "completed_attempts": len(rows),
        "complete_blocks": sum(
            sum(row["case_id"] == identifier for row in rows) == len(ARMS)
            for identifier in identifiers
        ),
        "arms": totals,
        "comparisons": comparisons,
        "status": "MEASUREMENT_COMPLETE"
        if len(rows) == len(cases) * len(ARMS)
        else "INCOMPLETE",
        "promotion": "NOT_QUALIFIED",
        "reason": "Same-author controlled panel; source-valid JSON does not establish entailment or broad specialist quality.",
    }


def summarize(rows, cases):
    """Keep semantic/category outcomes and sampled resource availability separate from broad promotion."""
    summary = aggregate(rows, cases)
    summary["categories"] = {
        category: aggregate(
            [row for row in rows if row["category"] == category],
            [case for case in cases if case["category"] == category],
        )["arms"]
        for category in sorted(CATEGORIES)
    }
    metrics = [row["resource_summary"] for row in rows]
    summary["resources"] = {
        "status": "COMPLETE"
        if len(rows) == len(cases) * len(ARMS)
        and all(row["status"] == "COMPLETE" for row in metrics)
        else "INCOMPLETE",
        "measured_attempts": len(metrics),
        "sampled_peak_rss_kib": max(
            (row["sampled_peak_rss_kib"] for row in metrics), default=None
        ),
        "sampled_peak_gpu_process_mib": max(
            (row["sampled_peak_gpu_process_mib"] for row in metrics), default=None
        ),
        "limits": "Warm process RSS/allocation sampled every 0.2 seconds; not absolute peaks or per-model tensor consumption. TTFT is unobservable on this nonstreaming task API and needs the separate predeclared streaming replay.",
    }
    summary["reason"] = (
        "Same-author controlled maintenance panel, one draw per arm/case; broader independent generalization and skill benefit remain unestablished."
    )
    summary["line_pair_invalid"] = {
        arm: sum(not row["line_pair_valid"] for row in rows if row["arm"] == arm)
        for arm in ARMS
    }
    return summary


def evaluate(
    api,
    workspace,
    workspace_root,
    output,
    *,
    pid,
    corpus_path=CORPUS,
    sampler_factory=ResourceSampler,
    preflight=process_memory,
    clock=time.monotonic,
    pause=time.sleep,
):
    """Freeze a new cohort before inference and retain every first response, including failed contracts, without retries."""
    raw = corpus_path.read_bytes()
    cases = load_panel(raw)
    native = preflight(pid)
    output = Path(output)
    output.mkdir(mode=0o700, parents=False, exist_ok=False)
    source_root = Path(workspace_root)
    if source_root.is_symlink() or not source_root.is_dir():
        raise ValueError("explicit_workspace_root_required")
    folder = "har008-l1-order-" + uuid4().hex
    directory = source_root / folder
    directory.mkdir(mode=0o700, exist_ok=False)
    for case in cases:
        child = directory / case["id"]
        child.mkdir(mode=0o700)
        for source in case["sources"]:
            with (child / source["path"]).open("x") as stream:
                stream.write(source["text"])
    manifest = {
        "description": "Frozen HAR-008-L1 six-arm review order panel; gold oracles never enter requests.",
        "native_process": native,
        "corpus_sha256": hashlib.sha256(raw).hexdigest(),
        "corpus": json.loads(raw),
        "workspace_id": str(workspace),
        "source_folder": folder,
        "source_sha256": {
            case["id"] + "/" + source["path"]: hashlib.sha256(
                source["text"].encode()
            ).hexdigest()
            for case in cases
            for source in case["sources"]
        },
        "skill_sha256": {
            name: hashlib.sha256(path.read_bytes()).hexdigest()
            for name, path in SKILLS.items()
        },
        "source_files_sha256": {
            str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (
                Path(__file__),
                ROOT / "benchmarks/harness_resources.py",
                ROOT / "benchmarks/harness_stream_timing.py",
                ROOT / "benchmarks/har008_contract.py",
                ROOT / "benchmarks/har008.py",
                ROOT / "apps/harness/service.py",
                ROOT / "apps/harness/inference.py",
                ROOT / "apps/harness/routes.py",
                ROOT / "src/application/services/context_composer.py",
                ROOT / "src/application/services/source_output_contract.py",
                ROOT / "src/application/services/review_output_contract.py",
                ROOT / "apps/cli/main.py",
                ROOT / "configs/models.yaml",
                ROOT / "configs/llama-cpp-commit.txt",
            )
        },
        "options": {
            "profile": "core",
            "preset": "fast",
            "max_tokens": 512,
            "context_strategy": "strict",
            "arms": ARMS,
            "attempts": len(cases) * len(ARMS),
            "retries": 0,
            "campaign_seconds": 900,
            "order": "cyclic four-arm rotation by case index",
        },
    }
    save_json(output / "frozen-inputs.json", manifest)
    installs, created, rows = {}, [], []
    started, deadline = clock(), clock() + 900
    active, submission_uncertain, completed = None, False, False
    try:
        existing = api.request("GET", "/api/v1/harness/skills")
        for name, path in SKILLS.items():
            matches = [
                row
                for row in existing
                if row["workspace_id"] == str(workspace)
                and row["id"] == name
                and row["sha256"] == manifest["skill_sha256"][name]
            ]
            if len(matches) > 1:
                raise ValueError("ambiguous_installation")
            if matches:
                installs[name] = matches[0]["installation_id"]
                continue
            review = api.request(
                "POST",
                "/api/v1/harness/skills/reviews",
                {"workspace_id": str(workspace), "manifest": path.read_text()},
            )
            result = api.request(
                "POST",
                "/api/v1/harness/skills/installations",
                {
                    "workspace_id": str(workspace),
                    "review_id": review["review_id"],
                    "sha256": review["sha256"],
                },
            )
            installs[name] = result["installation_id"]
            created.append(result["installation_id"])
        for index, case in enumerate(cases):
            rotation = index % len(ARMS)
            for arm in ARMS[rotation:] + ARMS[:rotation]:
                if clock() >= deadline:
                    raise TimeoutError("campaign_deadline")
                source_paths = [
                    f"{folder}/{case['id']}/{source['path']}"
                    for source in case["sources"]
                ]
                request = dict(
                    workspace_id=str(workspace),
                    task=task_text(case, source_paths),
                    tools=[
                        dict(
                            name="workspace.read",
                            arguments=dict(
                                path=path,
                                start_line=case["read_start"]
                                if path.endswith("/" + case["target"])
                                else 1,
                                end_line=200,
                            ),
                        )
                        for path in source_paths
                    ],
                    skill=installs[case["skill"]] if arm.endswith("_skill") else None,
                    preset="fast",
                    max_tokens=512,
                    context_strategy="strict",
                    output_contract=QUOTE_FIRST_NAME
                    if arm.startswith("quote_")
                    else REVIEW_NAME
                    if arm.startswith("value_")
                    else NAME,
                    review_target=next(
                        path
                        for path in source_paths
                        if path.endswith("/" + case["target"])
                    )
                    if not arm.startswith("generic_")
                    else None,
                )
                attempt = len(rows) + 1
                save_json(output / f"{attempt:02d}-request.json", request)
                with sampler_factory(
                    pid, expected_start=manifest["native_process"]["start_ticks"]
                ) as telemetry:
                    before = clock()
                    submission_uncertain = True
                    row = api.request("POST", "/api/v1/harness/runs", request)
                    active = row["id"]
                    submission_uncertain = False
                    while row["state"] not in {"succeeded", "failed", "cancelled"}:
                        if clock() >= min(deadline, before + 125):
                            raise TimeoutError("attempt_deadline")
                        pause(0.1)
                        row = api.request("GET", f"/api/v1/harness/runs/{active}")
                    save_json(output / f"{attempt:02d}-response.json", row)
                    elapsed = clock() - before
                resources = telemetry.report()
                save_json(output / f"{attempt:02d}-resources.json", resources)
                contract_failed = (
                    row["state"] == "failed"
                    and row.get("diagnostic", {}).get("code")
                    == "source_contract_invalid"
                    and request["output_contract"]
                    in {NAME, REVIEW_NAME, QUOTE_FIRST_NAME}
                )
                if row["state"] != "succeeded" and not contract_failed:
                    raise ValueError("native_attempt_failed")
                native = (
                    row.get("diagnostic", {}).get("raw_result")
                    if contract_failed
                    else row["result"]
                )
                context = row.get("context")
                if not contract_failed and (
                    context["skill_sha256"]
                    != (
                        manifest["skill_sha256"][case["skill"]]
                        if request["skill"]
                        else None
                    )
                    or len(context["included_evidence"]) != len(case["sources"])
                    or (
                        request["output_contract"]
                        in {NAME, REVIEW_NAME, QUOTE_FIRST_NAME}
                        and context.get("output_contract", {}).get("status") != "VALID"
                    )
                ):
                    raise ValueError("context_binding_mismatch")
                if not contract_failed and (
                    context["output_contract"]["name"] != request["output_contract"]
                    or (
                        not arm.startswith("generic_")
                        and context["output_contract"].get("review_target")
                        != request["review_target"]
                    )
                ):
                    raise ValueError("review_contract_binding_mismatch")
                try:
                    content = native["choices"][0]["message"]["content"]
                except (TypeError, KeyError, IndexError):
                    content = None
                score = score_answer(content, case)
                if contract_failed:
                    score["passed"] = False
                result = dict(
                    case_id=case["id"],
                    arm=arm,
                    elapsed_seconds=round(elapsed, 6),
                    category=case["category"],
                    resource_summary={
                        key: value
                        for key, value in resources.items()
                        if key != "samples"
                    },
                    score=score,
                    line_pair_valid=pair_valid(case, content),
                    contract_failed=contract_failed,
                    usage=native.get("usage") if isinstance(native, dict) else None,
                    model=native.get("model") if isinstance(native, dict) else None,
                    context=context,
                )
                rows.append(result)
                save_json(output / f"{attempt:02d}-score.json", result)
                api.request("DELETE", f"/api/v1/harness/runs/{active}")
                active = None
                LOGGER.info(
                    "har008_l1_order_attempt_completed attempt=%d arm=%s passed=%s contract_failed=%s",
                    attempt,
                    arm,
                    score["passed"],
                    contract_failed,
                )
        if (
            any(
                hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != expected
                for name, expected in manifest["source_files_sha256"].items()
            )
            or any(
                hashlib.sha256(
                    (directory / case["id"] / source["path"]).read_bytes()
                ).hexdigest()
                != manifest["source_sha256"][case["id"] + "/" + source["path"]]
                for case in cases
                for source in case["sources"]
            )
            or corpus_path.read_bytes() != raw
            or any(
                hashlib.sha256(path.read_bytes()).hexdigest()
                != manifest["skill_sha256"][name]
                for name, path in SKILLS.items()
            )
        ):
            raise ValueError("frozen_inputs_changed")
        completed = True
    finally:
        summary = summarize(rows, cases)
        if not completed:
            summary["status"] = "INCOMPLETE"
        cleanup_failures = int(submission_uncertain)
        if active is not None:
            try:
                api.request("POST", f"/api/v1/harness/runs/{active}/cancel", {})
            except Exception:
                cleanup_failures += 1
                LOGGER.warning("har008_l1_order_active_cleanup_failed")
        for identifier in created:
            try:
                api.request(
                    "DELETE",
                    f"/api/v1/harness/skills/installations/{identifier}?workspace_id={workspace}",
                )
            except Exception:
                cleanup_failures += 1
                LOGGER.warning("har008_l1_order_grant_cleanup_failed")
        summary.update(
            cleanup_failures=cleanup_failures,
            unidentified_submission=submission_uncertain,
            elapsed_seconds=round(clock() - started, 3),
        )
        save_json(output / "summary.json", summary)
    return summary


def main():
    """Run one finite campaign with explicit workspace, native PID and new private output location."""
    parser = argparse.ArgumentParser(
        description="Run HAR-008-L1 target line/quote review measurement."
    )
    parser.add_argument("--workspace", type=UUID, required=True)
    parser.add_argument("--workspace-root", type=Path, required=True)
    parser.add_argument("--pid", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--url", default="http://127.0.0.1:7092")
    parser.add_argument("--token-file", type=Path, default=DEFAULT_TOKEN)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    result = evaluate(
        ApiClient(args.url, read_token(args.token_file)),
        args.workspace,
        args.workspace_root,
        args.output,
        pid=args.pid,
    )
    print(json.dumps(result))


if __name__ == "__main__":
    main()
