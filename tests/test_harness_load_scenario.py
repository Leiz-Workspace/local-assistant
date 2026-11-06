"""Verify native read load respects finite admission rather than accumulating queued work or refunding rejected attempts."""

import pytest
from harness_load_scenario import run_load


@pytest.mark.asyncio
async def test_hundred_native_reads_have_one_admission_and_explicit_recovery(tmp_path):
    """Require exact overload accounting, unchanged source bytes and a new explicit read after previous run cleanup."""
    result = await run_load(tmp_path / "load")
    assert result["attempts"] == 100 and result["accepted"] == 1
    assert result["rejected"] == dict(busy=7, limit=92)
    assert (
        result["all_owned_operations_joined"]
        and result["explicit_fresh_run_after_cleanup_succeeded"]
    )
