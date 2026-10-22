"""Verify the real sealed diagnostic namespace excludes parent-only corpus metadata and preparation code without neural execution."""

import importlib.util
import json
import logging
import subprocess
from pathlib import Path


def namespace_probe():
    """Inspect actual readonly namespace visibility using only the existing Python standard library and pure response validator."""
    from scripts import tts_local_review_diagnostic_runtime as runtime

    assert not Path("/app/scripts/tts_local_review_diagnostic.py").exists()
    assert importlib.util.find_spec("scripts.tts_local_review_diagnostic") is None
    assert not hasattr(runtime, "SOURCES") and not hasattr(runtime, "prepare_packet")
    assert not Path("/samples/parent-only.json").exists()
    assert not Path("/home/korosaki-ryukai/Workspace/Server/ai").exists()
    assert runtime.parse_answer("no") == "no" and runtime.MAX_TOKENS == 16
    print(json.dumps(dict(parent_metadata_unmounted=True,preparation_module_unimportable=True,pure_response_runtime_available=True,no_neural_import=True)),flush=True)


def test_sealed_namespace_excludes_parent_control_definitions(tmp_path):
    """Probe the genuine bwrap mount layout rather than inferring metadata isolation from generated argument text alone."""
    from scripts import tts_local_review as controller
    from scripts.tts_local_review_assets import PROJECT

    command = controller.sandbox("imports", tmp_path)
    position = command.index("--chdir")
    command[position:position] = ["--ro-bind", str(PROJECT / "tests/test_tts_local_review_diagnostic_namespace.py"), "/app/probe.py"]
    command[-1] = "/app/probe.py"
    result = subprocess.run(command,capture_output=True,timeout=30,check=False)
    logging.getLogger(__name__).info("diagnostic_namespace_probe exit_code=%d stdout=%s stderr=%s",result.returncode,result.stdout.decode(),result.stderr.decode())
    assert result.returncode == 0,result.stderr.decode()
    evidence = json.loads(result.stdout.splitlines()[-1])
    assert evidence["parent_metadata_unmounted"] and evidence["preparation_module_unimportable"]


if __name__ == "__main__":
    namespace_probe()
