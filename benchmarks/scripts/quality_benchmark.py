
import argparse
import json
import re
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

API = "http://127.0.0.1:8080/v1/chat/completions"
OUTPUT_DIR = Path("benchmarks/results/quality")

TESTS = [
    {
        "id": "math_01",
        "category": "mathematics",
        "prompt": "Tính 17 * 23. Chỉ trả về số.",
        "expected": "391",
    },
    {
        "id": "math_02",
        "category": "mathematics",
        "prompt": "Tính tổng các số nguyên từ 1 đến 100. Chỉ trả về số.",
        "expected": "5050",
    },
    {
        "id": "reason_01",
        "category": "reasoning",
        "prompt": (
            "Mọi con mèo đều là động vật. "
            "Một số động vật biết bơi. "
            "Có thể kết luận mọi con mèo đều biết bơi không? "
            "Chỉ trả lời CO hoặc KHONG, không dấu."
        ),
        "expected": "KHONG",
    },
    {
        "id": "reason_02",
        "category": "reasoning",
        "prompt": (
            "Dãy số 2, 6, 12, 20, 30, ? "
            "Số tiếp theo là gì? Chỉ trả về số."
        ),
        "expected": "42",
    },
    {
        "id": "code_01",
        "category": "coding",
        "prompt": (
            "Python: len([1, 2, 3, 4]) cho kết quả gì? "
            "Chỉ trả về số."
        ),
        "expected": "4",
    },
    {
        "id": "code_02",
        "category": "coding",
        "prompt": (
            "Python: print(10 // 3). "
            "Chỉ trả về kết quả được in."
        ),
        "expected": "3",
    },
    {
        "id": "vi_01",
        "category": "vietnamese",
        "prompt": (
            "Từ nào trái nghĩa với 'tăng' trong ngữ cảnh giá cả? "
            "Chỉ trả về một từ."
        ),
        "expected": "giảm",
    },
    {
        "id": "instruction_01",
        "category": "instruction",
        "prompt": (
            "Chỉ in đúng chuỗi sau, không thêm ký tự khác: "
            "SHLDD-READY-2026"
        ),
        "expected": "SHLDD-READY-2026",
    },
    {
        "id": "json_01",
        "category": "json",
        "prompt": (
            'Chỉ trả về JSON object chứa '
            '"status" là "ok" và "count" là số 3.'
        ),
        "expected_json": {"status": "ok", "count": 3},
    },
]

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Tra cứu thời tiết của một thành phố",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {
                        "type": "string",
                        "description": "Tên thành phố",
                    }
                },
                "required": ["city"],
                "additionalProperties": False,
            },
        },
    }
]


def request_chat(payload):
    request = urllib.request.Request(
        API,
        data=json.dumps(
            payload, ensure_ascii=False
        ).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with urllib.request.urlopen(
        request, timeout=180
    ) as response:
        return json.load(response)


def normalize(text):
    return re.sub(
        r"\s+", " ", text.strip()
    ).strip(" .!\n").casefold()


def evaluate(test, answer):
    if "expected_json" in test:
        try:
            return json.loads(answer) == test["expected_json"]
        except (ValueError, TypeError):
            return False

    return normalize(answer) == normalize(test["expected"])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--profile", required=True)
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    results = []

    for test in TESTS:
        payload = {
            "model": args.model,
            "messages": [
                {"role": "user", "content": test["prompt"]}
            ],
            "temperature": 0,
            "max_tokens": 256,
            "stream": False,
        }

        start = time.perf_counter()

        try:
            response = request_chat(payload)
            choice = response["choices"][0]
            answer = choice["message"].get("content") or ""
            passed = (
                choice["finish_reason"] == "stop"
                and evaluate(test, answer)
            )
            error = None
        except Exception as exc:
            answer = ""
            passed = False
            error = str(exc)
            response = {}

        elapsed = time.perf_counter() - start

        results.append({
            "id": test["id"],
            "category": test["category"],
            "passed": passed,
            "answer": answer,
            "error": error,
            "elapsed_seconds": round(elapsed, 3),
            "usage": response.get("usage"),
            "timings": response.get("timings"),
        })

        print(
            f'{"PASS" if passed else "FAIL"} | '
            f'{test["id"]} | {elapsed:.2f}s'
        )

    # Test gọi tool thực tế qua OpenAI-compatible API.
    tool_test = {
        "model": args.model,
        "messages": [
            {
                "role": "user",
                "content": (
                    "Hãy dùng công cụ để tra cứu thời tiết "
                    "tại Hà Nội."
                ),
            }
        ],
        "tools": TOOLS,
        "tool_choice": "required",
        "temperature": 0,
        "max_tokens": 256,
        "stream": False,
    }

    start = time.perf_counter()
    tool_response = None
    tool_error = None

    try:
        tool_response = request_chat(tool_test)
        message = tool_response["choices"][0]["message"]
        calls = message.get("tool_calls") or []

        passed = False
        if len(calls) == 1:
            function = calls[0].get("function", {})
            arguments = json.loads(function.get("arguments", "{}"))
            passed = (
                function.get("name") == "get_weather"
                and arguments == {"city": "Hà Nội"}
            )
    except Exception as exc:
        passed = False
        tool_error = str(exc)

    results.append({
        "id": "tool_01",
        "category": "tool_calling",
        "passed": passed,
        "answer": tool_response,
        "error": tool_error,
        "elapsed_seconds": round(
            time.perf_counter() - start, 3
        ),
    })

    print(
        f'{"PASS" if passed else "FAIL"} | tool_01'
    )

    passed_count = sum(r["passed"] for r in results)
    total = len(results)

    report = {
        "timestamp_utc": datetime.now(
            timezone.utc
        ).isoformat(),
        "profile": args.profile,
        "model": args.model,
        "reasoning_expected": "off",
        "temperature": 0,
        "max_tokens": 256,
        "test_count": total,
        "passed": passed_count,
        "score": passed_count / total,
        "results": results,
    }

    output = OUTPUT_DIR / f"{args.profile}.json"
    output.write_text(
        json.dumps(
            report, indent=2, ensure_ascii=False
        ) + "\n",
        encoding="utf-8",
    )

    print()
    print(f"SCORE: {passed_count}/{total}")
    print(f"ACCURACY: {report['score']:.1%}")
    print(f"SAVED: {output}")


if __name__ == "__main__":
    main()
