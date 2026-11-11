"""Verify private signed run metadata, restart isolation, process locking and fail-closed publication."""

import json
import logging
import os
import asyncio
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path
from uuid import UUID, uuid4

import pytest
import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from apps.harness.main import compose
from apps.harness.routes import RunInput
from apps.harness.service import HarnessError, ProductHarness
from src.infrastructure.harness_history import HarnessHistoryStore, HistoryError
from tests.test_product_harness import FixtureInference, bearer

LOGGER = logging.getLogger(__name__)


def create_history_fixture():
    """Create a model-free process-restart fixture, optionally blocking its first completion."""
    inference = FixtureInference()
    if os.environ.get("HARNESS_HISTORY_FIXTURE_BLOCK") == "1":
        inference.block = asyncio.Event()
    LOGGER.warning("harness_history_process_fixture_no_model")
    return compose(
        FastAPI(),
        inference=inference,
        history_dir=Path(os.environ["HARNESS_HISTORY_FIXTURE_DIR"]),
    )


def created_row(owner=None):
    """Build one synthetic host-owned metadata identity with a canary task that must never reach disk."""
    return dict(
        id=str(uuid4()),
        owner=owner or uuid4(),
        workspace_id=str(uuid4()),
        state="created",
        events=[dict(sequence=1, state="created")],
        request_sha256="a" * 64,
        task="PRIVATE_TASK_CANARY",
    )


def transition(row, state, **values):
    """Create an independent next-state fixture without mutating previously signed event arrays."""
    return {
        **row,
        **values,
        "state": state,
        "events": row["events"] + [dict(sequence=len(row["events"]) + 1, state=state)],
    }


def test_terminal_metadata_roundtrip_does_not_store_raw_text_or_grants(tmp_path):
    """Retain digests and identity while excluding prompt, answer, context and approval canaries."""
    store = HarnessHistoryStore(tmp_path / "history")
    row = created_row()
    store.save(row)
    row = transition(row, "running")
    store.save(row)
    row = transition(
        row,
        "succeeded",
        result={"text": "PRIVATE_ANSWER_CANARY"},
        context={"body": "PRIVATE_CONTEXT_CANARY"},
        approval="PRIVATE_APPROVAL_CANARY",
    )
    store.save(row)
    raw = (tmp_path / "history" / (row["id"] + ".json")).read_bytes()
    assert b"CANARY" not in raw
    recovered = store.load()[0]
    assert recovered["state"] == "succeeded" and recovered["result_sha256"]
    assert not {"task", "result", "context", "approval"}.intersection(recovered)
    store.close()
    reopened = HarnessHistoryStore(tmp_path / "history")
    assert reopened.load() == [recovered]
    reopened.close()
    LOGGER.info("test_harness_metadata_privacy_verified")


@pytest.mark.parametrize(
    "damage",
    ["mac", "truncate", "extra", "permission", "symlink", "hardlink", "unknown_file"],
)
def test_corrupt_or_unsafe_history_fails_closed(tmp_path, damage):
    """Reject altered bytes, schema drift and filesystem aliases without discarding earlier records."""
    root = tmp_path / "history"
    store = HarnessHistoryStore(root)
    row = created_row()
    store.save(row)
    store.close()
    path = root / (row["id"] + ".json")
    if damage == "mac":
        value = json.loads(path.read_text())
        value["record"]["request_sha256"] = "b" * 64
        path.write_text(json.dumps(value))
    elif damage == "truncate":
        path.write_bytes(path.read_bytes()[:20])
    elif damage == "extra":
        value = json.loads(path.read_text())
        value["record"]["approved"] = True
        path.write_text(json.dumps(value))
    elif damage == "permission":
        path.chmod(0o644)
    elif damage == "symlink":
        path.rename(tmp_path / "outside.json")
        path.symlink_to(tmp_path / "outside.json")
    elif damage == "hardlink":
        os.link(path, tmp_path / "linked.json")
    else:
        (root / "unexpected").write_text("keep this unknown file")
    opened = None
    try:
        with pytest.raises(HistoryError):
            opened = HarnessHistoryStore(root)
            opened.load()
    finally:
        if opened is not None:
            opened.close()
    assert path.exists()


def test_private_root_and_process_lock_are_required(tmp_path):
    """Reject shared directories and a second process until the first owner releases its lock."""
    root = tmp_path / "history"
    root.mkdir(mode=0o755)
    with pytest.raises(HistoryError):
        HarnessHistoryStore(root)
    root.chmod(0o700)
    store = HarnessHistoryStore(root)
    script = '''"""Attempt one competing metadata-store open without modifying records."""
import sys
from src.infrastructure.harness_history import HarnessHistoryStore, HistoryError
try:
    store = HarnessHistoryStore(sys.argv[1])
except HistoryError:
    raise SystemExit(7)
store.close()
'''
    result = subprocess.run(
        [sys.executable, "-c", script, str(root)], capture_output=True, timeout=5
    )
    assert result.returncode == 7
    store.close()
    result = subprocess.run(
        [sys.executable, "-c", script, str(root)], capture_output=True, timeout=5
    )
    assert result.returncode == 0


