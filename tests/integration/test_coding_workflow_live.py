"""Measure one frozen visible sample through actual original CORE, two typed fixture approvals and native checks while retaining every observed stage."""

import ast
import base64
import hashlib
import json
import logging
import os
from pathlib import Path
from uuid import UUID, uuid4

import httpx
from test_check_http import approve_cli
from test_coding_workflow_http import base, proposal_body
from test_coding_workflow_http import check_client as check_client
from test_coding_workflow_http import checkpoint_client as checkpoint_client
from test_coding_workflow_http import patch_client as patch_client
from test_coding_workflow_http import workflow_client as workflow_client
from test_coding_workflow_http import workspace_client as workspace_client
from test_coding_workflow_service import sample_case
from test_reranker_tcp_trial import localhost_server

from apps.api.core.model_config import get_model_profile
from src.infrastructure.inference.llama_adapter import LlamaInferenceAdapter

logger = logging.getLogger(__name__)


def save_evidence(directory, name, value):
    """Write one bounded complete private JSON artifact exclusively and fsync bytes without logging model/source contents."""
    raw = (
        json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + "\n"
    ).encode()
    assert len(raw) <= 1048576
    path = directory / name
    descriptor = os.open(
        path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW, 0o600
    )
    with os.fdopen(descriptor, "wb") as output:
        output.write(raw)
        output.flush()
        os.fsync(output.fileno())
    logger.info("coding_workflow_trial_artifact_saved bytes=%d", len(raw))
    return dict(
        path=str(path.relative_to(Path.cwd())), sha256=hashlib.sha256(raw).hexdigest()
    )


class ObservedOriginalCore:
    """Delegate unchanged inference to the original configured CORE while counting only actual application-port attempts."""

    def __init__(self):
        """Prepare the existing adapter without loading or reconfiguring any model."""
        self.adapter = LlamaInferenceAdapter()
        self.calls = []

    async def complete(self, **options):
        """Record finite call configuration and prompt hash before delegating the real model request without a retry wrapper."""
        self.calls.append(
            dict(
                profile=options["profile"],
                preset=options["preset"],
                temperature=options["temperature"],
                max_tokens=options["max_tokens"],
                prompt_sha256=hashlib.sha256(
                    json.dumps(
                        options["messages"], ensure_ascii=False, sort_keys=True
                    ).encode()
                ).hexdigest(),
            )
        )
        logger.info("coding_workflow_original_core_attempt count=%d", len(self.calls))
        return await self.adapter.complete(**options)


