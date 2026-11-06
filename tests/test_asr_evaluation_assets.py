"""Test pinned public ASR artifact integrity, path/redirect guards and exclusive publication without downloading real models."""

import hashlib
import io
from types import SimpleNamespace

import pytest

from scripts.asr_evaluation_assets import (
    AssetError,
    allowed_url,
    fetch,
    source_url,
    validate_spec,
)


class Response(io.BytesIO):
    """Expose a controlled bounded public HTTPS artifact stream without any network request."""

    status = 200

    def geturl(self):
        """Return an admitted provider CDN URL while keeping signed URLs out of test outputs."""
        return "https://cdn-lfs.huggingface.co/public"


def specification(raw, *, lfs=True):
    """Build independently expected complete SHA256 or ordinary Git blob identity for an authored artifact."""
    return dict(
        filename="model.bin",
        bytes=len(raw),
        git_blob_sha1=hashlib.sha1(
            b"blob " + str(len(raw)).encode() + b"\0" + raw
        ).hexdigest(),
        lfs_sha256=hashlib.sha256(raw).hexdigest() if lfs else None,
    )


def client(raw):
    """Provide a fake metadata-free public stream with no credentials, proxy or real remote I/O."""

    def open_request(request, timeout):
        """Inspect credential-free fixed request headers before returning the authored artifact bytes."""
        assert (
            "Authorization" not in request.headers
            and "Cookie" not in request.headers
            and timeout == 30
        )
        return Response(raw)

    return SimpleNamespace(open=open_request)


@pytest.mark.parametrize("lfs", [True, False])
def test_complete_pinned_artifact_is_private_verified_and_never_replaced(tmp_path, lfs):
    """Publish complete bytes once and verify repeated access instead of redownloading or overwriting an existing model."""
    raw = b"authored model fixture"
    spec = specification(raw, lfs=lfs)
    result = fetch("https://huggingface.co/public", tmp_path, spec, client=client(raw))
    destination = tmp_path / "model.bin"
    assert (
        destination.read_bytes() == raw and destination.stat().st_mode & 0o777 == 0o600
    )
    assert (
        result["status"] == "DOWNLOADED_VERIFIED"
        and not (tmp_path / "model.bin.partial").exists()
    )
    assert (
        fetch("https://huggingface.co/public", tmp_path, spec, client=client(b"wrong"))[
            "status"
        ]
        == "EXISTING_VERIFIED"
    )
    assert destination.read_bytes() == raw


@pytest.mark.parametrize(
    "raw", [b"wrong bytes", b"", b"authored model fixture plus extra"]
)
def test_truncated_extended_or_changed_download_never_becomes_published_model(
    tmp_path, raw
):
    """Retain an incomplete owned partial for diagnosis while refusing a wrong-size/hash public model artifact."""
    spec = specification(b"authored model fixture")
    with pytest.raises(AssetError):
        fetch("https://huggingface.co/public", tmp_path, spec, client=client(raw))
    assert (
        not (tmp_path / "model.bin").exists()
        and (tmp_path / "model.bin.partial").exists()
    )


def test_existing_foreign_artifact_is_not_overwritten_or_adopted(tmp_path):
    """Protect all preexisting bytes even when they use the planned candidate's filename."""
    path = tmp_path / "model.bin"
    path.write_bytes(b"old user bytes")
    with pytest.raises(AssetError):
        fetch(
            "https://huggingface.co/public",
            tmp_path,
            specification(b"new model bytes"),
            client=client(b"new model bytes"),
        )
    assert path.read_bytes() == b"old user bytes"


@pytest.mark.parametrize("kind", ["destination", "partial", "directory"])
def test_symlink_locations_are_not_followed_into_existing_data(tmp_path, kind):
    """Refuse symlink destinations/partials/evaluation leaf directories without modifying their external targets."""
    outside = tmp_path / "outside"
    outside.mkdir()
    foreign = outside / "model.bin"
    foreign.write_bytes(b"old user bytes")
    directory = tmp_path / "owned"
    directory.mkdir()
    if kind == "directory":
        directory.rmdir()
        directory.symlink_to(outside, target_is_directory=True)
    else:
        (
            directory / ("model.bin" if kind == "destination" else "model.bin.partial")
        ).symlink_to(foreign)
    with pytest.raises(AssetError):
        fetch(
            "https://huggingface.co/public",
            directory,
            specification(b"new bytes"),
            client=client(b"new bytes"),
        )
    assert foreign.read_bytes() == b"old user bytes"


@pytest.mark.parametrize(
    "name,size,digest",
    [
        ("../model.bin", 1, "a" * 64),
        ("/model.bin", 1, "a" * 64),
        ("model.bin", True, "a" * 64),
        ("model.bin", 0, "a" * 64),
        ("model.bin", 2 * 1024**3 + 1, "a" * 64),
        ("model.bin", 1, "invalid"),
    ],
)
def test_invalid_artifact_paths_sizes_and_hashes_refuse_before_io(name, size, digest):
    """Reject traversal, coerced/unbounded sizes and missing content identity before creating any cache file."""
    with pytest.raises(AssetError):
        validate_spec(dict(filename=name, bytes=size, lfs_sha256=digest))


@pytest.mark.parametrize(
    "url",
    [
        "http://huggingface.co/public",
        "https://user:secret@huggingface.co/public",
        "https://127.0.0.1/private",
        "file:///private",
        "https://huggingface.co.attacker.invalid/model",
        "https://huggingface.co:8080/model",
    ],
)
def test_public_endpoint_guard_refuses_private_plaintext_credentialed_or_foreign_locations(
    url,
):
    """Keep artifact fetch redirects inside the fixed credential-free public HTTPS provider boundary."""
    assert not allowed_url(url)


def test_pinned_source_constructor_never_accepts_unplanned_models_or_unpinned_revision():
    """Require original registry repositories and exact source commits instead of silently substituting a model or mutable main branch."""
    assert source_url("Qwen/Qwen3-ASR-0.6B", "a" * 40, "model.safetensors").startswith(
        "https://huggingface.co/Qwen/Qwen3-ASR-0.6B/resolve/"
    )
    for repository, revision, path in [
        ("other/model", "a" * 40, "model.bin"),
        ("Qwen/Qwen3-ASR-0.6B", "main", "model.bin"),
        ("Qwen/Qwen3-ASR-0.6B", "a" * 40, "../private"),
    ]:
        with pytest.raises(AssetError):
            source_url(repository, revision, path)


def test_symlinked_intermediate_directory_cannot_create_files_outside_owned_cache(
    tmp_path,
):
    """Reject a symlinked parent before mkdir follows it into unrelated existing data."""
    outside = tmp_path / "outside"
    outside.mkdir()
    owned = tmp_path / "owned"
    owned.mkdir()
    (owned / "link").symlink_to(outside, target_is_directory=True)
    with pytest.raises(AssetError, match="artifact_path_invalid"):
        fetch(
            "https://huggingface.co/public",
            owned / "link" / "new",
            specification(b"new bytes"),
            client=client(b"new bytes"),
        )
    assert not (outside / "new").exists()
