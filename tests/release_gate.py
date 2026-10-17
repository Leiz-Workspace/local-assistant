
import argparse
import hashlib
import json
import subprocess
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/models.yaml"
RESULT = ROOT / "benchmarks/results/release/day14-gate.json"

EXPECTED = [
    "benchmarks/results/quality/core.json",
    "benchmarks/results/quality/unrestricted.json",
    "benchmarks/results/quality/day11/core-structured.json",
    "benchmarks/results/quality/day11/unrestricted-structured.json",
    "benchmarks/results/quality/day11/core-coding.json",
    "benchmarks/results/quality/day11/unrestricted-coding.json",
    "benchmarks/results/quality/day12/core-agent.json",
    "benchmarks/results/quality/day12/unrestricted-agent.json",
    "benchmarks/results/scorecards/day13-scorecard.json",
    "benchmarks/results/scorecards/day13-scorecard.md",
]

checks = []


def record(name, passed, detail):
    checks.append({
        "name": name,
        "passed": bool(passed),
        "detail": str(detail),
    })
    print(
        f'{"PASS" if passed else "FAIL"} '
        f'| {name} | {detail}'
    )


def file_sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def check_models(config):
    models = config.get("models", {})

    for profile in ("core", "unrestricted"):
        model = models.get(profile)
        if not isinstance(model, dict):
            record(f"RG01_{profile}", False, "Missing profile")
            continue

        inf = model.get("inference", {})
        required = [
            "name", "path", "sha256", "inference"
        ]
        valid = (
            all(model.get(key) for key in required)
            and isinstance(inf, dict)
            and inf.get("host") == "127.0.0.1"
            and inf.get("port") == 8080
            and inf.get("reasoning") == "off"
            and inf.get("context_size") == 16384
            and inf.get("parallel") == 1
        )

        record(
            f"RG01_{profile}",
            valid,
            "Configuration validated" if valid else
            "Incomplete or unexpected configuration",
        )

        path_value = model.get("path")
        if not path_value:
            record(f"RG02_{profile}", False, "Missing model path")
            continue

        path = (ROOT / path_value).resolve()
        model_root = (ROOT / "models").resolve()

        if not path.is_relative_to(model_root) or not path.is_file():
            record(f"RG02_{profile}", False, "Missing/invalid path")
            continue

        actual = file_sha256(path)
        expected = str(model.get("sha256", "")).lower()

        record(
            f"RG02_{profile}",
            actual == expected,
            f"SHA256: {actual[:16]}...",
        )


def check_runtime():
    binary = (
        ROOT /
        "runtimes/llama.cpp/build-cuda/bin/llama-server"
    )
    if not binary.is_file():
        record("RG03_runtime", False, "llama-server missing")
        return

    try:
        result = subprocess.run(
            [str(binary), "--version"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        record(
            "RG03_runtime",
            result.returncode == 0,
            (result.stdout or result.stderr).strip()[:160],
        )
    except Exception as exc:
        record("RG03_runtime", False, str(exc))


def check_artifacts():
    missing = [str(p) for p in EXPECTED if not (ROOT / p).is_file()]
    record(
        "RG04_artifacts",
        not missing,
        "All expected artifacts present" if not missing
        else "Missing: " + ", ".join(missing),
    )


def check_docker():
    try:
        result = subprocess.run(
            [
                "docker", "image", "inspect", "python:3.12-slim",
                "--format", "{{.Id}}",
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
        record(
            "RG05_docker",
            result.returncode == 0,
            result.stdout.strip() or result.stderr.strip(),
        )
    except Exception as exc:
        record("RG05_docker", False, str(exc))


def check_api(profile, config):
    model = config["models"][profile]
    inf = model["inference"]
    base = f"http://127.0.0.1:{inf['port']}"

    try:
        with urllib.request.urlopen(
            base + "/health", timeout=10
        ) as response:
            health = json.load(response)

        with urllib.request.urlopen(
            base + "/v1/models", timeout=10
        ) as response:
            data = json.load(response)

        ids = [
            item.get("id")
            for item in data.get("data", [])
        ]

        valid = (
            health.get("status") == "ok"
            and model["name"] in ids
        )
        record(
            f"RG06_api_{profile}",
            valid,
            f"health={health.get('status')}; models={ids}",
        )
    except Exception as exc:
        record(f"RG06_api_{profile}", False, str(exc))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--profile", choices=["core", "unrestricted"],
        required=True,
    )
    parser.add_argument(
        "--check-api", action="store_true",
        help="Check currently running llama-server",
    )
    args = parser.parse_args()

    try:
        config = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
        if not isinstance(config, dict):
            raise ValueError("YAML root must be an object")
    except Exception as exc:
        record("RG01_yaml", False, str(exc))
        config = None

    if config:
        record("RG01_yaml", True, "Valid YAML")
        check_models(config)

    check_runtime()
    check_artifacts()
    check_docker()

    if args.check_api:
        if config and args.profile in config.get("models", {}):
            check_api(args.profile, config)
        else:
            record("RG06_api", False, "Profile unavailable")

    passed = sum(item["passed"] for item in checks)
    report = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "profile_checked": args.profile,
        "api_checked": args.check_api,
        "passed": passed,
        "total": len(checks),
        "checks": checks,
    }

    RESULT.parent.mkdir(parents=True, exist_ok=True)
    RESULT.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"\nRELEASE GATE: {passed}/{len(checks)}")
    print("SAVED:", RESULT)

    raise SystemExit(0 if passed == len(checks) else 1)


if __name__ == "__main__":
    main()
