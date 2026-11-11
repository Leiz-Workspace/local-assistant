"""Verify pinned UI provisioning with synthetic archives and no external downloads."""

import hashlib
import io
import json
import logging
import tarfile

import httpx
import pytest

from apps.harness import assets as assets_module
from apps.harness.assets import prepare_assets, unpack_archive

LOGGER = logging.getLogger(__name__)


def archive_bytes(name="index.html", *, link=False):
    """Create a tiny archive that can represent either a valid file or an unsafe member."""
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w:gz") as package:
        directory = tarfile.TarInfo(".")
        directory.type = tarfile.DIRTYPE
        package.addfile(directory)
        info = tarfile.TarInfo(name)
        if link:
            info.type, info.linkname = tarfile.SYMTYPE, "/etc/passwd"
            package.addfile(info)
        else:
            data = b"<html><head></head><body>fixture</body></html>"
            info.size = len(data)
            package.addfile(info, io.BytesIO(data))
    return output.getvalue()


@pytest.mark.parametrize(
    "name,link", [("../escape", False), ("/absolute", False), ("linked", True)]
)
def test_archive_refuses_paths_and_links(tmp_path, name, link):
    """Reject traversal and symlink entries without creating attacker-selected files."""
    archive = tmp_path / "archive.tar.gz"
    archive.write_bytes(archive_bytes(name, link=link))
    with pytest.raises(ValueError):
        unpack_archive(archive, tmp_path / "assets")
    assert not (tmp_path / "escape").exists()


def test_pinned_download_checks_digest_and_records_assets(tmp_path, monkeypatch):
    """Provision only the configured version and verify it again on reuse."""
    # The real license comes from the git-ignored llama.cpp checkout, which hosted runners lack.
    license_file = tmp_path / "LICENSE"
    license_file.write_text("llama.cpp license fixture\n")
    monkeypatch.setattr(assets_module, "LLAMA_CPP_LICENSE", license_file)
    archive = archive_bytes()
    digest = hashlib.sha256(archive).hexdigest()
    seen = []

    def respond(request):
        """Serve a deterministic archive and checksum while rejecting latest fallback."""
        seen.append(str(request.url))
        assert "b11557" in str(request.url) and "latest" not in str(request.url)
        return httpx.Response(
            200, content=digest.encode() if ".sha256" in request.url.path else archive
        )

    destination = tmp_path / "assets"
    receipt = prepare_assets(
        destination=destination, transport=httpx.MockTransport(respond)
    )
    assert receipt["files"] == 1 and len(seen) == 2
    assert (
        json.loads((destination / "receipt.json").read_text())["archive_sha256"]
        == digest
    )
    assert (destination / "LLAMA_CPP_LICENSE").is_file()
    assert prepare_assets(destination=destination)["available"]
    (destination / "index.html").write_text("tampered")
    with pytest.raises(ValueError, match="ui_asset_changed"):
        prepare_assets(destination=destination)
    LOGGER.info("test_pinned_ui_receipt_verified")


def test_bad_checksum_never_publishes_assets(tmp_path):
    """Leave no installed UI tree when archive bytes do not match the retained checksum."""
    archive = archive_bytes()

    def respond(request):
        """Return a mismatched expected checksum for the otherwise valid archive."""
        return httpx.Response(
            200, content=b"0" * 64 if ".sha256" in request.url.path else archive
        )

    with pytest.raises(ValueError, match="ui_checksum_mismatch"):
        prepare_assets(
            destination=tmp_path / "assets", transport=httpx.MockTransport(respond)
        )
    assert not (tmp_path / "assets").exists()
