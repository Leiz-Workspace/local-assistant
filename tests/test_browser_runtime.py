"""Verify fixed browser confinement, private snapshot/journal fences and truthful exact-container retirement without starting Docker."""

import json
import logging
import os
import subprocess

import pytest

from src.application.services.browser_policy import BrowserError
from src.infrastructure.browser_runtime import (
    IMAGE,
    ROOT,
    NativeBrowserWorker,
    runtime_config,
)

logger = logging.getLogger(__name__)


def test_pinned_runtime_config_and_described_worker_are_syntax_valid():
    """Require the immutable cached tool and explicit outer isolation, with a valid documented fixed CDP-only worker."""
    config = runtime_config()
    assert config["image"] == IMAGE and config["browser_native_sandbox"] is False
    assert config["memory_bytes"] == 1073741824 and config["resource_requests"] == 32
    worker = ROOT / "scripts/browser_readonly_worker.cjs"
    assert worker.read_text().startswith("/**")
    process = subprocess.run(["node", "--check", str(worker)], capture_output=True)
    assert process.returncode == 0


def test_handle_construction_does_not_create_jobs_or_launch_native_code(tmp_path):
    """Keep the optional browser default-inert until an explicit navigation operation starts acquisition."""
    path = tmp_path / "jobs"
    current = NativeBrowserWorker(root=path)
    assert (
        not path.exists() and current.process is None and current.container_id is None
    )


@pytest.mark.asyncio
async def test_private_snapshot_and_journal_retire_without_docker_when_never_created(
    tmp_path, monkeypatch
):
    """Close only the known prepared files without contacting Docker for an unattempted create."""
    current = NativeBrowserWorker(root=tmp_path / "jobs")
    current.prepare()
    worker = current.directory / "worker.cjs"
    assert (
        worker.read_bytes()
        == (ROOT / "scripts/browser_readonly_worker.cjs").read_bytes()
    )
    assert worker.stat().st_mode & 0o777 == 0o600
    record = json.loads((current.directory / "journal.json").read_text())
    assert (
        record["description"] and record["state"] == "prepared" and "url" not in record
    )

    async def forbidden(*args):
        """Fail if local-only preparation unexpectedly tries to contact or delete a Docker container."""
        raise AssertionError("docker_after_unattempted_create")

    monkeypatch.setattr(current, "command", forbidden)
    await current.close()
    assert (
        current.closed
        and current.retired
        and not current.directory.exists()
        and not list(current.root.iterdir())
    )
    await current.close()


@pytest.mark.asyncio
async def test_unknown_job_root_entries_are_preserved_without_adopting_authority(
    tmp_path,
):
    """Refuse an unknown leftover entry without deleting it or launching another container."""
    root = tmp_path / "jobs"
    root.mkdir(mode=0o700)
    unknown = root / "unknown"
    unknown.write_text("PRIVATE-UNKNOWN-FIXTURE")
    current = NativeBrowserWorker(root=root)
    with pytest.raises(BrowserError, match="browser_cleanup_uncertain"):
        current.prepare()
    await current.close()
    assert unknown.read_text() == "PRIVATE-UNKNOWN-FIXTURE"


