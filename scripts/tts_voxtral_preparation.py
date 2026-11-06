"""Prepare only the explicitly approved ADR-107 artifacts and CPU SDK, without loading a model or accepting audio."""

import argparse
import hashlib
import json
import logging
import os
import re
import shutil
import signal
import stat
import subprocess
import time
from pathlib import Path

from scripts.asr_evaluation_corpus import save_bytes
from scripts.tts_local_review import publish_json, sandbox
from scripts.tts_local_review_assets import ROOT as OLD_ROOT
from scripts.tts_local_review_assets import digest, download, validate_spec
from scripts.tts_public_audio_review import wall_limit

logger = logging.getLogger(__name__)
PROJECT = Path(__file__).resolve().parents[1]
ROOT = PROJECT / "data/backups/d70-voxtral-local-reviewer"
MANIFEST = PROJECT / "docs/evidence/d70-voxtral-preparation-manifest.json"
MANIFEST_SHA256 = "4be2871c3e88da5cb76b521f3fae6874708a9ee4765fe2856c596f56b377a801"
PREPARATION_ALLOWED = False
DISK_BUDGET = 20 * 1024**3
SDK_BUDGET = 6 * 1024**3
PINS = {"torch": "2.10.0+cpu", "transformers": "4.57.3", "numpy": "2.3.5", "safetensors": "0.8.0", "mistral-common[audio]": "1.8.1"}
PROBE = '''"""Import the pinned CPU SDK without model files, constructors, audio or network access."""
import importlib.metadata
import json
import logging
import os
import sys


def main():
    """Verify package identities and native import compatibility without instantiating any model or processor."""
    logging.basicConfig(level=logging.INFO)
    os.sched_setaffinity(0, {0, 1})
    import torch
    from transformers import VoxtralForConditionalGeneration, VoxtralProcessor
    import mistral_common.audio
    torch.set_num_threads(2)
    torch.set_num_interop_threads(1)
    expected = {"torch": "2.10.0+cpu", "transformers": "4.57.3", "numpy": "2.3.5", "safetensors": "0.8.0", "mistral-common": "1.8.1"}
    versions = {name: importlib.metadata.version(name) for name in expected}
    assert versions == expected and sys.version_info[:3] == (3, 12, 3)
    assert torch.version.cuda is None and not torch.cuda.is_available()
    assert not os.path.exists("/model") and not os.listdir("/samples")
    assert VoxtralForConditionalGeneration and VoxtralProcessor and mistral_common.audio
    logging.info("voxtral_sdk_imports_verified model_loaded=False audio_calls=0")
    print(json.dumps(dict(versions=versions, CPU_only=True, imports_passed=True, model_loaded=False, audio_calls=0)), flush=True)


if __name__ == "__main__":
    main()
'''


def approved_manifest():
    """Bind all artifact and resource decisions to the exact owner-reviewed historical manifest before mutations."""
    if not PREPARATION_ALLOWED:
        raise ValueError("voxtral_preparation_retired")
    raw = MANIFEST.read_bytes()
    if hashlib.sha256(raw).hexdigest() != MANIFEST_SHA256:
        raise ValueError("voxtral_manifest_changed")
    value = json.loads(raw)
    names = set()
    for row in value["files"]:
        name, _ = validate_spec(row)
        expected = f"https://huggingface.co/{value['repository']}/resolve/{value['revision']}/{name}"
        if row["url"] != expected or name in names:
            raise ValueError("voxtral_manifest_authority")
        names.add(name)
    if len(names) != 9 or value["disk_budget_bytes"] != DISK_BUDGET:
        raise ValueError("voxtral_manifest_resources")
    logger.info("voxtral_approved_manifest_verified artifacts=9 inference_approved=False")
    return value


def tree_bytes(root):
    """Count unique local file inodes without following SDK symlinks or double-counting transient publication links."""
    seen, total = set(), 0
    for path in root.rglob("*"):
        try:
            item = path.lstat()
        except FileNotFoundError:
            continue
        key = (item.st_dev, item.st_ino)
        if key not in seen and not stat.S_ISDIR(item.st_mode):
            total += item.st_size
            seen.add(key)
    return total


def check_budget(root, reserve=0, limit=DISK_BUDGET):
    """Refuse work whose measured files and declared maximum addition exceed the approved evaluation-root budget."""
    size = tree_bytes(root)
    if size + reserve > limit:
        logger.error("voxtral_disk_budget_rejected bytes=%d reserve=%d limit=%d", size, reserve, limit)
        raise ValueError("voxtral_disk_budget")
    return size


def environment(root):
    """Provide a public-only uv environment with private caches and no inherited credentials, proxies or package indexes."""
    return dict(PATH=f"{Path(shutil.which('uv')).parent}:/usr/bin:/bin", HOME=str(root / "home"), TMPDIR=str(root / "tmp"), UV_CACHE_DIR=str(root / "cache"), UV_NO_CONFIG="1", UV_PYTHON_DOWNLOADS="never", UV_LINK_MODE="copy", CUDA_VISIBLE_DEVICES="", PYTHONDONTWRITEBYTECODE="1", LANG="C.UTF-8")


