"""Validate every frozen D46 buggy/reference functional oracle through actual separately approved native check capsules before model inference."""

import hashlib
import json
import logging
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from coding_mvp_cases import (
    candidate_review,
    case_digest,
    corpus,
    fixture_files,
    save_artifact,
)
from test_check_jobs import job_store as job_store
from test_check_service import approve
from test_coding_workflow_service import workflow_service as workflow_service
from test_controlled_coding_workflow_service import (
    controlled_workflow as controlled_workflow,
)

logger = logging.getLogger(__name__)
CASES = corpus()["cases"]


@pytest.mark.asyncio
@pytest.mark.parametrize("case", CASES, ids=[row["id"] for row in CASES])
async def test_actual_buggy_rejected_and_reference_passes_both_frozen_suites(
    controlled_workflow, case
):
    """Run both complete trusted suites against wrong and reference source with explicit fixture grants, preserving actual exits and immutable independent goldens."""
    service, source, root, core = controlled_workflow
    directory = (
        Path.cwd() / "data/backups" / ("d46-oracle-" + case["id"] + "-" + uuid4().hex)
    )
    directory.mkdir(mode=0o700)
    stages = []
    for variant in ["buggy_source", "reference_source"]:
        candidate_review(case, case[variant])
        files = fixture_files(case, variant)
        for name, raw in files.items():
            path = root / name
            path.write_bytes(raw)
            path.chmod(0o644)
        selections = [
            dict(path=name, expected_sha256=hashlib.sha256(raw).hexdigest())
            for name, raw in files.items()
        ]
        value = await service.checks.propose(
            source.owner, source.workspace, "python_unittest", selections
        )
        request = UUID(value["approval_id"])
        approve(service, source.owner, request)
        result = await service.checks.run(
            source.owner, source.workspace, UUID(value["job_id"]), request
        )
        observed = result["observation"]
        stages.append(save_artifact(directory, variant + ".json", result))
        assert (
            observed["started_acknowledged"]
            and observed["outcome"] == "exited"
            and not observed["cleanup_uncertain"]
        )
        assert (
            observed["exit_code"] == 0
            if variant == "reference_source"
            else observed["exit_code"] != 0
        )
        assert all((root / name).read_bytes() == raw for name, raw in files.items())
    assert not core.calls and not service.records and not service.patches.records
    report = dict(
        description="Actual pre-inference buggy/reference oracle validation with complete visible and held-out suites; no model measurement or production action.",
        status="PASS_FROZEN_ORACLES",
        case_id=case["id"],
        case_sha256=case_digest(case),
        buggy_exit_nonzero=True,
        reference_exit_zero=True,
        fixture_approvals=2,
        native_runs=2,
        model_attempts=0,
        stages=stages,
    )
    summary = save_artifact(directory, "summary.json", report)
    pointers = Path("data/backups/d46-oracle-latest")
    pointers.mkdir(mode=0o700, exist_ok=True)
    pointer = pointers / (case["id"] + ".json")
    pointer.touch(mode=0o600, exist_ok=True)
    pointer.chmod(0o600)
    pointer.write_text(json.dumps(summary, indent=2) + "\n")
    logger.info(
        "d46_actual_oracle_pair_verified case_id=%s models0 native2", case["id"]
    )
