#!/usr/bin/env python3
"""Local Assistant llama.cpp runtime benchmark. Requires httpx, PyYAML, Pillow."""
import argparse
import base64
import csv
import io
import json
import re
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
import yaml
from PIL import Image, ImageDraw

DEFAULTS = {
    "core": "qwen3.5-9b-core",
    "unrestricted": "qwen3.5-9b-unrestricted",
}
MMPROJ = {
    "core": "/models/core/qwen3.5-9b/mmproj-Qwen_Qwen3.5-9B-bf16.gguf",
    "unrestricted": "/models/unrestricted/qwen3.5-9b/mmproj-Qwen3.5-9B-Uncensored-HauhauCS-Aggressive-BF16.gguf",
}
# Tests ordered from simple to more experimental. Crucially, one variable at a time.
CASES = [
    {"name": "text_off_f16", "group": "baseline", "reasoning": "off", "vision": False, "kv": "f16"},
    {"name": "vision_off_f16", "group": "vision", "reasoning": "off", "vision": True, "kv": "f16"},
    {"name": "reason_on_f16", "group": "reasoning", "reasoning": "on", "vision": False, "kv": "f16"},
    {"name": "reason_auto_f16", "group": "reasoning", "reasoning": "auto", "vision": False, "kv": "f16"},
    {"name": "kv_bf16", "group": "kv", "reasoning": "off", "vision": False, "kv": "bf16"},
    {"name": "kv_q8_0", "group": "kv", "reasoning": "off", "vision": False, "kv": "q8_0"},
    {"name": "effort_low", "group": "effort", "reasoning": "on", "vision": False, "kv": "f16", "effort": "low"},
    {"name": "effort_high", "group": "effort", "reasoning": "on", "vision": False, "kv": "f16", "effort": "high"},
    {"name": "budget_1024", "group": "budget", "reasoning": "on", "vision": False, "kv": "f16", "budget": 1024},
    {"name": "mtp_draft", "group": "mtp", "reasoning": "off", "vision": False, "kv": "f16", "spec": "draft-mtp"},
]
REMOVE = {"--reasoning", "--reasoning-effort", "--reasoning-budget", "--reasoning-format", "--mmproj", "-mm", "--no-mmproj", "--cache-type-k", "-ctk", "--cache-type-v", "-ctv", "--spec-type", "--flash-attn"}
TAKES_VALUE = {"--reasoning", "--reasoning-effort", "--reasoning-budget", "--reasoning-format", "--mmproj", "-mm", "--cache-type-k", "-ctk", "--cache-type-v", "-ctv", "--spec-type", "--flash-attn"}


def shell(args, cwd, check=True, timeout=150):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, check=check, timeout=timeout)


def base_command(cmd):
    cleaned = []
    i = 0
    while i < len(cmd):
        item = cmd[i]
        key = item.split("=", 1)[0]
        if key in REMOVE:
            i += 1 if "=" in item or key not in TAKES_VALUE else 2
        else:
            cleaned.append(item)
            i += 1
    return cleaned


def variant_command(cmd, case, profile):
    cmd = base_command(cmd)
    cmd += ["--reasoning", case["reasoning"], "--reasoning-format", "auto",
            "--cache-type-k", case["kv"], "--cache-type-v", case["kv"],
            "--flash-attn", "auto"]
    if case["vision"]:
        cmd += ["--mmproj", MMPROJ[profile]]
    else:
        cmd += ["--no-mmproj"]
    if "effort" in case:
        cmd += ["--reasoning-effort", case["effort"]]
    if "budget" in case:
        cmd += ["--reasoning-budget", str(case["budget"])]
    if "spec" in case:
        cmd += ["--spec-type", case["spec"]]
    return cmd


def gpu_stats():
    try:
        p = subprocess.run(["nvidia-smi", "--query-gpu=memory.used,memory.free", "--format=csv,noheader,nounits"],
                           capture_output=True, text=True, timeout=8, check=True)
        parts = p.stdout.strip().splitlines()[0].split(",")
        return {"used_mib": int(parts[0].strip()), "free_mib": int(parts[1].strip())}
    except Exception:
        return {"used_mib": None, "free_mib": None}


