"""Provide a loopback-only HTTP client and private credential-file handling for the CLI."""

import hashlib
import json
import logging
import os
import secrets
import stat
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

import httpx

LOGGER = logging.getLogger(__name__)
DEFAULT_TOKEN = Path.home() / ".local/state/local-assistant/token"
DEFAULT_AUTH = DEFAULT_TOKEN.with_name("principals.json")


def initialize_auth(token_path, auth_path):
    """Create an isolated local principal without overwriting existing authentication files."""
    token_path, auth_path = Path(token_path), Path(auth_path)
    if (
        token_path.absolute() == auth_path.absolute()
        or token_path.exists()
        or auth_path.exists()
    ):
        raise ClientError("initialization_requires_new_files", 5)
    token, owner = secrets.token_urlsafe(48), uuid4()
    created = []
    try:
        save_token(token_path, token)
        created.append(token_path)
        auth_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        descriptor = os.open(
            auth_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
        )
        created.append(auth_path)
        with os.fdopen(descriptor, "w") as output:
            json.dump(
                {
                    "principals": [
                        {
                            "id": str(owner),
                            "token_sha256": hashlib.sha256(token.encode()).hexdigest(),
                        }
                    ]
                },
                output,
            )
    except Exception:
        for path in created:
            path.unlink(missing_ok=True)
        raise
    LOGGER.info("cli_isolated_auth_initialized principal_id=%s", owner)
    return {
        "principal_id": str(owner),
        "auth_file": str(auth_path),
        "token_file": str(token_path),
        "existing_credentials_changed": False,
    }


class ClientError(Exception):
    """Carry a redacted error code and stable CLI exit category."""

    def __init__(self, code, exit_code=1):
        """Expose only a finite public diagnostic instead of arbitrary HTTP response bodies."""
        self.code, self.exit_code = code, exit_code
        super().__init__(code)


def validate_token(value):
    """Require the same bounded non-whitespace ASCII credential shape as the application."""
    if (
        not isinstance(value, str)
        or not 32 <= len(value) <= 512
        or not value.isascii()
        or any(c.isspace() for c in value)
    ):
        raise ClientError("invalid_credential", 3)
    return value


def read_token(path):
    """Load an owner-only regular token file without following its final symlink."""
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(descriptor, "rb") as stream:
            info = os.fstat(stream.fileno())
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_uid != os.geteuid()
                or info.st_mode & 0o077
                or info.st_nlink != 1
                or info.st_size > 514
            ):
                raise ValueError()
            value = stream.read(514).decode().strip()
        return validate_token(value)
    except (OSError, ValueError, UnicodeError):
        raise ClientError("private_token_file_required", 3) from None


def save_token(path, value):
    """Create a new private credential file without overwriting an existing file or symlink."""
    value = validate_token(value)
    path = Path(path)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        descriptor = os.open(
            path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
        )
        with os.fdopen(descriptor, "w") as stream:
            stream.write(value)
    except OSError:
        raise ClientError("credential_file_exists_or_unwritable", 5) from None
    LOGGER.info("cli_credential_saved")


class ApiClient:
    """Send credentials only to an explicit direct loopback HTTP endpoint with redirects disabled."""

    def __init__(self, url, token=None, *, transport=None):
        """Reject remote hosts, URL credentials, paths, proxy use and insecure redirect credential forwarding."""
        parsed = urlsplit(url)
        if (
            parsed.scheme != "http"
            or parsed.hostname not in {"127.0.0.1", "::1"}
            or parsed.username
            or parsed.password
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
        ):
            raise ClientError("direct_loopback_url_required", 2)
        self.url, self.token, self.transport = url.rstrip("/"), token, transport

    def request(self, method, path, payload=None, *, timeout=125):
        """Return a bounded JSON response and map HTTP failures to safe stable exit categories."""
        headers = {"Content-Type": "application/json"}
        if self.token is not None:
            headers["Authorization"] = "Bearer " + validate_token(self.token)
        try:
            with httpx.Client(
                base_url=self.url,
                headers=headers,
                timeout=timeout,
                trust_env=False,
                follow_redirects=False,
                transport=self.transport,
            ) as client:
                response = client.request(method, path, json=payload)
        except httpx.HTTPError:
            raise ClientError("server_unavailable", 6) from None
        if response.status_code >= 300:
            category = {401: 3, 403: 4, 404: 6, 409: 5, 422: 2, 429: 7, 503: 6}.get(
                response.status_code, 1
            )
            raise ClientError(f"http_{response.status_code}", category)
        try:
            if len(response.content) > 524288:
                raise ValueError()
            return response.json()
        except ValueError:
            raise ClientError("invalid_server_response", 6) from None
