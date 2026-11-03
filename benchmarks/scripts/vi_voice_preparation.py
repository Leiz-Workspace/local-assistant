"""Prepare the owner-approved ADR-154 assets and isolated CPU SDK without model execution."""

import argparse
import hashlib
import json
import logging
import os
import re
import shutil
import signal
import subprocess
import time
import urllib.request
from pathlib import Path

LOGGER = logging.getLogger(__name__)
PROJECT = Path(__file__).resolve().parents[2]
ROOT = PROJECT / "data/backups/d74-vi-approved-campaign-20261103"
MANIFEST = PROJECT / "docs/evidence/d74-vi-turbo-proposed-artifacts-20261103.json"
MANIFEST_SHA = "c85f751b1d986a97eb4d3f0ad6898764fdac3b0454ef2375084892f2d481f36f"
PACKET = PROJECT / "docs/evidence/d74-vi-voice-proposed-packet-20261103.json"
PACKET_SHA = "e6f771c3e12882e04f21096a4d5df202b0ce0d8c676bcd592bad3ece9bcf869a"
REVISION = "04044e1b8f822f946bafb2c88b716459f4164152"
BUDGET = 8 * 1024**3
SOURCES = (
    "LICENSE",
    "pyproject.toml",
    "src/vieneu/__init__.py",
    "src/vieneu/factory.py",
    "src/vieneu/base.py",
    "src/vieneu/v3turbo.py",
    "src/vieneu/_v3_turbo_engine/__init__.py",
    "src/vieneu/_v3_turbo_engine/onnx_runtime_lite.py",
    "src/vieneu/_v3_turbo_engine/onnx_denoiser.py",
    "src/vieneu/_v3_turbo_engine/rep_history.py",
    "src/vieneu_utils/__init__.py",
    "src/vieneu_utils/core_utils.py",
    "src/vieneu_utils/phonemize_text.py",
)
REQUIREMENTS = """sea-g2p==0.9.1
onnxruntime>=1.20.0
numpy
soundfile
soxr
kaldi-native-fbank>=1.20
tokenizers>=0.20
huggingface_hub
PyYAML
"""
ORT_FIXTURES = {
    "mul_1.onnx": "71f431c4e9321ec6fbeb158d02ed240459a7dcc98673fa79a4f439ce42efaf10",
    "logreg_iris.onnx": "8224784c98d73412d9fd99abcd57a38568bd590980d0fbe5916464531c52e8fc",
    "sigmoid.onnx": "5340aba67a7e3475162ad794378af55f1718f55f9a5d74b4af60ecc7f7a624b6",
}
SDK_DATA_FILES = {
    "_virtualenv.pth": "69ac3d8f27e679c81b94ab30b3b56e9cd138219b1ba94a1fa3606d5a76a1433d",
    "sea_g2p/sea_g2p.bin": "4346e690d0711ebc5231e7a42c5c88aaf6e40377e894b4617c018fd81c6f4096",
    "numpy/lib/tests/data/py2-objarr.npz": "c68d771c14f415b159daabd9cf42d61836f74ae40049269787baca7d57098f1e",
    "numpy/lib/tests/data/py3-objarr.npz": "bd5465f7f359effabe86376e52bf185a7cd1cbc1123659af30f95a4920baf5f9",
}
NEURAL_SUFFIXES = {
    ".onnx",
    ".safetensors",
    ".pt",
    ".pth",
    ".ckpt",
    ".gguf",
    ".tflite",
    ".h5",
    ".npz",
}


def digest(path):
    """Hash a regular file incrementally without retaining its payload in memory."""
    result = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024**2), b""):
            result.update(chunk)
    return result.hexdigest()


