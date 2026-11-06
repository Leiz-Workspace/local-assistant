"""Run one credential-free embedding comparison process in the locked evaluation environment."""
# /// script
# requires-python = ">=3.12,<3.13"
# dependencies = ["torch==2.10.0+cpu", "transformers==4.57.6", "numpy==2.5.4", "httpx==0.28.1", "typing-extensions==4.15.0"]
# [tool.uv.sources]
# torch = { index = "pytorch-cpu" }
# [[tool.uv.index]]
# name = "pytorch-cpu"
# url = "https://download.pytorch.org/whl/cpu"
# explicit = true
# ///

import argparse
import json
import logging
import resource
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main():
    """Execute an isolated measured model only after environment/dependency provisioning completes."""
    from scripts.qwen_embedding_comparison import measure_one

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", choices=["qwen", "e5"], required=True)
    args = parser.parse_args()
    resource.setrlimit(resource.RLIMIT_AS, (8 * 1024**3, 8 * 1024**3))
    resource.setrlimit(resource.RLIMIT_CPU, (480, 481))
    print(json.dumps(measure_one(args.candidate)))
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    raise SystemExit(main())
