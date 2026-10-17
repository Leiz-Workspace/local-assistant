
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
CONFIG = ROOT / "configs/models.yaml"


class ModelConfigError(Exception):
    pass


def get_model_profile(profile: str) -> dict:
    if not CONFIG.is_file():
        raise ModelConfigError("Model config file not found")

    try:
        with CONFIG.open(encoding="utf-8") as file:
            data = yaml.safe_load(file)

        models = data["models"]
        model = models[profile]
        inference = model["inference"]

        name = model["name"]
        host = inference["host"]
        port = int(inference["port"])

        if not isinstance(name, str) or not name:
            raise ValueError("Invalid model name")

        if host not in ("127.0.0.1", "localhost", "::1"):
            raise ValueError("Model gateway requires loopback host")

        if not 1 <= port <= 65535:
            raise ValueError("Invalid model port")

        return {
            "profile": profile,
            "model_id": name,
            "base_url": f"http://127.0.0.1:{port}",
        }

    except KeyError as exc:
        raise ModelConfigError(
            f"Missing configuration key: {exc}"
        ) from exc
    except (ValueError, TypeError, yaml.YAMLError) as exc:
        raise ModelConfigError(
            f"Invalid model configuration: {exc}"
        ) from exc
