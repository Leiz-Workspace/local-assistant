"""Verify fixed recording resources, loopback privacy headers and the absence of server-side audio submission."""

import logging
import shutil
import subprocess

import pytest
from fastapi.testclient import TestClient

from apps.voice.main import app

logger = logging.getLogger(__name__)


@pytest.mark.parametrize(
    "path", ["/", "/page.mjs", "/recorder.mjs", "/capture-worklet.js"]
)
def test_fixed_local_assets_have_private_capture_security_headers(path):
    """Expose only a local opt-in surface while denying frames, remote media and cached assets."""
    with TestClient(
        app, base_url="http://127.0.0.1:8091", client=("127.0.0.1", 1234)
    ) as client:
        response = client.get(path)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-frame-options"] == "DENY"
    assert "microphone=(self)" in response.headers["permissions-policy"]
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
    assert "form-action 'none'" in response.headers["content-security-policy"]


@pytest.mark.parametrize(
    "headers",
    [
        {"host": "attacker.example"},
        {"origin": "https://attacker.example"},
        {"x-forwarded-for": "127.0.0.1"},
        {"sec-fetch-site": "cross-site"},
        {"host": "user@localhost"},
        {"host": "localhost/path"},
    ],
)
def test_remote_authority_and_cross_site_requests_cannot_open_recording_surface(
    headers,
):
    """Keep DNS rebinding, proxy headers and external origins outside the local microphone surface."""
    with TestClient(
        app, base_url="http://localhost:8091", client=("127.0.0.1", 1234)
    ) as client:
        response = client.get("/", headers=headers)
    assert response.status_code == 403


def test_remote_peer_and_media_upload_are_denied():
    """Provide no upload or arbitrary file-reading operation even to an otherwise local caller."""
    with TestClient(
        app, base_url="http://localhost:8091", client=("192.0.2.1", 1234)
    ) as client:
        assert client.get("/").status_code == 403
    with TestClient(
        app, base_url="http://localhost:8091", client=("127.0.0.1", 1234)
    ) as client:
        assert client.post("/", content=b"private_audio").status_code == 405
        assert client.get("/configs/models.yaml").status_code == 404
        assert client.get("/openapi.json").status_code == 404


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
def test_no_user_audio_write_or_persistent_storage_endpoint_exists(method, caplog):
    """Reject every write method and keep media bytes outside server logs or files."""
    caplog.set_level("INFO")
    marker = "private-captured-speech-marker"
    with TestClient(
        app, base_url="http://localhost:8091", client=("127.0.0.1", 1234)
    ) as client:
        response = client.request(method, "/", content=marker)
    assert response.status_code == 405
    assert marker not in caplog.text


def test_explicit_recorder_node_lifecycle_and_pcm_controls():
    """Run native JavaScript lifecycle and waveform tests with injected device capabilities and no real recording."""
    node = shutil.which("node")
    assert node, "Node is required to verify the browser recorder source."
    result = subprocess.run(
        [node, "--test", "tests/test_explicit_recording.mjs"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    logger.info("explicit_recording_node_controls exit=%d", result.returncode)
    assert result.returncode == 0, result.stdout + result.stderr
