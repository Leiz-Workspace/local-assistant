#!/usr/bin/env python3
"""Read-only 32K needle-in-haystack benchmark for a running llama.cpp server.

Only calls /health, /v1/models, /tokenize, /v1/chat/completions. Does not
manage Docker, files or model processes. Python standard library only.
"""
from __future__ import annotations
import argparse
import json
import math
import re
import subprocess
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

BASE = "http://127.0.0.1:8080"
NEEDLE = "RAVEN-73-Q-6152"
FILLER_SENTENCES = [
    "Record {i:05d}: Delta station logged neutral observations about the calibration timeline and routine maintenance checks.",
    "Record {i:05d}: The storage inventory was reconciled, with no exceptions noted in the weekly audit.",
    "Record {i:05d}: A paper form described the order of ordinary tasks, from intake through archival review.",
    "Record {i:05d}: Measurements of indoor humidity and temperature were collected for routine historical reference.",
    "Record {i:05d}: The team documented status updates and resolved duplicated paperwork from an earlier cycle.",
]

def request(base, path, payload=None, timeout=300):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(base.rstrip("/") + path, data=data,
        headers={"Content-Type": "application/json"}, method="POST" if data else "GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))

def tokenize(base, content):
    res = request(base, "/tokenize", {"content": content, "add_special": False}, timeout=180)
    tokens = res.get("tokens")
    if not isinstance(tokens, list):
        raise RuntimeError("Unexpected /tokenize schema: expected {tokens:[...]}" )
    return len(tokens)

def gpu_mem():
    try:
        out = subprocess.check_output(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
                                      text=True, timeout=5).strip().splitlines()[0]
        return int(out.strip())
    except (OSError, ValueError, subprocess.SubprocessError, IndexError):
        return None

class GPUPoll:
    def __init__(self):
        self.max_mem = None
        self.event = threading.Event()
        self.worker = threading.Thread(target=self.run, daemon=True)
    def run(self):
        while not self.event.is_set():
            m = gpu_mem()
            if m is not None:
                self.max_mem = max(m, self.max_mem or 0)
            self.event.wait(.35)
    def __enter__(self):
        self.worker.start()
        return self
    def __exit__(self, *args):
        self.event.set()
        self.worker.join(timeout=3)

def filler_lines(n=1500):
    return [FILLER_SENTENCES[i % len(FILLER_SENTENCES)].format(i=i) for i in range(n)]

def generate_prompt(base, desired_pos, target_total, reserve, ctx):
    """Position needle around desired token offset within constant-length content.

    Tokenize full content during calibration. Offset is measured for the content
    (not chat template), and the actual prompt_tokens reported by server is logged.
    """
    lines = filler_lines()
    text = "\n".join(lines)
    size = tokenize(base, text)
    if size < target_total:
        # Increase deterministically until enough text exists
        lines = filler_lines(max(2200, math.ceil(len(lines) * target_total / max(size, 1) * 1.2)))
    lo, hi = 0, len(lines)
    while lo < hi:
        mid = (lo + hi) // 2
        length = tokenize(base, "\n".join(lines[:mid]))
        if length < target_total:
            lo = mid + 1
        else:
            hi = mid
    lines = lines[:max(1, lo)]
    # Locate injection position by tokenizing only prefix
    lo, hi = 0, len(lines)
    while lo < hi:
        mid = (lo + hi) // 2
        pos = tokenize(base, "\n".join(lines[:mid]))
        if pos < desired_pos:
            lo = mid + 1
        else:
            hi = mid
    insert_at = lo
    start = "You are performing a precise retrieval test. In the text below, one line begins with CANARY_SECRET. " \
            "Return ONLY the secret on that line, with no explanation. Do not invent a value.\n\nDOCUMENT:\n"
    end = "\nEND DOCUMENT. Question: What is the exact CANARY_SECRET? Respond with the secret only."
    line = "CANARY_SECRET: " + NEEDLE
    before = lines[:insert_at]
    after = lines[insert_at:]
    # Trim from end until strict reserve satisfied. This never removes needle.
    while True:
        body = "\n".join(before + [line] + after)
        prompt = start + body + end
        count = tokenize(base, prompt)
        if count <= min(target_total + 100, ctx - reserve):
            break
        if not after:
            raise RuntimeError("Cannot fit prompt with requested position and reserve")
        after.pop()
    offset = tokenize(base, start + "\n".join(before))
    return prompt, count, offset

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--profile", choices=["core", "unrestricted"], required=True)
    p.add_argument("--base-url", default=BASE)
    p.add_argument("--positions", default="8000,16000,24000,30000")
    p.add_argument("--target-total", type=int, default=30500)
    p.add_argument("--reserve", type=int, default=1700)
    p.add_argument("--max-tokens", type=int, default=1024)
    p.add_argument("--thinking", choices=["off", "auto"], default="off", help="Request no-thinking via chat-template kwargs; verify effectiveness in reasoning_chars")
    p.add_argument("--output-dir", default="benchmarks/results/context-32k")
    p.add_argument("--execute", action="store_true")
    args = p.parse_args()
    positions = [int(x.strip()) for x in args.positions.split(",") if x.strip()]
    if not positions or min(positions) < 100 or max(positions) >= args.target_total:
        p.error("positions must be >100 and below --target-total")
    expected_model = "qwen3.5-9b-" + args.profile
    print(f"Profile: {args.profile}; expected model: {expected_model}; positions: {positions}")
    print("READ ONLY: does not stop/recreate containers or edit Compose.")
    if not args.execute:
        print("DRY RUN. Add --execute to run against the currently active server.")
        return
    health = request(args.base_url, "/health")
    if health.get("status") != "ok":
        raise RuntimeError(f"Server unhealthy: {health}")
    info = request(args.base_url, "/v1/models")
    entries = info.get("data", [])
    match = next((m for m in entries if m.get("id") == expected_model), None)
    if not match:
        raise RuntimeError(f"Wrong model is running. Expected {expected_model}; got {[m.get('id') for m in entries]}")
    ctx = match.get("meta", {}).get("n_ctx")
    if not isinstance(ctx, int) or ctx < 32000:
        raise RuntimeError(f"Expected 32K context, model meta reports n_ctx={ctx}")
    if args.max_tokens > args.reserve:
        raise RuntimeError(f"max-tokens={args.max_tokens} exceeds reserved headroom={args.reserve}")
    if args.target_total > ctx - args.reserve:
        raise RuntimeError(f"target-total={args.target_total} exceeds ctx-reserve={ctx-args.reserve}")
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    date = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    results = []
    output = out_dir / f"context-32k-{args.profile}-{date}.json"
    for i, pos in enumerate(positions, 1):
        print(f"[{i}/{len(positions)}] Needle target ~{pos:,} content tokens", flush=True)
        record = {"profile": args.profile, "position_target": pos, "context_config": ctx, "status": "ERROR"}
        try:
            prompt, count, actual_offset = generate_prompt(args.base_url, pos, args.target_total, args.reserve, ctx)
            record.update({"prompt_content_tokens": count, "needle_content_offset": actual_offset,
                           "vram_before_mib": gpu_mem()})
            payload = {"model": expected_model, "messages": [{"role": "user", "content": prompt}],
                       "temperature": 0, "max_tokens": args.max_tokens, "stream": False}
            if args.thinking == "off":
                payload["chat_template_kwargs"] = {"enable_thinking": False}
            start = time.perf_counter()
            with GPUPoll() as poll:
                answer_data = request(args.base_url, "/v1/chat/completions", payload, timeout=1200)
            seconds = time.perf_counter() - start
            choice = answer_data.get("choices", [{}])[0]
            msg = choice.get("message") or {}
            answer = (msg.get("content") or "").strip()
            usage = answer_data.get("usage") or {}
            actual_prompt_tokens = usage.get("prompt_tokens")
            finish = choice.get("finish_reason")
            quality = "PASS" if answer == NEEDLE and finish == "stop" else ("INCOMPLETE" if finish == "length" else "FAIL")
            timings = answer_data.get("timings") or {}
            record.update({"status": quality, "answer": answer, "finish_reason": finish,
                           "elapsed_s": round(seconds, 3), "prompt_tokens_server": actual_prompt_tokens,
                           "completion_tokens": usage.get("completion_tokens"),
                           "reasoning_chars": len(msg.get("reasoning_content") or ""),
                           "vram_peak_sampled_mib": poll.max_mem, "vram_after_mib": gpu_mem(),
                           "thinking_requested": args.thinking, "reasoning_disabled_observed": not bool(msg.get("reasoning_content")),
                           "timings": timings})
            if actual_prompt_tokens is not None and actual_prompt_tokens + args.max_tokens > ctx:
                record["context_warning"] = "prompt+max_tokens exceeds model n_ctx; inspect server behavior"
            print(f"  {quality}: needle@{actual_offset}, actual prompt={actual_prompt_tokens}, "
                  f"elapsed={seconds:.2f}s, peak VRAM={poll.max_mem} MiB, answer={answer[:100]!r}", flush=True)
        except Exception as exc:
            record["error"] = str(exc)
            print(f"  ERROR: {exc}", flush=True)
        results.append(record)
        output.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"  Saved: {output}", flush=True)
    passed = sum(x["status"] == "PASS" for x in results)
    print(f"Finished: {passed}/{len(results)} PASS. Results: {output}")

if __name__ == "__main__":
    main()
