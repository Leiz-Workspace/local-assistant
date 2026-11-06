"""Verify native namespace command isolation and async supervisor ownership under controlled faults without actual Office claims."""

import asyncio
import logging
import threading

import pytest
from test_report_export_policy import authored_payload

from src.application.services.report_export_policy import ReportExportError
from src.infrastructure import report_export as module
from src.infrastructure.file_verifier import sandbox_command
from src.infrastructure.report_export import (
    NativeReportExporter,
    export_command,
    supervise,
)

logger = logging.getLogger(__name__)


def test_new_export_command_keeps_accepted_sandbox_unchanged_and_only_adds_private_working_state():
    """Keep readonly accepted parser defaults intact while adding no network/secret/host writable mount or arbitrary command authority."""
    arguments = ["/venv/bin/python", "-m", "src.infrastructure.report_export_worker"]
    original = sandbox_command(arguments)
    command = export_command()
    assert sandbox_command(arguments) == original
    assert ["--remount-ro", "/tmp"] in [
        original[index : index + 2] for index in range(len(original))
    ]
    assert ["--remount-ro", "/tmp"] not in [
        command[index : index + 2] for index in range(len(command))
    ]
    assert (
        "--unshare-all" in command
        and "--share-net" not in command
        and "--clearenv" in command
        and "--die-with-parent" in command
        and "--cap-drop" in command
    )
    assert ["--uid", "65534"] in [
        command[index : index + 2] for index in range(len(command))
    ]
    assert command.index("/etc/fonts") < command.index("--remount-ro")
    assert (
        "HOME" not in command
        and "--bind" not in command
        and command.count("--tmpfs") == 1
        and str(64 * 1024**2) in command
    )


@pytest.mark.asyncio
async def test_native_process_launch_failure_is_finite_and_retains_no_owned_selector_or_process(
    monkeypatch,
):
    """Refuse a controlled native executable failure without leaking the private launch exception into an application error."""
    _, payload = await authored_payload()

    def fail(*args, **options):
        """Raise before process ownership exists without starting any native executable."""
        raise OSError("PRIVATE-NATIVE-LAUNCH")

    monkeypatch.setattr(module.subprocess, "Popen", fail)
    with pytest.raises(ReportExportError, match="export_unavailable"):
        await asyncio.to_thread(supervise, payload, threading.Event())


@pytest.mark.asyncio
async def test_repeated_async_cancel_waits_for_real_owned_supervisor_thread_acknowledgement(
    monkeypatch,
):
    """Set the stop signal without cancelling a thread future that could otherwise outlive native admission."""
    _, payload = await authored_payload()
    exporter = NativeReportExporter()
    entered, stopped, release = threading.Event(), threading.Event(), threading.Event()

    def held(raw, stop):
        """Retain a controlled native ownership obligation until cancellation and explicit cleanup release are observed."""
        entered.set()
        assert stop.wait(2)
        stopped.set()
        assert release.wait(2)
        raise ReportExportError("export_timeout")

    monkeypatch.setattr(module, "supervise", held)
    task = asyncio.create_task(exporter.render(payload))
    assert await asyncio.to_thread(entered.wait, 2)
    task.cancel()
    assert await asyncio.to_thread(stopped.wait, 2)
    task.cancel()
    with pytest.raises(ReportExportError, match="export_busy"):
        await exporter.render(payload)
    assert not task.done() and exporter.admission.locked()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert (
        not exporter.operations
        and not exporter.admission.locked()
        and not exporter.closing
    )


@pytest.mark.parametrize("trigger", ["completion", "cancellation"])
@pytest.mark.asyncio
async def test_unknown_thread_cleanup_poisons_native_admission(trigger, monkeypatch):
    """Keep unknown synchronous cleanup state fatal instead of treating a completed failed future as proof of native retirement."""
    _, payload = await authored_payload()
    exporter = NativeReportExporter()
    entered = threading.Event()

    def uncertain(raw, stop):
        """Model an unknown cleanup failure after normal execution or after the controlled stop acknowledgement."""
        entered.set()
        if trigger == "cancellation":
            assert stop.wait(2)
        raise RuntimeError("PRIVATE-CLEANUP")

    monkeypatch.setattr(module, "supervise", uncertain)
    task = asyncio.create_task(exporter.render(payload))
    assert await asyncio.to_thread(entered.wait, 2)
    if trigger == "cancellation":
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    else:
        with pytest.raises(ReportExportError, match="export_cleanup_uncertain"):
            await task
    assert (
        exporter.closing and not exporter.operations and not exporter.admission.locked()
    )


@pytest.mark.asyncio
async def test_explicit_thread_cleanup_uncertainty_also_closes_native_admission(
    monkeypatch,
):
    """Treat finite explicit uncertainty as fatal just like an unknown native supervisor cleanup exception."""
    _, payload = await authored_payload()
    exporter = NativeReportExporter()

    def uncertain(raw, stop):
        """Return one controlled finite uncertainty without setting the exporter's mutable state directly."""
        raise ReportExportError("export_cleanup_uncertain")

    monkeypatch.setattr(module, "supervise", uncertain)
    with pytest.raises(ReportExportError, match="export_cleanup_uncertain"):
        await exporter.render(payload)
    assert (
        exporter.closing and not exporter.operations and not exporter.admission.locked()
    )
