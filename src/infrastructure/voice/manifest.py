"""Validate operator-pinned existing voice artifacts without discovery, downloads or model selection."""

import fcntl
import hashlib
import json
import logging
import os
import stat
from pathlib import Path

LOGGER = logging.getLogger(__name__)
PATHS = {
    "tts_venv",
    "tts_sources",
    "tts_model",
    "tts_cache",
    "asr_venv",
    "asr_sources",
    "asr_model",
    "cuda_venv",
    "vad_venv",
    "vad_official",
}
PINS = {
    "ASR": "5eb144179a02acc5e5ba31e748d22b0cf3e303b0",
    "TTS": "61b85e3d937fbbacb387714180e8182823512523",
    "TTS_SDK": "04044e1b8f822f946bafb2c88b716459f4164152",
    "codec": "ceff0d0749bfb3fa2d61149794ec6feef0d1e1ae",
    "VAD": "5cd2ba54db059f961e7545d4f211b44f005a6dfb",
    "CORE_GGUF": "073a9275e65d9c8cd2819cf5f77b99fbaa6e87ba591da6bbaa86ec073a64bfef",
}
PROJECT = Path(__file__).resolve().parents[3]


def file_sha(path):
    """Hash one existing regular artifact incrementally without materializing neural weights."""
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        while chunk := stream.read(8 * 1024**2):
            value.update(chunk)
    return value.hexdigest()


class VoiceManifest:
    """Hold one private evaluation-only manifest and a lifetime single-worker file lock."""

    def __init__(self, path, descriptor, raw, value):
        """Bind exact manifest bytes and explicit paths, never infer or search for alternative assets."""
        self.path, self.descriptor, self.raw, self.value = path, descriptor, raw, value
        self.sha256 = hashlib.sha256(raw).hexdigest()
        self.paths = {k: Path(v) for k, v in value["paths"].items()}

    @classmethod
    def load(cls, path):
        """Load a private bounded manifest and reject unapproved scope or multi-worker reuse."""
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            info = os.fstat(descriptor)
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_uid != os.geteuid()
                or info.st_mode & 0o077
                or info.st_size > 16 * 1024**2
            ):
                raise ValueError("voice_manifest_permissions")
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            raw = os.read(descriptor, 16 * 1024**2 + 1)
            value = json.loads(raw)
            if (
                type(value) is not dict
                or value.get("purpose") != "integration_evaluation"
                or value.get("pins") != PINS
                or value.get("production_activation") is not False
                or type(value.get("paths")) is not dict
                or set(value["paths"]) != PATHS
                or any(
                    type(p) is not str or not Path(p).is_absolute()
                    for p in value["paths"].values()
                )
                or not value.get("inventory")
                or not value.get("source_sha256")
                or set(value.get("reading_binding", {}))
                != {"speaker_sha256", "reference_codes_sha256"}
            ):
                raise ValueError("voice_manifest_scope")
            LOGGER.info("voice_manifest_loaded activation=False")
            return cls(Path(path), descriptor, raw, value)
        except BaseException:
            os.close(descriptor)
            raise

    def verify(self):
        """Verify exact source and complete declared existing artifact trees before native imports or loads."""
        if self.path.read_bytes() != self.raw:
            raise ValueError("voice_manifest_changed")
        for name, expected in self.value["source_sha256"].items():
            relative = Path(name)
            if (
                relative.is_absolute()
                or ".." in relative.parts
                or file_sha(PROJECT / relative) != expected
            ):
                raise ValueError("voice_source_changed")
        verified = set()
        for directory, entries in self.value["inventory"].items():
            base = Path(directory)
            if not base.is_absolute() or not base.is_dir() or type(entries) is not dict:
                raise ValueError("voice_inventory_root")
            actual = set()
            for path in base.rglob("*"):
                if path.is_file() or path.is_symlink():
                    actual.add(str(path.relative_to(base)))
            if actual != set(entries):
                raise ValueError("voice_inventory_set_changed")
            for name, info in entries.items():
                path = base / name
                if ".." in Path(name).parts or Path(name).is_absolute():
                    raise ValueError("voice_inventory_path")
                if "target" in info:
                    if not path.is_symlink() or os.readlink(path) != info["target"]:
                        raise ValueError("voice_inventory_link")
                elif (
                    path.is_symlink()
                    or path.stat().st_size != info["bytes"]
                    or file_sha(path) != info["sha256"]
                ):
                    raise ValueError("voice_artifact_changed")
            verified.add(base.resolve())
        for path in self.paths.values():
            if not path.is_dir() or not any(
                path.resolve().is_relative_to(base) for base in verified
            ):
                raise ValueError("voice_unverified_runtime_path")
        core = self.value["core"]
        if file_sha(core["model_path"]) != PINS["CORE_GGUF"]:
            raise ValueError("voice_core_artifact_changed")
        LOGGER.info("voice_artifact_manifest_verified roots=%d", len(verified))

    def close(self):
        """Release only this manifest's process lock after application-owned work has joined."""
        if self.descriptor is not None:
            os.close(self.descriptor)
            self.descriptor = None
            LOGGER.info("voice_manifest_closed")
