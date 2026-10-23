"""Verify sealed synthetic Voxtral buffer, cache and realistic attention-shape diagnostics without original checkpoint or audio access."""

import json
import logging
import subprocess
from pathlib import Path

import pytest

from scripts import tts_voxtral_load as load
from scripts import tts_voxtral_synthetic_diagnostics as diagnostics

logger = logging.getLogger(__name__)


def diagnostic_command(probe):
    """Mount only the synthetic diagnostic source alongside the accepted pure loader in a model-free offline namespace."""
    command = load.command()
    index = command.index("--chdir")
    command[index:index] = ["--ro-bind", str(Path(diagnostics.__file__).resolve()), "/app/synthetic_diagnostics.py"]
    command[-1] = "/app/synthetic_diagnostics.py"
    command += [probe]
    return command


def test_diagnostic_namespace_has_no_original_inputs():
    """Exclude original weights, samples, parent labels and control packets from each fixed synthetic probe."""
    command = diagnostic_command("buffers")
    mounts = [command[i + 1:i + 3] for i, token in enumerate(command) if token == "--ro-bind"]
    assert mounts == [["/usr", "/usr"], [str(load.ROOT / "venv"), "/venv"], [str(load.WORKER), "/app/worker.py"], [str(Path(diagnostics.__file__).resolve()), "/app/synthetic_diagnostics.py"]]
    assert "--as=12884901888" in command and "--unshare-all" in command and "--clearenv" in command
    assert "/model" not in command and "/samples" not in command
    logger.info("voxtral_synthetic_diagnostic_namespace_verified original_inputs=False")


@pytest.mark.parametrize("probe", ["buffers", "cache", "attention", "mel"])
def test_native_synthetic_diagnostic(probe):
    """Run the exact pinned SDK against authored fixtures and retain all native results without any original-weight inference."""
    result = subprocess.run(diagnostic_command(probe), capture_output=True, timeout=90)
    logger.info("voxtral_synthetic_diagnostic probe=%s exit_code=%d stdout=%s stderr=%s", probe, result.returncode, result.stdout.decode(), result.stderr.decode())
    assert result.returncode == 0, result.stderr.decode()
    observed = json.loads(result.stdout.splitlines()[-1])
    assert observed["probe"] == probe and observed["original_weight_predictions"] == 0
    assert observed["original_weights_mounted"] is False and observed["recorded_audio_mounted"] is False
    if probe == "buffers":
        assert observed["maximum_logit_difference"] == 0 and observed["parameters"] < 20000
        assert any(not row["persistent"] and "inv_freq" in row["name"] for row in observed["buffers"])
    elif probe == "cache":
        assert [row["backend"] for row in observed["backends"]] == ["eager", "sdpa"]
        assert all(row["cached_audio_encoder_calls"] == 1 and row["uncached_audio_encoder_calls"] == 4 and row["cached_and_uncached_tokens_equal"] is True for row in observed["backends"])
    elif probe == "attention":
        assert observed["sequence_length"] == 1500 and observed["heads"] == 20
        assert observed["bidirectional_future_influence"] is True and observed["is_causal"] is False
    else:
        assert [row["signal"] for row in observed["signals"]] == ["silence", "two_tones", "noise", "step"]
        assert all(row["padded_samples"] == 480000 for row in observed["signals"])
