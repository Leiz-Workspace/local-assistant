"""Serve actual main voice assets/auth in an isolated browser fixture that forbids all native runtime creation."""

import logging
import os

from fastapi import FastAPI

from apps.api.voice import compose

LOGGER = logging.getLogger(__name__)


def forbidden_runtime(*args):
    """Fail if a browser test escapes its authored model API stubs and attempts native preparation."""
    LOGGER.error("main_browser_native_creation_forbidden")
    raise AssertionError("browser_test_has_no_model_capability")


def create_app():
    """Compose real static/identity routes with disposable test auth and no inference implementation."""
    LOGGER.info("main_browser_fixture_composed models=0")
    return compose(
        FastAPI(),
        auth_file=os.environ["ASSISTANT_AUTH_FILE"],
        runtime_factory=forbidden_runtime,
    )
