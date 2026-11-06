"""Measure one frozen D46 coding case through actual TCP, trusted typed reviews and distinct visible/held-out native checks without retries or host candidate execution."""

import base64
import hashlib
import json
import logging
import time
from pathlib import Path
from uuid import UUID, uuid4

import httpx
from coding_mvp_cases import (
    FixtureReviewError,
    candidate_review,
    case_digest,
    fixture_files,
    save_artifact,
)
from test_check_http import approve_cli
from test_coding_workflow_live import ObservedOriginalCore
from test_reranker_tcp_trial import localhost_server

from src.application.services.coding_workflow import workflow_messages, workflow_options

logger = logging.getLogger(__name__)


class TimedOriginalCore(ObservedOriginalCore):
    """Measure only actual existing CORE application-port duration while preserving its fixed request and original adapter behavior."""

    def __init__(self):
        """Initialize the accepted adapter plus bounded per-case latency metadata without loading a new model."""
        super().__init__()
        self.durations = []

    async def complete(self, **options):
        """Retain the one actual call duration even when its bounded transport or completion fails."""
        started = time.monotonic()
        try:
            return await super().complete(**options)
        finally:
            self.durations.append(round(time.monotonic() - started, 6))


def require(value, code):
    """Fail protocol/evidence integrity with a stable safe code instead of converting an infrastructure fault into model quality."""
    if not value:
        logger.warning("d46_protocol_failed code=%s", code)
        raise ValueError(code)


def frozen_oracle(case):
    """Require the exact pre-inference manifest binding and successful native buggy/reference validation for an actual case."""
    path = Path("data/backups/d46-pre-inference-oracles.json")
    value = json.loads(path.read_text())
    row = value["cases"][case["id"]]
    require(row["case_sha256"] == case_digest(case), "oracle_case_changed")
    artifact = Path(row["summary"]["path"])
    require(
        hashlib.sha256(artifact.read_bytes()).hexdigest() == row["summary"]["sha256"],
        "oracle_summary_changed",
    )
    report = json.loads(artifact.read_text())
    require(
        report["status"] == "PASS_FROZEN_ORACLES"
        and report["model_attempts"] == 0
        and report["buggy_exit_nonzero"]
        and report["reference_exit_zero"],
        "oracle_not_validated",
    )
    return row


def observed_post(http, path, headers, body, directory, stages, name):
    """Record each actual response before checking its successful status so a later protocol failure retains known component evidence."""
    response = http.post(path, headers=headers, json=body)
    value = response.json()
    stages.append(
        save_artifact(
            directory,
            name + ".json",
            dict(http_status=response.status_code, body=value),
        )
    )
    require(response.status_code == 200, "http_stage_" + name)
    return value


def native_observation(value):
    """Require known joined native evidence and leave functional pass/fail separate from generic API quality flags."""
    observation = value["observation"]
    require(
        observation
        and observation["started_acknowledged"]
        and observation["exit_code"] is not None,
        "native_not_observed",
    )
    require(
        not observation["cleanup_uncertain"]
        and not value.get("terminal_persistence_uncertain"),
        "native_cleanup_uncertain",
    )
    require(
        observation["output_is_untrusted"] and not observation["quality_evaluated"],
        "native_quality_relabelled",
    )
    return observation


