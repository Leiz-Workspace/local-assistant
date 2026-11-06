"""Test real private session inode guards, durable state transitions, retained archives and corruption/capacity refusal."""

import hashlib
import json
import logging
import os
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from src.application.services.research_session_policy import (
    ResearchSessionError,
    check_journal,
    decode,
    pack_archive,
)
from src.infrastructure.readonly_workspace import WorkspaceCatalog
from src.infrastructure.research_sessions import PrivateResearchSessions

logger = logging.getLogger(__name__)
CLAIMS = ("Atlas restore needs G-17.",)


def opened(path):
    """Open an explicit existing private fixture with an empty trusted workspace catalog."""
    return PrivateResearchSessions(path, WorkspaceCatalog())


@pytest.fixture
def storage(tmp_path):
    """Yield a real private0700 root and close its exclusive capabilities without deleting acknowledged outputs."""
    path = tmp_path / "sessions"
    path.mkdir(mode=0o700)
    store = opened(path)
    yield store, path
    store.close()


def initial(store, owner=None):
    """Create a normalized goal/claim session without executing any tool."""
    owner = owner or uuid4()
    value = store.create(owner, "Compare sources", CLAIMS)
    return owner, UUID(value["run_id"])


def blob(kind, owner, run_id):
    """Construct explicitly authored archive bytes without asserting real source/model/native results."""
    return pack_archive(
        kind,
        owner,
        run_id,
        dict(
            authored_fixture=True, original_text="Tiếng Việt <script>literal</script>"
        ),
    )


def paused(store, owner, run_id):
    """Commit the entire first-stage fixture and pause at a durable restart boundary."""
    store.begin(owner, run_id)
    store.append(owner, run_id, "discover", blob("discover", owner, run_id))
    return store.finish(owner, run_id)


def test_actual_restart_preserves_complete_bytes_attempts_and_two_stage_graph(
    storage, caplog
):
    """Reopen real storage across both explicit stages without recreating counters, receipts or automatic calls."""
    store, path = storage
    caplog.set_level(logging.INFO)
    owner, run_id = initial(store)
    assert paused(store, owner, run_id)["state"] == "paused"
    original = store.archive(owner, run_id, "discover")
    store.close()
    second = opened(path)
    try:
        assert second.recover() == 0
        assert second.load(owner, run_id)["attempts"] == ["discover"]
        assert second.archive(owner, run_id, "discover") == original
        second.begin(owner, run_id)
        for kind in ("report", "export"):
            second.append(owner, run_id, kind, blob(kind, owner, run_id))
        value = second.finish(owner, run_id)
        assert value["state"] == "complete" and len(value["attempts"]) == 2
        assert set(value["blobs"]) == {"discover", "report", "export"}
        with pytest.raises(ResearchSessionError, match="session_state_invalid"):
            second.begin(owner, run_id)
        for kind, info in value["blobs"].items():
            raw = second.archive(owner, run_id, kind)
            assert hashlib.sha256(raw).hexdigest() == info["sha256"]
            assert len(raw) == info["bytes"]
        assert str(owner) not in caplog.text and CLAIMS[0] not in caplog.text
        assert "Tiếng Việt" not in caplog.text
        assert all(
            p.stat().st_mode & 0o777 == 0o600 for p in (path / str(run_id)).iterdir()
        )
    finally:
        second.close()


@pytest.mark.parametrize("point", ["reservation", "draft", "candidate", "temporary"])
def test_recover_uncertain_stage_retains_acknowledged_and_candidate_bytes_without_adoption(
    storage, point
):
    """Terminate ambiguous progress without replay, deletion, counter reset or promoting uncommitted candidate output."""
    store, path = storage
    owner, run_id = initial(store)
    paused(store, owner, run_id)
    store.begin(owner, run_id)
    if point != "reservation":
        store.append(owner, run_id, "report", blob("report", owner, run_id))
    if point == "candidate":
        p = path / str(run_id) / "export.blob"
        p.write_bytes(b"partial unpublished bytes")
        p.chmod(0o600)
    if point == "temporary":
        p = path / str(run_id) / (".journal-" + uuid4().hex + ".tmp")
        p.write_bytes(b'{"partial":')
        p.chmod(0o600)
    before = {
        str(p): p.read_bytes()
        for p in (path / str(run_id)).iterdir()
        if p.name != "journal.json"
    }
    store.close()
    second = opened(path)
    try:
        assert second.recover() == 1 and second.recover() == 0
        value = second.load(owner, run_id)
        assert value["state"] == "interrupted" and value["attempts"] == [
            "discover",
            "publish",
        ]
        assert (
            value["error_code"] == "session_process_interrupted"
            and "export" not in value["blobs"]
        )
        assert all(Path(p).read_bytes() == raw for p, raw in before.items())
        with pytest.raises(ResearchSessionError, match="session_state_invalid"):
            second.begin(owner, run_id)
        with pytest.raises(ResearchSessionError, match="session_not_found"):
            second.archive(owner, run_id, "export")
    finally:
        second.close()