def vision_image():
    im = Image.new("RGB", (600, 200), "white")
    d = ImageDraw.Draw(im)
    for idx, color in enumerate(("red", "green", "blue")):
        x = 20 + idx * 200
        d.rectangle((x, 20, x + 165, 180), fill=color)
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def questions(case):
    if case["vision"]:
        return [{"role": "user", "content": [
            {"type": "text", "text": "Look at the picture. List the colored blocks from left to right using exactly three English color names."},
            {"type": "image_url", "image_url": {"url": vision_image()}},
        ]}]
    if case["group"] in {"reasoning", "effort", "budget"}:
        return [{"role": "user", "content": "A shop sells 3 pens for 12 dollars. How much do 7 pens cost at the same unit price? Explain briefly."}]
    return [{"role": "user", "content": "In one sentence, explain why the sky looks blue in daytime."}]


def evaluate(case, answer):
    lower = answer.lower()
    if case["vision"]:
        positions = [lower.find(c) for c in ("red", "green", "blue")]
        return all(x >= 0 for x in positions) and positions == sorted(positions)
    if case["group"] in {"reasoning", "effort", "budget"}:
        return bool(re.search(r"(?<!\d)28(?:\.0+)?(?!\d)", answer))
    return bool(answer.strip())


def select_cases(groups):
    requested = set(groups.split(","))
    if "all" in requested:
        return CASES
    invalid = requested - {c["group"] for c in CASES}
    if invalid:
        raise ValueError(f"Unknown groups: {sorted(invalid)}")
    return [c for c in CASES if c["group"] in requested]


def wait_ready(client, expected, timeout_s):
    end = time.monotonic() + timeout_s
    last = ""
    while time.monotonic() < end:
        try:
            health = client.get("/health", timeout=3)
            if health.status_code == 200 and health.json().get("status") == "ok":
                response = client.get("/v1/models", timeout=5)
                ids = [m.get("id") for m in response.json().get("data", [])]
                if expected in ids:
                    return True, ids
                last = f"Model aliases do not match {expected}: {ids}"
            else:
                last = f"Health: {health.status_code}"
        except Exception as exc:
            last = str(exc)
        time.sleep(3)
    return False, last


def write_report(results, output_dir):
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    jsonpath = output_dir / f"runtime-bench-{timestamp}.json"
    csvpath = output_dir / f"runtime-bench-{timestamp}.csv"
    jsonpath.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    keys = ["profile", "case", "group", "status", "quality_pass", "tokens_per_second", "elapsed_s", "prompt_tokens", "completion_tokens", "reasoning_chars", "finish_reason", "vram_before_mib", "vram_loaded_mib", "vram_after_mib", "error", "answer"]
    with csvpath.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(results)
    print(f"\nJSON: {jsonpath}\nCSV:  {csvpath}", flush=True)


