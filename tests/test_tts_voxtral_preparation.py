"""Test ADR-107 artifact authority, CPU SDK isolation and bounded subprocess ownership without network or model loading."""

import hashlib
import json
import logging
import sys

import pytest

from scripts import tts_voxtral_preparation as prep

logger = logging.getLogger(__name__)


def test_reviewed_manifest_exact_artifacts(monkeypatch):
    """Require the reviewed nine artifacts and reject byte mutation before creating the evaluation root."""
    monkeypatch.setattr(prep, "PREPARATION_ALLOWED", True)
    value = prep.approved_manifest()
    assert len(value["files"]) == 9
    assert sum(row["bytes"] for row in value["files"]) == 9371455742
    assert "consolidated.safetensors" not in {row["filename"] for row in value["files"]}
    monkeypatch.setattr(prep, "MANIFEST_SHA256", "0" * 64)
    with pytest.raises(ValueError, match="manifest_changed"):
        prep.approved_manifest()


def test_retired_permission_before_filesystem(tmp_path, monkeypatch):
    """Reject a retired preparation without making directories or invoking a package client."""
    monkeypatch.setattr(prep, "PREPARATION_ALLOWED", False)
    with pytest.raises(ValueError, match="retired"):
        prep.prepare(tmp_path / "absent")
    assert not (tmp_path / "absent").exists()


@pytest.mark.parametrize("mutation", ["url", "duplicate", "traversal", "budget"])
def test_reject_manifest_authority(tmp_path, monkeypatch, mutation):
    """Exercise structural validation separately from the immutable production manifest digest."""
    value = json.loads(prep.MANIFEST.read_bytes())
    if mutation == "url":
        value["files"][0]["url"] = "https://example.com/README.md"
    elif mutation == "duplicate":
        value["files"][1] = value["files"][0]
    elif mutation == "traversal":
        value["files"][0]["filename"] = "../escape"
    else:
        value["disk_budget_bytes"] += 1
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(value))
    monkeypatch.setattr(prep, "MANIFEST", path)
    monkeypatch.setattr(prep, "MANIFEST_SHA256", hashlib.sha256(path.read_bytes()).hexdigest())
    monkeypatch.setattr(prep, "PREPARATION_ALLOWED", True)
    with pytest.raises(ValueError):
        prep.approved_manifest()


def test_budget_unique_inodes_and_external_symlinks(tmp_path):
    """Count a publication link once and avoid following a symlink outside the owned root."""
    import os

    (tmp_path / "file").write_bytes(b"123")
    os.link(tmp_path / "file", tmp_path / "link")
    (tmp_path / "external").symlink_to("/usr")
    assert prep.tree_bytes(tmp_path) == 3 + len("/usr")
    with pytest.raises(ValueError, match="disk_budget"):
        prep.check_budget(tmp_path, reserve=4, limit=10)


def test_no_inherited_credentials_or_indexes(tmp_path, monkeypatch):
    """Restrict SDK network setup to public package infrastructure and root-owned cache/temp paths."""
    monkeypatch.setenv("HF_TOKEN", "fake-should-not-be-inherited")
    monkeypatch.setenv("UV_INDEX_URL", "https://private.invalid")
    result = prep.environment(tmp_path)
    assert "HF_TOKEN" not in result and "UV_INDEX_URL" not in result
    assert result["UV_CACHE_DIR"] == str(tmp_path / "cache")
    assert result["UV_LINK_MODE"] == "copy" and result["CUDA_VISIBLE_DEVICES"] == ""


def test_namespace_cannot_see_checkpoint_or_audio(tmp_path):
    """Exclude old and new model mounts while retaining CPU/offline/readonly import constraints."""
    command = prep.imports_command(tmp_path)
    assert str(prep.OLD_ROOT / "model") not in command and "/model" not in command
    assert str(tmp_path / "model") not in command
    assert "--unshare-all" in command and "--clearenv" in command
    assert "--as=12884901888" in command and command[-1] == "/app/sdk_probe.py"
    assert str(tmp_path / "venv") in command
    assert "from_pretrained" not in prep.PROBE and ".generate(" not in prep.PROBE
    compile(prep.PROBE, "sdk_probe.py", "exec")


def test_lock_cpu_pins_and_hashes(tmp_path):
    """Reject a changed core version or a CUDA dependency even if other requirement hashes exist."""
    path = tmp_path / "requirements.lock"
    packages = {name.split("[")[0]: version for name, version in prep.PINS.items()}
    packages.update(soundfile="0.14.0", soxr="1.1.0")
    text = "\n".join(f"{name}=={version} --hash=sha256:{'0' * 64}" for name, version in packages.items())
    path.write_text(text)
    prep.verify_lock(path)
    for invalid in [text.replace("2.10.0+cpu", "2.10.0"), text + "\nnvidia-cublas-cu12==1"]:
        path.write_text(invalid)
        with pytest.raises(ValueError):
            prep.verify_lock(path)


def test_owned_subprocess_timeout_preserves_failure_log(tmp_path):
    """Terminate and join a harmless timed-out child while preserving exclusive first-run output."""
    with pytest.raises(TimeoutError):
        prep.run_step([sys.executable, "-c", "import time; print('started', flush=True); time.sleep(30)"], tmp_path, "timeout", timeout=0.1)
    assert b"started" in (tmp_path / "timeout.log").read_bytes()
    with pytest.raises(FileExistsError):
        prep.run_step([sys.executable, "-c", "pass"], tmp_path, "timeout")


def test_inventory_detects_changes(tmp_path):
    """Bind regular bytes and symlink targets without importing the inspected runtime."""
    (tmp_path / "file").write_bytes(b"first")
    (tmp_path / "link").symlink_to("file")
    before = prep.inventory(tmp_path)
    (tmp_path / "file").write_bytes(b"second")
    assert prep.inventory(tmp_path) != before
    assert before["link"] == dict(kind="symlink", target="file")
    logger.info("voxtral_preparation_fixture_inventory_passed")


def test_existing_or_symlink_root_not_adopted(tmp_path, monkeypatch):
    """Refuse an existing directory or a symlink before writing an approval or starting SDK installation."""
    monkeypatch.setattr(prep, "PREPARATION_ALLOWED", True)
    with pytest.raises(FileExistsError):
        prep.prepare(tmp_path)
    link = tmp_path / "link"
    link.symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        prep.prepare(link)
    assert not (tmp_path / "approval.json").exists()


def test_resume_rejects_unexpected_stage(tmp_path, monkeypatch):
    """Prevent recovery from adopting an arbitrary or already-installed environment."""
    monkeypatch.setattr(prep, "PREPARATION_ALLOWED", True)
    monkeypatch.setattr(prep, "ROOT", tmp_path)
    (tmp_path / "venv").mkdir()
    with pytest.raises(ValueError, match="unexpected_stage"):
        prep.resume_resolved()
    assert not (tmp_path / "resolution-recovery.json").exists()


def test_actual_resolved_lock():
    """Check the first real uv lock without installing packages or treating resolution as import compatibility."""
    prep.verify_lock(prep.PROJECT / "data/backups/d70-voxtral-local-reviewer/requirements.lock")


def test_completed_preparation_closed_by_default(tmp_path):
    """Keep every preparation entry point closed after the approved download/install scope is consumed."""
    assert prep.PREPARATION_ALLOWED is False
    for action in [prep.approved_manifest, prep.resume_resolved]:
        with pytest.raises(ValueError, match="retired"):
            action()
    with pytest.raises(ValueError, match="retired"):
        prep.finish_preparation(tmp_path, {}, "/does-not-run")
    assert not list(tmp_path.iterdir())
