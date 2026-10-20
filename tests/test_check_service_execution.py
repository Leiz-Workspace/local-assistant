"""Exercise real native async cancellation, dependency drain and truthful uncertain check receipts without production authority."""

import asyncio
import hashlib
import threading
from uuid import UUID

import pytest
from test_check_jobs import job_store as job_store
from test_check_service import approve, proposal
from test_check_service import check_service as check_service

from src.application.services.workspace_policy import WorkspaceAccessError
from src.infrastructure import check_runner as runner_module


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["task_cancel", "owner_cancel", "shutdown"])
async def test_actual_native_work_joins_before_cancel_or_dependency_teardown(
    check_service, job_store, monkeypatch, mode
):
    """Cancel a real started sleeping namespace while preserving actual consumed-grant and joined native exit observations."""
    service, sources = check_service
    root = job_store[2][0]
    raw = b'"""Controlled cancellable unittest fixture."""\nimport time\nimport unittest\nclass Fixture(unittest.TestCase):\n    """Retain only a disposable sleeping check."""\n    def test_wait(self):\n        """Wait until the native parent cancels the owned namespace."""\n        time.sleep(10)\n'
    (root / "test_wait.py").write_bytes(raw)
    value = await service.propose(
        sources.owner,
        sources.workspace,
        "python_unittest",
        [dict(path="test_wait.py", expected_sha256=hashlib.sha256(raw).hexdigest())],
    )
    identifier, request = UUID(value["job_id"]), UUID(value["approval_id"])
    approve(service, sources.owner, request)
    started, loop, processes = asyncio.Event(), asyncio.get_running_loop(), []
    original = runner_module.subprocess.Popen

    def observed_start(*arguments, **options):
        """Notify the owning event loop only after an actual native process handle exists."""
        process = original(*arguments, **options)
        processes.append(process)
        loop.call_soon_threadsafe(started.set)
        return process

    monkeypatch.setattr(runner_module.subprocess, "Popen", observed_start)
    task = asyncio.create_task(
        service.run(sources.owner, sources.workspace, identifier, request)
    )
    await asyncio.wait_for(started.wait(), 5)
    if mode == "task_cancel":
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    elif mode == "owner_cancel":
        result = await service.cancel(sources.owner, sources.workspace, identifier)
        assert result["observation"]["exit_code"] is not None
        with pytest.raises(WorkspaceAccessError):
            await task
    else:
        await service.shutdown()
        with pytest.raises(asyncio.CancelledError):
            await task
    record = service.records[identifier]
    assert record.finished.is_set() and record.sources is None
    assert record.evidence["observation"]["started_acknowledged"]
    assert record.evidence["observation"]["exit_code"] is not None
    assert service.approvals.review(sources.owner, request)["state"] == "consumed"
    assert all(process.poll() is not None for process in processes)
    assert not any(
        thread.name.startswith("checks-native-") for thread in threading.enumerate()
    )


@pytest.mark.asyncio
async def test_known_native_result_survives_terminal_journal_failure(
    check_service, monkeypatch
):
    """Retain actual native exit/bytes when durable final publication cannot acknowledge the known observation."""
    service, sources = check_service
    value = await proposal(check_service)
    identifier, request = UUID(value["job_id"]), UUID(value["approval_id"])
    approve(service, sources.owner, request)
    original = service.store.storage.replace_journal

    def terminal_fault(directory, value):
        """Fail only terminal persistence after actual native execution completes."""
        if value["state"] == "observed":
            raise OSError("controlled terminal journal failure")
        return original(directory, value)

    monkeypatch.setattr(service.store.storage, "replace_journal", terminal_fault)
    result = await service.run(sources.owner, sources.workspace, identifier, request)
    assert result["state"] == "observed_persistence_uncertain"
    assert result["persisted_state"] == "starting"
    assert result["observation"]["exit_code"] == 0
    assert result["terminal_persistence_uncertain"] and not result["live_proposal"]


@pytest.mark.asyncio
async def test_history_never_reconstructs_live_source_capability_or_old_action_authority(
    check_service,
):
    """Treat a retained job as history after losing process-local capabilities instead of recovering an old approved request."""
    service, sources = check_service
    value = await proposal(check_service)
    identifier, request = UUID(value["job_id"]), UUID(value["approval_id"])
    record = service.records.pop(identifier)
    await service.close_sources(record)
    approve(service, sources.owner, request)
    with pytest.raises(WorkspaceAccessError) as caught:
        await service.run(sources.owner, sources.workspace, identifier, request)
    assert caught.value.code == "checks_job_not_live"
    assert service.approvals.review(sources.owner, request)["state"] == "approved"
