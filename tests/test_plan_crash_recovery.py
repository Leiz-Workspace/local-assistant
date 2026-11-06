"""Crash an actual disposable plan process after durable in-flight publication and verify lock release/read-only recovery without write replay."""

import os
import subprocess
import sys
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from test_run_planner import plan, runner

from src.application.services.run_planner import PlanError


@pytest.mark.parametrize("effect", ["read", "write"])
@pytest.mark.asyncio
async def test_actual_crash_releases_kernel_lock_and_preserves_nonrefundable_inflight_state(
    tmp_path, effect
):
    """Recover an expected exit17 under the same owner/plan/catalog and forbid any uncertain write re-execution."""
    owner, workspace = uuid4(), uuid4()
    source = '''"""Crash only after the disposable planner durably records an in-flight attempt."""
import asyncio,os,sys
from pathlib import Path
from uuid import UUID
from test_run_planner import plan,runner
async def crash(step,call):
    """Exit the actual process before a terminal receipt, releasing the kernel-owned lock."""
    os._exit(17)
value,store=runner(Path(sys.argv[1]),crash,effect=sys.argv[2],owner=UUID(sys.argv[3]),workspace=UUID(sys.argv[4]))
asyncio.run(value.start(plan(),explicit_start=True))
'''
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            source,
            str(tmp_path),
            effect,
            str(owner),
            str(workspace),
        ],
        capture_output=True,
        text=True,
        timeout=10,
        env={
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "LANG": "C.UTF-8",
            "PYTHONPATH": str(Path("tests").resolve()),
        },
    )
    assert result.returncode == 17, result.stdout + result.stderr
    cases = list((tmp_path / "state").glob("*.02.json"))
    assert len(cases) == 1
    run_id = UUID(cases[0].name.split(".")[0])
    calls = []

    async def recovered(step, call):
        """Record only explicit parent recovery work after the crashed process has been reaped."""
        calls.append(True)
        return b"recovered read"

    value, store = runner(
        tmp_path, recovered, effect=effect, owner=owner, workspace=workspace
    )
    state, reference = store.latest(run_id)
    assert state["status"] == "inflight" and state["attempts"] == 1
    with store.lock(run_id):
        pass
    if effect == "read":
        recovered_result = await value.resume(plan(), reference, explicit_resume=True)
        assert (
            recovered_result["status"] == "complete"
            and recovered_result["attempts"] == 2
            and calls == [True]
        )
    else:
        with pytest.raises(PlanError, match="uncertain_write"):
            await value.resume(plan(), reference, explicit_resume=True)
        assert calls == []
    await value.close()
    store.close()
