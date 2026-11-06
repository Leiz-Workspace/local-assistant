"""Verify pre-consumption private-byte tampering, source-pin cleanup uncertainty and persistent owner quota denial using real stores."""

import os
import threading

import pytest
from test_check_jobs import job_store as job_store
from test_check_jobs import pending_native_job

from src.application.services.workspace_policy import WorkspaceAccessError
from src.infrastructure.check_jobs import CheckJobStore


@pytest.mark.parametrize("target", ["snapshot", "runtime"])
def test_changed_private_bytes_after_approval_prevent_grant_consumption(
    job_store, target
):
    """Reject real private source/runtime mutation before starting a native child or consuming its exact approval."""
    store, _, paths, _, _ = job_store
    sources, identifier, approvals, request = pending_native_job(job_store)
    path = paths[1] / (
        identifier.hex + "/snapshot/value.py"
        if target == "snapshot"
        else "runtime/bin/ruff"
    )
    original = path.read_bytes()
    original_mode = path.stat().st_mode & 0o777
    path.chmod(0o600)
    path.write_bytes(b"changed private bytes")
    evidence = {}
    try:
        with pytest.raises(WorkspaceAccessError):
            store.run_attempt(
                sources, identifier, request, approvals, threading.Event(), evidence
            )
        assert evidence["observation"] is None
        assert approvals.review(sources.owner, request)["state"] == "approved"
        assert sources.closed
    finally:
        path.write_bytes(original)
        path.chmod(original_mode)
        sources.close()
        approvals.close()


def test_native_exit_and_source_pin_cleanup_uncertainty_are_persisted_together(
    job_store, monkeypatch
):
    """Close real source capabilities then inject a lost close acknowledgement before terminal journaling without erasing the actual exit."""
    store = job_store[0]
    sources, identifier, approvals, request = pending_native_job(job_store)
    close = sources.close

    def uncertain_close():
        """Close the actual owned native descriptors before reporting a controlled acknowledgement error."""
        close()
        raise OSError("CONTROLLED-SOURCE-CLOSE-ACK")

    monkeypatch.setattr(sources, "close", uncertain_close)
    try:
        evidence = store.run_attempt(
            sources, identifier, request, approvals, threading.Event(), {}
        )
        result = store.read(sources.owner, sources.workspace, identifier)
        assert result["state"] == "observed" and result["observation"]["exit_code"] == 0
        assert result["observation"]["cleanup_uncertain"]
        assert evidence["error_code"] == "checks_source_pin_cleanup_uncertain"
        assert not evidence["terminal_persistence_uncertain"] and sources.closed
        assert approvals.review(sources.owner, request)["state"] == "consumed"
    finally:
        monkeypatch.setattr(sources, "close", close)
        close()
        approvals.close()


def test_owner_capacity_remains_charged_after_reopen_without_history_deletion(
    job_store,
):
    """Retain all eight real owner reservations across restart and refuse a ninth before creating another job directory."""
    store, sources, paths, spec, checkpoint = job_store
    for _ in range(8):
        store.capture(sources)
    before = set(os.listdir(paths[1]))
    with pytest.raises(WorkspaceAccessError):
        store.capture(sources)
    assert set(os.listdir(paths[1])) == before
    store.close()
    reopened = CheckJobStore(str(paths[1]), store.catalog, spec, checkpoint)
    try:
        assert len(reopened.list(sources.owner, sources.workspace)) == 8
        with pytest.raises(WorkspaceAccessError):
            reopened.capture(sources)
        assert set(os.listdir(paths[1])) == before
    finally:
        reopened.close()
