"""Provide private authentication files for HTTP tests without runtime credential bypasses."""

import hashlib
import json
import logging
import secrets
from uuid import uuid4

import pytest

from src.application.services.special_literals import reset_binding_for_tests

logger = logging.getLogger(__name__)


@pytest.fixture(autouse=True)
def unrecorded_special_literal_binding():
    """Start and end every test unrecorded, because application startup records the model binding process-wide."""
    reset_binding_for_tests()
    yield
    reset_binding_for_tests()


@pytest.fixture
def auth_settings(tmp_path, monkeypatch):
    """Create two isolated test principals and a private digest-only auth configuration."""
    tokens = [secrets.token_urlsafe(48) for _ in range(2)]
    principals = [uuid4(), uuid4()]
    path = tmp_path / "principals.json"
    path.write_text(
        json.dumps(
            {
                "principals": [
                    {
                        "id": str(principal),
                        "token_sha256": hashlib.sha256(token.encode()).hexdigest(),
                    }
                    for principal, token in zip(principals, tokens)
                ]
            }
        )
    )
    path.chmod(0o600)
    monkeypatch.setenv("ASSISTANT_AUTH_FILE", str(path))
    logger.info("test_auth_configuration_created principals=2")
    return {
        "path": path,
        "tokens": tokens,
        "principals": principals,
        "headers": [{"Authorization": "Bearer " + token} for token in tokens],
    }
