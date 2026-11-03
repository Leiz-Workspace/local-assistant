"""Test ADR-154 preparation identity, bounded downloads, locks and SDK payload rejection."""

import hashlib
import io
import json
from pathlib import Path

import pytest

from benchmarks.scripts import vi_voice_preparation as prep


def entry(raw):
    """Create a small Git-pinned fixture independent of retained private assets."""
    return dict(
        bytes=len(raw),
        git_blob_sha1=hashlib.sha1(f"blob {len(raw)}\0".encode() + raw).hexdigest(),
    )


def test_approved_inputs_remain_exact():
    """Check that the runner still binds the sixteen reviewed payloads and fixed denominators."""
    assert prep.digest(prep.MANIFEST) == prep.MANIFEST_SHA
    assert prep.digest(prep.PACKET) == prep.PACKET_SHA
    manifest = json.loads(prep.MANIFEST.read_text())
    packet = json.loads(prep.PACKET.read_text())
    assert len(manifest["entries"]) == 16
    assert sum(e["bytes"] for e in manifest["entries"]) == 608816450
    assert len(packet["tts_cases"]) == 8
    assert len(packet["workflow_sources"]) == 6
    assert packet["workflow_turns"] == 48
    assert len(prep.SOURCES) == len(set(prep.SOURCES))
    assert all(not p.endswith((".onnx", ".json", ".bin")) for p in prep.SOURCES)


def test_git_and_lfs_validation(tmp_path):
    """Reject altered Git/LFS bytes even when their lengths remain unchanged."""
    p = tmp_path / "asset"
    p.write_bytes(b"abc")
    prep.verify_artifact(p, entry(b"abc"))
    prep.verify_artifact(
        p, dict(bytes=3, lfs_sha256=hashlib.sha256(b"abc").hexdigest())
    )
    for bad in [
        entry(b"abd"),
        dict(bytes=2, lfs_sha256="0" * 64),
        dict(bytes=3, lfs_sha256="0" * 64),
    ]:
        with pytest.raises(ValueError):
            prep.verify_artifact(p, bad)
    link = tmp_path / "link"
    link.symlink_to(p)
    with pytest.raises(ValueError):
        prep.verify_artifact(link, entry(b"abc"))


def test_budget_rejects_external_links_and_excess(tmp_path):
    """Stop on excess disk use and links outside the isolated root."""
    (tmp_path / "file").write_bytes(b"abcd")
    assert prep.budget(tmp_path, 4) == 4
    with pytest.raises(ValueError, match="budget"):
        prep.budget(tmp_path, 3)
    (tmp_path / "link").symlink_to("/etc/passwd")
    with pytest.raises(ValueError, match="external_link"):
        prep.budget(tmp_path)


def test_download_has_no_retry_or_failed_publication(tmp_path, monkeypatch):
    """Retain failed partial bytes and make one request only when a payload hash mismatches."""
    calls = []

    class Opener:
        """Supply one deterministic bounded network response."""

        def open(self, url, timeout):
            """Record the sole request and return wrong but equal-sized bytes."""
            calls.append((url, timeout))
            return io.BytesIO(b"bad")

    monkeypatch.setattr(prep.urllib.request, "build_opener", lambda *args: Opener())
    with pytest.raises(ValueError, match="identity"):
        prep.fetch(
            "https://example.org/pin", tmp_path / "asset", entry(b"yes"), tmp_path
        )
    assert len(calls) == 1
    assert not (tmp_path / "asset").exists()
    assert (tmp_path / "asset.partial").read_bytes() == b"bad"


def test_download_oversize_and_existing_partial(tmp_path, monkeypatch):
    """Reject surplus bytes and prohibit a second attempt over preserved partial output."""

    class Opener:
        """Return an oversized fixture without a real network request."""

        def open(self, url, timeout):
            """Provide four bytes for a three-byte approval."""
            return io.BytesIO(b"abcd")

    monkeypatch.setattr(prep.urllib.request, "build_opener", lambda *args: Opener())
    with pytest.raises(ValueError, match="size_or_wall"):
        prep.fetch(
            "https://example.org/pin", tmp_path / "asset", entry(b"abc"), tmp_path
        )
    with pytest.raises(FileExistsError):
        prep.fetch(
            "https://example.org/pin", tmp_path / "asset", entry(b"abc"), tmp_path
        )


