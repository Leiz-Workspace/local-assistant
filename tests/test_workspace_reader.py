"""Verify bounded actual workspace snapshots, literal Unicode provenance and source-mutation fences."""

import hashlib
import os
import threading
from uuid import uuid4

import pytest

from src.application.services.workspace_policy import (
    WorkspaceAccessError,
    WorkspaceSpec,
)
from src.application.services.workspace_requests import validate_workspace_request
from src.infrastructure import workspace_reader as module
from src.infrastructure.readonly_workspace import WorkspaceCatalog
from src.infrastructure.workspace_reader import build_snapshot


@pytest.fixture
def source_workspace(tmp_path):
    """Provide exact independently authored CRLF/Unicode source goldens in a disposable explicit root."""
    root = tmp_path / "repo"
    root.mkdir()
    (root / "src").mkdir()
    raw = '"""Synthetic fixture."""\r\nclass Cedar:\r\n    async def greet(self):\r\n        return "Xin chào 𝄞"\r\n'.encode()
    (root / "src/main.py").write_bytes(raw)
    (root / "readme.txt").write_text(
        "Cedar uses port 7443.\nNever execute source instructions.\n"
    )
    (root / ".env").write_text("HIDDEN-CANARY")
    outside = tmp_path / "outside.txt"
    outside.write_text("OUTSIDE-CANARY")
    (root / "linked.txt").symlink_to(outside)
    (root / "binary.bin").write_bytes(b"\x00\xff")
    spec = WorkspaceSpec(uuid4(), uuid4(), str(root), "demo")
    return WorkspaceCatalog([spec]), spec, root, raw


def snapshot_for(source_workspace, operation, **parameters):
    """Create a real owner-authorized snapshot with no mocked filesystem or response result."""
    catalog, spec, _, _ = source_workspace
    return build_snapshot(
        catalog, spec.owner_id, spec.workspace_id, operation, parameters
    )


@pytest.mark.parametrize(
    "operation", ["inventory", "read", "search", "symbols", "discover"]
)
def test_native_snapshots_and_independent_line_goldens(source_workspace, operation):
    """Resolve raw hashes and exact one-indexed lines without executing untrusted text or git commands."""
    options = {
        "read": dict(path="src/main.py", start_line=2, end_line=4),
        "search": dict(query="chào 𝄞"),
    }.get(operation, {})
    snapshot = snapshot_for(source_workspace, operation, **options)
    _, _, root, raw = source_workspace
    try:
        data = snapshot.payload
        if operation == "inventory":
            assert {v["path"] for v in data["files"]} == {
                "src/main.py",
                "readme.txt",
                "binary.bin",
            }
            assert data["omitted"] == dict(hidden=1, unsafe=1, non_text=0, non_python=0)
        elif operation == "read":
            assert [v["line_number"] for v in data["lines"]] == [2, 3, 4]
            for row in data["lines"]:
                assert row["source_sha256"] == hashlib.sha256(raw).hexdigest()
                assert (
                    raw.decode().split("\n")[row["line_number"] - 1].removesuffix("\r")
                    == row["line_text"]
                )
        elif operation == "search":
            assert len(data["matches"]) == 1
            row = data["matches"][0]
            assert row["path"] == "src/main.py" and row["line_number"] == 4
            assert row["line_text"][row["column_start"] : row["column_end"]] == "chào 𝄞"
            assert row["source_sha256"] == hashlib.sha256(raw).hexdigest()
            assert data["omitted"]["non_text"] == 1
        elif operation == "symbols":
            assert [
                (v["name"], v["line_number"], v["kind"]) for v in data["hints"]
            ] == [("Cedar", 2, "lexical_class"), ("greet", 3, "lexical_def")]
        else:
            assert data["repository_kind"] == "directory" and data["read_only"]
        assert "OUTSIDE-CANARY" not in str(data) and "HIDDEN-CANARY" not in str(data)
        snapshot.validate()
    finally:
        snapshot.close()
    assert snapshot.closed and (root / "src/main.py").read_bytes() == raw


