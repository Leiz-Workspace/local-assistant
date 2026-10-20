"""Measure every frozen D38 repair with actual unchanged CORE and native deterministic tools, retaining both successes and failures."""

import hashlib
import json
from pathlib import Path
from uuid import uuid4

import pytest

from scripts.coding_baseline_trial import run_trial


@pytest.mark.asyncio
async def test_actual_existing_core_coding_baseline():
    """Freeze case-wise oracles before inference and evaluate all six tasks without equating model failures with harness PASS."""
    case_path = Path("configs/coding-baseline-cases.json")
    value = json.loads(case_path.read_text())
    freeze = dict(
        description="D38 case/oracle freeze before actual original CORE inference; six authored synthetic repairs, no specialist adoption or production edit/command authority.",
        cases_sha256=hashlib.sha256(case_path.read_bytes()).hexdigest(),
        cases=value,
        harness_gate="All six frozen tasks actually attempted; all original oracle sets valid/failing, no unavailable sandbox, retained case-wise success/failure and joined cleanup. Model accuracy is measured, not assumed perfect.",
    )
    freeze_path = Path("docs/evidence/d38-coding-case-freeze.json")
    if freeze_path.exists():
        assert json.loads(freeze_path.read_text()) == freeze
    else:
        freeze_path.write_text(json.dumps(freeze, indent=2) + "\n")
    directory = Path.cwd() / "data/backups" / ("d38-live-coding-" + uuid4().hex)
    result = await run_trial(directory)
    assert result["attempted"] == result["total"] == 6
    assert result["cases_sha256"] == freeze["cases_sha256"]
    assert all(
        row["before"]["status"] == "completed" and not all(row["before_outcomes"])
        for row in result["tasks"]
    )
    assert all(
        row["status"] in {"measured", "model_or_proposal_failed"}
        for row in result["tasks"]
    )
    assert all(
        row["after"]["status"] != "unavailable"
        for row in result["tasks"]
        if row["status"] == "measured"
    )
    assert (
        not result["specialist_model_adopted"]
        and not result["production_edit_command_authority"]
    )
    summary = dict(
        description="Observed actual D38 native/Git/D35/original CORE case-wise coding baseline; authored synthetic task accuracy and resource policy are limited evidence, not a model replacement decision.",
        artifact=str(directory.relative_to(Path.cwd())),
        freeze_sha256=hashlib.sha256(freeze_path.read_bytes()).hexdigest(),
        report=result,
    )
    Path("docs/evidence/d38-core-observations.json").write_text(
        json.dumps(summary, indent=2) + "\n"
    )