def test_receipts_are_private_and_exclusive(tmp_path):
    """Preserve prior receipts and disallow non-finite JSON values."""
    p = tmp_path / "receipt.json"
    prep.publish(p, {"description": "Test receipt.", "ok": True})
    assert p.stat().st_mode & 0o077 == 0
    with pytest.raises(FileExistsError):
        prep.publish(p, {})
    with pytest.raises(ValueError):
        prep.publish(tmp_path / "bad.json", {"value": float("nan")})


def test_sdk_rejects_unapproved_payloads(tmp_path):
    """Distinguish exact non-neural ORT math fixtures from any undeclared checkpoint."""
    (tmp_path / "anything.onnx").write_bytes(b"undeclared")
    with pytest.raises(ValueError, match="undeclared_neural"):
        prep.audit_sdk(tmp_path)
    (tmp_path / "anything.onnx").unlink()
    prep.audit_sdk(tmp_path)
    p = tmp_path / "onnxruntime/datasets/mul_1.onnx"
    p.parent.mkdir(parents=True)
    p.write_bytes(b"wrong fixture")
    with pytest.raises(ValueError, match="undeclared_neural"):
        prep.audit_sdk(tmp_path)


def test_lock_rejects_remote_unhashed_and_gpu(tmp_path):
    """Require all pinned CPU packages and reject injected requirements."""
    names = [
        "sea-g2p",
        "numpy",
        "onnxruntime",
        "tokenizers",
        "soundfile",
        "soxr",
        "huggingface-hub",
    ]
    good = "\n".join(
        f"{n}=={'0.9.1' if n == 'sea-g2p' else '1.0'} --hash=sha256:{'a' * 64}"
        for n in names
    )
    p = tmp_path / "lock"
    p.write_text(good)
    assert len(prep.verify_lock(p)) == 7
    for extra in [
        "torch==1 --hash=sha256:" + "b" * 64,
        "numpy>=1",
        "https://example.org/file",
        good.splitlines()[0],
    ]:
        p.write_text(good + "\n" + extra)
        with pytest.raises(ValueError):
            prep.verify_lock(p)


def test_environment_does_not_inherit_secrets(tmp_path, monkeypatch):
    """Exclude user credentials, proxies and GPU visibility from preparation commands."""
    monkeypatch.setenv("HF_TOKEN", "private")
    monkeypatch.setenv("HTTPS_PROXY", "private")
    env = prep.environment(tmp_path)
    assert "HF_TOKEN" not in env and "HTTPS_PROXY" not in env
    assert env["CUDA_VISIBLE_DEVICES"] == ""
    assert env["UV_PYTHON_DOWNLOADS"] == "never"
    assert Path(env["UV_CACHE_DIR"]).is_relative_to(tmp_path)


def test_sdk_data_allowlist_is_exact(tmp_path, monkeypatch):
    """Permit reviewed non-neural data only at its exact path and with its exact digest."""
    name = "_virtualenv.pth"
    p = tmp_path / "lib/python3.12/site-packages" / name
    p.parent.mkdir(parents=True)
    p.write_bytes(b"import _virtualenv")
    prep.audit_sdk(tmp_path)
    p.write_bytes(b"import unreviewed\n")
    with pytest.raises(ValueError, match="undeclared_neural"):
        prep.audit_sdk(tmp_path)


def test_audit_completion_never_repeats_sdk_steps(tmp_path, monkeypatch):
    """Reject an unrelated failure before downloads, installation or completion receipt publication."""
    prep.publish(
        tmp_path / "preparation-receipt.json",
        dict(
            status="FAILED_STOPPED",
            model_calls=0,
            downloads=[{}] * len(prep.SOURCES),
            error="ValueError:unrelated",
        ),
    )
    monkeypatch.setattr(
        prep, "step", lambda *a, **k: pytest.fail("SDK command repeated")
    )
    monkeypatch.setattr(prep, "fetch", lambda *a, **k: pytest.fail("Download repeated"))
    with pytest.raises(ValueError, match="wrong_failure"):
        prep.complete_reviewed_sdk_audit(tmp_path)
    assert not (tmp_path / "audit-completion-attempt.json").exists()
