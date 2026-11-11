"""Verify browser-free native launch, nonce isolation, owner-scoped storage and exact owned-process cleanup."""

import json
import logging
import subprocess
from types import SimpleNamespace

import httpx
import pytest

from apps.cli.client import ApiClient, ClientError
from apps.desktop import launcher, runtime

LOGGER = logging.getLogger(__name__)


def bootstrap():
    """Create a finite nonsecret stand-in for one real pairing and owner/origin profile."""
    return dict(url="http://127.0.0.1:7092", code="n" * 43, profile="a" * 64)


@pytest.mark.parametrize(
    "url",
    [
        "https://127.0.0.1:7092",
        "http://example.com",
        "http://127.0.0.1:7092/extra",
        "http://user@127.0.0.1:7092",
        "http://127.0.0.1:7092#secret",
        "http://127.0.0.1:80",
    ],
)
def test_desktop_bootstrap_rejects_remote_and_credential_bearing_origins(url):
    """Reject dangerous native origins before any renderer or network request is constructed."""
    with pytest.raises(ValueError):
        runtime.validate_bootstrap({**bootstrap(), "url": url})


@pytest.mark.parametrize(
    "uri,expected",
    [
        ("http://127.0.0.1:7092/", True),
        ("http://127.0.0.1:7092/pair/#nonce", True),
        ("http://127.0.0.1:7093/", False),
        ("https://example.com/", False),
        ("file:///etc/passwd", False),
        ("javascript:alert(1)", False),
        ("http://private@127.0.0.1:7092/", False),
    ],
)
def test_native_navigation_stays_inside_exact_origin(uri, expected):
    """Distinguish same-host ports and reject local file/script navigation without launching another browser."""
    assert runtime.allowed_uri(uri, bootstrap()["url"]) is expected


def test_profile_is_private_and_rejects_traversal_or_symlinks(tmp_path, monkeypatch):
    """Keep device history under the dedicated account/origin scope and refuse unsafe storage targets."""
    monkeypatch.setattr(runtime.Path, "home", lambda: tmp_path)
    path = runtime.private_profile("a" * 64)
    assert path.stat().st_mode & 0o077 == 0
    assert runtime.private_profile("b" * 64) != path
    with pytest.raises(ValueError):
        runtime.private_profile("../other")
    path.rmdir()
    path.symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(ValueError, match="unsafe"):
        runtime.private_profile("a" * 64)


def test_native_command_never_discovers_or_invokes_external_browsers(monkeypatch):
    """Use only uv plus OS Python and the application runtime, with no browser fallback."""
    seen = []

    def which(name):
        """Return the existing uv path and record every requested executable."""
        seen.append(name)
        return "/usr/bin/uv"

    monkeypatch.setattr(launcher.shutil, "which", which)
    command = launcher.native_command()
    assert seen == ["uv"]
    assert command[-1].endswith("apps/desktop/main.py")
    assert "--offline" in command and "--no-project" in command
    assert not any(
        "brave" in arg or "chromium" in arg or "--app=" in arg for arg in command
    )


@pytest.mark.parametrize(
    "stdout,code",
    [
        (b"not json", 0),
        (b'{"renderer":"chromium","external_browser":true}', 0),
        (b"{}", 6),
    ],
)
def test_missing_native_dependencies_fail_before_pairing(monkeypatch, stdout, code):
    """Return a bounded prerequisite error without leaking native diagnostics or falling back to a browser."""
    monkeypatch.setattr(
        launcher.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(stdout=stdout, returncode=code),
    )
    with pytest.raises(ClientError, match="native_desktop_dependencies_required"):
        launcher.check_native(["uv", "runtime"])


class NativeProcess:
    """Capture stdin transport and provide a deterministic native application lifetime without any real process."""

    def __init__(self, fail=False):
        """Track one complete or failed synthetic renderer process."""
        self.returncode = None
        self.input = None
        self.waits = 0
        self.pid = 456789
        self.fail = fail

    def communicate(self, data):
        """Consume the private bootstrap via stdin and emit only finite known native events."""
        self.input = json.loads(data)
        self.returncode = 6 if self.fail else 0
        return (
            b"INFO aevra_desktop_window_opened\nINFO aevra_desktop_window_closed\n",
            b"",
        )

    def poll(self):
        """Expose the controlled process state for lifecycle cleanup."""
        return self.returncode

    def wait(self, timeout=None):
        """Record that the owned process was joined."""
        self.waits += 1
        self.returncode = self.returncode or 0
        return self.returncode


