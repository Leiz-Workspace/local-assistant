"""Run a frozen native-only semantic review prototype with one planned self-check and no production workflow changes."""

import argparse
import asyncio
import hashlib
import json
import logging
import time
from pathlib import Path
from uuid import UUID, uuid4

import httpx

from apps.api.runtime.presets import build_generation_params, calculate_budget
from apps.api.services.workspaces import WorkspaceService
from apps.api.services.workspace_tools import WorkspaceToolRun
from apps.harness.inference import ProductInference
from benchmarks.har008 import ROOT, SKILLS, save_json
from benchmarks.harness_resources import ResourceSampler, process_memory
from benchmarks.semantic_review import score, schema, task, verification_task
from benchmarks.semantic_review_cases import cases, outcomes
from src.application.services.skill_contract import parse_manifest
from src.application.services.source_output_contract import digest, quote_catalog
from src.application.services.workspace_policy import WorkspaceSpec
from src.infrastructure.readonly_workspace import WorkspaceCatalog

LOGGER = logging.getLogger(__name__)
ARMS = ("single_baseline", "checked_baseline", "single_skill", "checked_skill")


def verify_source(case, raw, path):
    """Match complete actual read bytes/provenance to the registered source before freezing trusted gold."""
    quote_catalog([raw], [dict(index=0, sha256=hashlib.sha256(raw).hexdigest())])
    lines = json.loads(raw)["data"]["lines"]
    expected = case["source"].splitlines()
    sha = hashlib.sha256(case["source"].encode()).hexdigest()
    if len(lines) != len(expected) or any(
        line["path"] != path
        or line["source_sha256"] != sha
        or line["line_number"] != index
        or line["line_text"] != text
        for index, (line, text) in enumerate(zip(lines, expected, strict=True), 1)
    ):
        raise ValueError("semantic_source_gold_mismatch")
    LOGGER.info("semantic_source_gold_binding_verified lines=%d", len(lines))


def summarize(rows):
    """Separate trusted finite correctness, classification errors and self-check regressions from broad qualification."""
    keys = [(row["case_id"], row["arm"]) for row in rows]
    if len(keys) != len(set(keys)) or any(arm not in ARMS for _, arm in keys):
        raise ValueError("duplicate_semantic_outcomes")
    arms = {}
    for arm in ARMS:
        selected = [row for row in rows if row["arm"] == arm]
        arms[arm] = dict(
            attempts=len(selected),
            passed=sum(row["score"]["passed"] for row in selected),
            format=sum(row["score"]["format"] for row in selected),
            false_positives=sum(
                row["gold_verdict"] == "no_defect" and row["verdict"] == "defect"
                for row in selected
            ),
            unsupported_claims=sum(
                row["gold_verdict"] == "uncertain" and row["verdict"] != "uncertain"
                for row in selected
            ),
            missed_defects=sum(
                row["gold_verdict"] == "defect" and row["verdict"] != "defect"
                for row in selected
            ),
        )
    pairs = {}
    for suffix in ("baseline", "skill"):
        values = []
        for identifier in sorted({row["case_id"] for row in rows}):
            group = {row["arm"]: row for row in rows if row["case_id"] == identifier}
            if "single_" + suffix in group and "checked_" + suffix in group:
                values.append(
                    (
                        group["single_" + suffix]["score"]["passed"],
                        group["checked_" + suffix]["score"]["passed"],
                    )
                )
        pairs[suffix] = dict(
            pairs=len(values),
            gains=sum(not a and b for a, b in values),
            regressions=sum(a and not b for a, b in values),
        )
    return dict(
        status="MEASUREMENT_COMPLETE" if len(rows) == 48 else "INCOMPLETE",
        expected_calls=48,
        completed_calls=len(rows),
        arms=arms,
        self_check_pairs=pairs,
        promotion="NOT_QUALIFIED",
        scope="Trusted finite registered-template probe semantics; title prose ungraded; same-model self-check is not independent proof or a deployed product workflow.",
    )