def run_case(client_info, case, inference, *, inference_type, oracle=None, run_id=None):
    """Execute one declared fixture proposal/review/edit/visible/held-out sequence and retain every complete result without retrying a failed repair."""
    client, auth, specs, roots, _, _, _ = client_info
    if run_id is not None:
        try:
            valid_run = str(UUID(run_id)) == run_id
        except (ValueError, TypeError, AttributeError):
            valid_run = False
        require(valid_run, "evaluation_run_id")
    root, headers = roots[0], auth["headers"][0]
    files = fixture_files(case)
    for name, raw in files.items():
        path = root / name
        path.write_bytes(raw)
        path.chmod(0o644)
    canary = root.parent / ("d46-host-canary-" + case["id"])
    canary.write_bytes(b"D46-UNCHANGED-HOST-CANARY")
    canary.chmod(0o600)
    service = client.app.state.coding_workflow_service
    service.inference = inference
    directory = (
        Path.cwd()
        / "data/backups"
        / ("d46-coding-case-" + case["id"] + "-" + uuid4().hex)
    )
    directory.mkdir(mode=0o700)
    body = dict(
        issue=case["issue"],
        target=dict(
            path=case["target_path"], expected_sha256=case["sha256"]["buggy_source"]
        ),
        tests=[
            dict(
                path=case["visible_test_path"],
                expected_sha256=case["sha256"]["visible_test_source"],
            )
        ],
        profile="python_unittest",
    )
    options = workflow_options(**body)
    selected = {
        name: files[name] for name in [case["target_path"], case["visible_test_path"]]
    }
    messages = workflow_messages(options, selected)
    payload = json.loads(messages[1]["content"])
    require(
        [row["path"] for row in payload["sources"]]
        == [case["target_path"], case["visible_test_path"]],
        "heldout_prompt_scope",
    )
    expected_prompt = hashlib.sha256(
        json.dumps(messages, ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()
    freeze = save_artifact(
        directory,
        "freeze.json",
        dict(
            description="Frozen case/visible-only prompt/held-out oracle/review contract and fixed one-attempt budget before inference.",
            case_id=case["id"],
            case_sha256=case_digest(case),
            source_sha256=case["sha256"],
            expected_prompt_sha256=expected_prompt,
            model_attempts_before=len(inference.calls),
            evaluation_run_id=run_id,
            oracle=oracle,
            inference_type=inference_type,
            heldout_source_supplied_to_model=False,
        ),
    )
    stages, shown = [], []
    result = dict(
        description="One complete authored D46 repair measurement; protocol execution and functional repair outcome remain separate.",
        case_id=case["id"],
        case_sha256=case_digest(case),
        inference_type=inference_type,
        freeze=freeze,
        stages=stages,
        model_attempts=0,
        fixture_approvals=0,
        native_runs=0,
        functional_pass=False,
        repair_outcome=None,
        review_rejection=None,
        visible_exit_code=None,
        heldout_exit_code=None,
        quality_evaluated_by_native_api=False,
        general_quality_evaluated=False,
    )
    started = time.monotonic()
    collection = "/api/v1/workspaces/" + specs[0]["workspace_id"] + "/coding-workflows"
    checks = "/api/v1/workspaces/" + specs[0]["workspace_id"] + "/checks"
    try:
        with (
            localhost_server(client) as origin,
            httpx.Client(base_url=origin, trust_env=False, timeout=90) as http,
        ):
            proposal = observed_post(
                http, collection, headers, body, directory, stages, "proposal"
            )
            result["workflow_id"] = proposal["workflow_id"]
            observation = proposal["model_observation"]
            require(
                len(inference.calls) == 1
                and observation
                and observation.get("completion_received"),
                "model_measurement_missing",
            )
            result.update(
                model_attempts=1,
                model_observation=observation,
                model_call_config=inference.calls[0],
                model_call_seconds=list(getattr(inference, "durations", [])),
            )
            if inference_type == "actual_existing_CORE":
                require(
                    inference.calls[0]["prompt_sha256"] == expected_prompt,
                    "actual_prompt_changed",
                )
            require(
                all((root / name).read_bytes() == raw for name, raw in files.items()),
                "source_changed_before_review",
            )
            require(
                canary.read_bytes() == b"D46-UNCHANGED-HOST-CANARY",
                "host_canary_changed",
            )
            if proposal["state"] == "proposal_failed":
                result.update(
                    repair_outcome="PROPOSAL_FAILED", error_code=proposal["error_code"]
                )
                require(
                    proposal["patch"] is None and proposal["check"] is None,
                    "failed_proposal_published_component",
                )
            else:
                require(
                    proposal["state"] == "awaiting_patch_review",
                    "unexpected_proposal_state",
                )
                require(
                    not observation["prefix_truncated"], "candidate_prefix_incomplete"
                )
                raw = base64.b64decode(observation["raw_prefix_base64"], validate=True)
                require(
                    hashlib.sha256(raw).hexdigest() == observation["raw_sha256"],
                    "candidate_bytes_changed",
                )
                candidate = json.loads(raw)["replacement"]
                try:
                    review = candidate_review(case, candidate)
                except FixtureReviewError as error:
                    result.update(
                        repair_outcome="REVIEW_REJECTED", review_rejection=error.code
                    )
                else:
                    require(
                        review["candidate_sha256"] == proposal["patch"]["new_sha256"],
                        "reviewed_candidate_changed",
                    )
                    result["fixture_review"] = review
                    target = collection + "/" + proposal["workflow_id"]
                    patch = proposal["patch"]["approval_id"]
                    approve_cli(origin, UUID(patch), headers, shown)
                    result["fixture_approvals"] += 1
                    applied = observed_post(
                        http,
                        target + "/apply",
                        headers,
                        dict(approval_id=patch),
                        directory,
                        stages,
                        "apply",
                    )
                    result["applied_receipt"] = applied["patch"]["receipt"]
                    require(
                        applied["summary"]["edit_applied"] is True
                        and applied["patch"]["state"] == "applied",
                        "edit_not_known_applied",
                    )
                    require(
                        hashlib.sha256(
                            (root / case["target_path"]).read_bytes()
                        ).hexdigest()
                        == review["candidate_sha256"],
                        "applied_bytes_changed",
                    )
                    check = observed_post(
                        http,
                        target + "/checks",
                        headers,
                        {},
                        directory,
                        stages,
                        "visible_review",
                    )
                    request = check["check"]["approval_id"]
                    require(request != patch, "check_reused_patch_grant")
                    approve_cli(origin, UUID(request), headers, shown)
                    result["fixture_approvals"] += 1
                    visible = observed_post(
                        http,
                        target + "/run-checks",
                        headers,
                        dict(approval_id=request),
                        directory,
                        stages,
                        "visible_run",
                    )
                    visible_observation = native_observation(visible["check"])
                    result.update(
                        native_runs=1,
                        visible_exit_code=visible_observation["exit_code"],
                        visible_outcome=visible_observation["outcome"],
                        workflow_summary=visible["summary"],
                    )
                    heldout_body = dict(
                        profile="python_unittest",
                        files=[
                            dict(
                                path=case["target_path"],
                                expected_sha256=review["candidate_sha256"],
                            ),
                            dict(
                                path=case["heldout_test_path"],
                                expected_sha256=case["sha256"]["heldout_test_source"],
                            ),
                        ],
                    )
                    hidden = observed_post(
                        http,
                        checks,
                        headers,
                        heldout_body,
                        directory,
                        stages,
                        "heldout_review",
                    )
                    last = hidden["approval_id"]
                    require(last not in {patch, request}, "heldout_reused_grant")
                    approve_cli(origin, UUID(last), headers, shown)
                    result["fixture_approvals"] += 1
                    hidden = observed_post(
                        http,
                        checks + "/" + hidden["job_id"] + "/run",
                        headers,
                        dict(approval_id=last),
                        directory,
                        stages,
                        "heldout_run",
                    )
                    hidden_observation = native_observation(hidden)
                    passed = (
                        visible_observation["outcome"]
                        == hidden_observation["outcome"]
                        == "exited"
                        and visible_observation["exit_code"]
                        == hidden_observation["exit_code"]
                        == 0
                    )
                    result.update(
                        native_runs=2,
                        heldout_exit_code=hidden_observation["exit_code"],
                        heldout_outcome=hidden_observation["outcome"],
                        functional_pass=passed,
                        repair_outcome="FUNCTIONAL_PASS"
                        if passed
                        else "FUNCTIONAL_FAIL",
                    )
                    require(
                        hashlib.sha256(
                            (root / case["target_path"]).read_bytes()
                        ).hexdigest()
                        == review["candidate_sha256"],
                        "target_changed_after_oracles",
                    )
            require(
                (root / case["visible_test_path"]).read_bytes()
                == files[case["visible_test_path"]]
                and (root / case["heldout_test_path"]).read_bytes()
                == files[case["heldout_test_path"]],
                "trusted_test_changed",
            )
            require(
                canary.read_bytes() == b"D46-UNCHANGED-HOST-CANARY",
                "host_canary_changed",
            )
            require(
                len(inference.calls) == 1 and len(service.records) == 1,
                "implicit_retry_or_record",
            )
            require(
                not service.operations and not service.active_tasks,
                "workflow_not_joined",
            )
            if result["fixture_approvals"] == 0:
                require(
                    (root / case["target_path"]).read_bytes()
                    == files[case["target_path"]],
                    "unapproved_edit",
                )
                require(not service.checks.records, "unapproved_native_run")
            result.update(
                status="COMPLETE_MEASUREMENT",
                elapsed_seconds=round(time.monotonic() - started, 6),
                selected_tests_unchanged=True,
                host_canary_unchanged=True,
                automatic_retries=0,
                heldout_source_supplied_to_model=False,
            )
            result["cli_display"] = save_artifact(
                directory,
                "cli-display.json",
                dict(
                    description="Complete trusted fixture CLI review display; decision UUIDs supplied only by the test harness.",
                    display=shown,
                ),
            )
            summary = save_artifact(directory, "summary.json", result)
    except BaseException as error:
        save_artifact(
            directory,
            "failed.json",
            dict(
                description="Protocol failure retains actual known stages and outcomes; never relabel it as a model repair score or retry it.",
                status="PROTOCOL_FAILED_OR_INTERRUPTED",
                failure_type=type(error).__name__,
                known_result=result,
                stages=stages,
                model_attempts=len(inference.calls),
            ),
        )
        raise
    pointers = (
        Path("data/backups") / ("d46-evaluation-" + run_id) / "case-index"
        if run_id is not None
        else Path("data/backups/d46-case-latest")
    )
    if run_id is not None:
        pointers.parent.mkdir(mode=0o700, exist_ok=True)
    pointers.mkdir(mode=0o700, exist_ok=True, parents=True)
    pointer = pointers / (case["id"] + ".json")
    pointer.touch(mode=0o600, exist_ok=True)
    pointer.chmod(0o600)
    pointer.write_text(json.dumps(summary, indent=2) + "\n")
    logger.info(
        "d46_case_measurement_complete case_id=%s repair_outcome=%s attempts1",
        case["id"],
        result["repair_outcome"],
    )
    return result, summary