def main():
    ap = argparse.ArgumentParser(description="Local Assistant runtime benchmark (dry-run by default)")
    ap.add_argument("--profile", choices=["core", "unrestricted"], default="core")
    ap.add_argument("--groups", default="baseline,vision,reasoning", help="baseline,vision,reasoning,kv,effort,budget,mtp or all")
    ap.add_argument("--compose-file", default="docker-compose.yaml")
    ap.add_argument("--base-url", default="http://127.0.0.1:8080")
    ap.add_argument("--output-dir", default="benchmarks/results/runtime-config")
    ap.add_argument("--ready-timeout", type=int, default=240)
    ap.add_argument("--request-timeout", type=int, default=180)
    ap.add_argument("--max-tokens", type=int, default=256)
    ap.add_argument("--execute", action="store_true", help="Actually stop/recreate model containers")
    ap.add_argument("--confirm-restarts", action="store_true", help="Acknowledge that active core/unrestricted containers will be stopped")
    args = ap.parse_args()
    root = Path.cwd().resolve()
    compose_file = (root / args.compose_file).resolve()
    if not compose_file.is_file():
        ap.error(f"Missing {compose_file}; run from project root")
    try:
        cases = select_cases(args.groups)
    except ValueError as exc:
        ap.error(str(exc))
    command_base = ["docker", "compose", "-f", str(compose_file), "--profile", "core", "--profile", "unrestricted"]
    try:
        config = json.loads(shell(command_base + ["config", "--format", "json"], root).stdout)
        cmd = config["services"][args.profile]["command"]
        assert isinstance(cmd, list) and cmd, "Compose command must be list"
    except Exception as exc:
        ap.error(f"Cannot parse existing Compose config: {exc}")
    print(f"Profile: {args.profile} | model: {DEFAULTS[args.profile]}")
    print("Will benchmark:", ", ".join(c["name"] for c in cases))
    print("Existing compose file remains unchanged. Only the two model services are managed.")
    if not args.execute:
        print("DRY RUN only. To run: --execute --confirm-restarts")
        return
    if not args.confirm_restarts:
        ap.error("Add --confirm-restarts to explicitly permit stopping/recreating model containers")

    results = []
    output_dir = root / args.output_dir
    with tempfile.TemporaryDirectory(prefix="la-runtime-bench-") as td:
        # Overlay is YAML but outside project; relative mounts are resolved against first compose file.
        overlay = Path(td) / "benchmark.override.yaml"
        cmd_base = command_base + ["-f", str(overlay)]
        with httpx.Client(base_url=args.base_url, trust_env=False) as client:
            try:
                for i, case in enumerate(cases, 1):
                    print(f"\n[{i}/{len(cases)}] {case['name']}", flush=True)
                    row = {"profile": args.profile, "case": case["name"], "group": case["group"], "status": "failed",
                           "quality_pass": False, "tokens_per_second": None, "elapsed_s": None, "prompt_tokens": None,
                           "completion_tokens": None, "reasoning_chars": None, "finish_reason": None, "vram_before_mib": None, "vram_loaded_mib": None,
                           "vram_after_mib": None, "error": "", "answer": ""}
                    try:
                        shell(command_base + ["stop", "core", "unrestricted"], root, timeout=120)
                        time.sleep(2)
                        row["vram_before_mib"] = gpu_stats()["used_mib"]
                        overlay.write_text(yaml.safe_dump({"services": {args.profile: {"command": variant_command(cmd, case, args.profile)}}}, sort_keys=False))
                        shell(cmd_base + ["up", "-d", "--no-build", "--force-recreate", args.profile], root, timeout=90)
                        ready, info = wait_ready(client, DEFAULTS[args.profile], args.ready_timeout)
                        if not ready:
                            raise RuntimeError(f"Server readiness timed out: {info}")
                        row["vram_loaded_mib"] = gpu_stats()["used_mib"]
                        messages = questions(case)
                        payload = {"model": DEFAULTS[args.profile], "messages": messages,
                                   "max_tokens": args.max_tokens, "temperature": 0.0, "stream": False}
                        start = time.monotonic()
                        reply = client.post("/v1/chat/completions", json=payload, timeout=args.request_timeout)
                        row["elapsed_s"] = round(time.monotonic() - start, 3)
                        reply.raise_for_status()
                        data = reply.json()
                        message = data["choices"][0]["message"]
                        answer = message.get("content") or ""
                        row["answer"] = answer[:1200]
                        row["reasoning_chars"] = len(message.get("reasoning_content") or "")
                        row["finish_reason"] = data["choices"][0].get("finish_reason")
                        row["quality_pass"] = evaluate(case, answer)
                        usage = data.get("usage", {})
                        timing = data.get("timings", {})
                        row["prompt_tokens"] = usage.get("prompt_tokens")
                        row["completion_tokens"] = usage.get("completion_tokens")
                        row["tokens_per_second"] = timing.get("predicted_per_second")
                        row["vram_after_mib"] = gpu_stats()["used_mib"]
                        row["status"] = "ok"
                        print(f"  quality={row['quality_pass']}, tokens/s={row['tokens_per_second']}, reasoning_chars={row['reasoning_chars']}, VRAM={row['vram_after_mib']} MiB", flush=True)
                    except Exception as exc:
                        row["error"] = str(exc)[:600]
                        print(f"  FAIL: {row['error']}", flush=True)
                        try:
                            log = shell(command_base + ["logs", "--tail", "30", args.profile], root, check=False, timeout=20)
                            row["error"] += "\n" + (log.stdout + log.stderr)[-3000:]
                        except Exception:
                            pass
                    finally:
                        results.append(row)
                        write_report(results, output_dir)
                        # Stop before changing configuration / starting another case.
                        try:
                            shell(command_base + ["stop", "core", "unrestricted"], root, check=False, timeout=100)
                        except Exception:
                            pass
            except KeyboardInterrupt:
                print("Interrupted. Results already saved; model containers are being stopped.", file=sys.stderr)
            finally:
                try:
                    shell(command_base + ["stop", "core", "unrestricted"], root, check=False, timeout=100)
                except Exception:
                    pass
                if results:
                    write_report(results, output_dir)
    print("\nCompleted. Model services left STOPPED to release VRAM.")

if __name__ == "__main__":
    main()
