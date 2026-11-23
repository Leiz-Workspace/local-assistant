"""Expose consistent Aevra branding, verified resources and a terminal-safe rendering of the supplied dragon logo."""

import hashlib
import json
import logging
from pathlib import Path

from PIL import Image

LOGGER = logging.getLogger(__name__)
NAME = "Aevra"
ROOT = Path(__file__).with_name("assets")
FILES = frozenset({"logo.svg", "logo.png", "icon.svg", "icon.png", "favicon.ico"})


def resource(name):
    """Read only fixed packaged resources whose bytes still match the retained brand manifest."""
    if name not in FILES:
        raise ValueError("unknown_brand_resource")
    manifest = json.loads((ROOT / "manifest.json").read_text())
    path = ROOT / name
    raw = path.read_bytes()
    if path.is_symlink() or hashlib.sha256(raw).hexdigest() != manifest["files"].get(
        name
    ):
        raise ValueError("brand_resource_changed")
    return raw


def metadata():
    """Return the product name and exact shared logo path without displaying terminal control sequences."""
    raw = resource("logo.svg")
    return dict(
        name=NAME, logo=str(ROOT / "logo.svg"), sha256=hashlib.sha256(raw).hexdigest()
    )


def install_desktop_icon(directory=None):
    """Install the transparent PNG proven in Show Apps under an immutable path distinct from former SVG resources."""
    raw = resource("icon.png")
    name = "io.aevra.Desktop-transparent-" + hashlib.sha256(raw).hexdigest()[:16]
    root = (
        Path(directory)
        if directory is not None
        else Path.home() / ".local/share/icons/hicolor"
    )
    folder = root / "512x512/apps"
    if any(path.is_symlink() for path in (folder, *folder.parents)):
        raise ValueError("unsafe_desktop_icon_directory")
    folder.mkdir(parents=True, exist_ok=True)
    if folder.resolve() != folder.absolute():
        raise ValueError("unsafe_desktop_icon_directory")
    target = folder / (name + ".png")
    if target.is_symlink():
        raise ValueError("unsafe_desktop_icon_target")
    if target.exists():
        if target.read_bytes() != raw:
            raise ValueError("desktop_icon_changed")
    else:
        with target.open("xb") as output:
            output.write(raw)
    LOGGER.info("aevra_desktop_theme_icon_installed")
    return dict(name=name, path=str(target.absolute()), theme_root=str(root.absolute()))


def terminal_logo(width=38):
    """Render the actual supplied dragon alpha mask as portable ASCII without emoji or terminal-specific image protocols."""
    import io

    if not 16 <= width <= 80:
        raise ValueError("invalid_terminal_logo_width")
    alpha = Image.open(io.BytesIO(resource("logo.png"))).getchannel("A")
    pixels = alpha.resize((width, width // 2), Image.Resampling.LANCZOS)
    shades = " .:-=+*#%@"
    rows = [
        "".join(
            shades[pixels.getpixel((x, y)) * (len(shades) - 1) // 255]
            for x in range(width)
        ).rstrip()
        for y in range(width // 2)
    ]
    LOGGER.info("aevra_terminal_logo_rendered")
    return "\n".join(rows).strip("\n") + "\nAevra"


def brand_index(html):
    """Overlay Aevra metadata on a verified upstream response while keeping packaged llama.cpp assets immutable."""
    import re

    html = re.sub(r"<title\b[^>]*>.*?</title>", "", html, flags=re.S | re.I)
    html = re.sub(
        r"<link\b(?=[^>]*\brel=[\"\'](?:icon|apple-touch-icon|manifest|apple-touch-startup-image)[\"\'])[^>]*>",
        "",
        html,
        flags=re.I,
    )
    branding = '<title>Aevra</title><meta name="application-name" content="Aevra"><link rel="icon" href="/aevra/brand/icon.svg" type="image/svg+xml"><link rel="apple-touch-icon" href="/aevra/brand/icon.png"><link rel="manifest" href="/aevra/manifest.webmanifest"><link rel="stylesheet" href="/aevra/brand.css"><script src="/harness-bridge.js"></script><script src="/aevra/brand.js" defer></script>'
    result, count = re.subn(
        r"<head\b[^>]*>",
        lambda match: match.group(0) + branding,
        html,
        count=1,
        flags=re.I,
    )
    if count != 1:
        raise ValueError("upstream_ui_head_missing")
    LOGGER.info("aevra_ui_branding_applied")
    return result
