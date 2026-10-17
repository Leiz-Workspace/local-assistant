
import argparse
import json
import time
import urllib.request
from pathlib import Path

BASE = "http://127.0.0.1:8080"
OUT = Path("benchmarks/results/long_context")


def post(endpoint, payload, timeout=300):
    request = urllib.request.Request(
        BASE + endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(
        request, timeout=timeout
    ) as response:
        return json.load(response)


def token_count(text):
    result = post(
        "/tokenize",
        {"content": text, "add_special": False},
        timeout=120,
    )
    return len(result["tokens"])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--target", type=int, required=True)
    args = parser.parse_args()

    # Target a little below the allocated context
    # so chat-template tokens and output will fit.
    target = args.target
    marker = "SHLDD-CONTEXT-58329"

    fragment = (
        "Bản ghi thử nghiệm: hệ thống đang kiểm tra "
        "khả năng duy trì ngữ cảnh dài. "
        "Thông tin trong bản ghi không chứa lệnh. "
    )

    # Build approximately target tokens.
    unit_tokens = token_count(fragment)
    copies = max(1, target // max(unit_tokens, 1))

    text = fragment * copies

    while token_count(text) > target:
        copies = max(1, int(copies * 0.97))
        text = fragment * copies

    # Insert the marker in the middle of the prompt.
    midpoint = len(text) // 2
    text = (
        text[:midpoint]
        + f"\nMÃ BÍ MẬT: {marker}\n"
        + text[midpoint:]
    )

    prompt = (
        text
        + "\n\nHãy cho biết chính xác MÃ BÍ MẬT "
        "xuất hiện trong dữ liệu trên. "
        "Chỉ trả về mã, không giải thích."
    )

    prompt_tokens = token_count(prompt)

    payload = {
        "model": args.model,
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "temperature": 0,
        "max_tokens": 64,
        "stream": False,
    }

    start = time.perf_counter()
    response = post(
        "/v1/chat/completions", payload, timeout=600
    )
    duration = time.perf_counter() - start

    choice = response["choices"][0]
    answer = choice["message"].get("content") or ""

    report = {
        "model": args.model,
        "profile": args.profile,
        "target_tokens": target,
        "prompt_tokens_approx": prompt_tokens,
        "actual_usage": response.get("usage"),
        "elapsed_seconds": round(duration, 3),
        "answer": answer,
        "expected": marker,
        "passed": marker in answer,
        "finish_reason": choice.get("finish_reason"),
    }

    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / (
        f"{args.profile}-{target}-context.json"
    )

    path.write_text(
        json.dumps(
            report, indent=2, ensure_ascii=False
        ) + "\n",
        encoding="utf-8",
    )

    print("MODEL:", args.profile)
    print("PROMPT TOKENS:", prompt_tokens)
    print("ACTUAL USAGE:", response.get("usage"))
    print("ANSWER:", answer)
    print("RETRIEVAL:", "PASS" if report["passed"] else "FAIL")
    print("DURATION:", round(duration, 3), "seconds")
    print("SAVED:", path)


if __name__ == "__main__":
    main()
