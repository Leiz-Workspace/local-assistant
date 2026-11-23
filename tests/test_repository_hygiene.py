"""Keep stale backup copies of entry points and Compose files out of the tracked tree."""

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def tracked(*patterns):
    """Return tracked paths matching git pathspecs, skipping outside a git checkout."""
    git = shutil.which("git")
    if git is None or not (ROOT / ".git").exists():
        pytest.skip("git_checkout_unavailable")
    result = subprocess.run(
        [git, "-C", str(ROOT), "ls-files", "-z", "--", *patterns],
        capture_output=True,
        check=True,
        timeout=30,
    )
    return sorted(name for name in result.stdout.decode().split("\0") if name)


def test_pathspec_reaches_nested_tracked_files():
    """Prove the wildcard crosses directories, so an empty result below is meaningful."""
    assert "apps/api/main.py" in tracked("*main.py")


def test_no_backup_copies_are_tracked():
    """Reject tracked *.bak files such as the removed apps/api/main.py.bak."""
    assert tracked("*.bak") == []
