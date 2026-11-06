"""Provision the explicitly approved original research-only D70 audio evaluator without changing project models or existing runtimes."""

import argparse
import hashlib
import json
import logging
import os
import re
import stat
import urllib.request
from pathlib import Path

from scripts.asr_evaluation_assets import allowed_url, opener
from scripts.asr_evaluation_corpus import save_bytes

logger = logging.getLogger(__name__)
PROJECT = Path(__file__).resolve().parents[1]
ROOT = PROJECT / "data/backups/d70-local-audio-reviewer"
REVISION = "f75b40e3da2003cdd6e1829b1f420ca70797c34e"
REPOSITORY = "Qwen/Qwen2.5-Omni-3B"
SHARDS = {
    "model-00001-of-00003.safetensors": (4994850880, "349972cebff443030e9e96e1e930d7230979c6961cf046fa29fc580e4bcf49a6"),
    "model-00002-of-00003.safetensors": (4999787448, "b29a76dfefb3aa33a5bd0faa19c681d039a44de57223653ea0e933df728c6d8c"),
    "model-00003-of-00003.safetensors": (1978024880, "8f2138170a87ec604b53232491a96d6dcf19e0724aca37e69aace143e508b170"),
}
MODEL_FILES = set(SHARDS) | {
    "LICENSE", "README.md", "added_tokens.json", "chat_template.json", "config.json",
    "generation_config.json", "merges.txt", "model.safetensors.index.json",
    "preprocessor_config.json", "special_tokens_map.json", "tokenizer.json",
    "tokenizer_config.json", "vocab.json",
}


def digest(path):
    """Hash a complete regular file in bounded chunks without mapping original checkpoint shards into memory."""
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        while raw := stream.read(1024**2):
            value.update(raw)
    return value.hexdigest()


def specs():
    """Bind the approved repository and exact original shard identities to retained preapproval metadata, excluding unused pickle speaker assets."""
    metadata = json.loads((PROJECT / "data/backups/d70-audio-reviewer-planning/model-info.json").read_text())
    if metadata.get("sha") != REVISION or metadata.get("id") != REPOSITORY:
        raise ValueError("reviewer_metadata_identity")
    rows = []
    for item in metadata["siblings"]:
        name = item["rfilename"]
        if name not in MODEL_FILES:
            continue
        row = dict(filename=name, bytes=item["size"], git_blob_sha1=item["blobId"], lfs_sha256=item.get("lfs", {}).get("sha256"))
        if name in SHARDS and (row["bytes"], row["lfs_sha256"]) != SHARDS[name]:
            raise ValueError("reviewer_shard_identity")
        rows.append(row)
    if {row["filename"] for row in rows} != MODEL_FILES or len(rows) != len(MODEL_FILES):
        raise ValueError("reviewer_artifact_coverage")
    logger.info("local_audio_reviewer_pins_verified artifacts=%d", len(rows))
    return rows


def validate_spec(spec):
    """Reject traversal, unbounded lengths or incomplete hash identities before creating an owned download file."""
    name, size = spec.get("filename"), spec.get("bytes")
    if type(name) is not str or not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", name) or name in {".", ".."}:
        raise ValueError("reviewer_artifact_name")
    if type(size) is not int or not 0 < size <= 5 * 1024**3:
        raise ValueError("reviewer_artifact_size")
    key = "lfs_sha256" if spec.get("lfs_sha256") is not None else "git_blob_sha1"
    length = 64 if key == "lfs_sha256" else 40
    if type(spec.get(key)) is not str or not re.fullmatch(f"[0-9a-f]{{{length}}}", spec[key]):
        raise ValueError("reviewer_artifact_hash_spec")
    return name, size


