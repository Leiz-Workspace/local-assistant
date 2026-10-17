
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from huggingface_hub import HfApi, hf_hub_download

ROOT = Path(__file__).resolve().parents[1]
API = HfApi()

UPSTREAM = "Qwen/Qwen3.5-9B"
CORE_GGUF = "bartowski/Qwen_Qwen3.5-9B-GGUF"
UNRESTRICTED = (
    "HauhauCS/"
    "Qwen3.5-9B-Uncensored-HauhauCS-Aggressive"
)

CORE_DIR = ROOT / "models/core/qwen3.5-9b"
UNRESTRICTED_DIR = ROOT / "models/unrestricted/qwen3.5-9b"

JOBS = [
    {
        "profile": "core",
        "repo": CORE_GGUF,
        "directory": CORE_DIR,
        "files": [
            "mmproj-Qwen_Qwen3.5-9B-bf16.gguf",
        ],
    },
    {
        "profile": "core",
        "repo": UPSTREAM,
        "directory": CORE_DIR,
        "files": [
            "config.json",
            "preprocessor_config.json",
            "video_preprocessor_config.json",
            "README.md",
            "LICENSE",
        ],
    },
    {
        "profile": "unrestricted",
        "repo": UNRESTRICTED,
        "directory": UNRESTRICTED_DIR,
        "files": [
            "mmproj-Qwen3.5-9B-Uncensored-HauhauCS-Aggressive-BF16.gguf",
            "README.md",
        ],
    },
    {
        "profile": "unrestricted",
        "repo": UPSTREAM,
        "directory": UNRESTRICTED_DIR / "upstream_reference",
        "files": [
            "config.json",
            "preprocessor_config.json",
            "video_preprocessor_config.json",
            "LICENSE",
        ],
    },
]


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(
            lambda: stream.read(8 * 1024 * 1024), b""
        ):
            digest.update(chunk)
    return digest.hexdigest()


manifests = {
    "core": [],
    "unrestricted": [],
}

failed = False

for job in JOBS:
    profile = job["profile"]
    repo = job["repo"]
    directory = job["directory"]
    directory.mkdir(parents=True, exist_ok=True)

    print(f"\n=== {profile.upper()} | {repo} ===", flush=True)

    info = API.model_info(repo)
    revision = info.sha
    available = set(API.list_repo_files(
        repo_id=repo, revision=revision
    ))

    for filename in job["files"]:
        if filename not in available:
            print(f"MISSING IN REPO: {filename}")
            continue

        destination = directory / filename

        try:
            # Download into HF cache, then make a regular
            # local copy in the selected profile directory.
            cached = hf_hub_download(
                repo_id=repo,
                filename=filename,
                revision=revision,
            )

            if destination.exists():
                # Avoid unnecessary copying if identical.
                if sha256(destination) != sha256(cached):
                    shutil.copy2(cached, destination)
            else:
                shutil.copy2(cached, destination)

            record = {
                "file": str(destination.relative_to(ROOT)),
                "repository": repo,
                "revision": revision,
                "sha256": sha256(destination),
                "bytes": destination.stat().st_size,
            }

            manifests[profile].append(record)
            print(f"OK: {destination.name}", flush=True)

        except Exception as exc:
            failed = True
            print(f"FAILED: {filename}: {exc}", flush=True)

for profile, directory in [
    ("core", CORE_DIR),
    ("unrestricted", UNRESTRICTED_DIR),
]:
    manifest_path = directory / "metadata-sources.json"

    manifest = {
        "profile": profile,
        "created_at_utc": datetime.now(
            timezone.utc
        ).isoformat(),
        "files": manifests[profile],
    }

    manifest_path.write_text(
        json.dumps(
            manifest, ensure_ascii=False, indent=2
        ) + "\n",
        encoding="utf-8",
    )
    print(f"\nMANIFEST: {manifest_path}")

if failed:
    raise SystemExit("Some downloads failed")

print("\nMETADATA DOWNLOAD COMPLETE")
