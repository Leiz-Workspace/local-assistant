#!/usr/bin/env python3
"""Advanced Local Assistant runtime A/B benchmark, dry-run by default.
Install beside runtime_bench.py. Needs httpx, PyYAML and original runtime_bench.py.
"""
import argparse
import base64
import io
import csv
import hashlib
import json
import re
import statistics
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
import yaml
from runtime_bench import DEFAULTS, MMPROJ, base_command, gpu_stats, shell, wait_ready, vision_image

TASKS = {
    "math": {
        "prompt": "Solve carefully: A factory produces 18 items per hour for 7 hours. A quality check rejects 14 items. How many acceptable items remain? End with exactly 'FINAL: <integer>'.",
        "expected": 112,
        "max_tokens": 1024,
    },
    "reasoning": {
        "prompt": "A store buys 36 notebooks at $4 each. It sells 2/3 of them for $7 each, and all remaining notebooks for $5 each. After paying a flat $18 delivery fee, what is the net profit in dollars? Solve step by step and end with exactly 'FINAL: <integer>'.",
        "expected": 66,  # cost 144; revenue 168+60=228; fee 18 => 66
        "max_tokens": 1536,
    },
    "writing": {
        "prompt": "Write a practical, structured explanation of how a local AI assistant can use a FastAPI orchestration layer, a llama.cpp inference server, SQLite/PostgreSQL conversation storage, and Qdrant retrieval. Discuss request routing, retrieval, security, errors, and an implementation checklist. Write at least 450 words. End with exactly 'FINAL: DONE'.",
        "expected": "DONE",
        "max_tokens": 3072,
    },
}


def cases_for(groups):
    out = []
    if "mtp" in groups:
        for task in ("math", "reasoning", "writing"):
            out.extend([
                {"name": f"mtp_off_{task}", "group": "mtp", "task": task, "mtp": False, "reasoning": "off", "budget": -1},
                {"name": f"mtp_on_{task}", "group": "mtp", "task": task, "mtp": True, "reasoning": "off", "budget": -1},
            ])
    if "budget" in groups:
        for budget in (-1, 256, 512, 1024):
            out.append({"name": f"budget_{'unlimited' if budget == -1 else budget}", "group": "budget", "task": "reasoning", "mtp": False, "reasoning": "on", "budget": budget})
    if "integration" in groups:
        out.extend([
            {"name": "vision_mtp_off", "group": "integration", "task": "vision", "mtp": False, "vision": True, "reasoning": "off", "budget": -1},
            {"name": "vision_mtp_on", "group": "integration", "task": "vision", "mtp": True, "vision": True, "reasoning": "off", "budget": -1},
            {"name": "thinking_mtp_off", "group": "integration", "task": "reasoning", "mtp": False, "vision": False, "reasoning": "on", "budget": 512},
            {"name": "thinking_mtp_on", "group": "integration", "task": "reasoning", "mtp": True, "vision": False, "reasoning": "on", "budget": 512},
        ])
    for case in out:
        case.setdefault("vision", False)
    return out


def command_for(original, case, profile):
    cmd = base_command(original)
    # Old script's base_command deliberately removes these tuning flags.
    cmd += ["--reasoning", case["reasoning"], "--reasoning-format", "auto", "--reasoning-effort", "default",
            "--reasoning-budget", str(case["budget"]), "--cache-type-k", "f16", "--cache-type-v", "f16",
            "--flash-attn", "auto"]
    if case.get("vision"):
        cmd += ["--mmproj", MMPROJ[profile]]
    else:
        cmd += ["--no-mmproj"]
    if case["mtp"]:
        cmd += ["--spec-type", "draft-mtp"]
    return cmd


def score(task, answer, finish):
    if finish == "length":
        return "INCOMPLETE"
    if finish != "stop":
        return "ERROR"
    if task == "vision":
        words = re.findall(r"\b(?:red|green|blue)\b", answer.lower())
        return "PASS" if words == ["red", "green", "blue"] else "WRONG"
    expected = TASKS[task]["expected"]
    found = re.search(r"FINAL:\s*([^\n\r]+)", answer, flags=re.I)
    if not found:
        return "WRONG_OR_UNFORMATTED"
    actual = found.group(1).strip().rstrip(".* `")
    if task == "writing":
        words = len(answer.split())
        required = ("fastapi", "llama.cpp", "qdrant", "security", "error")
        ok = actual.upper() == expected and words >= 450 and all(term in answer.lower() for term in required)
        if not ok:
            return "WRONG_OR_TOO_SHORT"
        return "PASS_FORMAT_REVIEW_CONTENT"  # still requires human review of factual quality
    match = re.match(r"^\$?(-?\d+)(?:\.0+)?(?:\b|$)", actual)
    return "PASS" if match and int(match.group(1)) == expected else "WRONG"