def test_unpublished_snapshot_is_not_a_result_and_cross_owner_delete_is_denied(
    tmp_path,
):
    """Preserve crash leftovers as nonauthoritative and require exact metadata ownership for removal."""
    root = tmp_path / "history"
    store = HarnessHistoryStore(root)
    pending = root / ("pending-" + "f" * 32)
    pending.write_bytes(b"partial")
    pending.chmod(0o600)
    assert store.load() == [] and pending.exists()
    row = created_row()
    store.save(row)
    row = transition(row, "cancelled")
    store.save(row)
    with pytest.raises(HistoryError):
        store.remove(uuid4(), UUID(row["id"]))
    store.remove(row["owner"], UUID(row["id"]))
    assert store.load() == [] and pending.exists()
    store.close()


def test_atomic_publication_failure_retains_last_signed_state(tmp_path, monkeypatch):
    """Keep the prior snapshot when atomic replacement fails instead of publishing partial success."""
    store = HarnessHistoryStore(tmp_path / "history")
    row = created_row()
    store.save(row)

    def fail_replace(*args, **kwargs):
        """Inject a publication fault before replacing any complete metadata file."""
        raise OSError("synthetic_disk_failure")

    monkeypatch.setattr(os, "replace", fail_replace)
    with pytest.raises(HistoryError):
        store.save(transition(row, "running"))
    assert store.load()[0]["state"] == "created"
    store.close()


@pytest.mark.asyncio
async def test_directory_sync_failure_after_rename_recovers_as_interrupted(
    tmp_path, monkeypatch
):
    """Treat an already-renamed snapshot with uncertain durability as metadata, never resumed execution."""
    root = tmp_path / "history"
    store = HarnessHistoryStore(root)
    row = created_row()
    store.save(row)
    original_sync = os.fsync

    def fail_directory_sync(descriptor):
        """Fail only the post-rename directory flush while allowing the temporary file flush."""
        if descriptor == store.fd:
            raise OSError("synthetic_directory_flush_failure")
        return original_sync(descriptor)

    monkeypatch.setattr(os, "fsync", fail_directory_sync)
    with pytest.raises(HistoryError):
        store.save(transition(row, "running"))
    assert store.load()[0]["state"] == "running"
    monkeypatch.setattr(os, "fsync", original_sync)
    store.close()
    reopened = HarnessHistoryStore(root)
    inference = FixtureInference()
    service = ProductHarness(inference, history=reopened)
    assert service.get(row["owner"], UUID(row["id"]))["state"] == "interrupted"
    assert not inference.calls and not service.tasks
    await service.close()
    reopened.close()


@pytest.mark.asyncio
async def test_restore_active_run_as_interrupted_without_inference_or_trust(tmp_path):
    """Recover metadata after process loss without restoring installs, requests, output bodies or task execution."""
    root = tmp_path / "history"
    first = HarnessHistoryStore(root)
    row = created_row()
    first.save(row)
    first.save(transition(row, "running"))
    first.close()
    store = HarnessHistoryStore(root)
    inference = FixtureInference()
    service = ProductHarness(inference, history=store)
    identifier = UUID(row["id"])
    result = service.get(row["owner"], identifier)
    assert (
        result["state"] == "interrupted"
        and result["archive_only"]
        and not result["result_available"]
    )
    assert (
        not service.tasks
        and not inference.calls
        and service.list_skills(row["owner"]) == []
    )
    with pytest.raises(HarnessError):
        service.get(uuid4(), identifier)
    assert (await service.cancel(row["owner"], identifier))["state"] == "interrupted"
    assert service.remove(row["owner"], identifier)["removed"]
    await service.close()
    store.close()


@pytest.mark.parametrize("fail_at", [1, 2, 3])
@pytest.mark.asyncio
async def test_history_failure_never_falls_back_or_retries_a_snapshot(
    tmp_path, fail_at
):
    """Stop before inference or hide its result when the required metadata transition cannot be persisted."""
    underlying = HarnessHistoryStore(tmp_path / "history")

    class FailingHistory:
        """Wrap a real store with one deterministic publication failure."""

        def __init__(self):
            """Count publication attempts without changing prior signed records."""
            self.calls = 0

        def load(self):
            """Return the real initial metadata without fabricating recovery state."""
            return underlying.load()

        def save(self, row):
            """Fail exactly one selected transition without performing or retrying its write."""
            self.calls += 1
            if self.calls == fail_at:
                raise HistoryError("synthetic_failure")
            underlying.save(row)

    history, inference = FailingHistory(), FixtureInference()
    service = ProductHarness(inference, history=history)
    owner = uuid4()
    request = RunInput(workspace_id=uuid4(), task="PRIVATE_TASK_CANARY")
    if fail_at == 1:
        with pytest.raises(HarnessError):
            service.start(owner, request)
        assert not service.tasks and not service.runs
    else:
        identifier = UUID(service.start(owner, request)["id"])
        await service.tasks[identifier]
        result = service.get(owner, identifier)
        assert result["state"] == "failed" and not result["history_persisted"]
        assert not result["result_available"] and "result" not in result
    assert history.calls == fail_at and len(inference.calls) == (
        1 if fail_at == 3 else 0
    )
    with pytest.raises(HarnessError):
        service.start(owner, request)
    await service.close()
    underlying.close()


