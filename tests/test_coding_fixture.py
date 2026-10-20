"""Verify fixed private Git checkpoints/diffs and refusal of source/root aliases without production repository changes."""

import pytest
from test_coding_baseline import SOURCE

from src.infrastructure.coding_fixture import CodingFixture


def test_actual_private_git_checkpoint_diff_and_cleared_hooks(tmp_path, monkeypatch):
    """Create an actual isolated Git fixture while ignoring a hostile global hook/config path."""
    marker = tmp_path / "never-hooked"
    hooks = tmp_path / "hooks"
    hooks.mkdir()
    hook = hooks / "pre-commit"
    hook.write_text('#!/bin/sh\ntouch "' + str(marker) + '"\nexit 1\n')
    hook.chmod(0o700)
    config = tmp_path / "global-config"
    config.write_text("[core]\n\thooksPath = " + str(hooks) + "\n")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(config))
    fixture = CodingFixture(tmp_path / "repo", SOURCE)
    fixture.verify_source()
    changed = SOURCE.replace("return value", "return value + 1")
    diff = fixture.replace(changed)
    assert "diff --git a/solve.py b/solve.py" in diff
    assert "+    return value + 1" in diff and fixture.source.read_text() == changed
    assert len(fixture.checkpoint) == 40 and not marker.exists()
    assert fixture.git("rev-parse", "HEAD").strip() == fixture.checkpoint


@pytest.mark.parametrize(
    "fault", ["existing", "changed", "symlink", "hardlink", "root"]
)
def test_invalid_fixture_targets_cannot_be_overwritten(tmp_path, fault):
    """Reject existing/root-replaced/source-mutated/link-alias targets while preserving unrelated file bytes."""
    root = tmp_path / "repo"
    if fault == "existing":
        root.mkdir()
        with pytest.raises(FileExistsError):
            CodingFixture(root, SOURCE)
        return
    fixture = CodingFixture(root, SOURCE)
    outside = tmp_path / "outside"
    outside.write_text("UNRELATED-CANARY")
    if fault == "root":
        root.rename(tmp_path / "old-root")
        root.mkdir(mode=0o700)
    elif fault == "changed":
        fixture.source.write_text("changed")
    else:
        fixture.source.unlink()
        if fault == "symlink":
            fixture.source.symlink_to(outside)
        else:
            fixture.source.hardlink_to(outside)
    with pytest.raises((OSError, RuntimeError)):
        fixture.replace(SOURCE)
    assert outside.read_text() == "UNRELATED-CANARY"