def publish(path, value):
    """Publish an exclusive, private JSON receipt without replacing prior evidence."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    LOGGER.info("receipt_published name=%s", path.name)


def budget(root, limit=BUDGET):
    """Reject links escaping the owned root and enforce the complete logical disk budget."""
    root = Path(root).resolve()
    total = 0
    for path in root.rglob("*"):
        if path.is_symlink():
            target = path.resolve()
            if not target.is_relative_to(root) and target != Path(
                "/usr/bin/python3.12"
            ):
                raise ValueError("preparation_external_link")
        elif path.is_file():
            total += path.stat().st_size
            if total > limit:
                raise ValueError("preparation_disk_budget")
    return total


def verify_artifact(path, entry):
    """Check exact payload size and its approved LFS content or Git blob identity."""
    path = Path(path)
    if path.is_symlink() or path.stat().st_size != entry["bytes"]:
        raise ValueError("artifact_size_or_link")
    if entry.get("lfs_sha256"):
        actual, expected = digest(path), entry["lfs_sha256"]
    else:
        raw = path.read_bytes()
        actual = hashlib.sha1(f"blob {len(raw)}\0".encode() + raw).hexdigest()
        expected = entry["git_blob_sha1"]
    if actual != expected:
        raise ValueError("artifact_identity")
    LOGGER.info("artifact_verified file=%s bytes=%d", path.name, entry["bytes"])


def fetch(url, path, entry, root):
    """Download exactly one pinned public artifact without retries and retain failed partial bytes."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    partial = path.with_name(path.name + ".partial")
    descriptor = os.open(partial, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    started, count = time.monotonic(), 0
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with (
        os.fdopen(descriptor, "wb") as output,
        opener.open(url, timeout=60) as response,
    ):
        while chunk := response.read(1024**2):
            count += len(chunk)
            if count > entry["bytes"] or time.monotonic() - started > 600:
                raise ValueError("download_size_or_wall")
            output.write(chunk)
            budget(root)
    verify_artifact(partial, entry)
    if path.exists():
        raise FileExistsError(path)
    partial.rename(path)
    return dict(
        path=str(path.relative_to(root)), bytes=count, sha256=digest(path), url=url
    )


def environment(root):
    """Return a credential-free uv environment with all mutable SDK files inside the owned root."""
    return dict(
        PATH=f"{Path(shutil.which('uv')).parent}:/usr/bin:/bin",
        HOME=str(root / "home"),
        TMPDIR=str(root / "tmp"),
        UV_CACHE_DIR=str(root / "cache"),
        UV_NO_CONFIG="1",
        UV_PYTHON_DOWNLOADS="never",
        UV_LINK_MODE="copy",
        PYTHONDONTWRITEBYTECODE="1",
        CUDA_VISIBLE_DEVICES="",
        LANG="C.UTF-8",
    )


def terminate(process):
    """Terminate and join only the owned process group, escalating after a bounded grace period."""
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=5)
    LOGGER.info(
        "owned_process_joined pid=%d returncode=%s", process.pid, process.returncode
    )


def step(command, root, label, timeout=600):
    """Run one SDK operation with exclusive logs, a wall deadline and sampled root budget."""
    started = time.monotonic()
    LOGGER.info("preparation_step_started label=%s", label)
    with (root / (label + ".log")).open("xb") as output:
        process = subprocess.Popen(
            command,
            stdout=output,
            stderr=subprocess.STDOUT,
            env=environment(root),
            start_new_session=True,
        )
        try:
            while process.poll() is None:
                budget(root)
                if time.monotonic() - started > timeout:
                    raise TimeoutError("preparation_step_wall")
                time.sleep(0.2)
            if process.returncode:
                raise ValueError("preparation_step_failed_" + label)
            budget(root)
        finally:
            terminate(process)
    LOGGER.info(
        "preparation_step_completed label=%s wall=%.3f",
        label,
        time.monotonic() - started,
    )


def verify_lock(path):
    """Reject unpinned, unhashed, remote or GPU dependencies before installation."""
    packages = {}
    for line in path.read_text().replace("\\\n", " ").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        match = re.fullmatch(
            r"([\w.-]+)==([^\s;]+)\s+((?:--hash=sha256:[a-f0-9]{64}\s*)+)", line.strip()
        )
        if not match or match[1] in packages:
            raise ValueError("sdk_lock_structure")
        packages[match[1]] = match[2]
    if (
        packages.get("sea-g2p") != "0.9.1"
        or not {
            "numpy",
            "onnxruntime",
            "tokenizers",
            "soundfile",
            "soxr",
            "huggingface-hub",
        }
        <= packages.keys()
    ):
        raise ValueError("sdk_required_packages")
    if any(
        name.startswith(("torch", "nvidia", "triton", "tensorflow"))
        for name in packages
    ):
        raise ValueError("sdk_unapproved_backend")
    LOGGER.info("sdk_lock_verified packages=%d", len(packages))
    return packages


def inventory(root):
    """Freeze regular SDK/source bytes and symlink targets for subsequent integrity checks."""
    return {
        str(p.relative_to(root)): dict(target=os.readlink(p))
        if p.is_symlink()
        else dict(bytes=p.stat().st_size, sha256=digest(p))
        for p in sorted(Path(root).rglob("*"))
        if p.is_file() or p.is_symlink()
    }


