from pathlib import Path
import subprocess
import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/models.yaml"

with CONFIG.open(encoding="utf-8") as file:
    data = yaml.safe_load(file)

model = data["models"]["core"]
inference = model["inference"]
reasoning = inference["reasoning"]

if not isinstance(reasoning, str) or reasoning not in {"on", "off", "auto"}:
    raise ValueError(
        "inference.reasoning phải là chuỗi 'on', 'off' hoặc 'auto'. "
        'Ví dụ trong YAML: reasoning: "off"'
    )

server = ROOT / "runtimes/llama.cpp/build-cuda/bin/llama-server"
model_path = ROOT / model["path"]

if not server.is_file():
    raise SystemExit(f"Không tìm thấy llama-server: {server}")

if not model_path.is_file():
    raise SystemExit(f"Không tìm thấy model: {model_path}")

command = [
    str(server),
    "--model", str(model_path),
    "--alias", model["name"],
    "--host", str(inference["host"]),
    "--port", str(inference["port"]),
    "--n-gpu-layers", str(inference["gpu_layers"]),
    "--ctx-size", str(inference["context_size"]),
    "--parallel", str(inference["parallel"]),
    "--reasoning", reasoning,
]

print("Starting:", model["name"], flush=True)
print("Context:", inference["context_size"], flush=True)
print("API:", f'http://{inference["host"]}:{inference["port"]}', flush=True)

try:
    subprocess.run(command, cwd=ROOT, check=True)
except KeyboardInterrupt:
    print("\nllama-server đã dừng.")
