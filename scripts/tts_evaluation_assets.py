"""Provision only pinned nominated TTS checkpoints and curate an unchanged official Piper runtime excluding unused neural helper assets."""

import argparse
import hashlib
import json
import logging
import os
import stat
import zipfile
from pathlib import Path, PurePosixPath

from scripts.asr_evaluation_assets import fetch, verify_file
from scripts.asr_evaluation_corpus import save_bytes

logger = logging.getLogger(__name__)
PROJECT = Path(__file__).resolve().parents[1]
ROOT = (PROJECT / "data/backups/d70-tts-evaluation").resolve()
PIPER_WHEEL_SHA256 = "25b4d3f31ff70c8fa7151908e00aaa5650cbdf16bca8fcf21299f3941b89a7d3"
OMITTED_NEURAL = {"piper/hebrew/nakdimon.onnx", "piper/tashkeel/model.onnx"}
PINS = {
    "qwen3-tts-0.6b": (
        "Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice",
        "85e237c12c027371202489a0ec509ded67b5e4b5",
    ),
    "piper-en": ("rhasspy/piper-voices", "5041a7a49ae5b3a0f30e6837769eb03fdbb231bd"),
    "piper-vi": ("rhasspy/piper-voices", "5041a7a49ae5b3a0f30e6837769eb03fdbb231bd"),
}
QWEN_PATHS = {
    "README.md",
    "config.json",
    "generation_config.json",
    "merges.txt",
    "model.safetensors",
    "preprocessor_config.json",
    "tokenizer_config.json",
    "vocab.json",
    "speech_tokenizer/config.json",
    "speech_tokenizer/configuration.json",
    "speech_tokenizer/model.safetensors",
    "speech_tokenizer/preprocessor_config.json",
}


def candidate_url(candidate, artifact):
    """Reject substituted repositories/revisions/paths before reusing the accepted HTTPS/hash/exclusive-publication downloader."""
    identity = candidate["id"]
    if (
        identity not in PINS
        or (candidate["repository"], candidate["revision"]) != PINS[identity]
    ):
        raise ValueError("tts_candidate_pin")
    path = artifact["path"]
    if identity == "qwen3-tts-0.6b":
        allowed = QWEN_PATHS
    else:
        prefix, voice = (
            ("en/en_US/ljspeech/medium/", "en_US-ljspeech-medium")
            if identity == "piper-en"
            else ("vi/vi_VN/vais1000/medium/", "vi_VN-vais1000-medium")
        )
        allowed = {
            prefix + "MODEL_CARD",
            prefix + voice + ".onnx",
            prefix + voice + ".onnx.json",
        }
    if path not in allowed:
        raise ValueError("tts_artifact_path")
    logger.info(
        "tts_pinned_artifact_authorized candidate=%s artifact=%s",
        identity,
        PurePosixPath(path).name,
    )
    return f"https://huggingface.co/{candidate['repository']}/resolve/{candidate['revision']}/{path}"


def provision(root=ROOT):
    """Fetch exact original checkpoint/voice/codecs and publish a separate immutable receipt, preserving foreign files and first failures."""
    root = Path(root)
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    if root.is_symlink() or root.stat().st_mode & 0o077:
        raise ValueError("tts_private_root_permissions")
    config = json.loads(
        (PROJECT / "configs/tts-evaluation-candidates.json").read_text()
    )
    records = []
    for candidate in config["candidates"]:
        for artifact in candidate["artifacts"]:
            url = candidate_url(candidate, artifact)
            relative = PurePosixPath(artifact["path"])
            spec = {
                key: artifact[key] for key in ["bytes", "git_blob_sha1", "lfs_sha256"]
            } | dict(filename=relative.name)
            directory = (
                root
                / "models"
                / candidate["id"]
                / candidate["revision"]
                / str(relative.parent)
            )
            result = fetch(url, directory, spec)
            records.append(
                dict(
                    candidate=candidate["id"],
                    path=str(relative),
                    expected_spec=spec,
                    **result,
                )
            )
    save_bytes(
        root / "models-provisioned.json",
        (
            json.dumps(
                dict(
                    description="Exact D70 nominated Qwen0.6BCustomVoice with required included codec and frozen Piper English/Vietnamese voices; evaluation-only, no selected/default model.",
                    results=records,
                    selected_model=None,
                ),
                indent=2,
            )
            + "\n"
        ).encode(),
    )
    logger.info(
        "tts_nominated_artifacts_provisioned count=%d selected_models=0", len(records)
    )