def run_step(command, root, label, timeout=1200, limit=SDK_BUDGET):
    """Own a bounded subprocess group and preserve logs while terminating and joining failures or sampled budget breaches."""
    started = time.monotonic()
    logger.info("voxtral_preparation_step_started label=%s", label)
    with (root / (label + ".log")).open("xb") as output:
        process = subprocess.Popen(command, stdout=output, stderr=subprocess.STDOUT, env=environment(root), start_new_session=True)
        try:
            while process.poll() is None:
                check_budget(root, limit=limit)
                if time.monotonic() - started > timeout:
                    raise TimeoutError("voxtral_preparation_step_timeout")
                time.sleep(0.3)
            if process.returncode:
                raise ValueError("voxtral_preparation_step_failed_" + label)
            check_budget(root, limit=limit)
        except BaseException:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
            logger.error("voxtral_preparation_step_failed label=%s", label)
            raise
    logger.info("voxtral_preparation_step_passed label=%s elapsed_seconds=%.3f", label, time.monotonic() - started)


def verify_lock(path):
    """Reject lost pins, missing hashes or CUDA dependencies before installing the resolved CPU-only requirements."""
    text = path.read_text()
    packages = {}
    for line in text.replace("\\\n", " ").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        matched = re.fullmatch(r"([a-zA-Z0-9_.-]+)==([^\s;]+)\s+((?:--hash=sha256:[0-9a-f]{64}\s*)+)", line.strip())
        if not matched or matched[1] in packages:
            raise ValueError("voxtral_sdk_lock_structure")
        packages[matched[1]] = matched[2]
    for name, version in PINS.items():
        if packages.get(name.split("[")[0]) != version:
            raise ValueError("voxtral_sdk_core_pin_" + name)
    if not {"soundfile", "soxr"} <= packages.keys() or any(word in text.lower() for word in ["nvidia-", "triton==", "https://", "git+"]):
        raise ValueError("voxtral_sdk_lock_authority")
    logger.info("voxtral_sdk_hash_lock_verified core_pins=%d", len(PINS))


def inventory(directory):
    """Freeze every isolated SDK file and symlink for byte-preservation checks around the import smoke test."""
    files = {}
    for path in sorted(directory.rglob("*")):
        name = str(path.relative_to(directory))
        if path.is_symlink():
            files[name] = dict(kind="symlink", target=os.readlink(path))
        elif path.is_file():
            files[name] = dict(kind="file", bytes=path.stat().st_size, sha256=digest(path))
    logger.info("voxtral_sdk_inventory_verified entries=%d", len(files))
    return files


def imports_command(root):
    """Mount only the new SDK and import probe in an offline CPU namespace, excluding all checkpoint and audio mounts."""
    command = sandbox("imports", root / "empty-inputs")
    index = command.index(str(OLD_ROOT / "venv"))
    command[index] = str(root / "venv")
    index = command.index(str(OLD_ROOT / "model"))
    del command[index - 1:index + 2]
    index = command.index("--chdir")
    command[index:index] = ["--ro-bind", str(root / "sdk_probe.py"), "/app/sdk_probe.py"]
    command[-1] = "/app/sdk_probe.py"
    return command


def prepare(root=ROOT):
    """Perform the one approved preparation in a new private root, with no load, audio, selection or deployment operation."""
    manifest = approved_manifest()
    if any(path.is_symlink() for path in [root, *root.absolute().parents]):
        raise ValueError("voxtral_private_root_symlink")
    root.mkdir(mode=0o700, exist_ok=False)
    for name in ["home", "tmp", "cache", "empty-inputs"]:
        (root / name).mkdir(mode=0o700)
    publish_json(root / "approval.json", dict(description="Owner-approved preparation only; historical manifest remains unmodified.", owner_reply="Duyệt chuẩn bị local theo ADR-107", reviewed_commit="82bee5807e3b9c53c684d19291fcd280590f8678", manifest_sha256=MANIFEST_SHA256, source_sha256=digest(Path(__file__)), disk_budget_bytes=DISK_BUDGET, load_approved=False, audio_inference_approved=False))
    uv = shutil.which("uv")
    if not uv:
        raise ValueError("voxtral_uv_required")
    save_bytes(root / "requirements.in", ("# Purpose: Pin the ADR-107 isolated CPU SDK core.\n" + "\n".join(f"{name}=={version}" for name, version in PINS.items()) + "\n").encode())
    run_step([uv, "pip", "compile", "--python", "/usr/bin/python3.12", "--only-binary", ":all:", "--generate-hashes", "--torch-backend", "cpu", "--no-header", "--no-annotate", "--output-file", str(root / "requirements.lock"), str(root / "requirements.in")], root, "sdk-resolve")
    verify_lock(root / "requirements.lock")
    return finish_preparation(root, manifest, uv)


