"""Verify actual bounded native memory/disk failures and recovery without risking shared host memory, storage, models or databases."""

import pytest
from runtime_fault_scenario import command, run_fault


@pytest.mark.parametrize("mode", ["memory", "disk"])
def test_native_private_resource_exhaustion_recovers_and_child_is_reaped(
    tmp_path, mode
):
    """Run actual offline low-cap native fixtures and require finite expected failure plus successful small recovery work."""
    result = run_fault(tmp_path / mode, mode)
    assert result["child_reaped"] and result["exit_code"] == 0
    assert (
        result["wall_seconds"] < 10
        and result["measurement"]["peak_process_rss_kib"] < 262144
    )


def test_fault_command_refuses_arbitrary_operation_or_host_resource_target(tmp_path):
    """Reject model-selected commands or file paths before creating any child process."""
    for mode in ("shell", "oom-host", "fill-root", "/etc/passwd", True):
        with pytest.raises(ValueError):
            command(tmp_path / "fixture", mode)
    arguments = command(tmp_path / "fixture", "disk")
    assert "--unshare-all" in arguments and "--clearenv" in arguments
    assert "--as=268435456" in arguments and "65536" in arguments
    assert "/home" not in arguments and "/dev/nvidia0" not in arguments