def test_opt_in_http_restart_keeps_only_metadata_and_auth_scope(
    tmp_path, auth_settings
):
    """Reopen the optional app with the same private history and inspect terminal metadata without model calls."""
    root = tmp_path / "history"
    owner = auth_settings["principals"][0]
    store = HarnessHistoryStore(root)
    row = created_row(owner)
    store.save(row)
    row = transition(row, "running")
    store.save(row)
    store.save(transition(row, "succeeded", result={"body": "PRIVATE_ANSWER_CANARY"}))
    store.close()
    inference = FixtureInference()
    app = compose(FastAPI(), inference=inference, history_dir=root)
    with TestClient(
        app, base_url="http://127.0.0.1:7090", client=("127.0.0.1", 49004)
    ) as client:
        status = client.get(
            "/api/v1/harness/status", headers=bearer(auth_settings)
        ).json()
        assert status["persistence"] == "metadata-only" and not status["durable_resume"]
        path = "/api/v1/harness/runs/" + row["id"]
        recovered = client.get(path, headers=bearer(auth_settings))
        assert recovered.status_code == 200 and recovered.json()["archive_only"]
        assert not recovered.json()["result_available"] and not inference.calls
        assert "PRIVATE_ANSWER_CANARY" not in recovered.text
        assert client.get(path, headers=bearer(auth_settings, 1)).status_code == 404


def test_actual_process_loss_recovery_never_replays_task(tmp_path, auth_settings):
    """Kill only an owned fixture process and reopen signed state without replaying its task."""
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    address = f"http://127.0.0.1:{port}"
    directory = tmp_path / "process-history"
    processes, logs = [], []

    def launch(block):
        """Start one disposable loopback process without base storage, model calls or proxy headers."""
        environment = dict(
            os.environ,
            ASSISTANT_AUTH_FILE=str(auth_settings["path"]),
            HARNESS_HISTORY_FIXTURE_DIR=str(directory),
            HARNESS_HISTORY_FIXTURE_BLOCK="1" if block else "0",
        )
        log = (tmp_path / f"process-{len(processes)}.log").open("wb")
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "tests.test_harness_history:create_history_fixture",
                "--factory",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
                "--no-proxy-headers",
                "--no-access-log",
            ],
            cwd=Path(__file__).resolve().parents[1],
            env=environment,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        processes.append(process)
        logs.append(log)
        deadline = time.monotonic() + 10
        with httpx.Client(
            base_url=address, headers=bearer(auth_settings), trust_env=False, timeout=1
        ) as client:
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise AssertionError("fixture_process_exited")
                try:
                    if client.get("/api/v1/harness/status").status_code == 200:
                        return process
                except httpx.HTTPError:
                    pass
                time.sleep(0.02)
        raise AssertionError("fixture_startup_timeout")

    try:
        first = launch(True)
        with httpx.Client(
            base_url=address, headers=bearer(auth_settings), trust_env=False, timeout=2
        ) as client:
            created = client.post(
                "/api/v1/harness/runs",
                json={
                    "workspace_id": str(uuid4()),
                    "task": "DO_NOT_PERSIST_OR_REPLAY_THIS_TASK",
                },
            ).json()
            path = "/api/v1/harness/runs/" + created["id"]
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                if client.get(path).json()["state"] == "running":
                    break
                time.sleep(0.02)
            else:
                raise AssertionError("fixture_task_did_not_start")
        first.send_signal(signal.SIGKILL)
        first.wait(timeout=5)
        second = launch(False)
        assert second.pid != first.pid
        with httpx.Client(
            base_url=address, headers=bearer(auth_settings), trust_env=False, timeout=2
        ) as client:
            result = client.get(path).json()
            assert result["state"] == "interrupted" and result["archive_only"]
            assert not result["result_available"] and "result" not in result
            assert client.get("/api/v1/harness/skills").json() == []
            assert not client.get("/api/v1/harness/status").json()["durable_resume"]
            assert client.get(path, headers=bearer(auth_settings, 1)).status_code == 404
        raw = (directory / (created["id"] + ".json")).read_bytes()
        assert b"DO_NOT_PERSIST" not in raw and b"fixture answer" not in raw
        LOGGER.info("test_actual_harness_process_loss_verified")
    finally:
        for process in processes:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
        for log in logs:
            log.close()