def finish_preparation(root, manifest, uv):
    """Install the verified resolved SDK and fetch only the nine approved artifacts after the authority checks succeed."""
    if not PREPARATION_ALLOWED:
        raise ValueError("voxtral_preparation_retired")
    run_step([uv, "venv", "--python", "/usr/bin/python3.12", "--no-python-downloads", str(root / "venv")], root, "sdk-venv")
    run_step([uv, "pip", "sync", "--python", str(root / "venv/bin/python"), "--require-hashes", "--only-binary", ":all:", "--torch-backend", "cpu", "--link-mode", "copy", str(root / "requirements.lock")], root, "sdk-install")
    save_bytes(root / "sdk_probe.py", PROBE.encode())
    before = inventory(root / "venv")
    publish_json(root / "runtime-integrity.json", dict(description="Complete new CPU SDK inventory before import; not a model load.", files=before))
    run_step(imports_command(root), root, "sdk-imports", timeout=60)
    if inventory(root / "venv") != before:
        raise ValueError("voxtral_sdk_import_mutation")
    smoke = json.loads((root / "sdk-imports.log").read_text().splitlines()[-1])
    if smoke.get("imports_passed") is not True or smoke.get("model_loaded") is not False or smoke.get("audio_calls") != 0:
        raise ValueError("voxtral_sdk_import_receipt")
    sdk_bytes = check_budget(root, limit=SDK_BUDGET)
    check_budget(root, reserve=manifest["all_model_artifact_bytes"] + 16 * 1024**2)
    artifacts = []
    for spec in manifest["files"]:
        check_budget(root, reserve=spec["bytes"] + 1024**2)
        with wall_limit(3600):
            sha = download(spec["url"], root / "model", spec)
        artifacts.append(dict(**spec, sha256=sha))
        check_budget(root)
    result = dict(description="ADR-107 preparation only: verified original artifacts and isolated CPU SDK; no model load or audio evaluation.", owner_approved=True, artifacts=artifacts, SDK_before_download_bytes=sdk_bytes, SDK_entries=len(before), imports=smoke, requirements_lock_sha256=digest(root / "requirements.lock"), root_unique_file_bytes=check_budget(root), disk_budget_bytes=DISK_BUDGET, directory_quota_enforced=False, budget_enforcement="declared artifact write bounds, SDK subprocess sampled monitor and reserve checks", model_loaded=False, audio_inference_requests=0, D70_complete=False, D71_started=False)
    publish_json(root / "prepared.json", result)
    check_budget(root)
    logger.info("voxtral_preparation_complete artifacts=9 model_loaded=False audio_requests=0")
    return result


def resume_resolved():
    """Recover only the retained pre-install lock-validation failure, preserving its first log and immutable approval receipt."""
    manifest = approved_manifest()
    if any(path.is_symlink() for path in [ROOT, *ROOT.absolute().parents]):
        raise ValueError("voxtral_resume_symlink")
    expected = {"home", "tmp", "cache", "empty-inputs", "approval.json", "requirements.in", "requirements.lock", "sdk-resolve.log"}
    if {path.name for path in ROOT.iterdir()} != expected:
        raise ValueError("voxtral_resume_unexpected_stage")
    authority = json.loads((PROJECT / "docs/evidence/d70-voxtral-approved-preparation.json").read_text())
    approval = json.loads((ROOT / "approval.json").read_text())
    if approval["source_sha256"] != authority["sha256"]["scripts/tts_voxtral_preparation.py"] or approval["manifest_sha256"] != MANIFEST_SHA256 or approval["owner_reply"] != authority["owner_reply"] or approval["load_approved"] is not False or approval["audio_inference_approved"] is not False:
        raise ValueError("voxtral_resume_approval")
    expected_input = "# Purpose: Pin the ADR-107 isolated CPU SDK core.\n" + "\n".join(f"{name}=={version}" for name, version in PINS.items()) + "\n"
    if (ROOT / "requirements.in").read_text() != expected_input:
        raise ValueError("voxtral_resume_core_input")
    verify_lock(ROOT / "requirements.lock")
    publish_json(ROOT / "resolution-recovery.json", dict(description="Recover uv's normal extras-stripped lock validation; no pins changed, no prior outputs overwritten.", source_sha256=digest(Path(__file__)), lock_sha256=digest(ROOT / "requirements.lock"), first_failure_log_sha256=digest(PROJECT / "data/backups/d70-voxtral-preparation-first.log")))
    logger.info("voxtral_preparation_resuming_validated_preinstall_stage")
    return finish_preparation(ROOT, manifest, shutil.which("uv"))


def main():
    """Expose only a fixed-root, single-use preparation command with no neural execution mode."""
    logging.basicConfig(level=logging.INFO)
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resume-resolved", action="store_true")
    args = parser.parse_args()
    if args.resume_resolved:
        resume_resolved()
    else:
        prepare()


if __name__ == "__main__":
    main()