def test_actual_original_core_visible_sample_two_reviews_and_native_oracles(
    workflow_client,
):
    """Measure one pre-frozen visible sample end to end, requiring the independent structural oracle before either fixture action is approved."""
    client, auth, specs, roots, _, _, _ = workflow_client
    case = sample_case()
    body = proposal_body(roots[0])
    original = (roots[0] / "sample.py").read_bytes()
    test_original = (roots[0] / "test_sample.py").read_bytes()
    core = ObservedOriginalCore()
    client.app.state.coding_workflow_service.inference = core
    directory = Path.cwd() / "data/backups" / ("d43-live-workflow-" + uuid4().hex)
    directory.mkdir(mode=0o700)
    sources = [
        "src/application/services/coding_workflow.py",
        "apps/api/services/coding_workflows.py",
        "apps/api/routes/coding_workflows.py",
        "apps/api/storage/coding_workflows.py",
        "apps/api/main.py",
        "apps/api/storage/lifecycle.py",
        "tests/integration/test_coding_workflow_live.py",
    ]
    freeze = dict(
        description="D43 source/visible-case/model configuration freeze before original CORE inference; no unseen benchmark or replacement for immutable D38 first4/6.",
        case_sha256=hashlib.sha256(
            Path("docs/evidence/d43-visible-sample-case.pending.json").read_bytes()
        ).hexdigest(),
        source_sha256={
            name: hashlib.sha256(Path(name).read_bytes()).hexdigest()
            for name in sources
        },
        model_configuration_sha256=hashlib.sha256(
            Path("configs/models.yaml").read_bytes()
        ).hexdigest(),
        original_D38_sha256=hashlib.sha256(
            Path("docs/evidence/d38-core-observations.json").read_bytes()
        ).hexdigest(),
        core_profile="core",
        preset="fast",
        max_tokens=2048,
        structural_oracle=case["host_structural_oracle"],
        native_oracles=case["native_oracles"],
    )
    report = dict(
        description="Actual single original CORE visible sample workflow; authored synthetic structural/native oracles, explicit disposable approvals only, no general quality/adoption claim.",
        status="STARTED",
        freeze=save_evidence(directory, "freeze.json", freeze),
        stages=[],
        model_port_attempts=0,
        model_calls=[],
        fixture_approvals=0,
        structural_oracle_passed=False,
        fixed_test_source_unchanged=False,
        production_action_approved=False,
        model_replaced=False,
        original_D38_replaced=False,
    )
    shown = []
    headers = auth["headers"][0]

    def observed(name, response):
        """Retain each actual HTTP observation before checking status so failed model/component outcomes remain available."""
        value = response.json()
        report["stages"].append(
            save_evidence(
                directory,
                name + ".json",
                dict(
                    description="Actual private D43 workflow HTTP observation.",
                    stage=name,
                    http_status=response.status_code,
                    body=value,
                ),
            )
        )
        assert response.status_code == 200
        return value

    try:
        with (
            localhost_server(client) as origin,
            httpx.Client(
                base_url=origin, trust_env=False, follow_redirects=False, timeout=90
            ) as http,
        ):
            value = observed(
                "proposal", http.post(base(specs[0]), headers=headers, json=body)
            )
            assert value["state"] == "awaiting_patch_review", value["error_code"]
            assert len(core.calls) == 1
            assert (
                value["model_observation"]["model_id"]
                == get_model_profile("core")["model_id"]
            )
            assert (roots[0] / "sample.py").read_bytes() == original
            expected = ast.parse(
                case["target"]["source"].replace(
                    "return left - right", "return left + right"
                )
            )
            candidate = value["patch"]["replacement"]
            assert ast.dump(ast.parse(candidate), include_attributes=False) == ast.dump(
                expected, include_attributes=False
            ), "Original CORE changed statements outside the frozen structural repair"
            report["structural_oracle_passed"] = True
            report["candidate_sha256"] = hashlib.sha256(candidate.encode()).hexdigest()
            report["candidate_bytes_match_reference"] = (
                report["candidate_sha256"] == case["expected_fixed_source_sha256"]
            )
            target = base(specs[0]) + "/" + value["workflow_id"]
            patch_request = UUID(value["patch"]["approval_id"])
            approve_cli(origin, patch_request, headers, shown)
            report["fixture_approvals"] += 1
            applied = observed(
                "applied",
                http.post(
                    target + "/apply",
                    headers=headers,
                    json=dict(approval_id=str(patch_request)),
                ),
            )
            assert (
                applied["summary"]["edit_applied"] is True and applied["check"] is None
            )
            assert (roots[0] / "sample.py").read_bytes() == candidate.encode()
            value = observed(
                "check_proposal",
                http.post(target + "/checks", headers=headers, json={}),
            )
            check_request = UUID(value["check"]["approval_id"])
            assert (
                check_request != patch_request and value["check"]["observation"] is None
            )
            approve_cli(origin, check_request, headers, shown)
            report["fixture_approvals"] += 1
            value = observed(
                "checked",
                http.post(
                    target + "/run-checks",
                    headers=headers,
                    json=dict(approval_id=str(check_request)),
                ),
            )
            assert value["state"] == "completed" and value["summary"]["native_started"]
            assert value["summary"]["native_exit_code"] == 0
            assert (
                not value["summary"]["quality_evaluated"]
                and not value["summary"]["current_source_observed"]
            )
            stderr = base64.b64decode(
                value["check"]["observation"]["stderr_base64"], validate=True
            )
            assert b"Ran 1 test" in stderr and b"OK" in stderr
            assert (roots[0] / "sample.py").read_bytes() == candidate.encode()
            assert (roots[0] / "test_sample.py").read_bytes() == test_original
            report["fixed_test_source_unchanged"] = True
            report["native_fixture_assertions"] = len(
                case["native_oracles"]["expected"]
            )
            assert (
                http.post(
                    target + "/run-checks",
                    headers=headers,
                    json=dict(approval_id=str(check_request)),
                ).status_code
                == 409
            )
            assert (
                http.get(target, headers=headers).json()["summary"] == value["summary"]
            )
            report["summary"] = value["summary"]
            report["status"] = "PASS_VISIBLE_SAMPLE_WORKFLOW"
    finally:
        report["model_port_attempts"] = len(core.calls)
        report["model_calls"] = core.calls
        if report["status"] != "PASS_VISIBLE_SAMPLE_WORKFLOW":
            report["status"] = "FAILED_VISIBLE_SAMPLE_WORKFLOW"
        report["cli_display"] = save_evidence(
            directory,
            "cli-display.json",
            dict(
                description="Actual concrete fixture CLI review displays without bearer or nonce.",
                displayed=shown,
            ),
        )
        assert (
            hashlib.sha256(
                Path("docs/evidence/d38-core-observations.json").read_bytes()
            ).hexdigest()
            == freeze["original_D38_sha256"]
        )
        summary = save_evidence(directory, "summary.json", report)
        pointer = Path("data/backups/d43-most-recent-trial.json")
        temporary = Path("data/backups") / (".d43-pointer-" + uuid4().hex + ".tmp")
        save_evidence(
            Path.cwd() / "data/backups",
            temporary.name,
            dict(
                description="Pointer only; every D43 trial summary remains exclusive and immutable.",
                **summary,
            ),
        )
        os.replace(temporary, pointer)
        logger.info(
            "coding_workflow_live_trial_retained status=%s attempts=%d",
            report["status"],
            len(core.calls),
        )
