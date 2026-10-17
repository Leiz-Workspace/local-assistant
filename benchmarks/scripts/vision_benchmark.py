
import argparse
import base64
import json
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "benchmarks/fixtures/multimodal"
RESULTS = ROOT / "benchmarks/results/multimodal"
RESULTS.mkdir(parents=True, exist_ok=True)

parser = argparse.ArgumentParser()
parser.add_argument("--profile", choices=["core", "unrestricted"], required=True)
parser.add_argument("--port", type=int, default=8080)
args = parser.parse_args()

base_url = f"http://127.0.0.1:{args.port}"

def get_json(path):
    with urllib.request.urlopen(base_url + path, timeout=15) as r:
        return json.load(r)

health = get_json("/health")
print("HEALTH:", health)

models = get_json("/v1/models")
model_id = models["data"][0]["id"]
print("MODEL:", model_id)

def image_part(filename):
    path = FIXTURES / filename
    data = base64.b64encode(path.read_bytes()).decode("ascii")
    return {
        "type": "image_url",
        "image_url": {
            "url": f"data:image/png;base64,{data}"
        },
    }

tests = [
    {
        "id": "V01",
        "images": ["ocr.png"],
        "question": (
            "Read the exact CODE and VALUE in this image. "
            "Reply briefly."
        ),
    },
    {
        "id": "V02",
        "images": ["shapes.png"],
        "question": (
            "Describe the shape and color on the LEFT and RIGHT. "
            "Reply briefly."
        ),
    },
    {
        "id": "V03",
        "images": ["image_a.png", "image_b.png"],
        "question": (
            "First image is A, second image is B. "
            "Report the word and background color in each. "
            "Do not mix the two images."
        ),
    },
]

records = []

for case in tests:
    content = [
        {"type": "text", "text": case["question"]}
    ] + [image_part(name) for name in case["images"]]

    payload = {
        "model": model_id,
        "messages": [
            {"role": "user", "content": content}
        ],
        "temperature": 0,
        "max_tokens": 192,
        "stream": False,
    }

    request = urllib.request.Request(
        base_url + "/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    start = time.perf_counter()
    record = {
        "test": case["id"],
        "images": case["images"],
        "question": case["question"],
    }

    try:
        with urllib.request.urlopen(request, timeout=180) as r:
            response = json.load(r)

        record["status"] = "HTTP_OK"
        record["answer"] = response["choices"][0]["message"]["content"]
        record["usage"] = response.get("usage")
        record["elapsed_seconds"] = round(time.perf_counter() - start, 3)
    except urllib.error.HTTPError as exc:
        record["status"] = f"HTTP_{exc.code}"
        record["error"] = exc.read().decode("utf-8", "replace")[:2000]
    except Exception as exc:
        record["status"] = "ERROR"
        record["error"] = str(exc)

    records.append(record)
    print(f"\n=== {case['id']} ===")
    print("STATUS:", record["status"])
    print("ANSWER:", record.get("answer", record.get("error")))

output = RESULTS / f"{args.profile}-vision.json"
output.write_text(
    json.dumps({
        "profile": args.profile,
        "model_id": model_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "tests": records,
    }, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)

print("\nSAVED:", output)
print("Review semantic correctness before marking PASS.")
