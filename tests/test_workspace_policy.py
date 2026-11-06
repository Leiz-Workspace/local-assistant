"""Verify explicit workspace identities and fail-closed bounded POSIX paths before filesystem access."""

import logging
from dataclasses import FrozenInstanceError
from uuid import uuid4

import pytest

from src.application.services.workspace_policy import (
    WorkspaceAccessError,
    WorkspaceSpec,
    clean_parts,
)

logger = logging.getLogger(__name__)


@pytest.mark.parametrize(
    "path", ["src/main.py", "README.md", "tài liệu/đọc.txt", "a" * 255]
)
def test_clean_relative_paths_preserve_exact_components(path):
    """Keep explicitly authorized Unicode and case without normalization or environment expansion."""
    assert "/".join(clean_parts(path)) == path
    logger.info("workspace_clean_relative_verified")


@pytest.mark.parametrize(
    "path",
    [
        None,
        42,
        b"a",
        "",
        "/etc/passwd",
        "../secret",
        "src/../secret",
        "./a",
        "a/./b",
        "a//b",
        "a/",
        "\\etc\\passwd",
        "a\x00b",
        "a\nb",
        "a\x7fb",
        ".env",
        "src/.env.local",
        ".git/config",
        "a/" * 64 + "b",
        "x" * 4097,
        "\ud800",
    ],
)
def test_ambiguous_hidden_and_unbounded_paths_fail_closed(path):
    """Reject traversal, hidden secrets, malformed Unicode and unsupported path syntax with stable errors."""
    with pytest.raises(WorkspaceAccessError) as caught:
        clean_parts(path)
    assert (
        caught.value.code == "workspace_path_invalid"
        and caught.value.status_code == 422
    )


@pytest.mark.parametrize(
    "root",
    ["/", "relative", "~/repo", "$HOME/repo", "/a/../b", "/a//b", "/a/", "/a/./b"],
)
def test_roots_require_explicit_clean_absolute_paths(root):
    """Reject inferred or canonicalization-dependent roots before an adapter can touch the filesystem."""
    with pytest.raises(WorkspaceAccessError):
        WorkspaceSpec(uuid4(), uuid4(), root, "demo")


@pytest.mark.parametrize("name", [None, "", " ", "x" * 81, "path\nsecret", "\ud800"])
def test_display_names_are_bounded_safe_metadata(name):
    """Refuse blank or control-bearing display metadata without leaking it into logs."""
    with pytest.raises(WorkspaceAccessError) as caught:
        WorkspaceSpec(uuid4(), uuid4(), "/explicit/repository", name)
    assert caught.value.code == "workspace_name_invalid"


def test_specifications_are_immutable_and_uuid_bound(caplog):
    """Keep root/identity immutable and avoid logging configured private absolute paths."""
    caplog.set_level(logging.INFO)
    spec = WorkspaceSpec(uuid4(), uuid4(), "/private/ROOT-CANARY/repository", "demo")
    with pytest.raises(FrozenInstanceError):
        spec.root = "/replacement"
    with pytest.raises(WorkspaceAccessError):
        WorkspaceSpec(str(spec.owner_id), spec.workspace_id, spec.root, spec.name)
    assert (
        "ROOT-CANARY" not in caplog.text and "workspace_spec_validated" in caplog.text
    )
