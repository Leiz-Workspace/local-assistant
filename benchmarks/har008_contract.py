"""Measure four first-outcome output-contract/skill arms on a new frozen controlled cohort."""

import argparse
import hashlib
import json
import logging
import time
from pathlib import Path
from uuid import UUID, uuid4

from apps.cli.client import ApiClient, DEFAULT_TOKEN, read_token
from benchmarks.har008 import (
    ROOT,
    SKILLS,
    load_cases,
    save_json,
    score_answer,
    task_text,
)
from src.application.services.source_output_contract import NAME

LOGGER = logging.getLogger(__name__)
CORPUS = ROOT / "benchmarks/fixtures/har008-source-review-r1.json"
ARMS = ("text_baseline", "text_skill", "constrained_baseline", "constrained_skill")


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


def evaluate(
    api,
    workspace,
    workspace_root,
    output,
    *,
    corpus_path=CORPUS,
    clock=time.monotonic,
    pause=time.sleep,
):
    """Freeze a new cohort before inference and retain every first response, including failed contracts, without retries."""
    raw = corpus_path.read_bytes()
    cases = load_cases(raw)
    for case in cases:
        if case["quote"] is not None and case["quote"] not in [
            line.strip(" \t") for line in case["source"].splitlines()
        ]:
            raise ValueError("oracle_not_a_canonical_whole_line")
    output = Path(output)
    output.mkdir(mode=0o700, parents=False, exist_ok=False)
    source_root = Path(workspace_root)
    if source_root.is_symlink() or not source_root.is_dir():
        raise ValueError("explicit_workspace_root_required")
    folder = "har008-r1-" + uuid4().hex
    directory = source_root / folder
    directory.mkdir(mode=0o700, exist_ok=False)
    for case in cases:
        with (directory / (case["id"] + ".md")).open("x") as stream:
            stream.write(case["source"])
    manifest = {
        "description": "Frozen HAR-008-R1 four-arm controlled cohort; oracle fields never enter model requests.",
        "corpus_sha256": hashlib.sha256(raw).hexdigest(),
        "corpus": json.loads(raw),
        "workspace_id": str(workspace),
        "source_folder": folder,
        "source_sha256": {
            case["id"]: hashlib.sha256(case["source"].encode()).hexdigest()
            for case in cases
        },
        "skill_sha256": {
            name: hashlib.sha256(path.read_bytes()).hexdigest()
            for name, path in SKILLS.items()
        },
        "source_files_sha256": {
            str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (
                Path(__file__),
                ROOT / "benchmarks/har008.py",
                ROOT / "apps/harness/service.py",
                ROOT / "apps/harness/inference.py",
                ROOT / "apps/harness/routes.py",
                ROOT / "src/application/services/context_composer.py",
                ROOT / "src/application/services/source_output_contract.py",
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
            "attempts": 48,
            "retries": 0,
            "campaign_seconds": 480,
            "order": "cyclic four-arm rotation by case index",
        },
    }
    save_json(output / "frozen-inputs.json", manifest)
    installs, created, rows = {}, [], []
    started, deadline = clock(), clock() + 480
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
                source = f"{folder}/{case['id']}.md"
                request = dict(
                    workspace_id=str(workspace),
                    task=task_text(case, source),
                    tools=[dict(name="workspace.read", arguments=dict(path=source))],
                    skill=installs[case["skill"]] if arm.endswith("_skill") else None,
                    preset="fast",
                    max_tokens=512,
                    context_strategy="strict",
                    output_contract=NAME if arm.startswith("constrained_") else "text",
                )
                attempt = len(rows) + 1
                save_json(output / f"{attempt:02d}-request.json", request)
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
                contract_failed = (
                    row["state"] == "failed"
                    and row.get("diagnostic", {}).get("code")
                    == "source_contract_invalid"
                    and request["output_contract"] == NAME
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
                    or len(context["included_evidence"]) != 1
                    or (
                        request["output_contract"] == NAME
                        and context.get("output_contract", {}).get("status") != "VALID"
                    )
                ):
                    raise ValueError("context_binding_mismatch")
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
                    elapsed_seconds=round(clock() - before, 3),
                    score=score,
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
                    "har008_r1_attempt_completed attempt=%d arm=%s passed=%s contract_failed=%s",
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
                    (directory / (case["id"] + ".md")).read_bytes()
                ).hexdigest()
                != manifest["source_sha256"][case["id"]]
                for case in cases
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
        summary = aggregate(rows, cases)
        if not completed:
            summary["status"] = "INCOMPLETE"
        cleanup_failures = int(submission_uncertain)
        if active is not None:
            try:
                api.request("POST", f"/api/v1/harness/runs/{active}/cancel", {})
            except Exception:
                cleanup_failures += 1
                LOGGER.warning("har008_r1_active_cleanup_failed")
        for identifier in created:
            try:
                api.request(
                    "DELETE",
                    f"/api/v1/harness/skills/installations/{identifier}?workspace_id={workspace}",
                )
            except Exception:
                cleanup_failures += 1
                LOGGER.warning("har008_r1_grant_cleanup_failed")
        summary.update(
            cleanup_failures=cleanup_failures,
            unidentified_submission=submission_uncertain,
            elapsed_seconds=round(clock() - started, 3),
        )
        save_json(output / "summary.json", summary)
    return summary


def main():
    """Require explicit local workspace and private receipt paths for one finite four-arm campaign."""
    parser = argparse.ArgumentParser(
        description="Run one frozen HAR-008-R1 four-arm evaluation."
    )
    parser.add_argument("--workspace", type=UUID, required=True)
    parser.add_argument("--workspace-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--url", default="http://127.0.0.1:7092")
    parser.add_argument("--token-file", type=Path, default=DEFAULT_TOKEN)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    print(
        json.dumps(
            evaluate(
                ApiClient(args.url, read_token(args.token_file)),
                args.workspace,
                args.workspace_root,
                args.output,
            )
        )
    )


if __name__ == "__main__":
    main()
