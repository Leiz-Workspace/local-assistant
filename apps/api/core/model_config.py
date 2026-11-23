"""Read approved model profiles and their configured digests from configs/models.yaml."""

import logging
from pathlib import Path

import yaml

from src.application.services.special_literals import BOUND_MODEL_SHA256, record_binding

LOGGER = logging.getLogger(__name__)
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
        raise ModelConfigError(f"Missing configuration key: {exc}") from exc
    except (ValueError, TypeError, yaml.YAMLError) as exc:
        raise ModelConfigError(f"Invalid model configuration: {exc}") from exc


def get_model_digests() -> dict:
    """Return the configured sha256 of the core and unrestricted models for the special-literal binding."""
    if not CONFIG.is_file():
        raise ModelConfigError("Model config file not found")
    try:
        with CONFIG.open(encoding="utf-8") as file:
            data = yaml.safe_load(file)
        digests = {
            role: data["models"][role]["sha256"] for role in ("core", "unrestricted")
        }
    except KeyError as exc:
        raise ModelConfigError(f"Missing configuration key: {exc}") from exc
    except (OSError, ValueError, TypeError, yaml.YAMLError) as exc:
        raise ModelConfigError(f"Invalid model configuration: {exc}") from exc
    if any(not isinstance(value, str) for value in digests.values()):
        raise ModelConfigError("Invalid model digest")
    return digests


def bind_special_literals() -> tuple[str, ...]:
    """Record at process start whether the configured models match the pinned special-token list, and log the result."""
    try:
        configured = get_model_digests()
    except ModelConfigError:
        configured = None
    stale = record_binding(configured)
    if stale:
        LOGGER.error(
            "special_literals_binding status=stale roles=%s config=%s",
            ",".join(stale),
            "unreadable" if configured is None else "read",
        )
    else:
        LOGGER.info(
            "special_literals_binding status=ok roles=%s", ",".join(BOUND_MODEL_SHA256)
        )
    return stale
