"""Verify exact Aevra logo provenance, terminal identity and nondestructive web branding across authenticated UI routes."""

import hashlib
import io
import json
import logging
from pathlib import Path

import pytest
from PIL import Image

from apps.branding import identity
from apps.branding.build import prepare
from apps.cli import main as cli
from tests import test_product_harness as harness_tests

product_client = harness_tests.product_client
bearer = harness_tests.bearer
pair = harness_tests.pair
LOGGER = logging.getLogger(__name__)


def test_owner_logo_and_icon_manifest_are_exact_and_reproducible(tmp_path):
    """Rebuild from shipped source copies without requiring the owner's untracked asset folder in CI."""
    source = tmp_path / "source"
    source.mkdir()
    svg, png = identity.resource("logo.svg"), identity.resource("logo.png")
    (source / "aevra-dragon-white.svg").write_bytes(svg)
    (source / "aevra-dragon-white-1024.png").write_bytes(png)
    manifest = prepare(source, tmp_path / "assets")
    packaged = json.loads((identity.ROOT / "manifest.json").read_text())
    assert manifest == packaged
    assert (
        manifest["source_files"]["aevra-dragon-white.svg"]
        == hashlib.sha256(svg).hexdigest()
    )
    icon = Image.open(io.BytesIO(identity.resource("icon.png")))
    assert icon.size == (512, 512) and icon.getpixel((0, 0))[3] == 0
    assert icon.getextrema()[3] == (0, 255)
    assert identity.resource("icon.svg") == svg
    favicon = Image.open(io.BytesIO(identity.resource("favicon.ico"))).convert("RGBA")
    assert favicon.getpixel((0, 0))[3] == 0
    with pytest.raises(FileExistsError):
        prepare(source, tmp_path / "assets")
    LOGGER.info("test_aevra_exact_logo_and_icon_provenance_verified")


def test_brand_resource_denies_tampering_and_path_escape(tmp_path, monkeypatch):
    """Refuse changed or unregistered packaged bytes without serving arbitrary local paths."""
    monkeypatch.setattr(identity, "ROOT", tmp_path)
    (tmp_path / "manifest.json").write_text(
        json.dumps(dict(files={"logo.svg": "0" * 64}))
    )
    (tmp_path / "logo.svg").write_bytes(b"changed")
    with pytest.raises(ValueError, match="changed"):
        identity.resource("logo.svg")
    with pytest.raises(ValueError, match="unknown"):
        identity.resource("../secret")


def test_terminal_logo_and_cli_name_need_no_credentials(capsys, tmp_path):
    """Render the supplied dragon in portable ASCII and expose exact logo metadata in JSON mode."""
    logo = identity.terminal_logo()
    assert logo.endswith("Aevra") and all(ord(char) < 128 for char in logo)
    assert len(logo.splitlines()) > 8
    assert cli.main(["--token-file", str(tmp_path / "missing"), "logo"]) == 0
    assert "Aevra" in capsys.readouterr().out
    assert cli.main(["--json", "logo"]) == 0
    assert json.loads(capsys.readouterr().out)["name"] == "Aevra"
    assert cli.parser().prog == "aevra"


def test_brand_index_keeps_upstream_code_and_user_text():
    """Replace only head metadata while retaining source scripts, layout and conversation content byte-for-byte."""
    html = '<html><head><title>llama.cpp</title><link rel="icon" href="old.svg"><link rel="manifest" href="old.webmanifest"><script src="bundle.js"></script></head><body>My llama.cpp conversation</body></html>'
    result = identity.brand_index(html)
    assert "<title>Aevra</title>" in result
    assert "old.svg" not in result and "old.webmanifest" not in result
    assert '<script src="bundle.js"></script>' in result
    assert "<body>My llama.cpp conversation</body>" in result
    assert result.count("/harness-bridge.js") == 1
    with pytest.raises(ValueError, match="head_missing"):
        identity.brand_index("<body>missing head</body>")


def test_web_brand_assets_pairing_and_original_assets_unchanged(product_client):
    """Brand both pairing and chat with the same logo while preserving the upstream signed asset bytes."""
    client, _, settings, assets = product_client
    before = (assets / "index.html").read_bytes()
    assert client.app.title == "Aevra"
    login = client.get("/pair/")
    assert (
        "<title>Aevra</title>" in login.text and "/aevra/brand/logo.svg" in login.text
    )
    logo = client.get("/aevra/brand/logo.svg")
    assert logo.content == identity.resource("logo.svg")
    assert client.get("/aevra/brand/not-registered.svg").status_code == 404
    assert client.get("/aevra/brand.js").status_code == 401
    pair(client, settings)
    response = client.get("/")
    assert response.status_code == 200 and "<title>Aevra</title>" in response.text
    assert "/aevra/brand.js" in response.text
    assert client.get("/favicon-dark.svg").content == identity.resource("icon.svg")
    assert client.get("/favicon.ico").content == identity.resource("favicon.ico")
    assert client.get("/aevra/manifest.webmanifest").json()["name"] == "Aevra"
    assert client.get("/aevra/brand.js").status_code == 200
    assert client.get("/aevra/brand.css").status_code == 200
    assert (assets / "index.html").read_bytes() == before


def test_theme_install_uses_new_immutable_transparent_icon_key(tmp_path):
    """Use the proven transparent PNG through an immutable path distinct from former SVG and cached icon resources."""
    first = identity.install_desktop_icon(tmp_path / "icons")
    path = Path(first["path"])
    assert first["name"].startswith("io.aevra.Desktop-transparent-")
    assert path.read_bytes() == identity.resource("icon.png")
    assert path.suffix == ".png" and path.parent == tmp_path / "icons/512x512/apps"
    assert Image.open(path).convert("RGBA").getpixel((0, 0))[3] == 0
    assert identity.install_desktop_icon(tmp_path / "icons") == first
    path.write_bytes(b"changed")
    with pytest.raises(ValueError, match="desktop_icon_changed"):
        identity.install_desktop_icon(tmp_path / "icons")


def test_theme_install_rejects_linked_targets(tmp_path):
    """Prevent icon installation from overwriting an unrelated file through a link."""
    installed = identity.install_desktop_icon(tmp_path / "icons")
    path = Path(installed["path"])
    path.unlink()
    other = tmp_path / "unrelated"
    other.write_text("Keep this file.")
    path.symlink_to(other)
    with pytest.raises(ValueError, match="unsafe_desktop_icon_target"):
        identity.install_desktop_icon(tmp_path / "icons")
    assert other.read_text() == "Keep this file."


def test_theme_install_rejects_linked_directory_before_writing(tmp_path):
    """Avoid creating icon directories outside the requested tree through an existing linked root."""
    outside = tmp_path / "outside"
    outside.mkdir()
    linked = tmp_path / "icons"
    linked.symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="unsafe_desktop_icon_directory"):
        identity.install_desktop_icon(linked)
    assert list(outside.iterdir()) == []