def audit_sdk(root):
    """Reject undeclared neural artifacts shipped inside CPU dependency packages."""
    found = []
    for path in root.rglob("*"):
        if not path.is_file() or not (
            path.suffix.lower() in NEURAL_SUFFIXES or path.name.endswith(".bin")
        ):
            continue
        relative = str(path.relative_to(root))
        if (
            relative.endswith("/onnxruntime/datasets/" + path.name)
            and path.name in ORT_FIXTURES
            and digest(path) == ORT_FIXTURES[path.name]
        ):
            LOGGER.info("sdk_non_neural_math_fixture_verified file=%s", path.name)
            continue
        matches = [
            name
            for name in SDK_DATA_FILES
            if relative == "lib/python3.12/site-packages/" + name
        ]
        if matches and digest(path) == SDK_DATA_FILES[matches[0]]:
            LOGGER.info("sdk_non_neural_data_verified file=%s", matches[0])
            continue
        found.append(relative)
    if found:
        raise ValueError(
            "sdk_contains_undeclared_neural_payload:" + ",".join(found[:10])
        )
    LOGGER.info("sdk_neural_payload_audit_passed")


def prepare(root=ROOT):
    """Prepare the exact approved payload/source set and a hashed isolated SDK once, without inference."""
    root = Path(root)
    if digest(MANIFEST) != MANIFEST_SHA or digest(PACKET) != PACKET_SHA:
        raise ValueError("approved_input_changed")
    approval = json.loads(
        (PROJECT / "docs/evidence/d74-adr154-owner-approval-20261103.json").read_text()
    )
    if (
        approval["approved"] is not True
        or approval["manifest_sha256"] != MANIFEST_SHA
        or approval["packet_sha256"] != PACKET_SHA
    ):
        raise ValueError("owner_approval_binding")
    root.mkdir(mode=0o700)
    for name in ["home", "tmp", "cache", "sources", "models", "results"]:
        (root / name).mkdir(mode=0o700)
    receipt = dict(
        description="ADR-154 first preparation; no model imports, loads or predictions.",
        downloads=[],
        status="STARTED",
        model_calls=0,
    )
    try:
        tree_path = PROJECT / "data/backups/d74-vi-survey-20261103/upstream-tree.json"
        if (
            digest(tree_path)
            != "9a5eb7a2204635f9b618dda0a8b80b23ad206a6eadd6e80cb3f8671992a9d346"
        ):
            raise ValueError("source_tree_changed")
        tree = json.loads(tree_path.read_text())
        entries = {e["path"]: e for e in tree["tree"] if e["type"] == "blob"}
        for name in SOURCES:
            source = entries[name]
            entry = dict(bytes=source["size"], git_blob_sha1=source["sha"])
            url = f"https://raw.githubusercontent.com/pnnbao97/VieNeu-TTS/{REVISION}/{name}"
            receipt["downloads"].append(
                fetch(url, root / "sources" / name, entry, root)
            )
        uv = shutil.which("uv")
        (root / "requirements.in").write_text(REQUIREMENTS)
        step(
            [
                uv,
                "pip",
                "compile",
                "--python",
                "/usr/bin/python3.12",
                "--only-binary",
                ":all:",
                "--generate-hashes",
                "--no-header",
                "--no-annotate",
                "--output-file",
                str(root / "requirements.lock"),
                str(root / "requirements.in"),
            ],
            root,
            "sdk-resolve",
        )
        receipt["packages"] = verify_lock(root / "requirements.lock")
        receipt["lock_sha256"] = digest(root / "requirements.lock")
        step(
            [
                uv,
                "venv",
                "--python",
                "/usr/bin/python3.12",
                "--no-python-downloads",
                str(root / "venv"),
            ],
            root,
            "sdk-venv",
        )
        step(
            [
                uv,
                "pip",
                "sync",
                "--python",
                str(root / "venv/bin/python"),
                "--require-hashes",
                "--only-binary",
                ":all:",
                "--link-mode",
                "copy",
                str(root / "requirements.lock"),
            ],
            root,
            "sdk-install",
        )
        audit_sdk(root / "venv")
        manifest = json.loads(MANIFEST.read_text())
        for entry in manifest["entries"]:
            if entry["repository"] == "pnnbao97/VieNeu-TTS":
                path = root / "sources" / entry["path"]
                url = f"https://raw.githubusercontent.com/{entry['repository']}/{entry['revision']}/{entry['path']}"
            else:
                cache = (
                    root
                    / "models"
                    / ("models--" + entry["repository"].replace("/", "--"))
                )
                path = cache / "snapshots" / entry["revision"] / entry["path"]
                url = f"https://huggingface.co/{entry['repository']}/resolve/{entry['revision']}/{entry['path']}"
            receipt["downloads"].append(fetch(url, path, entry, root))
        for entry in manifest["entries"]:
            if entry["repository"] != "pnnbao97/VieNeu-TTS":
                ref = (
                    root
                    / "models"
                    / ("models--" + entry["repository"].replace("/", "--"))
                    / "refs/main"
                )
                ref.parent.mkdir(exist_ok=True)
                if not ref.exists():
                    ref.write_text(entry["revision"])
        receipt["status"] = "PREPARED_NOT_EXECUTED"
        receipt["total_root_bytes"] = budget(root)
        publish(
            root / "prepared-inventory.json",
            dict(
                description="Exact isolated prepared SDK/source/model files.",
                files=inventory(root),
            ),
        )
    except BaseException as error:
        receipt["status"], receipt["error"] = (
            "FAILED_STOPPED",
            type(error).__name__ + ":" + str(error),
        )
        LOGGER.exception("approved_preparation_stopped")
        raise
    finally:
        publish(root / "preparation-receipt.json", receipt)
    return receipt


