"""Verify a sealed blob in an isolated, credential-free and resource-bounded Linux process."""

import json
import logging
import subprocess
import sys
import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import BinaryIO

from src.application.services.file_storage_policy import (
    DEFAULT_POLICY,
    StoragePolicy,
    StoragePolicyError,
    normalize_filename,
    validate_detected_media,
)
from src.infrastructure.native_input import rewind_native_input

logger = logging.getLogger(__name__)
VERIFIER_WALL_SECONDS = 10
VERIFIER_MEMORY_BYTES = 512 * 1024**2
VERIFIER_CPU_SECONDS = 5
MAX_XML_BYTES = 2 * 1024**2
MAX_IMAGE_PIXELS = 20_000_000
MAX_PDF_PAGES = 1000
PAYLOAD_BOOTSTRAP = '''"""Replace consumed host stdin with the readonly namespace payload before trusted worker execution."""
import os
import sys
descriptor = os.open("/payload", os.O_RDONLY | os.O_CLOEXEC)
os.dup2(descriptor, 0)
os.set_inheritable(0, True)
if descriptor != 0:
    os.close(descriptor)
os.execv(sys.argv[1], sys.argv[1:])
'''


def sandbox_command(arguments: list[str]) -> list[str]:
    """Expose trusted runtime/code and consumed readonly payload mounts without a reopenable writable host stdin capability."""
    root = Path(__file__).resolve().parents[2]
    logger.info("document_sandbox_readonly_payload_prepared")
    return [
        "/usr/bin/bwrap",
        "--unshare-all",
        "--die-with-parent",
        "--new-session",
        "--cap-drop",
        "ALL",
        "--clearenv",
        "--ro-bind",
        "/usr",
        "/usr",
        "--symlink",
        "usr/bin",
        "/bin",
        "--symlink",
        "usr/lib",
        "/lib",
        "--symlink",
        "usr/lib64",
        "/lib64",
        "--ro-bind",
        str(Path(sys.prefix)),
        "/venv",
        "--dir",
        "/app",
        "--ro-bind",
        str(root / "src"),
        "/app/src",
        "--proc",
        "/proc",
        "--dev",
        "/dev",
        "--tmpfs",
        "/tmp",
        "--remount-ro",
        "/tmp",
        "--chdir",
        "/app",
        "--setenv",
        "PATH",
        "/venv/bin:/usr/bin",
        "--setenv",
        "PYTHONPATH",
        "/app",
        "--setenv",
        "LANG",
        "C.UTF-8",
        "--setenv",
        "PYTHONDONTWRITEBYTECODE",
        "1",
        "--ro-bind-data",
        "0",
        "/payload",
        "--remount-ro",
        "/",
        "--",
        "/venv/bin/python",
        "-I",
        "-S",
        "-B",
        "-c",
        PAYLOAD_BOOTSTRAP,
        *arguments,
    ]


def verify_file(
    source: BinaryIO,
    filename: str,
    *,
    policy: StoragePolicy = DEFAULT_POLICY,
    declared_media: str | None = None,
) -> str:
    """Verify a sealed FD through one bounded readonly namespace copy without passing secrets or host paths."""
    name = normalize_filename(filename)
    suffix = name.rsplit(".", 1)[1].lower()
    rewind_native_input(source)
    command = sandbox_command(
        [
            "/venv/bin/python",
            "-m",
            "src.infrastructure.file_verifier_worker",
            suffix,
            json.dumps(asdict(policy), separators=(",", ":")),
        ]
    )
    try:
        with tempfile.TemporaryFile() as verdict:
            result = subprocess.run(
                command,
                stdin=source,
                stdout=verdict,
                stderr=subprocess.DEVNULL,
                timeout=VERIFIER_WALL_SECONDS,
                env={},
                close_fds=True,
                start_new_session=True,
            )
            verdict.seek(0)
            output = verdict.read(4097)
    except subprocess.TimeoutExpired:
        raise StoragePolicyError("verification_timeout", 413) from None
    except OSError:
        raise StoragePolicyError("verification_unavailable", 503) from None
    finally:
        rewind_native_input(source)
    if result.returncode or len(output) > 4096:
        raise StoragePolicyError("verification_unavailable", 503)
    try:
        payload = json.loads(output)
    except (ValueError, UnicodeError):
        raise StoragePolicyError("verification_unavailable", 503) from None
    if not isinstance(payload, dict):
        raise StoragePolicyError("verification_unavailable", 503)
    if (
        set(payload) == {"error"}
        and isinstance(payload["error"], str)
        and payload["error"]
        in {
            "invalid_file_content",
            "archive_limits_exceeded",
            "verification_limits_exceeded",
        }
    ):
        code = payload["error"]
        raise StoragePolicyError(code, 413 if code.endswith("exceeded") else 415)
    if set(payload) != {"media_type"} or not isinstance(payload["media_type"], str):
        raise StoragePolicyError("verification_unavailable", 503)
    validate_detected_media(name, payload["media_type"], declared_media=declared_media)
    logger.info(
        "file_content_verified media_type=%s verification_version=1",
        payload["media_type"],
    )
    return payload["media_type"]