def report(rows, outdir, stamp):
    outdir.mkdir(parents=True, exist_ok=True)
    jp = outdir / f"advanced-{stamp}.json"
    cp = outdir / f"advanced-{stamp}.csv"
    jp.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    if rows:
        with cp.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()), extrasaction="ignore")
            w.writeheader()
            w.writerows(rows)
    return jp, cp


def summary(rows, outdir, stamp):
    grouped = {}
    for r in rows:
        if r["status"] == "ok":
            grouped.setdefault(r["case"], []).append(r)
    records = []
    for case, data in grouped.items():
        speeds = [r["tokens_per_second"] for r in data if isinstance(r["tokens_per_second"], (int, float))]
        latencies = [r["elapsed_s"] for r in data if r["elapsed_s"] is not None]
        records.append({"case": case, "runs": len(data), "pass": sum(str(r["quality"]).startswith("PASS") for r in data),
                        "incomplete": sum(r["quality"] == "INCOMPLETE" for r in data),
                        "median_tps": round(statistics.median(speeds), 2) if speeds else None,
                        "median_elapsed_s": round(statistics.median(latencies), 3) if latencies else None,
                        "max_vram_mib": max((r["vram_after_mib"] or 0) for r in data)})
    sp = outdir / f"advanced-summary-{stamp}.json"
    sp.write_text(json.dumps(records, indent=2), encoding="utf-8")
    print("\nSUMMARY")
    for r in records:
        print(f"  {r['case']}: {r['pass']}/{r['runs']} PASS, incomplete={r['incomplete']}, median={r['median_tps']} tok/s, median latency={r['median_elapsed_s']}s")
    print(f"Summary: {sp}")


