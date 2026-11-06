"""Verify actual killed-process checkpoint/intent/commit recovery observations without resuming edits or recovering old approval grants."""

import json
import os
import selectors
import subprocess
import sys
from pathlib import Path
from uuid import UUID

import pytest
from test_atomic_patch import patch_fixture as patch_fixture

from src.application.services.approvals import ApprovalError, ApprovalStore
from src.infrastructure.checkpoint_recovery import observe_checkpoint
from src.infrastructure.checkpoints import CheckpointStore

CHILD = '''"""Create one trusted synthetic checkpoint phase and wait for controlled parent SIGKILL."""
import hashlib,json,sys
from pathlib import Path
from uuid import UUID
from src.application.services.approvals import ApprovalStore
from src.application.services.workspace_policy import WorkspaceSpec
from src.infrastructure.atomic_patch import NativePatch
from src.infrastructure.checkpoints import CheckpointStore
from src.infrastructure.readonly_workspace import WorkspaceCatalog
settings=json.loads(sys.argv[1])
spec=WorkspaceSpec(UUID(settings["owner"]),UUID(settings["workspace"]),settings["source_root"],"controlled-process-fixture")
catalog=WorkspaceCatalog([spec])
store=CheckpointStore(settings["backup_root"],catalog)
approvals=ApprovalStore(catalog)
proposal=NativePatch(catalog,spec.owner_id,spec.workspace_id,"src/main.py",settings["source_sha256"],"controlled approved process change\\n")
checkpoint=store.capture(proposal)
approval=proposal.register_approval(approvals)
review=approvals.review(spec.owner_id,approval)
approvals.decide(spec.owner_id,approval,"approve",review["scope_digest"],review["review_nonce"])
if settings["phase"]!="ready":
    store.transition(proposal,checkpoint)
if settings["phase"]=="committed":
    proposal.apply(approvals,approval)
print(json.dumps(dict(checkpoint_id=str(checkpoint),proposal_id=str(proposal.identifier),approval_id=str(approval),phase=settings["phase"])),flush=True)
sys.stdin.buffer.read(1)
'''


@pytest.mark.parametrize("phase", ["ready", "intent", "committed"])
def test_actual_sigkill_reopen_does_not_infer_commit_or_recover_grants(
    tmp_path, patch_fixture, phase
):
    """Kill a real child after acknowledged durable stages and inspect original/replacement bytes without treating journal intent as action authority."""
    import hashlib

    root, source, raw, spec, _, _ = patch_fixture
    backup = tmp_path / "process-checkpoints"
    backup.mkdir(mode=0o700)
    settings = dict(
        owner=str(spec.owner_id),
        workspace=str(spec.workspace_id),
        source_root=str(root),
        backup_root=str(backup),
        source_sha256=hashlib.sha256(raw).hexdigest(),
        phase=phase,
    )
    environment = dict(PATH="/usr/bin:/bin", LANG="C.UTF-8", PYTHONPATH=str(Path.cwd()))
    process = subprocess.Popen(
        [sys.executable, "-c", CHILD, json.dumps(settings)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=tmp_path,
        env=environment,
        start_new_session=True,
    )
    selector = selectors.DefaultSelector()
    try:
        selector.register(process.stdout, selectors.EVENT_READ)
        assert selector.select(10), (
            "controlled checkpoint child did not reach its durable phase"
        )
        message = process.stdout.readline(4096)
        assert message and len(message) < 4096, (
            "controlled checkpoint child exited before durable phase"
        )
        observed = json.loads(message)
        assert observed["phase"] == phase
        process.kill()
        assert process.wait(timeout=3) == -9
    finally:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=3)
        for stream in (process.stdin, process.stdout, process.stderr):
            stream.close()
        selector.close()
    with pytest.raises(ProcessLookupError):
        os.kill(process.pid, 0)
    store = CheckpointStore(backup, patch_fixture[4].catalog)
    try:
        snapshot = store.read(
            spec.owner_id, spec.workspace_id, UUID(observed["checkpoint_id"])
        )
        assert snapshot["journal"]["state"] == (
            "ready" if phase == "ready" else "applying"
        )
        recovery = observe_checkpoint(
            store.catalog, spec.owner_id, spec.workspace_id, snapshot
        )
        assert recovery["observation"] == (
            "observed_replacement" if phase == "committed" else "observed_original"
        )
        assert (
            not recovery["action_taken"]
            and not recovery["causality_inferred"]
            and not recovery["recovered_approval"]
        )
        assert source.read_bytes() == (
            b"controlled approved process change\n" if phase == "committed" else raw
        )
        fresh = ApprovalStore(store.catalog)
        with pytest.raises(ApprovalError, match="approval_not_found"):
            fresh.review(spec.owner_id, UUID(observed["approval_id"]))
        fresh.close()
    finally:
        store.close()