@pytest.mark.parametrize(
    "fault",
    [
        "byte",
        "hash",
        "duplicate",
        "nan",
        "permission",
        "symlink",
        "hardlink",
        "unknown",
        "root_replace",
        "lock_replace",
    ],
)
def test_actual_unsafe_or_tampered_store_fails_closed_and_preserves_evidence(
    storage, tmp_path, fault
):
    """Reject real byte/hash/JSON/inode/entry/root/lock corruption without repairing or deleting the forensic cohort."""
    store, path = storage
    owner, run_id = initial(store)
    paused(store, owner, run_id)
    journal = path / str(run_id) / "journal.json"
    output = path / str(run_id) / "discover.blob"
    if fault == "byte":
        output.write_bytes(output.read_bytes() + b" ")
    elif fault == "hash":
        v = json.loads(journal.read_text())
        v["blobs"]["discover"]["sha256"] = "0" * 64
        journal.write_text(json.dumps(v))
    elif fault in {"duplicate", "nan"}:
        journal.write_bytes(b'{"x":1,"x":2}' if fault == "duplicate" else b'{"x":NaN}')
    elif fault == "permission":
        output.chmod(0o640)
    elif fault in {"symlink", "hardlink"}:
        other = tmp_path / "unrelated"
        output.rename(other)
        output.symlink_to(other) if fault == "symlink" else output.hardlink_to(other)
    elif fault == "unknown":
        (path / str(run_id) / "unknown").write_bytes(b"KEEP")
    elif fault == "root_replace":
        path.rename(tmp_path / "retained")
        path.mkdir(mode=0o700)
    else:
        (path / ".store.lock").unlink()
        (path / ".store.lock").write_bytes(b"KEEP")
    with pytest.raises(ResearchSessionError, match="session_store_invalid"):
        store.load(owner, run_id)
    assert store.closing
    assert path.exists()


def test_owner_uuid_capacity_and_exclusive_store_lock(storage, monkeypatch):
    """Hide foreign/missing identities, reject string paths and retain all completed/ready sessions when capacity is exhausted."""
    store, path = storage
    owner, run_id = initial(store)
    with pytest.raises(ResearchSessionError, match="session_store_invalid"):
        opened(path)
    with pytest.raises(ResearchSessionError, match="session_not_found"):
        store.load(uuid4(), run_id)
    with pytest.raises(ResearchSessionError, match="session_invalid"):
        store.load(owner, "../../escape")
    for _ in range(3):
        initial(store, owner)
    with pytest.raises(ResearchSessionError, match="session_capacity"):
        initial(store, owner)
    for _ in range(12):
        initial(store)
    with pytest.raises(ResearchSessionError, match="session_capacity"):
        initial(store)
    assert len(os.listdir(path)) == 17 and not store.closing


@pytest.mark.parametrize(
    "mutation",
    [
        "reset",
        "loop",
        "complete_missing",
        "paused_no_output",
        "foreign_kind",
        "bad_input",
        "error_state",
    ],
)
def test_strict_journal_rejects_invented_progress_or_budget_reset(storage, mutation):
    """Require exact finite attempt prefixes and acknowledged outputs rather than trusting a caller-provided state label."""
    store, _ = storage
    owner, run_id = initial(store)
    v = paused(store, owner, run_id)
    if mutation == "reset":
        v["attempts"] = []
    elif mutation == "loop":
        v["attempts"] += ["discover"]
    elif mutation == "complete_missing":
        v["state"] = "complete"
    elif mutation == "paused_no_output":
        v["blobs"] = {}
    elif mutation == "foreign_kind":
        v["blobs"]["action"] = {}
    elif mutation == "bad_input":
        v["claims"] = [""]
    else:
        v["error_code"] = "session_cancelled"
    with pytest.raises(ResearchSessionError, match="session_store_invalid"):
        check_journal(v)


@pytest.mark.parametrize("raw", [b'{"x":1,"x":2}', b'{"x":NaN}', b"[]", b"{}" * 20000])
def test_ambiguous_or_oversized_json_rejected(raw):
    """Reject ambiguous/nonfinite/type/byte-limit JSON before treating it as recovery metadata."""
    with pytest.raises(ResearchSessionError, match="session_store_invalid"):
        decode(raw, 32768)
