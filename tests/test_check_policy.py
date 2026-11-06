"""Reject command/selection/resource authority widening and preserve exact immutable test/lint policy inputs."""

import pytest

from src.application.services.check_policy import (
    PROFILES,
    execution_policy,
    selection_input,
    source_bytes,
)
from src.application.services.workspace_policy import WorkspaceAccessError


def test_exact_selection_and_profile_cannot_be_widened_after_validation():
    """Copy only complete source hashes and keep server profiles immune to mutable client input or output policy edits."""
    values = [{"path": "tests/test_value.py", "expected_sha256": "a" * 64}]
    profile, selected = selection_input("python_unittest", values)
    values[0]["path"] = "/etc/passwd"
    assert selected == (("tests/test_value.py", "a" * 64),)
    assert profile.argv[:4] == ("/runtime/bin/python3.12", "-I", "-S", "-B")
    with pytest.raises(TypeError):
        PROFILES["shell"] = profile
    policy = execution_policy(0)
    policy["cpu_affinity"].append(1)
    policy["network"] = True
    assert execution_policy(0)["cpu_affinity"] == [0]
    assert not execution_policy(0)["network"]
    assert "--ignore-noqa" in PROFILES["ruff_check"].argv
    assert "--fix" not in PROFILES["ruff_check"].argv


@pytest.mark.parametrize(
    "profile", ["shell", "pytest", "ruff_check --fix", "", None, True]
)
def test_untrusted_profile_names_cannot_select_executables_or_arguments(profile):
    """Reject command injection and unsupported frameworks before any filesystem access."""
    with pytest.raises(WorkspaceAccessError) as caught:
        selection_input(profile, [{"path": "test_a.py", "expected_sha256": "a" * 64}])
    assert caught.value.code == "checks_profile_invalid"


@pytest.mark.parametrize(
    "path",
    [
        "/etc/secret.py",
        "../secret.py",
        ".hidden/test.py",
        "a//test.py",
        "a/./test.py",
        "a\\test.py",
        "a\x00.py",
        "a/b/c/d/test.py",
        "é" * 127 + ".py",
        "test.py;touch-canary",
        "README.md",
        "test.PY",
        "\ud800.py",
        None,
    ],
)
def test_unsafe_or_out_of_scope_source_paths_are_rejected(path):
    """Prevent traversal, hidden/config selection, overdeep or oversized UTF-8 paths and unsupported input types."""
    with pytest.raises(WorkspaceAccessError):
        selection_input("ruff_check", [{"path": path, "expected_sha256": "a" * 64}])


@pytest.mark.parametrize(
    "values",
    [
        [],
        (),
        None,
        [{"path": "test.py"}],
        [{"path": "test.py", "expected_sha256": "a" * 64, "argv": ["--fix"]}],
        [{"path": "test.py", "expected_sha256": True}],
        [{"path": "test.py", "expected_sha256": "A" * 64}],
        [{"path": "test.py", "expected_sha256": "a" * 63}],
        [{"path": "test.py", "expected_sha256": "a" * 64}] * 2,
        [{"path": "test.py", "expected_sha256": "a" * 64}] * 17,
    ],
)
def test_exact_bounded_selection_schema_and_unique_hashes_are_required(values):
    """Deny omitted hashes, body widening, ambiguous types, duplicate sources and count overflow."""
    with pytest.raises(WorkspaceAccessError):
        selection_input("python_unittest", values)


@pytest.mark.parametrize(
    "raw", [b"x" * 8193, b"\x00", b"\xff", "source", bytearray(b"x")]
)
def test_invalid_or_oversized_source_bytes_are_never_host_parsed(raw):
    """Reject binary/type/size violations before snapshot publication or child launch."""
    with pytest.raises(WorkspaceAccessError):
        source_bytes(raw)


def test_source_boundary_preserves_exact_raw_bytes_and_does_not_validate_syntax():
    """Keep CRLF and the admitted8192-byte boundary while leaving syntax/check outcomes to the isolated process."""
    raw = b'"""Controlled source."""\r\n' + b"#" * (8192 - 26)
    assert len(raw) == 8192
    assert source_bytes(raw) is raw
    assert (
        source_bytes(b"def deliberately_incomplete(") == b"def deliberately_incomplete("
    )
    assert source_bytes(b"") == b""


@pytest.mark.parametrize("cpu", [True, -1, "0", None])
def test_resource_policy_cannot_receive_ambiguous_cpu_values(cpu):
    """Reject untyped/negative affinity inputs rather than widening trusted resource policy."""
    with pytest.raises(WorkspaceAccessError):
        execution_policy(cpu)
