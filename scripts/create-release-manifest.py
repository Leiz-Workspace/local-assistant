
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
RELEASE = ROOT / "releases/v0.1"
RESULTS = ROOT / "benchmarks/results"
RELEASE.mkdir(parents=True, exist_ok=True)


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(
            lambda: handle.read(8 * 1024 * 1024), b""
        ):
            digest.update(block)
    return digest.hexdigest()


def run(command, cwd=None):
    result = subprocess.run(
        command,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    return result.stdout.strip()


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


config_path = ROOT / "configs/models.yaml"
config = yaml.safe_load(config_path.read_text(encoding="utf-8"))

# Do not accept release results without both API gates.
gates = {}

for profile in ("core", "unrestricted"):
    path = (
        RESULTS / "release" /
        f"day14-{profile}-gate.json"
    )
    data = load_json(path)

    if (
        data["profile_checked"] != profile
        or not data["api_checked"]
        or data["passed"] != data["total"]
        or data["total"] != 9
        or not all(c["passed"] for c in data["checks"])
    ):
        raise SystemExit(
            f"Release gate not verified: {profile}"
        )

    gates[profile] = {
        "passed": data["passed"],
        "total": data["total"],
        "report": str(path.relative_to(ROOT)),
        "report_sha256": sha256_file(path),
    }


models = {}

for profile in ("core", "unrestricted"):
    entry = config["models"][profile]
    path = (ROOT / entry["path"]).resolve()

    if not path.is_file():
        raise SystemExit(f"Missing model: {path}")

    actual = sha256_file(path)
    expected = entry["sha256"].lower()

    if actual != expected:
        raise SystemExit(
            f"SHA256 mismatch for {profile}"
        )

    models[profile] = {
        "name": entry["name"],
        "base_model": entry.get("base_model"),
        "repository": entry.get("repository"),
        "path": entry["path"],
        "quantization": entry.get("quantization"),
        "sha256": actual,
        "size_bytes": path.stat().st_size,
        "inference": entry["inference"],
    }


llama_root = ROOT / "runtimes/llama.cpp"
llama_commit = run(
    ["git", "rev-parse", "HEAD"],
    cwd=llama_root,
)

docker_id = run([
    "docker", "image", "inspect",
    "python:3.12-slim",
    "--format", "{{.Id}}",
])

scorecard_path = (
    RESULTS / "scorecards/day13-scorecard.json"
)

scorecard = load_json(scorecard_path)

manifest = {
    "release": "shldd-personal-ai-v0.1",
    "stage": "phase_1_runtime_and_evaluation",
    "created_at_utc": datetime.now(
        timezone.utc
    ).isoformat(),
    "status": "runtime_baseline_accepted",
    "default_profile": "core",
    "optional_profiles": ["unrestricted"],
    "runtime": {
        "engine": "llama.cpp",
        "git_commit": llama_commit,
        "build": 11557,
        "backend": "cuda",
    },
    "models": models,
    "docker_sandbox": {
        "image": "python:3.12-slim",
        "image_id": docker_id,
    },
    "benchmark": {
        "scorecard": str(
            scorecard_path.relative_to(ROOT)
        ),
        "scorecard_sha256": sha256_file(scorecard_path),
        "profiles": scorecard["profiles"],
        "release_gates": gates,
    },
    "limitations": [
        "No comprehensive reasoning benchmark",
        "No vision acceptance benchmark",
        "No complete provenance audit",
        "No production-grade agent sandbox",
        "No real file-editing agent authorization",
        "Network exposure and firewall not audited",
    ],
}

output = RELEASE / "release-manifest.json"
output.write_text(
    json.dumps(
        manifest, ensure_ascii=False, indent=2
    ) + "\n",
    encoding="utf-8",
)

print("RELEASE:", manifest["release"])
print("STATUS:", manifest["status"])
print("DEFAULT:", manifest["default_profile"])
print("LLAMA COMMIT:", llama_commit[:12])

for profile, gate in gates.items():
    print(
        f"GATE {profile.upper()}: "
        f"{gate['passed']}/{gate['total']}"
    )

print("SAVED:", output)
