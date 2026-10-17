
import argparse
import base64
import json
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FRAMES = ROOT / "benchmarks/fixtures/multimodal/extracted"
RESULTS = ROOT / "benchmarks/results/multimodal"
RESULTS.mkdir(parents=True, exist_ok=True)

parser = argparse.ArgumentParser()
parser.add_argument(
    "--profile",
    choices=["core", "unrestricted"],
    required=True,
)
args = parser.parse_args()

base_url = "http://127.0.0.1:8080"

with urllib.request.urlopen(base_url + "/v1/models") as r:
    models = json.load(r)

model_id = models["data"][0]["id"]
expected = f"qwen3.5-9b-{args.profile}"

if model_id != expected:
    raise SystemExit(
        f"Wrong model loaded: {model_id}. Expected: {expected}"
    )

content = [{
    "type": "text",
    "text": (
        "The following images are frames sampled from a video. "
        "Each image has an explicit timestamp in seconds. "
        "Analyze the background colors and identify the first "
        "timestamp where each NEW color appears. "
        "Return only JSON with keys: colors, "
        "first_appearance_seconds, transition_seconds. "
        "All timestamps must be numbers."
    )
}]

for index, path in enumerate(sorted(FRAMES.glob("frame_*.png"))):
    content.append({
        "type": "text",
        "text": f"Video frame timestamp: {index} seconds."
    })

    encoded = base64.b64encode(
        path.read_bytes()
    ).decode("ascii")

    content.append({
        "type": "image_url",
        "image_url": {
            "url": f"data:image/png;base64,{encoded}"
        },
    })

payload = {
    "model": model_id,
    "messages": [{
        "role": "user",
        "content": content,
    }],
    "temperature": 0,
    "max_tokens": 256,
    "stream": False,
}

request = urllib.request.Request(
    base_url + "/v1/chat/completions",
    data=json.dumps(payload).encode("utf-8"),
    headers={"Content-Type": "application/json"},
    method="POST",
)

with urllib.request.urlopen(request, timeout=180) as r:
    result = json.load(r)

answer = result["choices"][0]["message"]["content"]

print("\nMODEL:", model_id)
print("ANSWER:")
print(answer)

output = RESULTS / f"{args.profile}-video-frames.json"
output.write_text(
    json.dumps({
        "model": model_id,
        "answer": answer,
        "usage": result.get("usage"),
    }, indent=2, ensure_ascii=False) + "\n",
    encoding="utf-8",
)

print("\nSAVED:", output)
