"""Protect original and previous live benchmark observations from mutable latest-report overwrite during future regressions."""

import hashlib
import json
import stat

import pytest
from test_coding_baseline_live import save_trial_summary


def test_new_measurements_preserve_first_report_and_legacy_private_reference(
    tmp_path, monkeypatch
):
    """Publish two private summaries/pointers and prove neither an earlier summary nor the committed D40 legacy target changes."""
    monkeypatch.chdir(tmp_path)
    backups = tmp_path / "data/backups"
    backups.mkdir(parents=True, mode=0o700)
    legacy = backups / "d38-latest-core-observations.json"
    legacy.write_bytes(b"IMMUTABLE-D40-TRIAL")
    first = backups / "trial-one"
    second = backups / "trial-two"
    first.mkdir(mode=0o700)
    second.mkdir(mode=0o700)
    summary = dict(
        description="Synthetic artifact-only test, no model quality measurement.",
        cases=6,
    )
    original = save_trial_summary(first, summary)
    raw = original.read_bytes()
    latest = save_trial_summary(second, dict(summary, cases=7))
    pointer = json.loads((backups / "d38-most-recent-trial.json").read_text())
    assert (
        original.read_bytes() == raw and legacy.read_bytes() == b"IMMUTABLE-D40-TRIAL"
    )
    assert pointer["path"] == str(latest.relative_to(tmp_path))
    assert pointer["sha256"] == hashlib.sha256(latest.read_bytes()).hexdigest()
    assert stat.S_IMODE(latest.stat().st_mode) == 0o600
    assert (
        stat.S_IMODE((backups / "d38-most-recent-trial.json").stat().st_mode) == 0o600
    )


def test_repeated_summary_publication_cannot_overwrite_prior_observation(
    tmp_path, monkeypatch
):
    """Reject an already published target before pointer changes instead of silently replacing an earlier measured result."""
    monkeypatch.chdir(tmp_path)
    directory = tmp_path / "data/backups/owned-trial"
    directory.mkdir(parents=True, mode=0o700)
    target = save_trial_summary(
        directory, dict(description="Initial synthetic artifact.")
    )
    before = target.read_bytes()
    pointer = (tmp_path / "data/backups/d38-most-recent-trial.json").read_bytes()
    with pytest.raises(FileExistsError):
        save_trial_summary(directory, dict(description="Different synthetic artifact."))
    assert (
        target.read_bytes() == before
        and (tmp_path / "data/backups/d38-most-recent-trial.json").read_bytes()
        == pointer
    )
