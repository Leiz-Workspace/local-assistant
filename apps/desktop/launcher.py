"""Launch Aevra's native application and optionally own a missing local harness, never a browser or model process."""

import hashlib
import json
import logging
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time
from urllib.parse import urlsplit

LOG_DIR = Path.home() / ".local/state/aevra"
LOG_FILE = LOG_DIR / "desktop.log"


def launch_log_path():
    LOG_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    return LOG_FILE.open("a", encoding="utf-8")

from apps.cli.client import ClientError, DEFAULT_AUTH

LOGGER = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parents[2]


def native_command():
    """Select bundled Python when packaged, otherwise use the development uv path."""
    if sys.platform != "linux":
        raise ClientError("native_desktop_dependencies_required", 6)
    bundled = Path(sys.prefix) / "bin/python"
    if str(Path(sys.prefix)).startswith("/usr/lib/aevra/") and bundled.is_file() and bundled.stat().st_mode & 0o111:
        return [str(bundled), "-m", "apps.desktop.main"]
    uv = shutil.which("uv")
    python = Path("/usr/bin/python3")
    if uv is None or not python.is_file():
        raise ClientError("native_desktop_dependencies_required", 6)
    return [uv, "run", "--offline", "--no-project", "--python", str(python), "python", str(ROOT / "apps/desktop/main.py")]


def check_native(command):
    """Check GTK/WebKit availability before consuming a pairing or starting backend resources."""
    try:
        result = subprocess.run(
            command + ["--check"], capture_output=True, timeout=10, check=False
        )
        metadata = json.loads(result.stdout)
        if (
            result.returncode
            or metadata.get("renderer") != "webkitgtk-4.1"
            or metadata.get("external_browser") is not False
        ):
            raise ValueError
    except (OSError, ValueError, subprocess.TimeoutExpired):
        raise ClientError("native_desktop_dependencies_required", 6) from None
    LOGGER.info("aevra_native_dependencies_verified")
    return metadata


def stop_owned(process):
    """Terminate and reap only the exact session group created by this launcher."""
    if process is None:
        return
    if process.poll() is None:
        try:
            process.terminate()
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=5)
        except ProcessLookupError:
            process.wait(timeout=5)
    else:
        process.wait()
    LOGGER.info("aevra_owned_process_joined")


def ensure_backend(client, auth_file=DEFAULT_AUTH):
    """Reuse an authenticated Aevra server or start a missing owned harness with matching existing identity only."""
    try:
        status = client.request("GET", "/api/v1/harness/status", timeout=2)
    except ClientError as error:
        if error.code != "server_unavailable":
            raise
    else:
        if status.get("product") != "Aevra":
            raise ClientError("aevra_backend_restart_required", 6)
        LOGGER.info("aevra_existing_backend_reused")
        return None
    from apps.api.core.conversation_auth import load_principals

    path = Path(auth_file)
    try:
        principals = load_principals(path)
        if hashlib.sha256(client.token.encode()).hexdigest() not in principals:
            raise ValueError
    except (OSError, ValueError, TypeError, AttributeError):
        raise ClientError("matching_backend_auth_required", 3) from None
    parsed = urlsplit(client.url)
    if parsed.hostname != "127.0.0.1" or not 1024 <= (parsed.port or 80) <= 65535:
        raise ClientError("managed_backend_ipv4_port_required", 2)
    bundled_cli = Path(sys.prefix) / "bin/aevra"
    if str(Path(sys.prefix)).startswith("/usr/lib/aevra/") and bundled_cli.is_file() and bundled_cli.stat().st_mode & 0o111:
        command = [str(Path(sys.prefix) / "bin/aevra-python"), "-m", "apps.cli.main", "serve", "--port", str(parsed.port), "--auth-file", str(path.absolute())]
    else:
        uv = shutil.which("uv")
        if uv is None:
            raise ClientError("desktop_backend_runtime_required", 6)
        command = [uv, "run", "--offline", "--project", str(ROOT), "--no-sync", "aevra", "serve", "--port", str(parsed.port), "--auth-file", str(path.absolute())]
    log_handle = launch_log_path()
    process = subprocess.Popen(
        command,
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        cwd=str(ROOT),
        start_new_session=True,
    )
    LOGGER.info("aevra_owned_backend_started")
    deadline = time.monotonic() + 15
    try:
        while time.monotonic() < deadline and process.poll() is None:
            try:
                status = client.request("GET", "/api/v1/harness/status", timeout=2)
                if status.get("product") != "Aevra":
                    raise ClientError("aevra_backend_restart_required", 6)
                return process
            except ClientError as error:
                if error.code != "server_unavailable":
                    raise
            time.sleep(0.1)
        raise ClientError("desktop_backend_start_failed", 6)
    except BaseException:
        stop_owned(process)
        raise


