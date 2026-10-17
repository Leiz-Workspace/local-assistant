
import argparse
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/models.yaml"

def main():
    parser = argparse.ArgumentParser(
        description="Start Personal AI model using llama.cpp"
    )
    parser.add_argument(
        "--profile",
        choices=["core", "unrestricted"],
        required=True,
    )
    parser.add_argument(
        "--vision",
        action="store_true",
        help="Enable multimodal projector",
    )
    args = parser.parse_args()

    with CONFIG.open(encoding="utf-8") as file:
        config = yaml.safe_load(file)

    model = config["models"][args.profile]
    inference = model["inference"]

    server = (
        ROOT
        / "runtimes/llama.cpp/build-cuda/bin/llama-server"
    )
    model_path = ROOT / model["path"]

    if not server.is_file():
        raise SystemExit(f"Missing llama-server: {server}")

    if not model_path.is_file():
        raise SystemExit(f"Missing model: {model_path}")

    reasoning = inference["reasoning"]

    if reasoning not in ("on", "off", "auto"):
        raise SystemExit(
            'reasoning must be "on", "off" or "auto"'
        )

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

    print(f"Profile: {args.profile}", flush=True)
    print(f"Model: {model['name']}", flush=True)
    print(f"Context: {inference['context_size']}", flush=True)
    print(
        f"API: http://{inference['host']}:{inference['port']}",
        flush=True
    )
    if args.vision:
        mmproj_path = model.get("mmproj_path")
    
        if not mmproj_path:
            raise SystemExit(
                "mmproj_path is missing from models.yaml"
            )
    
        mmproj = ROOT / mmproj_path
    
        if not mmproj.is_file():
            raise SystemExit(f"Missing projector: {mmproj}")
    
        command.extend([
            "--mmproj", str(mmproj),
            "--mmproj-offload",
        ])
    
        print(f"Vision enabled: {mmproj.name}", flush=True)
    else:
        # Keep text-only behavior explicit and reproducible.
        command.append("--no-mmproj")
        
    try:
        subprocess.run(command, cwd=ROOT, check=True)
    except KeyboardInterrupt:
        print("\nModel stopped.")

if __name__ == "__main__":
    main()
