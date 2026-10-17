
import argparse
import json
import time
import urllib.request
from urllib.error import HTTPError
from datetime import datetime, timezone
from pathlib import Path

API = "http://127.0.0.1:8080/v1/chat/completions"
OUTPUT = Path("benchmarks/results/quality/day11")

SCHEMA = {
    "type": "object",
    "properties": {
        "status": {
            "type": "string",
            "enum": ["ok"]
        },
        "count": {
            "type": "integer",
            "enum": [3]
        }
    },
    "required": ["status", "count"],
    "additionalProperties": False
}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--profile", required=True)
    args = parser.parse_args()

    payload = {
        "model": args.model,
        "messages": [{
            "role": "user",
            "content": (
                'Trả về status="ok" và count=3 '
                "dưới dạng JSON."
            )
        }],
        "temperature": 0,
        "max_tokens": 256,
        "stream": False,
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "benchmark_response",
                "strict": True,
                "schema": SCHEMA
            }
        }
    }

    request = urllib.request.Request(
        API,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    start = time.perf_counter()
    result = None
    error = None
    content = ""
    passed = False

    try:
        with urllib.request.urlopen(
            request, timeout=120
        ) as response:
            result = json.load(response)

        choice = result["choices"][0]
        content = choice["message"].get("content") or ""
        parsed = json.loads(content)

        passed = (
            parsed == {"status": "ok", "count": 3}
            and choice["finish_reason"] == "stop"
        )

    except HTTPError as exc:
        error = (
            f"HTTP {exc.code}: "
            + exc.read().decode(
                "utf-8", errors="replace"
            )
        )
    except (ValueError, KeyError, TypeError) as exc:
        error = str(exc)

    elapsed = time.perf_counter() - start

    report = {
        "timestamp_utc": datetime.now(
            timezone.utc
        ).isoformat(),
        "model": args.model,
        "profile": args.profile,
        "test": "structured_json_schema_01",
        "passed": passed,
        "elapsed_seconds": round(elapsed, 3),
        "content": content,
        "error": error,
        "usage": result.get("usage") if result else None
    }

    OUTPUT.mkdir(parents=True, exist_ok=True)
    path = OUTPUT / f"{args.profile}-structured.json"

    path.write_text(
        json.dumps(
            report, indent=2, ensure_ascii=False
        ) + "\n",
        encoding="utf-8"
    )

    print("MODEL:", args.model)
    print("CONTENT:", content)
    print("PASS:", passed)
    print("TIME:", round(elapsed, 3), "s")
    print("ERROR:", error)
    print("SAVED:", path)

if __name__ == "__main__":
    main()
