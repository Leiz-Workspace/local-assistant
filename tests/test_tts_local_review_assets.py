"""Test approved local reviewer artifact pins, complete-byte verification and exclusive publication without downloading neural weights."""

import hashlib
import io
from types import SimpleNamespace

import pytest

from scripts.tts_local_review_assets import (
    MODEL_FILES,
    SHARDS,
    download,
    specs,
    validate_spec,
    verify,
)


def fixture_spec(raw=b"original checkpoint fixture"):
    """Bind authored harmless bytes as an artifact fixture without representing real model parameters."""
    return dict(filename="model.safetensors", bytes=len(raw), lfs_sha256=hashlib.sha256(raw).hexdigest())


def test_original_approved_model_pins_exclude_unused_pickle():
    """Require exact approved repository metadata and all three complete pinned original shards."""
    rows = specs()
    assert len(rows) == len(MODEL_FILES) == 16
    assert sum(row["bytes"] for row in rows if row["filename"] in SHARDS) == 11972663208
    assert "spk_dict.pt" not in MODEL_FILES


@pytest.mark.parametrize("change", [dict(filename="../other"), dict(filename=".."), dict(bytes=True), dict(bytes=6*1024**3), dict(lfs_sha256="0"*63)])
def test_invalid_artifact_specs_rejected(change):
    """Reject traversal, booleans, excessive size and incomplete digests before opening network or output files."""
    with pytest.raises(ValueError):
        validate_spec(dict(fixture_spec(), **change))


def test_complete_bytes_and_symlinks_checked(tmp_path):
    """Refuse same-size corruption and symlink aliases instead of adopting foreign model files."""
    raw = b"original checkpoint fixture"
    path = tmp_path / "fixture"
    path.write_bytes(raw)
    assert verify(path, fixture_spec()) == hashlib.sha256(raw).hexdigest()
    link = tmp_path / "link"
    link.symlink_to(path)
    with pytest.raises(ValueError):
        verify(link, fixture_spec())
    path.write_bytes(b"x" * len(raw))
    with pytest.raises(ValueError):
        verify(path, fixture_spec())


class Response(io.BytesIO):
    """Supply a bounded fake original HTTPS artifact response without network access."""

    status = 200

    def geturl(self):
        """Expose only the original permitted public source authority."""
        return "https://huggingface.co/fixture"


def test_download_exclusive_verified_publication_and_partial_retention(tmp_path):
    """Publish intact bytes privately once and preserve an overflowing failed download without accepting it."""
    raw = b"original checkpoint fixture"
    client = SimpleNamespace(open=lambda *args, **kwargs: Response(raw))
    assert download("https://huggingface.co/fixture", tmp_path, fixture_spec(), client) == hashlib.sha256(raw).hexdigest()
    assert (tmp_path / "model.safetensors").stat().st_mode & 0o777 == 0o600
    assert download("https://huggingface.co/fixture", tmp_path, fixture_spec(), None) == hashlib.sha256(raw).hexdigest()
    other = tmp_path / "other"
    bad = SimpleNamespace(open=lambda *args, **kwargs: Response(raw + b"x"))
    with pytest.raises(ValueError):
        download("https://huggingface.co/fixture", other, fixture_spec(), bad)
    assert (other / "model.safetensors.partial").exists()
    assert not (other / "model.safetensors").exists()


def test_foreign_authority_rejected_before_publication(tmp_path):
    """Never contact an arbitrary host or place private artifacts through a linked root."""
    with pytest.raises(ValueError):
        download("http://localhost/private", tmp_path, fixture_spec())