def verify_models(root=ROOT):
    """Reverify every full artifact against its original size/hash pins without loading a model or altering an existing file."""
    config = json.loads(
        (PROJECT / "configs/tts-evaluation-candidates.json").read_text()
    )
    for candidate in config["candidates"]:
        for artifact in candidate["artifacts"]:
            candidate_url(candidate, artifact)
            spec = {
                key: artifact[key] for key in ["bytes", "git_blob_sha1", "lfs_sha256"]
            } | dict(filename=PurePosixPath(artifact["path"]).name)
            verify_file(
                root
                / "models"
                / candidate["id"]
                / candidate["revision"]
                / artifact["path"],
                spec,
            )
    logger.info("tts_original_model_artifacts_reverified")


def verify_runtime_snapshot(root=ROOT):
    """Reverify every original isolated SDK/curated source file and link against a pre-prediction manifest, rejecting additions and missing files."""
    root = Path(root)
    snapshot = json.loads((root / "runtime-integrity.json").read_text())
    expected = snapshot["files"]
    actual = {
        str(path.relative_to(root))
        for directory in [root / "venv", root / "runtime-source/piper-curated"]
        for path in directory.rglob("*")
        if path.is_symlink() or path.is_file()
    }
    if actual != set(expected):
        raise ValueError("tts_runtime_inventory")
    for name, record in expected.items():
        path = root / name
        if record["kind"] == "symlink":
            if not path.is_symlink() or os.readlink(path) != record["target"]:
                raise ValueError("tts_runtime_link")
            if record.get("resolved_sha256") is None:
                continue
        elif (
            path.is_symlink()
            or not path.is_file()
            or path.stat().st_size != record["bytes"]
        ):
            raise ValueError("tts_runtime_file_type_size")
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            while block := stream.read(1024 * 1024):
                digest.update(block)
        if digest.hexdigest() != record.get("resolved_sha256", record.get("sha256")):
            raise ValueError("tts_runtime_file_hash")
    logger.info("tts_isolated_runtime_snapshot_verified entries=%d", len(actual))


def curate_piper(wheel, destination, expected_sha256=PIPER_WHEEL_SHA256):
    """Retain exact official inference/native/espeak/license bytes while never extracting the two known unused neural members or installing a complete wheel."""
    wheel, destination = Path(wheel), Path(destination)
    if (
        wheel.is_symlink()
        or not 1 <= wheel.stat().st_size <= 50 * 1024**2
        or hashlib.sha256(wheel.read_bytes()).hexdigest() != expected_sha256
    ):
        raise ValueError("tts_piper_wheel_integrity")
    with zipfile.ZipFile(wheel) as archive:
        entries = archive.infolist()
        if (
            len(entries) > 1000
            or sum(item.file_size for item in entries) > 128 * 1024**2
            or len({item.filename for item in entries}) != len(entries)
        ):
            raise ValueError("tts_piper_archive_bound")
        neural = set()
        for item in entries:
            path = PurePosixPath(item.filename)
            if (
                path.is_absolute()
                or ".." in path.parts
                or "\\" in item.filename
                or stat.S_ISLNK(item.external_attr >> 16)
            ):
                raise ValueError("tts_piper_archive_path")
            if item.filename.endswith((".onnx", ".pt", ".pth", ".safetensors")):
                neural.add(item.filename)
        if neural != OMITTED_NEURAL:
            raise ValueError("tts_unexpected_neural_asset")
        destination.mkdir(mode=0o700, parents=True, exist_ok=False)
        records = []
        for item in entries:
            if item.is_dir() or item.filename in OMITTED_NEURAL:
                continue
            relative = PurePosixPath(item.filename)
            if relative.parts[0] == "piper":
                target = destination / relative
            elif relative.parts[0].endswith(".dist-info"):
                target = destination / "archived-distribution-metadata" / relative
            else:
                continue
            target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            raw = archive.read(item)
            save_bytes(target, raw)
            records.append(
                dict(
                    member=item.filename,
                    path=str(target.relative_to(destination)),
                    bytes=len(raw),
                    sha256=hashlib.sha256(raw).hexdigest(),
                )
            )
    receipt = dict(
        description="Curated unchanged official Piper1.8.0 source/native/espeak runtime; not a complete installed wheel. The inspected archive contains two unused neural helpers; neither is extracted/installed/loaded. Exact original source/license bytes retained; no model logic or phonemizer substitution.",
        official_version="1.8.0",
        official_wheel_sha256=expected_sha256,
        omitted_neural_members=sorted(OMITTED_NEURAL),
        files=records,
        selected_model=None,
    )
    save_bytes(
        destination / "curation.json", (json.dumps(receipt, indent=2) + "\n").encode()
    )
    logger.info(
        "tts_piper_official_source_curated files=%d unused_neural_members_extracted=0",
        len(records),
    )
    return receipt


def main():
    """Provision only frozen candidate artifacts or verify them; SDK source curation is separately invoked on a pinned private archive."""
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify", action="store_true")
    arguments = parser.parse_args()
    verify_models() if arguments.verify else provision()


if __name__ == "__main__":
    main()
