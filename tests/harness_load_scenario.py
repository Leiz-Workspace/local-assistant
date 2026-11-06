"""Measure owned concurrent read admission and recovery on native disposable workspace fixtures without model/database/network load."""

import asyncio
import collections
import hashlib
import json
import logging
import time
from uuid import uuid4

from apps.api.services.harness_tools import HarnessToolRun
from apps.api.services.workspaces import WorkspaceService
from src.application.services.mcp_adapter import canonical
from src.application.services.tool_hooks import HookError
from src.application.services.workspace_policy import WorkspaceSpec
from src.infrastructure.readonly_workspace import WorkspaceCatalog

logger = logging.getLogger(__name__)


async def run_load(root):
    """Admit one of100 simultaneous owned native reads without queuing and verify an explicit fresh run can read after cleanup."""
    root = root.resolve()
    root.mkdir(mode=0o700, exist_ok=False)
    source = root / "source.py"
    raw = b'"""Owned D85 admission fixture."""\nVALUE = 1\n'
    source.write_bytes(raw)
    spec = WorkspaceSpec(uuid4(), uuid4(), str(root), "D85 native load fixture")
    workspace = WorkspaceService(WorkspaceCatalog([spec]))
    router = HarnessToolRun(
        spec.owner_id, spec.workspace_id, profile="core", workspace_service=workspace
    )
    request = canonical(dict(name="workspace.read", arguments=dict(path="source.py")))
    started = time.perf_counter()
    try:
        outcomes = await asyncio.gather(
            *(router.execute(request) for _ in range(100)), return_exceptions=True
        )
        accepted = [value for value in outcomes if type(value) is bytes]
        denied = [value for value in outcomes if isinstance(value, HookError)]
        assert len(accepted) == 1 and len(denied) == 99
        codes = dict(collections.Counter(value.code for value in denied))
        assert codes == dict(busy=7, limit=92)
        assert (
            not workspace.operations
            and not workspace.admission.locked()
            and router.guard.active is None
        )
        assert source.read_bytes() == raw
        receipt = json.loads(accepted[0])
        assert all(
            line["source_sha256"] == hashlib.sha256(raw).hexdigest()
            for line in receipt["data"]["lines"]
        )
        elapsed = time.perf_counter() - started
    finally:
        await router.close()
    second = HarnessToolRun(
        spec.owner_id, spec.workspace_id, profile="core", workspace_service=workspace
    )
    try:
        assert type(await second.execute(request)) is bytes
    finally:
        await second.close()
        await workspace.shutdown()
    logger.info("harness_load_complete attempts=100 accepted=1 busy=7 limit=92")
    return dict(
        description="Native disposable read admission, not model/HTTP/global throughput or production SLO.",
        attempts=100,
        accepted=1,
        rejected=codes,
        elapsed_seconds=elapsed,
        policy="one nonqueued active operation and eight charged attempts per explicit run",
        explicit_fresh_run_after_cleanup_succeeded=True,
        workspace_bytes_unchanged=True,
        all_owned_operations_joined=True,
    )