async def evaluate(
    inference,
    service,
    owner,
    workspace,
    workspace_root,
    output,
    *,
    pid,
    sampler_factory=ResourceSampler,
    preflight=process_memory,
    clock=time.monotonic,
):
    """Freeze exact sources/evidence/gold before 48 first native calls and retain all planned shared-candidate outcomes."""
    output = Path(output)
    output.mkdir(mode=0o700, parents=False, exist_ok=False)
    panel = cases()
    root = Path(workspace_root)
    if root.is_symlink() or not root.is_dir():
        raise ValueError("explicit_semantic_workspace_required")
    folder = "har008-q3-" + uuid4().hex
    directory = root / folder
    directory.mkdir(mode=0o700)
    evidence = {}
    for case in panel:
        source = directory / (case["id"] + ".py")
        source.write_text(case["source"])
        reader = WorkspaceToolRun(service, owner, workspace)
        try:
            evidence[case["id"]] = await reader.execute(
                json.dumps(
                    dict(
                        name="workspace.read",
                        arguments=dict(path=folder + "/" + source.name),
                    )
                ).encode()
            )
            verify_source(case, evidence[case["id"]], folder + "/" + source.name)
        finally:
            await reader.close()
    skill_raw = SKILLS["repo-review"].read_bytes()
    skill = parse_manifest(skill_raw)
    native = preflight(pid)
    files = [
        Path(__file__),
        ROOT / "benchmarks/semantic_review.py",
        ROOT / "benchmarks/semantic_review_cases.py",
        ROOT / "benchmarks/harness_resources.py",
        ROOT / "apps/harness/inference.py",
        ROOT / "src/application/services/context_composer.py",
        ROOT / "src/application/services/source_output_contract.py",
        ROOT / "src/application/services/review_output_contract.py",
        ROOT / "configs/models.yaml",
        ROOT / "configs/llama-cpp-commit.txt",
    ]
    frozen = dict(
        description="Q3 frozen finite semantic prototype; gold/outcome tables never enter model requests.",
        cases=panel,
        evidence={key: value.decode() for key, value in evidence.items()},
        trusted_probe_tables={
            case["id"]: {probe: outcomes(case, probe) for probe in case["probes"]}
            for case in panel
            if case["gold"]["verdict"] != "uncertain"
        },
        source_files_sha256={
            str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in files
        },
        skill_sha256=hashlib.sha256(skill_raw).hexdigest(),
        native_process=native,
        source_folder=folder,
        options=dict(
            preset="fast",
            max_tokens=512,
            per_call_seconds=120,
            campaign_seconds=1200,
            calls=48,
            retries=0,
            production_workflow_changed=False,
            order="Alternate skill group first by case; each self-check necessarily follows its shared single candidate.",
        ),
    )
    save_json(output / "frozen-inputs.json", frozen)
    rows = []
    completed = False
    try:
        async with asyncio.timeout(1200):
            for index, case in enumerate(panel):
                for use_skill in (False, True) if index % 2 == 0 else (True, False):
                    original = task(case)
                    candidate = None
                    first_seconds = 0
                    for checked in (False, True):
                        text = (
                            verification_task(original, candidate)
                            if checked
                            else original
                        )
                        arm = ("checked_" if checked else "single_") + (
                            "skill" if use_skill else "baseline"
                        )
                        attempt = len(rows) + 1
                        record = dict(
                            case_id=case["id"],
                            arm=arm,
                            status="INCOMPLETE",
                            shared_candidate_sha256=hashlib.sha256(
                                candidate.encode()
                            ).hexdigest()
                            if checked
                            else None,
                        )
                        telemetry = None
                        try:
                            with sampler_factory(
                                pid, expected_start=native["start_ticks"]
                            ) as telemetry:
                                before = clock()
                                async with asyncio.timeout(120):
                                    gateway, fitted, context = await inference.prepare(
                                        [dict(role="user", content=text)],
                                        preset="fast",
                                        max_tokens=512,
                                        evidence=[evidence[case["id"]]],
                                        skill=skill if use_skill else None,
                                        context_strategy="strict",
                                    )
                                    if len(context["included_evidence"]) != 1:
                                        raise ValueError("semantic_evidence_omitted")
                                    catalog = quote_catalog(
                                        [evidence[case["id"]]],
                                        context["included_evidence"],
                                    )
                                    contract = schema(catalog)
                                    plan = calculate_budget(
                                        preset="fast",
                                        input_tokens=context["input_tokens"],
                                        requested_max_tokens=512,
                                    )
                                    payload = build_generation_params(plan)
                                    payload.update(
                                        model=gateway.model_id,
                                        messages=fitted,
                                        temperature=0.7,
                                        stream=False,
                                        response_format={
                                            "type": "json_schema",
                                            "json_schema": {"schema": contract},
                                        },
                                    )
                                    save_json(
                                        output / f"{attempt:02d}-request.json", payload
                                    )
                                    async with httpx.AsyncClient(
                                        base_url=gateway.base_url,
                                        transport=inference.transport,
                                        timeout=gateway._timeout(),
                                        trust_env=False,
                                    ) as client:
                                        response = await client.post(
                                            "/v1/chat/completions", json=payload
                                        )
                                        record["http_status"] = response.status_code
                                        if len(response.content) > 262144:
                                            raise ValueError(
                                                "semantic_response_too_large"
                                            )
                                        try:
                                            result = response.json()
                                        except ValueError:
                                            record["raw_response_text"] = response.text
                                            raise ValueError(
                                                "semantic_nonjson_response"
                                            ) from None
                                        record["native"] = result
                                        response.raise_for_status()
                                    elapsed = clock() - before
                            record.update(
                                native=result,
                                context=context,
                                schema_sha256=digest(contract),
                                catalog_sha256=digest(catalog),
                                seconds=round(elapsed, 6),
                            )
                            choice = result["choices"][0]
                            content = choice["message"].get("content")
                            if (
                                type(content) is not str
                                or len(content.encode()) > 65536
                                or choice["message"].get("tool_calls")
                            ):
                                raise ValueError("semantic_native_response_invalid")
                            grade = score(content, case)
                            if choice.get("finish_reason") != "stop":
                                grade.update(format=False, passed=False)
                            try:
                                verdict = json.loads(content).get("verdict")
                            except (ValueError, AttributeError):
                                verdict = None
                            workflow = first_seconds + elapsed if checked else elapsed
                            record.update(
                                status="COMPLETE",
                                score=grade,
                                verdict=verdict,
                                gold_verdict=case["gold"]["verdict"],
                                workflow_seconds=round(workflow, 6),
                                raw_content_sha256=hashlib.sha256(
                                    content.encode()
                                ).hexdigest(),
                            )
                            if not checked:
                                candidate = content
                                first_seconds = elapsed
                        finally:
                            if telemetry is not None:
                                record["resources"] = telemetry.report()
                            save_json(output / f"{attempt:02d}-response.json", record)
                        rows.append(record)
                        LOGGER.info(
                            "semantic_native_attempt_retained attempt=%d arm=%s passed=%s",
                            attempt,
                            arm,
                            grade["passed"],
                        )
        if (
            any(
                hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != sha
                for name, sha in frozen["source_files_sha256"].items()
            )
            or hashlib.sha256(SKILLS["repo-review"].read_bytes()).hexdigest()
            != frozen["skill_sha256"]
            or any(
                (directory / (case["id"] + ".py")).read_text() != case["source"]
                for case in panel
            )
        ):
            raise ValueError("semantic_frozen_inputs_changed")
        completed = True
    finally:
        summary = summarize(rows)
        if not completed:
            summary["status"] = "INCOMPLETE"
        summary["resource_status"] = (
            "COMPLETE"
            if len(rows) == 48
            and all(row["resources"]["status"] == "COMPLETE" for row in rows)
            else "INCOMPLETE"
        )
        save_json(output / "summary.json", summary)
    return summary