@pytest.mark.parametrize("fail", [False, True])
def test_nonce_stdin_no_browser_and_owned_cleanup(monkeypatch, caplog, fail):
    """Keep nonce/token out of argv/logs and join both owned resources on native success or failure."""
    caplog.set_level(logging.INFO)
    client = SimpleNamespace(url=bootstrap()["url"], token="PRIVATE_BEARER_SENTINEL")
    calls, cleaned = [], []

    def request(method, path, payload=None):
        """Supply the one-use nonce only when the exact authenticated pairing endpoint is requested."""
        assert path.endswith("ui-pairings")
        return dict(code=bootstrap()["code"])

    client.request = request
    native, backend = NativeProcess(fail), object()

    def popen(arguments, **options):
        """Observe native argv and preserve stdin as the sole bootstrap transport."""
        calls.append((arguments, options))
        return native

    monkeypatch.setattr(launcher, "native_command", lambda: ["uv", "native-runtime"])
    monkeypatch.setattr(launcher, "check_native", lambda command: None)
    monkeypatch.setattr(launcher, "ensure_backend", lambda *args: backend)
    monkeypatch.setattr(launcher.subprocess, "Popen", popen)
    monkeypatch.setattr(launcher, "stop_owned", lambda process: cleaned.append(process))
    if fail:
        with pytest.raises(ClientError, match="native_desktop_failed"):
            launcher.launch(client)
    else:
        result = launcher.launch(client)
        assert result["renderer"] == "webkitgtk-4.1" and not result["external_browser"]
    assert cleaned == [native, backend]
    assert native.input["code"] == bootstrap()["code"]
    assert "PRIVATE_BEARER_SENTINEL" not in json.dumps(native.input)
    assert bootstrap()["code"] not in str(
        calls
    ) and "PRIVATE_BEARER_SENTINEL" not in str(calls)
    assert (
        bootstrap()["code"] not in caplog.text
        and "PRIVATE_BEARER_SENTINEL" not in caplog.text
    )
    assert calls[0][1]["stdin"] == subprocess.PIPE and calls[0][1]["start_new_session"]
    LOGGER.info("test_aevra_native_nonce_cleanup_verified")


def test_existing_server_reused_and_auth_failure_never_restarts(monkeypatch):
    """Reuse an Aevra backend and refuse occupied/unauthorized servers rather than replacing shared processes."""
    client = SimpleNamespace(request=lambda *args, **kwargs: {"product": "Aevra"})
    assert launcher.ensure_backend(client) is None
    client.request = lambda *args, **kwargs: {"product": "Old gateway"}
    with pytest.raises(ClientError, match="restart_required"):
        launcher.ensure_backend(client)

    def unauthorized(*args, **kwargs):
        """Represent an occupied backend with mismatched owner credentials."""
        raise ClientError("http_401", 3)

    client.request = unauthorized
    with pytest.raises(ClientError, match="http_401"):
        launcher.ensure_backend(client)


def test_missing_server_owned_start_has_matching_identity_and_finite_wait(
    auth_settings, monkeypatch
):
    """Start only a missing backend with the exact configured principal and never pass token contents in argv."""
    client = SimpleNamespace(url=bootstrap()["url"], token=auth_settings["tokens"][0])
    calls, requests = [], []

    def request(method, path, **options):
        """Fail the first connectivity probe, then expose the newly started Aevra backend."""
        requests.append(options)
        if len(requests) == 1:
            raise ClientError("server_unavailable", 6)
        return {"product": "Aevra"}

    client.request = request
    process = NativeProcess()

    def popen(arguments, **options):
        """Capture one owned harness start without executing model or browser commands."""
        calls.append((arguments, options))
        return process

    monkeypatch.setattr(launcher.shutil, "which", lambda name: "/usr/bin/uv")
    monkeypatch.setattr(launcher.subprocess, "Popen", popen)
    assert launcher.ensure_backend(client, auth_settings["path"]) is process
    assert all(options["timeout"] == 2 for options in requests)
    assert client.token not in str(calls)
    assert "serve" in calls[0][0] and "start-core.py" not in str(calls)
    assert calls[0][1]["start_new_session"]


def test_failed_owned_backend_is_joined(auth_settings, monkeypatch):
    """Reap an owned startup failure without touching any unowned server."""
    client = SimpleNamespace(url=bootstrap()["url"], token=auth_settings["tokens"][0])

    def unavailable(*args, **kwargs):
        """Represent a missing backend that never becomes ready."""
        raise ClientError("server_unavailable", 6)

    client.request = unavailable
    process = NativeProcess()
    process.returncode = 1
    cleaned = []
    monkeypatch.setattr(launcher.shutil, "which", lambda name: "/usr/bin/uv")
    monkeypatch.setattr(launcher.subprocess, "Popen", lambda *args, **kwargs: process)
    monkeypatch.setattr(launcher, "stop_owned", lambda value: cleaned.append(value))
    with pytest.raises(ClientError, match="start_failed"):
        launcher.ensure_backend(client, auth_settings["path"])
    assert cleaned == [process]


