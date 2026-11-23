"""Prepare exact owner-supplied Aevra logos and deterministic desktop/favicon derivatives without changing the originals."""

import hashlib
import io
import json
import logging
import shutil
from pathlib import Path

from defusedxml import ElementTree
from PIL import Image

LOGGER = logging.getLogger(__name__)


def prepare(source, destination):
    """Publish transparent logo/icon resources with source hashes and no added border or background."""
    source, destination = Path(source), Path(destination)
    svg = (source / "aevra-dragon-white.svg").read_bytes()
    png = (source / "aevra-dragon-white-1024.png").read_bytes()
    tree = ElementTree.fromstring(svg)
    if tree.tag != "{http://www.w3.org/2000/svg}svg" or any(
        node.tag
        not in {"{http://www.w3.org/2000/svg}svg", "{http://www.w3.org/2000/svg}path"}
        or any(
            key.lower().startswith("on") or "href" in key.lower() for key in node.attrib
        )
        for node in tree.iter()
    ):
        raise ValueError("unsupported_brand_svg")
    original = Image.open(io.BytesIO(png)).convert("RGBA")
    if original.size != (1024, 1024):
        raise ValueError("unexpected_brand_dimensions")
    destination.mkdir(mode=0o755, parents=True, exist_ok=False)
    try:
        (destination / "logo.svg").write_bytes(svg)
        (destination / "logo.png").write_bytes(png)
        icon = original.copy()
        icon.resize((512, 512), Image.Resampling.LANCZOS).save(destination / "icon.png")
        icon.save(
            destination / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48), (64, 64)]
        )
        (destination / "icon.svg").write_bytes(svg)
        files = {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(destination.iterdir())
        }
        manifest = dict(
            schema_version=1,
            product="Aevra",
            source_files={
                "aevra-dragon-white.svg": hashlib.sha256(svg).hexdigest(),
                "aevra-dragon-white-1024.png": hashlib.sha256(png).hexdigest(),
            },
            files=files,
            derivatives="Transparent white dragon icons without added borders or backgrounds; source logo bytes unchanged.",
        )
        (destination / "manifest.json").write_text(json.dumps(manifest, indent=2))
    except Exception:
        shutil.rmtree(destination)
        raise
    LOGGER.info("aevra_brand_prepared files=%d", len(files))
    return manifest