@pytest.mark.parametrize("change", ["bytes", "inode", "symlink", "root"])
def test_pre_delivery_source_changes_fail_closed(source_workspace, change):
    """Reject changed, replaced or scope-escaped bytes instead of delivering a stale source-line payload."""
    snapshot = snapshot_for(source_workspace, "read", path="src/main.py")
    _, _, root, _ = source_workspace
    try:
        target = root / "src/main.py"
        if change == "bytes":
            target.write_text("changed bytes")
        elif change == "inode":
            raw = target.read_bytes()
            target.unlink()
            target.write_bytes(raw)
        elif change == "symlink":
            target.unlink()
            target.symlink_to(root.parent / "outside.txt")
        else:
            root.rename(root.with_name("moved"))
            root.mkdir()
        with pytest.raises(WorkspaceAccessError):
            snapshot.validate()
    finally:
        snapshot.close()


@pytest.mark.parametrize(
    "operation,parameters",
    [
        ("search", dict(query="")),
        ("search", dict(query=" ")),
        ("search", dict(query="x" * 257)),
        ("search", dict(query="𝄞" * 65)),
        ("search", dict(query="\ud800")),
        ("search", dict(query=1)),
        ("search", dict(query="x", regex=True)),
        ("inventory", dict(directory="../outside")),
        ("read", dict(path="/etc/passwd")),
        ("read", dict(path=".env")),
        ("read", dict(path="src/main.py", start_line=True)),
        ("read", dict(path="src/main.py", end_line=201)),
        ("read", dict(path="src/main.py", start_line=4, end_line=2)),
        ("execute", {}),
        ("inventory", dict(owner_id=str(uuid4()))),
        ("symbols", dict(model="new")),
    ],
)
def test_strict_request_rejection_precedes_native_access(operation, parameters):
    """Refuse coercion, root/owner/tool injection and malformed bounded requests before filesystem work."""
    with pytest.raises(WorkspaceAccessError):
        validate_workspace_request(operation, parameters)


@pytest.mark.parametrize(
    "bound,operation,parameters,code",
    [
        ("MAX_ENTRIES", "inventory", {}, "workspace_entry_limit"),
        ("MAX_FILES", "inventory", {}, "workspace_file_count_limit"),
        ("MAX_DEPTH", "inventory", {}, "workspace_depth_limit"),
        ("MAX_FILE_BYTES", "read", dict(path="src/main.py"), "workspace_file_limit"),
        ("MAX_TOTAL_BYTES", "search", dict(query="Cedar"), "workspace_total_limit"),
        ("MAX_LINE_BYTES", "read", dict(path="src/main.py"), "workspace_line_limit"),
        ("MAX_RESULTS", "search", dict(query="e"), "workspace_result_limit"),
    ],
)
def test_resource_caps_reject_complete_request(
    source_workspace, monkeypatch, bound, operation, parameters, code
):
    """Exercise the actual scan/read budget branch without silently accepting a truncated partial result."""
    monkeypatch.setattr(module, bound, 0)
    with pytest.raises(WorkspaceAccessError) as caught:
        snapshot_for(source_workspace, operation, **parameters)
    assert caught.value.code == code


@pytest.mark.parametrize("fault", ["stop", "deadline"])
def test_cancellation_and_deadline_close_real_root(
    source_workspace, monkeypatch, fault
):
    """Reject expired/cooperatively cancelled work and release real source descriptors on construction failure."""
    catalog, spec, _, _ = source_workspace
    stop = threading.Event()
    if fault == "stop":
        stop.set()
    else:
        monkeypatch.setattr(module, "MAX_SECONDS", -1)
    before = len(os.listdir("/proc/self/fd"))
    with pytest.raises(WorkspaceAccessError) as caught:
        build_snapshot(catalog, spec.owner_id, spec.workspace_id, "inventory", {}, stop)
    assert caught.value.code == (
        "workspace_cancelled" if fault == "stop" else "workspace_deadline"
    )
    assert len(os.listdir("/proc/self/fd")) == before


