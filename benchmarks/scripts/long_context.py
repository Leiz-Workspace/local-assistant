
import json
import random
import time
import urllib.request
from urllib.error import HTTPError
from datetime import datetime, timezone
from pathlib import Path

API = "http://127.0.0.1:8080"
MODEL = "qwen3.5-9b-core"
CONTEXT_SIZE = 16384
TARGET_TOKENS = 12000
MAX_OUTPUT_TOKENS = 256

OUTPUT = Path(
    "benchmarks/results/qwen3.5-9b-q6k/long-context.json"
)

FACTS = {
    "dau": "SHLDD-ALPHA-7291",
    "giua": "SHLDD-BETA-4836",
    "cuoi": "SHLDD-GAMMA-9514",
}

PHRASES = [
    "Hệ thống lưu trữ tài liệu theo định danh và phiên bản.",
    "Bộ điều phối quản lý trạng thái công cụ.",
    "Quy trình kiểm thử đo hiệu năng mô hình.",
    "Các sự kiện được ghi nhận để hỗ trợ truy vết.",
    "Dữ liệu đầu vào được xác minh trước khi xử lý.",
    "Bộ nhớ truy xuất cung cấp thông tin liên quan.",
]

random.seed(42)


def post(path, payload, timeout=300):
    req = urllib.request.Request(
        API + path,
        data=json.dumps(
            payload, ensure_ascii=False
        ).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(
            req, timeout=timeout
        ) as response:
            return json.load(response)
    except HTTPError as error:
        print("HTTP Error:", error.code)
        print(error.read().decode(
            "utf-8", errors="replace"
        ))
        raise SystemExit(1)


def count_tokens(text):
    result = post(
        "/tokenize",
        {"content": text, "add_special": False},
    )
    return len(result["tokens"])


def create_prompt(number_of_records):
    rng = random.Random(42)

    paragraphs = [
        (
            f"Bản ghi {i:05d}: "
            f"{rng.choice(PHRASES)} "
            f"Mã mục {rng.randint(100000, 999999)}."
        )
        for i in range(number_of_records)
    ]

    positions = [
        (max(1, number_of_records // 20), "ĐẦU", FACTS["dau"]),
        (number_of_records // 2, "GIỮA", FACTS["giua"]),
        (number_of_records * 19 // 20, "CUỐI", FACTS["cuoi"]),
    ]

    for index, name, code in positions:
        paragraphs[index] += (
            f" MÃ BÍ MẬT VỊ TRÍ {name}: {code}."
        )

    document = "\n".join(paragraphs)

    return (
        "Đọc tài liệu và tìm chính xác ba mã bí mật "
        "vị trí ĐẦU, GIỮA, CUỐI. "
        'Trả lời JSON với key "dau", "giua", "cuoi".'
        "\n\n" + document
    )


# Tìm số bản ghi sao cho độ dài gần 12K token,
# nhưng không vượt quá mục tiêu.
low, high = 10, 2000
best_prompt = None
best_count = 0

while low <= high:
    mid = (low + high) // 2
    candidate = create_prompt(mid)
    tokens = count_tokens(candidate)

    if tokens <= TARGET_TOKENS:
        best_prompt = candidate
        best_count = tokens
        low = mid + 1
    else:
        high = mid - 1

if best_prompt is None:
    raise RuntimeError("Không tạo được prompt phù hợp")

print("Prompt tokens (/tokenize):", best_count)

# Chừa dư địa cho chat template và response.
if best_count + MAX_OUTPUT_TOKENS + 128 > CONTEXT_SIZE:
    raise RuntimeError("Prompt vượt context budget")

payload = {
    "model": MODEL,
    "messages": [
        {"role": "user", "content": best_prompt}
    ],
    "temperature": 0,
    "max_tokens": MAX_OUTPUT_TOKENS,
    "stream": False,
}

start = time.perf_counter()
result = post("/v1/chat/completions", payload)
elapsed = time.perf_counter() - start

choice = result["choices"][0]
answer = choice["message"].get("content", "")

scores = {
    key: value in answer
    for key, value in FACTS.items()
}

record = {
    "timestamp": datetime.now(
        timezone.utc
    ).isoformat(),
    "model": MODEL,
    "context_size": CONTEXT_SIZE,
    "target_tokens": TARGET_TOKENS,
    "estimated_prompt_tokens": best_count,
    "actual_prompt_tokens": result.get(
        "usage", {}
    ).get("prompt_tokens"),
    "completion_tokens": result.get(
        "usage", {}
    ).get("completion_tokens"),
    "finish_reason": choice["finish_reason"],
    "expected": FACTS,
    "answer": answer,
    "scores": scores,
    "accuracy": sum(scores.values()) / len(scores),
    "elapsed_seconds": elapsed,
    "timings": result.get("timings", {}),
}

OUTPUT.parent.mkdir(parents=True, exist_ok=True)

OUTPUT.write_text(
    json.dumps(
        record, indent=2, ensure_ascii=False
    ) + "\n",
    encoding="utf-8",
)

print("Actual prompt tokens:", record["actual_prompt_tokens"])
print("Time:", round(elapsed, 2), "s")
print("Answer:", answer)
print("Scores:", scores)
print("Accuracy:", f"{record['accuracy']:.0%}")
print("Finish reason:", record["finish_reason"])
print("Saved:", OUTPUT)
