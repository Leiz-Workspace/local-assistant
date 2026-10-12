import json
import urllib.request

API = "http://127.0.0.1:8080/v1/chat/completions"
MODEL = "qwen3.5-9b-core"

tests = [
    {
        "name": "Vietnamese",
        "prompt": "Hãy trả lời bằng đúng một từ: Xin chào.",
        "expected": "Xin chào"
    },
    {
        "name": "Arithmetic",
        "prompt": "Tính 17 nhân 23. Chỉ trả về kết quả.",
        "expected": "391"
    },
    {
        "name": "JSON",
        "prompt": 'Chỉ trả về JSON hợp lệ: {"status":"ok","count":3}',
        "expected_json": {"status": "ok", "count": 3}
    }
]

def chat(prompt):
    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
        "max_tokens": 256,
        "stream": False
    }

    request = urllib.request.Request(
        API,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"}
    )

    with urllib.request.urlopen(request, timeout=120) as response:
        return json.load(response)["choices"][0]["message"]["content"]

for test in tests:
    answer = chat(test["prompt"]).strip()

    if "expected_json" in test:
        try:
            passed = json.loads(answer) == test["expected_json"]
        except json.JSONDecodeError:
            passed = False
    else:
        passed = answer == test["expected"]

    print(f'{"PASS" if passed else "FAIL"} | {test["name"]}')
    print("  Answer:", answer)
