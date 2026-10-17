
import argparse
import json
import re
import subprocess
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

API = "http://127.0.0.1:8080/v1/chat/completions"
IMAGE = "sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1"
OUT = Path("benchmarks/results/quality/day11")

TASKS = [
    {
        "id": "floor_division",
        "prompt": (
            "Viết hàm Python solve(a, b) trả về kết quả "
            "phép chia lấy phần nguyên a // b. "
            "Chỉ xuất mã Python, không giải thích."
        ),
        "tests": """
assert solve(10, 3) == 3
assert solve(-10, 3) == -4
assert solve(0, 5) == 0
""",
    },
    {
        "id": "unique_preserve_order",
        "prompt": (
            "Viết hàm Python solve(items) loại bỏ phần tử "
            "trùng lặp trong list số nguyên, giữ nguyên "
            "thứ tự xuất hiện. Chỉ xuất mã Python."
        ),
        "tests": """
assert solve([2, 1, 2, 3, 1]) == [2, 1, 3]
assert solve([]) == []
assert solve([5, 5, 5]) == [5]
""",
    },
    {
        "id": "palindrome",
        "prompt": (
            "Viết hàm Python solve(text) kiểm tra chuỗi "
            "có phải palindrome không, không phân biệt "
            "hoa thường và bỏ qua khoảng trắng. "
            "Chỉ xuất mã Python."
        ),
        "tests": """
assert solve("Race car") is True
assert solve("hello") is False
assert solve("A") is True
""",
    },
]


def generate(model, prompt):
    payload = {
        "model": model,
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "temperature": 0,
        "max_tokens": 512,
        "stream": False,
    }

    req = urllib.request.Request(
        API,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.load(resp)

    choice = data["choices"][0]
    return (
        choice["message"].get("content") or "",
        choice["finish_reason"],
    )


def extract_code(answer):
    match = re.fullmatch(
        r"\s*```(?:python|py)?\s*\n(.*?)\n```\s*",
        answer,
        re.DOTALL | re.IGNORECASE,
    )
    return match.group(1) if match else answer


def run_in_sandbox(code, tests):
    # Chỉ truyền dữ liệu qua stdin.
    # Không mount workspace hoặc Docker socket.
    program = code + "\n\n" + tests + "\nprint('TESTS_PASSED')\n"

    command = [
        "docker", "run", "--rm", "-i",
        "--network", "none",
        "--read-only",
        "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges",
        "--user", "65534:65534",
        "--pids-limit", "64",
        "--memory", "512m",
        "--memory-swap", "512m",
        "--cpus", "1",
        "--tmpfs", "/tmp:rw,nosuid,nodev,noexec,size=64m,mode=1777",
        IMAGE,
        "python", "-B", "-",
    ]

    try:
        process = subprocess.run(
            command,
            input=program,
            text=True,
            capture_output=True,
            timeout=20,
            check=False,
        )
        return {
            "passed": (
                process.returncode == 0
                and "TESTS_PASSED" in process.stdout
            ),
            "returncode": process.returncode,
            "stdout": process.stdout[:4000],
            "stderr": process.stderr[:4000],
        }
    except subprocess.TimeoutExpired:
        return {
            "passed": False,
            "returncode": None,
            "stdout": "",
            "stderr": "Sandbox timeout (20s)",
        }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--profile", required=True)
    args = parser.parse_args()

    results = []

    for task in TASKS:
        started = time.perf_counter()
        answer = ""
        finish_reason = None

        try:
            answer, finish_reason = generate(
                args.model, task["prompt"]
            )
            code = extract_code(answer)

            if finish_reason != "stop":
                result = {
                    "passed": False,
                    "stderr": "Generation did not finish normally",
                }
            elif len(code) > 20000:
                result = {
                    "passed": False,
                    "stderr": "Generated code exceeds size limit",
                }
            else:
                result = run_in_sandbox(
                    code, task["tests"]
                )
        except Exception as exc:
            result = {
                "passed": False,
                "stderr": str(exc),
            }

        record = {
            "id": task["id"],
            "passed": result["passed"],
            "answer": answer,
            "finish_reason": finish_reason,
            "sandbox": result,
            "elapsed_seconds": round(
                time.perf_counter() - started, 3
            ),
        }

        results.append(record)
        print(
            f'{"PASS" if result["passed"] else "FAIL"}'
            f' | {task["id"]}'
            f' | {record["elapsed_seconds"]:.2f}s'
        )

    report = {
        "timestamp_utc": datetime.now(
            timezone.utc
        ).isoformat(),
        "model": args.model,
        "profile": args.profile,
        "passed": sum(r["passed"] for r in results),
        "total": len(results),
        "results": results,
    }

    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{args.profile}-coding.json"

    path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"\nSCORE: {report['passed']}/{report['total']}")
    print(f"SAVED: {path}")


if __name__ == "__main__":
    main()
