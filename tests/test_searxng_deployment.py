"""Validate the new isolated search deployment and content-free container log formatter before starting it."""

import importlib.util
import json
import logging
import os
import subprocess
from pathlib import Path

import pytest
import yaml

logger = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parents[2] / "infras/searxng-server"


def formatter():
    """Load only the newly authored metadata formatter without importing provider application code."""
    spec = importlib.util.spec_from_file_location(
        "searxng_test_log_policy", ROOT / "log_policy.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.MetadataOnlyFormatter()


@pytest.mark.parametrize(
    "name,scope",
    [
        ("searx", "search"),
        ("searx.engines.bing", "search"),
        ("granian", "http_server"),
        ("granian.access", "http_server"),
        ("private-name-fixture", "external"),
        ("searxEvil", "external"),
    ],
)
@pytest.mark.parametrize(
    "level,label", [(logging.ERROR, "ERROR"), (logging.INFO, "INFO"), (999, "UNKNOWN")]
)
def test_log_message_arguments_exceptions_and_names_cannot_escape(
    name, scope, level, label
):
    """Keep only finite categories even when messages, arguments, exceptions and stacks contain private data."""
    record = logging.LogRecord(
        name,
        level,
        "private-file",
        42,
        "private-message %s",
        ("private-argument",),
        (RuntimeError, RuntimeError("private-exception"), None),
    )
    record.stack_info = "private-stack"
    record.levelname = "private-levelname"
    record.exc_text = "private-cached-exception"
    raw = formatter().format(record)
    assert json.loads(raw) == dict(level=label, scope=scope)
    assert "private-" not in raw


def test_compose_isolated_loopback_resource_and_capability_contract():
    """Reject shared stacks, public binds, host sockets, writable roots and unbounded/GPU resources."""
    config = yaml.safe_load((ROOT / "searxng-compose.yaml").read_text())
    assert config["name"] == "local-assistant-search" and set(config["services"]) == {
        "searxng"
    }
    service = config["services"]["searxng"]
    assert service["image"].endswith(
        "@sha256:aa7270053bc3bf92155e2af83e2b0a7c3833c209cdeb8d396861a00c55ee7110"
    )
    assert service["ports"] == ["127.0.0.1:8889:8080"]
    assert service["read_only"] and service["cap_drop"] == ["ALL"]
    assert service["user"] == "searxng:searxng"
    assert service["security_opt"] == ["no-new-privileges:true"]
    assert service["mem_limit"] == service["memswap_limit"] == "768m"
    assert service["cpus"] == 1.0 and service["pids_limit"] == 128
    assert all(
        path.endswith(":ro") and "docker.sock" not in path
        for path in service["volumes"]
    )
    assert not set(service) & {"privileged", "gpus", "network_mode", "devices"}
    assert "networks" not in config and "volumes" not in config


def test_settings_enable_only_declared_engines_and_json_without_user_data():
    """Keep a private singleton-engine JSON tool without autocomplete, proxy images or persisted signing secrets."""
    config = yaml.safe_load((ROOT / "config/settings.yml").read_text())
    assert config["use_default_settings"]["engines"]["keep_only"] == ["brave"]
    assert all(row["disabled"] is False for row in config["engines"])
    assert config["search"]["formats"] == ["json"] and config["search"]["max_page"] == 1
    assert (
        not config["search"]["autocomplete"]
        and not config["search"]["favicon_resolver"]
    )
    assert config["server"]["secret_key"] is None
    assert all(
        config["server"][name] is False
        for name in ["public_instance", "limiter", "image_proxy"]
    )
    assert (
        config["general"]["debug"] is False
        and config["general"]["enable_metrics"] is False
    )
    logs = json.loads((ROOT / "config/logging.json").read_text())
    assert (
        logs["description"]
        and logs["formatters"]["metadata"]["()"]
        == "local_log_policy.MetadataOnlyFormatter"
    )
    service = yaml.safe_load((ROOT / "searxng-compose.yaml").read_text())["services"][
        "searxng"
    ]
    assert service["environment"]["GRANIAN_LOG_ACCESS_ENABLED"] == "false"


def test_actual_compose_schema_without_pull_or_start():
    """Validate the installed Compose schema with a synthetic secret and no daemon mutation."""
    environment = dict(os.environ, SEARXNG_SECRET="synthetic-test-signing-secret")
    result = subprocess.run(
        [
            "docker",
            "compose",
            "-f",
            str(ROOT / "searxng-compose.yaml"),
            "config",
            "--quiet",
        ],
        env=environment,
        capture_output=True,
        text=True,
        timeout=10,
    )
    logger.info("searxng_compose_schema_checked exit_code=%d", result.returncode)
    assert result.returncode == 0, result.stderr