def test_client_supports_bounded_desktop_probes_without_changing_default():
    """Use the requested short probe timeout while preserving the existing transport and authentication boundary."""
    observed = []

    def respond(request):
        """Inspect actual httpx timeout metadata without contacting a service."""
        observed.append(request.extensions["timeout"]["read"])
        return httpx.Response(200, json={"product": "Aevra"})

    client = ApiClient(
        "http://127.0.0.1:7092", "t" * 48, transport=httpx.MockTransport(respond)
    )
    client.request("GET", "/status", timeout=2)
    client.request("GET", "/status")
    assert observed == [2, 125]


def test_native_profile_lock_refuses_parallel_writers(tmp_path):
    """Protect the scoped WebKit store from simultaneous windows and release the lock after normal close."""
    with runtime.lock_profile(tmp_path):
        with pytest.raises(ValueError, match="profile_in_use"):
            with runtime.lock_profile(tmp_path):
                pytest.fail("Concurrent profile writer admitted")
    with runtime.lock_profile(tmp_path):
        assert (tmp_path / "window.lock").stat().st_mode & 0o077 == 0


def test_native_initialization_failure_quits_without_hidden_window(
    tmp_path, monkeypatch, caplog
):
    """Turn a native setup failure into a finite error, close its window and avoid a silent event-loop hang."""
    caplog.set_level(logging.INFO)
    state = dict(destroyed=False, quit=False)
    window = SimpleNamespace(
        set_default_size=lambda *args: None,
        destroy=lambda: state.update(destroyed=True),
    )

    def icon_failure():
        """Represent an unavailable verified icon without exposing its private underlying diagnostic."""
        raise ValueError("PRIVATE_NATIVE_ERROR")

    window.set_icon_from_file = lambda path: None

    class Application:
        """Dispatch one activate event and observe the runtime's initialization failure guard."""

        def __init__(self, **options):
            """Retain only the callback used by this deterministic application stub."""
            from apps.desktop.identity import APPLICATION_ID

            assert options["application_id"] == APPLICATION_ID == "io.aevra.Aevra"
            self.callback = None

        def connect(self, event, callback):
            """Record the activation handler without starting a real display."""
            self.callback = callback

        def run(self, arguments):
            """Trigger initialization once and return the controlled native loop status."""
            self.callback(self)
            return 0

        def get_windows(self):
            """Expose only the newly allocated owned window."""
            return [window]

        def quit(self):
            """Record that failure stops the application loop."""
            state["quit"] = True

    gtk = SimpleNamespace(
        init_check=lambda args: (True, []),
        Application=Application,
        ApplicationWindow=lambda **options: window,
    )
    glib = SimpleNamespace(
        set_application_name=lambda name: None, set_prgname=lambda name: None
    )
    gio = SimpleNamespace(ApplicationFlags=SimpleNamespace(NON_UNIQUE=1))
    monkeypatch.setattr(runtime, "dependencies", lambda: (gio, glib, gtk, None))
    monkeypatch.setattr(runtime, "private_profile", lambda scope: tmp_path)
    monkeypatch.setattr(runtime, "icon_path", icon_failure)
    with pytest.raises(ValueError, match="window_unavailable"):
        runtime.run(bootstrap())
    assert state == dict(destroyed=True, quit=True)
    assert "PRIVATE_NATIVE_ERROR" not in caplog.text


def test_native_dependency_probe_and_bad_arguments_are_finite(monkeypatch, capsys):
    """Expose a safe native dependency probe and reject unsupported startup flags without opening a window."""
    from apps.desktop import main as native

    monkeypatch.setattr(native, "dependencies", lambda: None)
    assert native.main(["--check"]) == 0
    assert json.loads(capsys.readouterr().out)["external_browser"] is False
    assert native.main(["--unexpected"]) == 6


def test_owned_stop_is_graceful_before_group_kill_fallback(monkeypatch):
    """Signal the owned uv supervisor once so its child can drain, then kill only its group if it times out."""
    calls = []

    class Process:
        """Model a stuck owned supervisor to exercise graceful and forced cleanup boundaries."""

        pid = 456789

        def poll(self):
            """Keep the fake child active until the cleanup sequence runs."""
            return None

        def terminate(self):
            """Record one graceful supervisor termination request."""
            calls.append("terminate")

        def wait(self, timeout):
            """Timeout once and then acknowledge the forced owned-group exit."""
            calls.append("wait")
            if calls.count("wait") == 1:
                raise subprocess.TimeoutExpired("owned-child", timeout)
            return -9

    monkeypatch.setattr(
        launcher.os, "killpg", lambda pid, signum: calls.append((pid, signum))
    )
    launcher.stop_owned(Process())
    assert calls == ["terminate", "wait", (456789, launcher.signal.SIGKILL), "wait"]