def verify(path, spec):
    """Verify full checkpoint/metadata bytes against the original LFS digest or ordinary Git blob without accepting symlinks or special files."""
    _, size = validate_spec(spec)
    if path.is_symlink() or not path.is_file() or path.stat().st_size != size:
        raise ValueError("reviewer_artifact_type_size")
    sha = digest(path)
    if spec.get("lfs_sha256") is not None:
        matched = sha == spec["lfs_sha256"]
    else:
        blob = hashlib.sha1(b"blob " + str(size).encode() + b"\0")
        with path.open("rb") as stream:
            while raw := stream.read(1024**2):
                blob.update(raw)
        matched = blob.hexdigest() == spec["git_blob_sha1"]
    if not matched:
        raise ValueError("reviewer_artifact_hash")
    return sha


def download(url, directory, spec, client=None):
    """Publish one verified original artifact exclusively, retaining partial failures and refusing redirects outside the existing public HTTPS allowlist."""
    name, size = validate_spec(spec)
    if not allowed_url(url) or any(p.is_symlink() for p in [directory, *directory.absolute().parents]):
        raise ValueError("reviewer_artifact_authority")
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    path, partial = directory / name, directory / (name + ".partial")
    if path.exists() or path.is_symlink():
        return verify(path, spec)
    descriptor = os.open(partial, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    logger.info("local_audio_reviewer_download_started artifact=%s bytes=%d", name, size)
    received = 0
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "local-assistant-research-evaluator/1", "Accept-Encoding": "identity", "Cache-Control": "no-cache"})
        with os.fdopen(descriptor, "wb") as output:
            with (client or opener()).open(request, timeout=30) as response:
                if response.status != 200 or not allowed_url(response.geturl()):
                    raise ValueError("reviewer_artifact_response")
                while raw := response.read(min(1024**2, size - received + 1)):
                    received += len(raw)
                    if received > size:
                        raise ValueError("reviewer_artifact_overflow")
                    output.write(raw)
                    if received // (256 * 1024**2) != (received - len(raw)) // (256 * 1024**2):
                        logger.info("local_audio_reviewer_download_progress artifact=%s received_bytes=%d", name, received)
            output.flush()
            os.fsync(output.fileno())
        sha = verify(partial, spec)
        os.link(partial, path, follow_symlinks=False)
        partial.unlink()
    except Exception:
        logger.error("local_audio_reviewer_download_failed artifact=%s received_bytes=%d", name, received)
        raise ValueError("reviewer_download_failed_partial_retained") from None
    logger.info("local_audio_reviewer_download_verified artifact=%s bytes=%d", name, size)
    return sha


def provision():
    """Download only owner-approved evaluation artifacts and retain an exclusive source/hash/license receipt; never load or select a model."""
    ROOT.mkdir(mode=0o700, exist_ok=True)
    if ROOT.is_symlink() or not stat.S_ISDIR(ROOT.stat().st_mode) or ROOT.stat().st_mode & 0o077:
        raise ValueError("reviewer_private_root")
    artifacts = specs()
    save_bytes(ROOT / "plan.json", (json.dumps(dict(description="Owner approved ADR-098 isolated research evaluator; original shards include unused output components, not a production replacement.", repository=REPOSITORY, revision=REVISION, artifacts=artifacts), indent=2) + "\n").encode())
    records = []
    for spec in artifacts:
        sha = download(f"https://huggingface.co/{REPOSITORY}/resolve/{REVISION}/{spec['filename']}?download=true", ROOT / "model", spec)
        records.append(dict(**spec, sha256=sha))
    save_bytes(ROOT / "provisioned.json", (json.dumps(dict(description="Pinned original research-only evaluator artifacts; no model-role selection/deployment or loading result.", repository=REPOSITORY, revision=REVISION, artifacts=records, owner_approved=True), indent=2) + "\n").encode())
    logger.info("local_audio_reviewer_provisioned artifacts=%d selected_models=0", len(records))


def main():
    """Provision the exact approved evaluator with no alternate model, revision or output-root overrides."""
    logging.basicConfig(level=logging.INFO)
    argparse.ArgumentParser(description=__doc__).parse_args()
    provision()


if __name__ == "__main__":
    main()
