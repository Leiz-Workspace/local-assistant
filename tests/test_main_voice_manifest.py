"""Verify private evaluation-only manifests, inventory integrity and worker exclusion without real artifacts."""

import hashlib
import json

import pytest

from src.infrastructure.voice import manifest


def fixture_manifest(tmp_path):
    """Build a disposable non-neural artifact tree and strict private manifest for validation tests."""
    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "neutral.txt").write_text("neutral non-neural test data")
    raw = (assets / "neutral.txt").read_bytes()
    value = dict(
        purpose="integration_evaluation",
        production_activation=False,
        pins=manifest.PINS,
        paths={name: str(assets) for name in manifest.PATHS},
        source_sha256={
            "src/infrastructure/voice/__init__.py": manifest.file_sha(
                manifest.PROJECT / "src/infrastructure/voice/__init__.py"
            )
        },
        inventory={
            str(assets): {
                "neutral.txt": {
                    "bytes": len(raw),
                    "sha256": hashlib.sha256(raw).hexdigest(),
                }
            }
        },
        reading_binding={
            "speaker_sha256": "a" * 64,
            "reference_codes_sha256": "b" * 64,
        },
        core={"model_path": str(tmp_path / "fake-model")},
    )
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(value))
    path.chmod(0o600)
    return path, value, assets


@pytest.mark.parametrize("mode", [0o644, 0o660, 0o777])
def test_manifest_rejects_nonprivate_permissions(tmp_path, mode):
    """Refuse manifests writable or readable by other identities before any native setup."""
    path, _, _ = fixture_manifest(tmp_path)
    path.chmod(mode)
    with pytest.raises(ValueError):
        manifest.VoiceManifest.load(path)


def test_manifest_single_worker_lock_and_production_scope_denial(tmp_path):
    """Refuse concurrent manifest reuse and unapproved activation or altered model revisions."""
    path, value, _ = fixture_manifest(tmp_path)
    held = manifest.VoiceManifest.load(path)
    with pytest.raises(BlockingIOError):
        manifest.VoiceManifest.load(path)
    held.close()
    held.close()
    for field, bad in [
        ("purpose", "production"),
        ("production_activation", True),
        ("pins", dict(manifest.PINS, ASR="other")),
    ]:
        path.write_text(json.dumps(dict(value, **{field: bad})))
        with pytest.raises(ValueError):
            manifest.VoiceManifest.load(path)


def test_manifest_inventory_and_original_sources_are_exact(tmp_path, monkeypatch):
    """Reject modified bytes, added files and altered capability metadata before neural imports."""
    path, value, assets = fixture_manifest(tmp_path)
    original = manifest.file_sha

    def fake_core_sha(candidate):
        """Avoid real weights while isolating the artifact-inventory checks under test."""
        return (
            manifest.PINS["CORE_GGUF"]
            if str(candidate) == value["core"]["model_path"]
            else original(candidate)
        )

    monkeypatch.setattr(manifest, "file_sha", fake_core_sha)
    settings = manifest.VoiceManifest.load(path)
    try:
        settings.verify()
        (assets / "extra.txt").write_text("unexpected")
        with pytest.raises(ValueError, match="inventory_set"):
            settings.verify()
        (assets / "extra.txt").unlink()
        (assets / "neutral.txt").write_text("changed")
        with pytest.raises(ValueError, match="artifact_changed"):
            settings.verify()
        path.write_text(path.read_text() + " ")
        with pytest.raises(ValueError, match="manifest_changed"):
            settings.verify()
    finally:
        settings.close()


def test_manifest_symlink_is_never_followed_as_authority(tmp_path):
    """Refuse a symbolic-link manifest even if its target contains otherwise admissible metadata."""
    path, _, _ = fixture_manifest(tmp_path)
    link = tmp_path / "link.json"
    link.symlink_to(path)
    with pytest.raises(OSError):
        manifest.VoiceManifest.load(link)
