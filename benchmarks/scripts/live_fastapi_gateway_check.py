#!/usr/bin/env python3
"""Live FastAPI -> llama-server smoke test. Stdlib only. Never manages containers."""
from __future__ import annotations
import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


def http(url: str, body=None, timeout=120):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST" if data is not None else "GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            raw = res.read().decode()
            return res.status, json.loads(raw)
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code} {url}: {e.read().decode()[:1600]}") from e


def post_paths(schema):
    return [(path, spec["post"]) for path, spec in schema.get("paths", {}).items() if isinstance(spec, dict) and "post" in spec]


def choose_path(schema):
    candidates = [(path, spec) for path, spec in post_paths(schema) if "chat" in path.lower() or "complet" in path.lower()]
    if len(candidates) != 1:
        raise RuntimeError(f"Cannot unambiguously select a chat POST route. Candidates: {[x[0] for x in candidates]}. Pass --api-path explicitly after reviewing /openapi.json")
    return candidates[0][0]


def pull_text(o):
    if isinstance(o, str):
        return o
    if isinstance(o, dict):
        if "choices" in o and isinstance(o["choices"], list):
            return " ".join(pull_text(x) for x in o["choices"])
        return " ".join(pull_text(v) for k, v in o.items() if k in {"content", "message", "answer", "response", "output", "text"})
    if isinstance(o, list):
        return " ".join(pull_text(x) for x in o)
    return ""


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--profile", choices=["core", "unrestricted"], required=True)
    ap.add_argument("--api-base", default="http://127.0.0.1:8000")
    ap.add_argument("--llama-base", default="http://127.0.0.1:8080")
    ap.add_argument("--api-path", help="Override auto-discovered FastAPI chat endpoint")
    ap.add_argument("--body-json", help="Exact request JSON for your FastAPI endpoint, if schema differs from OpenAI-compatible payload")
    ap.add_argument("--output-dir", default="benchmarks/results/live-gateway")
    ap.add_argument("--execute", action="store_true")
    args = ap.parse_args()
    expected = "qwen3.5-9b-" + args.profile
    print(f"Expected llama model: {expected}; API: {args.api_base}; llama: {args.llama_base}")
    print("READ ONLY: no Docker or Compose mutations.")
    if not args.execute:
        print("DRY RUN. Use --execute after starting FastAPI and the correct model.")
        return 0
    _, health = http(args.llama_base.rstrip("/") + "/health")
    if health.get("status") != "ok":
        raise RuntimeError(f"llama not ready: {health}")
    _, models = http(args.llama_base.rstrip("/") + "/v1/models")
    ids = [m.get("id") for m in models.get("data", [])]
    if expected not in ids:
        raise RuntimeError(f"Wrong llama model active: {ids}, expected {expected}")
    _, schema = http(args.api_base.rstrip("/") + "/openapi.json")
    path = args.api_path or choose_path(schema)
    if not path.startswith("/"):
        raise RuntimeError("--api-path must begin with /")
    if path not in [p for p, _ in post_paths(schema)]:
        raise RuntimeError(f"Route {path} is not registered as POST in FastAPI OpenAPI")
    sentinel = "GATEWAY-LIVE-VERIFICATION-713"
    question = f"Return exactly this marker and nothing else: {sentinel}"
    body = json.loads(Path(args.body_json).read_text()) if args.body_json else {
        "model": expected, "messages": [{"role": "user", "content": question}], "max_tokens": 256, "temperature": 0
    }
    if args.body_json:
        print("NOTE: custom JSON body in use. Ensure its prompt asks to echo the marker for full positive verification.")
    start = time.perf_counter()
    status, answer = http(args.api_base.rstrip("/") + path, body, timeout=180)
    elapsed = round(time.perf_counter() - start, 3)
    text = pull_text(answer)
    matched = sentinel in text
    result = {"status": "PASS" if matched else "UNVERIFIED", "profile": args.profile, "model": expected,
              "fastapi_route": path, "http_status": status, "elapsed_s": elapsed,
              "marker_found": matched, "extracted_response": text[:1200], "raw_response": answer}
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    dest = out / f"live-{args.profile}-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}.json"
    dest.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"{result['status']}: route={path}, status={status}, elapsed={elapsed}s, marker_found={matched}\nSaved: {dest}")
    if not matched:
        print("Endpoint responded, but live model routing is NOT yet proven. Inspect raw_response, request schema and FastAPI logs.")
    return 0 if matched else 2


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print(f"FAIL: {e}", file=sys.stderr)
        sys.exit(1)