@pytest.mark.asyncio
async def test_journal_hardlink_never_truncates_another_owned_file(tmp_path):
    """Check inode/link ownership before truncation so a replaced journal cannot destroy a private canary."""
    current = NativeBrowserWorker(root=tmp_path / "jobs")
    current.prepare()
    canary = tmp_path / "private-canary"
    canary.write_bytes(b"PRIVATE-CANARY-UNCHANGED")
    canary.chmod(0o600)
    journal = current.directory / "journal.json"
    journal.unlink()
    os.link(canary, journal)
    with pytest.raises(BrowserError, match="browser_cleanup_uncertain"):
        current.journal("invalid")
    assert canary.read_bytes() == b"PRIVATE-CANARY-UNCHANGED"
    with pytest.raises(BrowserError, match="browser_cleanup_uncertain"):
        await current.close()
    assert (
        canary.read_bytes() == b"PRIVATE-CANARY-UNCHANGED"
        and current.directory.exists()
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("mutation", ["unknown", "worker_bytes", "journal_bytes"])
async def test_changed_private_entries_are_retained_after_known_local_retirement(
    tmp_path, mutation
):
    """Retain unexpected private state without blind cleanup or pretending that unknown file bytes remain owned."""
    current = NativeBrowserWorker(root=tmp_path / "jobs")
    current.prepare()
    if mutation == "unknown":
        (current.directory / "unknown.txt").write_text("unknown")
    else:
        name = "worker.cjs" if mutation == "worker_bytes" else "journal.json"
        (current.directory / name).write_text("CHANGED-PRIVATE-FIXTURE")
    with pytest.raises(BrowserError, match="browser_cleanup_uncertain"):
        await current.close()
    assert current.directory.exists() and current.closed and current.retired
    assert current.fault.code == "browser_cleanup_uncertain"


def container_record(current):
    """Return a fixed labeled owned-container record for controlled retirement tests, without a real container."""
    return dict(
        Id="a" * 64,
        Name="/" + current.name,
        Config=dict(
            Image=IMAGE, Labels={"local.assistant.browser.owner": current.job_id}
        ),
    )


@pytest.mark.asyncio
async def test_known_container_is_retired_even_if_journal_became_unknown(
    tmp_path, monkeypatch
):
    """Remove the verified exact container while preserving unknown filesystem state and reporting cleanup uncertainty."""
    current = NativeBrowserWorker(root=tmp_path / "jobs")
    current.prepare()
    current.create_attempted = True
    current.container_id = "a" * 64
    (current.directory / "journal.json").write_text("CHANGED-JOURNAL-FIXTURE")
    calls = []

    async def command(*args):
        """Acknowledge only exact known inspect/remove operations and then explicit not-found."""
        calls.append(args)
        if len(calls) == 1:
            return 0, json.dumps([container_record(current)]).encode(), b""
        if args[0] == "rm":
            return 0, (current.container_id + "\n").encode(), b""
        return (
            1,
            b"[]\n",
            ("Error: No such container: " + current.container_id + "\n").encode(),
        )

    monkeypatch.setattr(current, "command", command)
    with pytest.raises(BrowserError, match="browser_cleanup_uncertain"):
        await current.close()
    assert (
        ("rm", "--force", "a" * 64) in calls
        and current.retired
        and current.directory.exists()
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure", ["daemon", "authorization", "foreign_owner", "post_remove_daemon"]
)
async def test_missing_or_foreign_docker_evidence_never_means_clean_retirement(
    tmp_path, monkeypatch, failure
):
    """Keep owned state when the daemon is unavailable, access is denied, ownership differs or absence is unconfirmed."""
    current = NativeBrowserWorker(root=tmp_path / "jobs")
    current.prepare()
    current.create_attempted = True
    current.container_id = "a" * 64
    calls = []

    async def command(*args):
        """Inject completed but nonauthoritative Docker responses without native processes or side effects."""
        calls.append(args)
        if failure in {"daemon", "authorization"}:
            return (
                1,
                b"",
                b"Cannot connect to daemon"
                if failure == "daemon"
                else b"permission denied",
            )
        if len(calls) == 1:
            row = container_record(current)
            if failure == "foreign_owner":
                row["Config"]["Labels"]["local.assistant.browser.owner"] = "foreign"
            return 0, json.dumps([row]).encode(), b""
        if args[0] == "rm":
            return 0, b"deleted", b""
        return 1, b"", b"Cannot connect to daemon"

    monkeypatch.setattr(current, "command", command)
    with pytest.raises(BrowserError, match="browser_cleanup_uncertain"):
        await current.close()
    assert current.directory.exists() and not current.retired
    if failure == "foreign_owner":
        assert all(call[0] != "rm" for call in calls)


@pytest.mark.asyncio
async def test_successful_exact_removal_and_acknowledged_absence_release_known_job(
    tmp_path, monkeypatch
):
    """Require remove acknowledgment and exact not-found before deleting the known worker/journal pair."""
    current = NativeBrowserWorker(root=tmp_path / "jobs")
    current.prepare()
    current.create_attempted = True
    current.container_id = "a" * 64
    calls = []

    async def command(*args):
        """Simulate the minimal completed native lifecycle using only the known immutable container identity."""
        calls.append(args)
        if len(calls) == 1:
            return 0, json.dumps([container_record(current)]).encode(), b""
        if args[0] == "rm":
            return 0, b"deleted", b""
        return 1, b"[]", ("Error: No such container: " + current.container_id).encode()

    monkeypatch.setattr(current, "command", command)
    await current.close()
    assert (
        current.retired
        and current.closed
        and current.fault is None
        and not current.directory.exists()
    )


@pytest.mark.asyncio
async def test_changed_root_is_not_followed_or_deleted_during_cleanup(tmp_path):
    """Retain the old inode and a replacement root's canary rather than cleaning a path after an identity change."""
    current = NativeBrowserWorker(root=tmp_path / "jobs")
    current.prepare()
    previous = tmp_path / "old-jobs"
    current.root.rename(previous)
    current.root.mkdir(mode=0o700)
    canary = current.root / "private.txt"
    canary.write_text("PRIVATE-ROOT-UNCHANGED")
    with pytest.raises(BrowserError, match="browser_cleanup_uncertain"):
        await current.close()
    assert (
        canary.read_text() == "PRIVATE-ROOT-UNCHANGED"
        and (previous / current.job_id / "worker.cjs").exists()
    )