def complete_reviewed_sdk_audit(root=ROOT):
    """Complete a corrected pre-execution audit without repeating source downloads, resolution or installation."""
    root = Path(root)
    prior = json.loads((root / "preparation-receipt.json").read_text())
    if (
        prior["status"] != "FAILED_STOPPED"
        or prior["model_calls"] != 0
        or len(prior["downloads"]) != len(SOURCES)
    ):
        raise ValueError("audit_completion_prior_scope")
    if not prior["error"].startswith(
        "ValueError:sdk_contains_undeclared_neural_payload:"
    ):
        raise ValueError("audit_completion_wrong_failure")
    if (
        any((root / "models").iterdir())
        or (root / "audit-completion-attempt.json").exists()
    ):
        raise ValueError("audit_completion_already_attempted")
    if digest(MANIFEST) != MANIFEST_SHA or digest(PACKET) != PACKET_SHA:
        raise ValueError("approved_input_changed")
    publish(
        root / "audit-completion-attempt.json",
        dict(
            description="One completion of a corrected non-neural data classification before execution; no repeated install/download/model operation.",
            prior_sha256=digest(root / "preparation-receipt.json"),
        ),
    )
    receipt = dict(
        description="SDK audit correction: exact phoneme dictionary, uv loader and NumPy object-array test fixtures are not neural weights. No inference retry; original failed audit retained.",
        prior_sha256=digest(root / "preparation-receipt.json"),
        downloads=[],
        model_calls=0,
        status="STARTED",
    )
    try:
        if digest(root / "requirements.lock") != prior["lock_sha256"]:
            raise ValueError("installed_lock_changed")
        verify_lock(root / "requirements.lock")
        for item in prior["downloads"]:
            if digest(root / item["path"]) != item["sha256"]:
                raise ValueError("prepared_source_changed")
        audit_sdk(root / "venv")
        for item in json.loads(MANIFEST.read_text())["entries"]:
            if item["repository"] == "pnnbao97/VieNeu-TTS":
                path = root / "sources" / item["path"]
                url = f"https://raw.githubusercontent.com/{item['repository']}/{item['revision']}/{item['path']}"
            else:
                cache = (
                    root
                    / "models"
                    / ("models--" + item["repository"].replace("/", "--"))
                )
                path = cache / "snapshots" / item["revision"] / item["path"]
                url = f"https://huggingface.co/{item['repository']}/resolve/{item['revision']}/{item['path']}"
            receipt["downloads"].append(fetch(url, path, item, root))
        for item in json.loads(MANIFEST.read_text())["entries"]:
            if item["repository"] != "pnnbao97/VieNeu-TTS":
                ref = (
                    root
                    / "models"
                    / ("models--" + item["repository"].replace("/", "--"))
                    / "refs/main"
                )
                ref.parent.mkdir(exist_ok=True)
                if not ref.exists():
                    ref.write_text(item["revision"])
        receipt["status"] = "PREPARED_NOT_EXECUTED"
        receipt["total_root_bytes"] = budget(root)
        publish(
            root / "prepared-inventory.json",
            dict(
                description="Prepared SDK/source/models after exact non-neural file classification; no imports or inference.",
                files=inventory(root),
            ),
        )
    except BaseException as error:
        receipt["status"], receipt["error"] = (
            "FAILED_STOPPED",
            type(error).__name__ + ":" + str(error),
        )
        LOGGER.exception("audit_completion_stopped")
        raise
    finally:
        publish(root / "audit-completion-receipt.json", receipt)
    return receipt


def main():
    """Expose the single approved preparation action with auditable lifecycle logs."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--complete-reviewed-sdk-audit", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    os.umask(0o077)
    if args.complete_reviewed_sdk_audit:
        complete_reviewed_sdk_audit()
    else:
        prepare()


if __name__ == "__main__":
    main()
