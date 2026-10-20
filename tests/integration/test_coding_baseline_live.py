"""Measure every frozen D38 repair with actual unchanged CORE and native deterministic tools, retaining both successes and failures."""

import hashlib
import json
import logging
import os
from pathlib import Path
from uuid import uuid4

import pytest

from scripts.coding_baseline_trial import run_trial

logger = logging.getLogger(__name__)


def save_trial_summary(directory, summary):
    """Keep each observed live measurement immutable and publish only a separate private most-recent pointer."""
    raw = (json.dumps(summary, indent=2) + "\n").encode()
    target = directory / "summary.json"

    def create(path, payload):
        """Write/fsync one new private artifact without truncating existing observations or following a symbolic link."""
        descriptor = os.open(
            path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
            0o600,
        )
        try:
            offset = 0
            while offset < len(payload):
                count = os.write(descriptor, payload[offset:])
                if count <= 0:
                    raise OSError("trial_summary_write_failed")
                offset += count
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    create(target, raw)
    pointer = dict(
        description="Pointer to an immutable additional regression measurement; never replaces the original public D38 baseline.",
        path=str(target.relative_to(Path.cwd())),
        sha256=hashlib.sha256(raw).hexdigest(),
    )
    temporary = Path("data/backups") / (".d38-pointer-" + uuid4().hex + ".tmp")
    create(temporary, (json.dumps(pointer, indent=2) + "\n").encode())
    os.replace(temporary, Path("data/backups/d38-most-recent-trial.json"))
    for parent in (directory, Path("data/backups")):
        descriptor = os.open(parent, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    logger.info("coding_trial_summary_saved bytes=%d", len(raw))
    return target


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
    save_trial_summary(directory, summary)
