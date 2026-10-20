"""Verify joined thread cancellation, nonqueued admission and source ownership across workspace response lifetimes."""

import asyncio
import threading

import pytest
from test_workspace_reader import source_workspace as source_workspace

from apps.api.services import workspaces as module
from apps.api.services.workspaces import WorkspaceService
from src.application.services.workspace_policy import WorkspaceAccessError


@pytest.mark.asyncio
async def test_busy_admission_and_snapshot_release(source_workspace):
    """Refuse overlapping work without queueing and retain source capabilities until the caller exits."""
    catalog, spec, _, _ = source_workspace
    service = WorkspaceService(catalog)
    async with service.operation(
        spec.owner_id, spec.workspace_id, "read", dict(path="src/main.py")
    ) as snapshot:
        assert not snapshot.closed and service.operations and service.admission.locked()
        with pytest.raises(WorkspaceAccessError) as caught:
            async with service.operation(
                spec.owner_id, spec.workspace_id, "inventory", {}
            ):
                pytest.fail("overlap admitted")
        assert caught.value.code == "workspace_busy"
        await service.validate(snapshot)
    assert snapshot.closed and not service.operations and not service.admission.locked()
    await service.shutdown()
    with pytest.raises(WorkspaceAccessError):
        async with service.operation(spec.owner_id, spec.workspace_id, "inventory", {}):
            pytest.fail("closed service admitted")


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["cancel", "shutdown", "repeated_cancel"])
async def test_owned_worker_stops_and_joins_before_request_exit(
    source_workspace, monkeypatch, action
):
    """Signal a real worker thread cooperatively and prove it exits before cancelled request resources release."""
    catalog, spec, _, _ = source_workspace
    service = WorkspaceService(catalog)
    entered, exited = threading.Event(), threading.Event()
    original = module.build_snapshot

    def delayed(*arguments):
        """Hold actual worker execution until cancellation then run the original source cleanup path."""
        entered.set()
        arguments[-1].wait(2)
        try:
            return original(*arguments)
        finally:
            exited.set()

    monkeypatch.setattr(module, "build_snapshot", delayed)

    async def run():
        """Keep one real request in its source-building phase until the controlled cancellation."""
        async with service.operation(spec.owner_id, spec.workspace_id, "inventory", {}):
            pytest.fail("cancelled builder delivered a payload")

    task = asyncio.create_task(run())
    assert await asyncio.to_thread(entered.wait, 2)
    if action == "shutdown":
        await service.shutdown()
    else:
        task.cancel()
        if action == "repeated_cancel":
            await asyncio.sleep(0)
            task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert exited.is_set() and not service.operations and not service.admission.locked()


@pytest.mark.asyncio
async def test_delivered_snapshot_closes_after_caller_cancellation(source_workspace):
    """Release the retained root after cancellation while the caller owns an already built source result."""
    catalog, spec, _, _ = source_workspace
    service = WorkspaceService(catalog)
    entered = asyncio.Event()
    retained = []

    async def run():
        """Hold an admitted snapshot through caller cancellation without creating any extra thread work."""
        async with service.operation(
            spec.owner_id, spec.workspace_id, "read", dict(path="src/main.py")
        ) as snapshot:
            retained.append(snapshot)
            entered.set()
            await asyncio.Event().wait()

    task = asyncio.create_task(run())
    await asyncio.wait_for(entered.wait(), 2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert (
        retained[0].closed and not service.admission.locked() and not service.operations
    )


@pytest.mark.asyncio
async def test_cleanup_failure_still_releases_service_admission(
    source_workspace, monkeypatch
):
    """Preserve nonqueued service recovery even if native descriptor close reports a controlled failure."""
    catalog, spec, _, _ = source_workspace
    service = WorkspaceService(catalog)
    with pytest.raises(OSError):
        async with service.operation(
            spec.owner_id, spec.workspace_id, "inventory", {}
        ) as snapshot:
            original = snapshot.close

            def failed_close():
                """Close the real source first then inject a sanitized native cleanup failure."""
                original()
                raise OSError("controlled close failure")

            monkeypatch.setattr(snapshot, "close", failed_close)
    assert not service.admission.locked() and not service.operations and snapshot.closed


@pytest.mark.asyncio
async def test_completed_builder_result_closes_when_outer_cancel_wins(monkeypatch):
    """Close a successful result when cancellation arrives after inner work completed but before outer ownership transfer."""
    stop = threading.Event()

    class Result:
        """Represent a descriptor-owning completed result for the exact cancellation ownership race."""

        closed = False

        def close(self):
            """Record result cleanup without requiring any host filesystem handle."""
            self.closed = True

    result = Result()
    original_shield = asyncio.shield

    async def controlled_io(function, *arguments, **options):
        """Complete the result normally before delivering a cancellation to the outer caller."""
        if function == result.close:
            result.close()
            return None
        return result

    async def cancelled_shield(task):
        """Wait for successful inner completion then inject the transfer-boundary cancellation."""
        await original_shield(task)
        raise asyncio.CancelledError()

    monkeypatch.setattr(module, "file_io", controlled_io)
    monkeypatch.setattr(module.asyncio, "shield", cancelled_shield)
    with pytest.raises(asyncio.CancelledError):
        await module.joined_work(stop, lambda: result, close_result=True)
    assert stop.is_set() and result.closed