def launch(client, *, auth_file=DEFAULT_AUTH):
    """Run native app lifetime and preserve bounded child diagnostics in the private state log."""
    log_handle = launch_log_path()
    command = native_command()
    check_native(command)
    backend, native = None, None
    try:
        backend = ensure_backend(client, auth_file)
        pairing = client.request("POST", "/api/v1/harness/ui-pairings", {})
        scope = hashlib.sha256(
            (
                client.url + "\n" + hashlib.sha256(client.token.encode()).hexdigest()
            ).encode()
        ).hexdigest()
        bootstrap = dict(url=client.url, code=pairing["code"], profile=scope)
        from apps.desktop.runtime import validate_bootstrap

        validate_bootstrap(bootstrap)
        native = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=log_handle,
            cwd=str(ROOT),
            start_new_session=True,
        )
        LOGGER.info("aevra_native_application_started")
        output, _ = native.communicate(json.dumps(bootstrap).encode() + b"\n")
        if len(output) > 262144 or native.returncode != 0:
            raise ClientError("native_desktop_failed", 6)
        events = output.decode("utf-8", errors="replace").splitlines()
        known = {
            "aevra_desktop_profile_ready",
            "aevra_desktop_profile_locked",
            "aevra_desktop_window_opened",
            "aevra_desktop_window_closed",
            "aevra_desktop_navigation_denied",
            "aevra_desktop_popup_denied",
            "aevra_desktop_download_denied",
            "aevra_desktop_permission_denied",
            "aevra_desktop_page_load_failed",
        }
        if not all(
            any(line.endswith(event) for line in events)
            for event in ("aevra_desktop_window_opened", "aevra_desktop_window_closed")
        ):
            raise ClientError("native_desktop_failed", 6)
        for event in sorted(known):
            count = sum(line.split(" ")[-1] == event for line in events)
            if count:
                LOGGER.info("aevra_native_event event=%s count=%d", event, count)
        return dict(
            product="Aevra",
            desktop=True,
            external_browser=False,
            renderer="webkitgtk-4.1",
            closed=True,
            backend_owned=backend is not None,
        )
    finally:
        stop_owned(native)
        stop_owned(backend)
        log_handle.close()


def main(argv=None):
    """Expose a native desktop entrypoint while retaining the CLI's existing credential and error handling."""
    import argparse
    from apps.cli.client import DEFAULT_TOKEN
    from apps.cli.main import main as cli_main

    parser = argparse.ArgumentParser(
        prog="aevra-desktop", description="Aevra native desktop"
    )
    parser.add_argument("--url", default="http://127.0.0.1:7090")
    parser.add_argument("--token-file", type=Path, default=DEFAULT_TOKEN)
    parser.add_argument("--auth-file", type=Path, default=DEFAULT_AUTH)
    args = parser.parse_args(argv)
    return cli_main(
        [
            "--url",
            args.url,
            "--token-file",
            str(args.token_file),
            "desktop",
            "--auth-file",
            str(args.auth_file),
        ]
    )

if __name__ == "__main__":
    raise SystemExit(main())
