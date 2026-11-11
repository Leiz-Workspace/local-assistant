"""Download and verify the exact pinned llama.cpp UI assets into private local desktop resources."""

import hashlib
import json
import logging
import shutil
import tarfile
import tempfile
from pathlib import Path, PurePosixPath

import httpx

LOGGER = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parents[2]
PIN = "5c8854fd88319125125dc4b836c98b1b215b0f23"
VERSION = "b11557"
ASSETS = ROOT / "data/ui" / VERSION
LLAMA_CPP_LICENSE = ROOT / "runtimes/llama.cpp/LICENSE"
BASE = f"https://huggingface.co/buckets/ggml-org/llama-ui/resolve/{VERSION}"


def asset_status(root=ASSETS):
    """Report local availability without downloading, executing or claiming runtime qualification."""
    return {
        "available": (root / "index.html").is_file()
        and (root / "receipt.json").is_file(),
        "version": VERSION,
        "source_pin": PIN,
        "path": str(root),
    }


def unpack_archive(archive, destination):
    """Extract bounded regular UI files while rejecting traversal, links, duplicates and archive bombs."""
    total, names, hashes = 0, set(), {}
    with tarfile.open(archive, mode="r:gz") as package:
        for member in package:
            if member.isdir() and member.name in {".", "./", "dist", "dist/"}:
                continue
            parts = PurePosixPath(member.name).parts
            if (
                not parts
                or member.name.startswith("/")
                or any(part in {"..", "."} for part in parts)
                or "\\" in member.name
            ):
                raise ValueError("unsafe_archive_path")
            if parts[0] in {"dist", "."}:
                parts = parts[1:]
            if not parts:
                continue
            if member.isdir():
                continue
            total += member.size
            name = "/".join(parts)
            if (
                not member.isfile()
                or name in names
                or name in {"receipt.json", "LLAMA_CPP_LICENSE"}
                or member.size > 33554432
                or total > 134217728
                or len(names) >= 4096
            ):
                raise ValueError("unsafe_archive_member")
            names.add(name)
            source = package.extractfile(member)
            if source is None:
                raise ValueError("missing_archive_member")
            target = destination.joinpath(*parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            with source, target.open("xb") as output:
                shutil.copyfileobj(source, output, length=65536)
            hashes[name] = hashlib.sha256(target.read_bytes()).hexdigest()
    if "index.html" not in hashes:
        raise ValueError("ui_index_missing")
    LOGGER.info("ui_archive_extracted files=%d bytes=%d", len(names), total)
    return hashes


def prepare_assets(*, destination=ASSETS, transport=None):
    """Prepare only the pinned UI archive, retaining checksum and per-file provenance without latest fallback."""
    if (ROOT / "configs/llama-cpp-commit.txt").read_text().strip() != PIN:
        raise ValueError("runtime_pin_changed")
    destination = Path(destination)
    if destination.exists():
        if asset_status(destination)["available"]:
            receipt = json.loads((destination / "receipt.json").read_text())
            if receipt.get("source_pin") != PIN:
                raise ValueError("ui_pin_mismatch")
            for name, digest in receipt["files"].items():
                if (
                    hashlib.sha256((destination / name).read_bytes()).hexdigest()
                    != digest
                ):
                    raise ValueError("ui_asset_changed")
            LOGGER.info("ui_assets_already_verified version=%s", VERSION)
            return asset_status(destination)
        raise ValueError("ui_destination_exists")
    destination.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="ui-prepare-", dir=destination.parent
    ) as temporary:
        staging = Path(temporary)
        archive = staging / "ui.tar.gz"
        with httpx.Client(
            transport=transport, timeout=30, follow_redirects=True, trust_env=False
        ) as client:
            response = client.get(BASE + "/dist.tar.gz.sha256?download=true")
            response.raise_for_status()
            if len(response.content) > 256:
                raise ValueError("invalid_checksum")
            checksum = response.text.split()[0]
            if len(checksum) != 64 or any(
                c not in "0123456789abcdef" for c in checksum
            ):
                raise ValueError("invalid_checksum")
            total = 0
            with (
                archive.open("xb") as output,
                client.stream("GET", BASE + "/dist.tar.gz?download=true") as download,
            ):
                download.raise_for_status()
                for chunk in download.iter_bytes(65536):
                    total += len(chunk)
                    if total > 67108864:
                        raise ValueError("ui_download_limit")
                    output.write(chunk)
        if hashlib.sha256(archive.read_bytes()).hexdigest() != checksum:
            raise ValueError("ui_checksum_mismatch")
        unpacked = staging / "assets"
        unpacked.mkdir()
        hashes = unpack_archive(archive, unpacked)
        shutil.copyfile(LLAMA_CPP_LICENSE, unpacked / "LLAMA_CPP_LICENSE")
        receipt = dict(
            schema_version=1,
            version=VERSION,
            source_pin=PIN,
            archive_sha256=checksum,
            files=hashes,
        )
        (unpacked / "receipt.json").write_text(json.dumps(receipt, indent=2))
        unpacked.rename(destination)
    LOGGER.info("ui_assets_prepared version=%s sha256=%s", VERSION, checksum)
    return {
        **asset_status(destination),
        "archive_sha256": checksum,
        "files": len(hashes),
    }