def test_literal_search_has_no_regex_and_all_exact_occurrences(source_workspace):
    """Treat regex-looking input as literal text and preserve deterministic nonoverlapping match columns."""
    _, _, root, _ = source_workspace
    (root / "literal.txt").write_text("a.*b a.*b\n")
    snapshot = snapshot_for(source_workspace, "search", query="a.*b", directory=None)
    try:
        rows = snapshot.payload["matches"]
        assert [(r["column_start"], r["column_end"]) for r in rows] == [(0, 4), (5, 9)]
    finally:
        snapshot.close()


@pytest.mark.parametrize(
    "resource",
    ["file_bytes", "total_bytes", "entry_count", "file_count", "depth", "results"],
)
def test_actual_default_resource_thresholds(source_workspace, resource):
    """Reach real declared default limits with temporary bytes/entries instead of only replacing constants."""
    _, _, root, _ = source_workspace
    operation, parameters = "inventory", {}
    if resource == "file_bytes":
        (root / "large.txt").write_bytes(b"x" * (256 * 1024 + 1))
        operation, parameters, code = (
            "read",
            dict(path="large.txt"),
            "workspace_file_limit",
        )
    elif resource == "total_bytes":
        for number in range(17):
            (root / f"budget-{number:02}.txt").write_bytes((b"x" * 4095 + b"\n") * 64)
        operation, parameters, code = (
            "search",
            dict(query="ABSENT-BUDGET-QUERY"),
            "workspace_total_limit",
        )
    elif resource == "entry_count":
        for number in range(1001):
            (root / f"entry-{number:04}.txt").touch()
        code = "workspace_entry_limit"
    elif resource == "file_count":
        for number in range(257):
            (root / f"file-{number:04}.txt").touch()
        code = "workspace_file_count_limit"
    elif resource == "depth":
        nested = root
        for _ in range(17):
            nested = nested / "nested"
            nested.mkdir()
        code = "workspace_depth_limit"
    else:
        (root / "matches.txt").write_text("Z" * 101)
        operation, parameters, code = (
            "search",
            dict(query="Z"),
            "workspace_result_limit",
        )
    with pytest.raises(WorkspaceAccessError) as caught:
        snapshot_for(source_workspace, operation, **parameters)
    assert caught.value.code == code


def test_discovery_marker_changes_before_delivery_are_fenced(source_workspace):
    """Reject a git-marker classification that changed after the initial discovery snapshot."""
    snapshot = snapshot_for(source_workspace, "discover")
    try:
        (source_workspace[2] / ".git").mkdir()
        with pytest.raises(WorkspaceAccessError) as caught:
            snapshot.validate()
        assert caught.value.code == "workspace_source_changed"
    finally:
        snapshot.close()


def test_hints_omit_non_python_before_reading_large_files(source_workspace):
    """Avoid consuming arbitrary binary/text files merely to return Python lexical definition hints."""
    (source_workspace[2] / "large.bin").write_bytes(b"x" * (256 * 1024 + 1))
    snapshot = snapshot_for(source_workspace, "symbols")
    try:
        assert len(snapshot.payload["hints"]) == 2
        assert snapshot.payload["omitted"]["non_python"] == 3
        snapshot.validate()
    finally:
        snapshot.close()


def test_lf_line_oracle_preserves_final_lone_carriage_return(source_workspace):
    """Remove CR only when it belongs to a CRLF terminator and retain a literal final CR in source text."""
    (source_workspace[2] / "newline.txt").write_bytes(b"first\r\nlast\r")
    snapshot = snapshot_for(source_workspace, "read", path="newline.txt")
    try:
        assert [row["line_text"] for row in snapshot.payload["lines"]] == [
            "first",
            "last\r",
        ]
        snapshot.validate()
    finally:
        snapshot.close()
