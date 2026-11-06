"""Exercise actual SIGKILL, exclusive-lock release and fsynced session publication windows using an owned subprocess and authored archive bytes."""

import logging
import os
import select
import signal
import subprocess
import sys
from pathlib import Path
from uuid import UUID, uuid4

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.application.services.research_session_policy import pack_archive
from src.infrastructure.readonly_workspace import WorkspaceCatalog
from src.infrastructure.research_sessions import PrivateResearchSessions

logger = logging.getLogger(__name__)


def retained_worker(path, owner, run_id, point):
    """Retain the actual exclusive store at one real journal/blob fsync boundary until the owning test kills this process."""
    store = PrivateResearchSessions(path, WorkspaceCatalog())
    original = store.root.replace_journal

    def held():
        """Signal a reached native publication boundary without disclosing identifiers or source data."""
        print("READY", flush=True)
        while True:
            signal.pause()

    def publish(directory, value):
        """Stop after real blob fsync and before its journal acknowledgement for the selected fault window."""
        target = (
            "discover"
            if point == "discover_candidate"
            else "export"
            if point == "export_candidate"
            else None
        )
        if target is not None and target in value["blobs"]:
            held()
        original(directory, value)

    def save(kind):
        """Write an explicitly authored archive through the actual immutable-file/fsync publication path."""
        raw = pack_archive(
            kind, owner, run_id, dict(authored_fixture=True, value="Giữ nguyên dữ liệu")
        )
        store.append(owner, run_id, kind, raw)

    store.root.replace_journal = publish
    store.begin(owner, run_id)
    if point == "reserved":
        held()
    save("discover")
    store.finish(owner, run_id)
    if point == "paused":
        held()
    store.begin(owner, run_id)
    save("report")
    if point == "draft":
        held()
    save("export")
    store.finish(owner, run_id)
    held()


@pytest.mark.parametrize(
    "point",
    [
        "reserved",
        "discover_candidate",
        "paused",
        "draft",
        "export_candidate",
        "complete",
    ],
)
def test_actual_sigkill_preserves_durable_prefix_and_never_replays_unknown_stage(
    tmp_path, point
):
    """Kill an actual store-owning process and prove exact retained bytes, exclusive failover and terminal unknown attempts."""
    path = tmp_path / "sessions"
    path.mkdir(mode=0o700)
    owner = uuid4()
    store = PrivateResearchSessions(path, WorkspaceCatalog())
    value = store.create(owner, "Compare sources", ("Atlas needs G-17.",))
    run_id = UUID(value["run_id"])
    store.close()
    log = tmp_path / "owned-worker.log"
    log.touch(mode=0o600)
    with log.open("wb") as errors:
        child = subprocess.Popen(
            [
                sys.executable,
                str(Path(__file__).resolve()),
                str(path),
                str(owner),
                str(run_id),
                point,
            ],
            stdout=subprocess.PIPE,
            stderr=errors,
            start_new_session=True,
        )
        try:
            ready, _, _ = select.select([child.stdout], [], [], 10)
            assert ready and child.stdout.readline() == b"READY\n", (
                "owned worker did not reach the frozen boundary"
            )
            before = {
                p.name: p.read_bytes()
                for p in (path / str(run_id)).iterdir()
                if p.name != "journal.json"
            }
            with pytest.raises(Exception):
                PrivateResearchSessions(path, WorkspaceCatalog())
            os.kill(child.pid, signal.SIGKILL)
            assert child.wait(timeout=5) == -signal.SIGKILL
        finally:
            if child.poll() is None:
                os.killpg(child.pid, signal.SIGKILL)
                child.wait(timeout=5)
            child.stdout.close()
    reopened = PrivateResearchSessions(path, WorkspaceCatalog())
    try:
        assert reopened.recover() == (0 if point in {"paused", "complete"} else 1)
        result = reopened.load(owner, run_id)
        expected = point if point in {"paused", "complete"} else "interrupted"
        assert result["state"] == expected
        assert len(result["attempts"]) == (
            1 if point in {"reserved", "discover_candidate", "paused"} else 2
        )
        assert all(
            (path / str(run_id) / name).read_bytes() == raw
            for name, raw in before.items()
        )
        if point == "discover_candidate":
            assert (path / str(run_id) / "discover.blob").exists() and not result[
                "blobs"
            ]
        if point == "export_candidate":
            assert (
                path / str(run_id) / "export.blob"
            ).exists() and "export" not in result["blobs"]
        assert child.poll() == -signal.SIGKILL
    finally:
        reopened.close()
    logger.info("research_session_native_kill_gate_passed point=%s", point)


if __name__ == "__main__":
    retained_worker(sys.argv[1], UUID(sys.argv[2]), UUID(sys.argv[3]), sys.argv[4])