async def run(args):
    """Bind only an explicitly configured fixture owner/workspace to the native research runner."""
    catalog = json.loads(args.workspace_config.read_text())["workspaces"]
    entries = [
        entry for entry in catalog if entry["workspace_id"] == str(args.workspace)
    ]
    if len(entries) != 1:
        raise ValueError("semantic_workspace_not_unique")
    entry = entries[0]
    spec = WorkspaceSpec(
        UUID(entry["owner_id"]),
        args.workspace,
        entry["root"],
        "semantic-research-fixture",
    )
    service = WorkspaceService(WorkspaceCatalog([spec]))
    try:
        return await evaluate(
            ProductInference(),
            service,
            spec.owner_id,
            spec.workspace_id,
            entry["root"],
            args.output,
            pid=args.pid,
        )
    finally:
        await service.shutdown()


def main():
    """Require explicit local fixture configuration, native PID and exclusive private output for one campaign."""
    parser = argparse.ArgumentParser(
        description="Run Q3 finite semantic review and a single planned self-check."
    )
    parser.add_argument("--workspace-config", type=Path, required=True)
    parser.add_argument("--workspace", type=UUID, required=True)
    parser.add_argument("--pid", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    print(json.dumps(asyncio.run(run(args))))


if __name__ == "__main__":
    main()
