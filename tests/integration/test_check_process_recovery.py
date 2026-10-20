"""Verify acknowledged SIGKILL check stages retain truthful history without recovering grants or automatically rerunning snapshots."""

import json
import logging
import os
import selectors
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path
from uuid import UUID

import pytest
from test_check_jobs import job_store as job_store

from src.application.services.approvals import ApprovalError, ApprovalStore
from src.infrastructure.check_jobs import CheckJobStore

logger = logging.getLogger(__name__)
CHILD = '''"""Reach one controlled durable snapshot-check phase for an acknowledged parent kill drill."""
import hashlib,json,os,sys,threading
from uuid import UUID
from src.application.services.approvals import ApprovalStore
from src.application.services.workspace_policy import WorkspaceSpec
from src.infrastructure.check_jobs import CheckJobStore
from src.infrastructure.check_runtime import RuntimeSpec
from src.infrastructure.check_sources import NativeCheckSources
from src.infrastructure.readonly_workspace import WorkspaceCatalog
s=json.loads(sys.argv[1])
owner,workspace=UUID(s["owner"]),UUID(s["workspace"])
catalog=WorkspaceCatalog([WorkspaceSpec(owner,workspace,s["source_root"],"Controlled recovery")])
checkpoint=os.open(s["checkpoint_root"],os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC)
store=CheckJobStore(s["check_root"],catalog,RuntimeSpec(**s["runtime"]),checkpoint)
sources=NativeCheckSources(catalog,owner,workspace,"ruff_check",[dict(path="value.py",expected_sha256=s["source_sha256"])])
captured=store.capture(sources)
request=None

def pause(observation=None):
    """Acknowledge only the reached fixture phase and wait for the parent without persisting inferred outcomes."""
    print(json.dumps(dict(job_id=str(captured["identifier"]),approval_id=str(request) if request else None,phase=s["phase"],observation=observation)),flush=True)
    sys.stdin.buffer.read(1)
    raise RuntimeError("kill drill resumed unexpectedly")

if s["phase"]=="captured":
    pause()
approvals=ApprovalStore(catalog)
request=approvals.create(owner,workspace,"run_checks",captured["review"])
store.link_approval(owner,workspace,captured["identifier"],request)
review=approvals.review(owner,request)
approvals.decide(owner,request,"approve",review["scope_digest"],review["review_nonce"])
replace=store.storage.replace_journal

def journal(directory,value):
    """Pause after durable starting intent or after native exit before terminal publication, never during a running child."""
    if s["phase"]=="after_exit" and value["state"]=="observed":
        assert sources.closed and approvals.review(owner,request)["state"]=="consumed"
        pause(value["observation"])
    replace(directory,value)
    if s["phase"]=="starting" and value["state"]=="starting":
        assert approvals.review(owner,request)["state"]=="approved"
        pause()

store.storage.replace_journal=journal
store.run_attempt(sources,captured["identifier"],request,approvals,threading.Event(),{})
raise RuntimeError("kill stage was not reached")
'''


@pytest.mark.parametrize("phase", ["captured", "starting", "after_exit"])
def test_actual_sigkill_retains_uncertain_history_without_old_grants(
    job_store, tmp_path, phase
):
    """Kill a real process at three acknowledged non-running stages and verify history cannot infer an unrecorded execution result."""
    store, sources, paths, spec, checkpoint = job_store
    original = (paths[0] / "value.py").read_bytes()
    settings = dict(
        owner=str(sources.owner),
        workspace=str(sources.workspace),
        source_root=str(paths[0]),
        check_root=str(paths[1]),
        checkpoint_root=str(paths[2]),
        runtime=asdict(spec),
        source_sha256=sources.receipts[0].sha256,
        phase=phase,
    )
    store.close()
    process = subprocess.Popen(
        [sys.executable, "-c", CHILD, json.dumps(settings)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=tmp_path,
        env=dict(PATH="/usr/bin:/bin", LANG="C.UTF-8", PYTHONPATH=str(Path.cwd())),
        start_new_session=True,
    )
    selector = selectors.DefaultSelector()
    try:
        selector.register(process.stdout, selectors.EVENT_READ)
        assert selector.select(10), (
            "controlled check child did not acknowledge its stage"
        )
        raw = process.stdout.readline(8192)
        assert raw and len(raw) < 8192, (
            "controlled child exited before stage acknowledgement"
        )
        observed = json.loads(raw)
        assert observed["phase"] == phase
        if phase == "after_exit":
            assert (
                observed["observation"]["started_acknowledged"]
                and observed["observation"]["exit_code"] == 0
            )
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
    reopened = CheckJobStore(str(paths[1]), store.catalog, spec, checkpoint)
    try:
        result = reopened.read(
            sources.owner, sources.workspace, UUID(observed["job_id"])
        )
        assert result["state"] == ("captured" if phase == "captured" else "starting")
        assert result["observation"] is None
        assert not result["recovered_approval"] and not result["live_action_authority"]
        assert (paths[0] / "value.py").read_bytes() == original
        fresh = ApprovalStore(store.catalog)
        try:
            if observed["approval_id"]:
                with pytest.raises(ApprovalError, match="approval_not_found"):
                    fresh.review(sources.owner, UUID(observed["approval_id"]))
        finally:
            fresh.close()
        logger.info(
            "checks_sigkill_fixture_reopened phase=%s historical_state=%s",
            phase,
            result["state"],
        )
    finally:
        reopened.close()