def main():
    ap = argparse.ArgumentParser(description="Local Assistant advanced benchmark; DRY RUN unless --execute --confirm-restarts")
    ap.add_argument("--profile", choices=list(DEFAULTS), default="core")
    ap.add_argument("--groups", default="integration", help="mtp,budget,integration")
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--compose-file", default="docker-compose.yaml")
    ap.add_argument("--base-url", default="http://127.0.0.1:8080")
    ap.add_argument("--max-tokens-budget", type=int, default=4096)
    ap.add_argument("--ready-timeout", type=int, default=240)
    ap.add_argument("--request-timeout", type=int, default=300)
    ap.add_argument("--output-dir", default="benchmarks/results/runtime-config/advanced")
    ap.add_argument("--execute", action="store_true")
    ap.add_argument("--confirm-restarts", action="store_true")
    args = ap.parse_args()
    if not 1 <= args.repeats <= 30:
        ap.error("--repeats must be 1..30")
    selected = {x.strip() for x in args.groups.split(",") if x.strip()}
    if not selected or selected - {"mtp", "budget", "integration"}:
        ap.error("--groups must contain mtp, budget, and/or integration")
    root = Path.cwd().resolve()
    compose = (root / args.compose_file).resolve()
    if not compose.is_file():
        ap.error(f"Missing Compose file: {compose}")
    base = ["docker", "compose", "-f", str(compose), "--profile", "core", "--profile", "unrestricted"]
    config = json.loads(shell(base + ["config", "--format", "json"], root).stdout)
    original = config["services"][args.profile]["command"]
    if not isinstance(original, list):
        ap.error("Compose command must be a list")
    cases = cases_for(selected)
    print(f"Profile: {args.profile}; repeats={args.repeats}; cases={len(cases)}; requests={len(cases)*args.repeats}")
    print("Cases:", ", ".join(c["name"] for c in cases))
    if "integration" in selected or "mtp" in selected:
        print("NOTE: MTP is experimental; Vision+MTP GPU memory can peak above sampled values.")
    print("Docker Compose source unchanged; both model services STOPPED at end; no other stacks touched.")
    if not args.execute:
        print("DRY RUN. Add --execute --confirm-restarts to run.")
        return
    if not args.confirm_restarts:
        ap.error("Must pass --confirm-restarts to change running model services")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    outdir = root / args.output_dir
    rows = []
    with tempfile.TemporaryDirectory(prefix="la-adv-bench-") as tmp:
        override = Path(tmp) / "override.yaml"
        with httpx.Client(base_url=args.base_url, trust_env=False) as client:
            try:
                for idx, case in enumerate(cases, 1):
                    print(f"\n[{idx}/{len(cases)}] {case['name']}", flush=True)
                    shell(base + ["stop", "core", "unrestricted"], root, timeout=120)
                    time.sleep(2)
                    before = gpu_stats()["used_mib"]
                    override.write_text(yaml.safe_dump({"services": {args.profile: {"command": command_for(original, case, args.profile)}}}, sort_keys=False))
                    active = base + ["-f", str(override)]
                    try:
                        shell(active + ["up", "-d", "--no-build", "--force-recreate", args.profile], root, timeout=120)
                        ok, detail = wait_ready(client, DEFAULTS[args.profile], args.ready_timeout)
                        if not ok:
                            raise RuntimeError(f"Not ready: {detail}")
                        loaded = gpu_stats()["used_mib"]
                        # Warm up once, excluded from score. Same text as experiment.
                        warm = {"model": DEFAULTS[args.profile], "messages": [{"role": "user", "content": "Reply exactly OK"}],
                                "max_tokens": 16, "temperature": 0, "stream": False, "seed": 42}
                        wr = client.post("/v1/chat/completions", json=warm, timeout=args.request_timeout)
                        wr.raise_for_status()
                        for repeat in range(1, args.repeats + 1):
                            task = TASKS.get(case["task"])
                            if case["task"] == "vision":
                                messages = [{"role": "user", "content": [
                                    {"type": "text", "text": "Read the image. Reply with exactly these colors left to right, separated by commas; no other text."},
                                    {"type": "image_url", "image_url": {"url": vision_image()}}
                                ]}]
                                limit = 128
                            else:
                                messages = [{"role": "user", "content": task["prompt"]}]
                                limit = args.max_tokens_budget if case["group"] == "budget" else task["max_tokens"]
                            payload = {"model": DEFAULTS[args.profile],
                                       "messages": messages,
                                       "max_tokens": limit,
                                       "temperature": 0.0, "seed": 42, "stream": False}
                            item = {"profile": args.profile, "case": case["name"], "group": case["group"], "task": case["task"],
                                    "repeat": repeat, "mtp": case["mtp"], "vision": case["vision"], "reasoning": case["reasoning"], "budget": case["budget"],
                                    "status": "failed", "quality": "ERROR", "finish_reason": None,
                                    "elapsed_s": None, "tokens_per_second": None, "prompt_tokens": None, "completion_tokens": None,
                                    "reasoning_chars": None, "vram_before_mib": before, "vram_loaded_mib": loaded, "vram_after_mib": None,
                                    "answer": "", "answer_words": None, "answer_sha256": "", "error": ""}
                            try:
                                start = time.monotonic()
                                res = client.post("/v1/chat/completions", json=payload, timeout=args.request_timeout)
                                item["elapsed_s"] = round(time.monotonic() - start, 3)
                                res.raise_for_status()
                                response = res.json()
                                choice = response["choices"][0]
                                message = choice["message"]
                                answer = message.get("content") or ""
                                item.update(status="ok", finish_reason=choice.get("finish_reason"),
                                            quality=score(case["task"], answer, choice.get("finish_reason")),
                                            reasoning_chars=len(message.get("reasoning_content") or ""),
                                            answer=answer, answer_words=len(answer.split()), answer_sha256=hashlib.sha256(answer.encode()).hexdigest(),
                                            prompt_tokens=response.get("usage", {}).get("prompt_tokens"),
                                            completion_tokens=response.get("usage", {}).get("completion_tokens"),
                                            tokens_per_second=response.get("timings", {}).get("predicted_per_second"))
                            except Exception as exc:
                                item["error"] = repr(exc)[:1000]
                            finally:
                                item["vram_after_mib"] = gpu_stats()["used_mib"]
                                rows.append(item)
                                report(rows, outdir, stamp)
                                print(f"  run {repeat}: {item['quality']}, {item['tokens_per_second']} tok/s, {item['elapsed_s']}s, {item['completion_tokens']} tokens", flush=True)
                    except Exception as exc:
                        print(f"  CASE ERROR: {exc}", file=sys.stderr)
                        rows.append({"profile": args.profile, "case": case["name"], "group": case["group"], "task": case["task"],
                                     "repeat": 0, "mtp": case["mtp"], "vision": case["vision"], "reasoning": case["reasoning"], "budget": case["budget"],
                                     "status": "failed", "quality": "ERROR", "finish_reason": None, "elapsed_s": None,
                                     "tokens_per_second": None, "prompt_tokens": None, "completion_tokens": None, "reasoning_chars": None,
                                     "vram_before_mib": before, "vram_loaded_mib": None, "vram_after_mib": gpu_stats()["used_mib"],
                                     "answer": "", "answer_words": None, "answer_sha256": "", "error": repr(exc)[:1000]})
                        report(rows, outdir, stamp)
                    finally:
                        shell(base + ["stop", "core", "unrestricted"], root, check=False, timeout=120)
            except KeyboardInterrupt:
                print("Interrupted; preserving partial results.", file=sys.stderr)
            finally:
                shell(base + ["stop", "core", "unrestricted"], root, check=False, timeout=120)
    if rows:
        jp, cp = report(rows, outdir, stamp)
        print(f"\nJSON: {jp}\nCSV: {cp}")
        summary(rows, outdir, stamp)
    print("Done. Model services left STOPPED.")


if __name__ == "__main__":
    main()
