"""Exercise CLI credentials, loopback isolation, stable exits and desktop launch arguments."""

import logging
import stat

import httpx
import pytest

from apps.cli import main as cli
from apps.cli.client import (
    ApiClient,
    ClientError,
    initialize_auth,
    read_token,
    save_token,
)

LOGGER = logging.getLogger(__name__)


def test_isolated_auth_initialization_is_private_and_never_overwrites(tmp_path):
    """Create a usable digest binding while preserving existing credentials on repeated setup."""
    import json
    import hashlib

    token, auth = tmp_path / "token", tmp_path / "auth.json"
    result = initialize_auth(token, auth)
    content = auth.read_bytes()
    assert stat.S_IMODE(auth.stat().st_mode) == 0o600
    assert (
        json.loads(content)["principals"][0]["token_sha256"]
        == hashlib.sha256(read_token(token).encode()).hexdigest()
    )
    assert not result["existing_credentials_changed"]
    with pytest.raises(ClientError):
        initialize_auth(token, auth)
    assert auth.read_bytes() == content


def test_desktop_shortcut_is_explicit_and_has_no_credential(tmp_path, monkeypatch):
    """Write one shortcut with quoted paths and no token contents or implicit OS installation."""
    monkeypatch.setattr(cli.shutil, "which", lambda name: "/usr/bin/uv")
    path = tmp_path / "Aevra.desktop"
    result = cli.write_launcher(
        path,
        "http://127.0.0.1:7090",
        tmp_path / "token",
        icon_directory=tmp_path / "icons",
    )
    text = path.read_text()
    assert "[Desktop Entry]" in text and '"desktop"' in text
    assert result["backend_managed_when_missing"] and not result["external_browser"]
    assert result["application_id"] == "io.aevra.Aevra"
    assert (
        "Name=Aevra" in text
        and f"Icon={tmp_path / 'icons/512x512/apps'}/io.aevra.Desktop-transparent-"
        in text
    )
    assert "Bearer" not in text
    with pytest.raises(FileExistsError):
        cli.write_launcher(
            path,
            "http://127.0.0.1:7090",
            tmp_path / "token",
            icon_directory=tmp_path / "icons",
        )


@pytest.mark.parametrize(
    "url",
    [
        "https://127.0.0.1:7090",
        "http://example.com",
        "http://127.0.0.1:7090/private",
        "http://token@127.0.0.1",
        "http://127.0.0.1?secret=1",
    ],
)
def test_client_rejects_credential_exfiltration_targets(url):
    """Reject remote, credential-bearing and path-bearing backend URLs before transport use."""
    with pytest.raises(ClientError):
        ApiClient(url, "t" * 48)


def test_private_credentials_are_exclusive_and_not_symlink_followed(tmp_path):
    """Write one private token and refuse permissive, overwritten and linked files."""
    path = tmp_path / "token"
    save_token(path, "s" * 48)
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert read_token(path) == "s" * 48
    with pytest.raises(ClientError):
        save_token(path, "other" * 10)
    path.chmod(0o644)
    with pytest.raises(ClientError):
        read_token(path)
    linked = tmp_path / "linked"
    linked.symlink_to(path)
    with pytest.raises(ClientError):
        read_token(linked)


def test_http_redirect_and_error_bodies_never_leak(capsys):
    """Map a redirect without following it or exposing server-supplied sensitive text."""

    def redirect(request):
        """Return a hostile redirect that must not receive a second request."""
        assert request.headers["authorization"] == "Bearer " + "s" * 48
        return httpx.Response(
            302, headers={"location": "https://example.com"}, text="PRIVATE_RESPONSE"
        )

    with pytest.raises(ClientError, match="http_302"):
        ApiClient(
            "http://127.0.0.1:7090", "s" * 48, transport=httpx.MockTransport(redirect)
        ).request("GET", "/status")
    assert "PRIVATE_RESPONSE" not in capsys.readouterr().out


def test_doctor_needs_no_credential_or_network(capsys, tmp_path):
    """Permit read-only startup inspection without a running backend or model."""
    assert cli.main(["--token-file", str(tmp_path / "absent"), "--json", "doctor"]) == 0
    output = capsys.readouterr().out
    assert '"services_started": false' in output
    LOGGER.info("test_cli_offline_doctor_verified")


def test_status_missing_credential_has_auth_exit(capsys, tmp_path):
    """Report a stable authentication category without a raw filesystem traceback."""
    assert cli.main(["--token-file", str(tmp_path / "absent"), "status"]) == 3
    assert "private_token_file_required" in capsys.readouterr().err


def test_logout_refuses_to_delete_noncredential_files(tmp_path, capsys):
    """Prevent a mistaken token path from deleting unrelated repository or user files."""
    path = tmp_path / "notes.md"
    path.write_text("Keep this user document.")
    assert cli.main(["--token-file", str(path), "auth", "logout"]) == 3
    assert path.read_text() == "Keep this user document."


def test_machine_readable_chat_requires_one_message(monkeypatch, capsys):
    """Reject interactive prompts when machine-readable output was explicitly requested."""
    monkeypatch.setattr(cli, "read_token", lambda path: "t" * 48)
    assert cli.main(["--json", "chat"]) == 2
    assert "json_chat_requires_message" in capsys.readouterr().err


@pytest.mark.parametrize("contract", ["text", "source-value-quote-v1"])
def test_run_cli_preserves_explicit_preset_and_context_policy(
    tmp_path, monkeypatch, capsys, contract
):
    """Transmit the exact requested budget policy without selecting another model or invoking tools locally."""
    from uuid import uuid4

    calls = []
    task = tmp_path / "task.md"
    task.write_text("Review this synthetic task.")

    class Client:
        """Capture one finite API request without creating a backend or reading credentials."""

        def __init__(self, url, token):
            """Accept the CLI transport arguments without granting filesystem or network authority."""

        def request(self, method, path, payload):
            """Record the submitted task contract and return a queued run receipt."""
            calls.append(payload)
            return {"id": str(uuid4()), "state": "created"}

    monkeypatch.setattr(cli, "read_token", lambda path: "t" * 48)
    monkeypatch.setattr(cli, "ApiClient", Client)
    assert (
        cli.main(
            [
                "--json",
                "run",
                "--workspace",
                str(uuid4()),
                "--task-file",
                str(task),
                "--preset",
                "balanced",
                "--max-tokens",
                "5000",
                "--context-strategy",
                "recent-turns",
                "--output-contract",
                contract,
            ]
        )
        == 0
    )
    assert calls[0]["preset"] == "balanced" and calls[0]["max_tokens"] == 5000
    assert calls[0]["context_strategy"] == "recent-turns"
    if contract == "text":
        assert "output_contract" not in calls[0]
    else:
        assert calls[0]["output_contract"] == contract


def test_wait_exits_on_archived_interruption_without_replay(
    tmp_path, monkeypatch, capsys
):
    """Report a restarted task as interrupted instead of polling indefinitely or resubmitting it."""
    from uuid import uuid4

    identifier = str(uuid4())
    calls = []
    task = tmp_path / "task.md"
    task.write_text("Synthetic interrupted task.")

    class Client:
        """Emulate a process restart between task creation and its first status poll."""

        def __init__(self, url, token):
            """Accept fixture transport arguments without network or credential access."""

        def request(self, method, path, payload=None):
            """Return one creation and an archived interruption without executing a replacement task."""
            calls.append(method)
            return {
                "id": identifier,
                "state": "created" if method == "POST" else "interrupted",
            }

    monkeypatch.setattr(cli, "ApiClient", Client)
    monkeypatch.setattr(cli, "read_token", lambda path: "t" * 48)
    monkeypatch.setattr(cli.time, "sleep", lambda seconds: None)
    assert (
        cli.main(
            [
                "--json",
                "run",
                "--workspace",
                str(uuid4()),
                "--task-file",
                str(task),
                "--wait",
            ]
        )
        == 1
    )
    assert calls == ["POST", "GET"] and "task_interrupted" in capsys.readouterr().err


def test_desktop_dispatches_to_native_app_without_a_browser(monkeypatch):
    """Delegate to the native lifecycle without invoking browser discovery or a default browser."""
    from apps.desktop import launcher

    calls = []
    client = object()

    def launch(value, **options):
        """Capture the native dispatch without creating a graphical window."""
        calls.append((value, options))
        return {"desktop": True, "external_browser": False}

    monkeypatch.setattr(launcher, "launch", launch)
    result = cli.open_ui(client, desktop=True)
    assert result["desktop"] and not result["external_browser"]
    assert calls[0][0] is client


def test_unavailable_desktop_does_not_consume_pairing(monkeypatch):
    """Fail before minting a nonce when native launch prerequisites are missing."""
    monkeypatch.setattr(cli.shutil, "which", lambda name: None)
    with pytest.raises(ClientError, match="native_desktop_dependencies_required"):
        cli.open_ui(None, desktop=True)


class ApprovalClient:
    """Serve one synthetic approval review and record decisions without a backend."""

    def __init__(self, state="pending"):
        """Hold a fixed review with a synthetic scope digest and nonce."""
        self.review = dict(
            request_id="00000000-0000-4000-8000-000000000001",
            kind="workspace_write",
            workspace_id="00000000-0000-4000-8000-000000000002",
            scope_digest="ab12cd34" + "0" * 56,
            artifact="synthetic artifact",
            review_nonce="n" * 43,
            state=state,
            expires_at="2026-11-12T00:00:00Z",
        )
        self.calls = []

    def request(self, method, path, payload=None):
        """Return the review for reads and record every decision post."""
        self.calls.append((method, path, payload))
        if method == "GET":
            return dict(self.review)
        return dict(state=payload["decision"] + "d")


class Terminal:
    """Report a fixed terminal state for stdin and return one typed line."""

    def __init__(self, tty, typed=""):
        """Remember whether the synthetic stdin is interactive and what the owner types."""
        self.tty, self.typed, self.reads = tty, typed, 0

    def isatty(self):
        """Return the configured terminal state."""
        return self.tty

    def readline(self):
        """Return the typed confirmation once."""
        self.reads += 1
        return self.typed


def run_approvals(monkeypatch, client, argv):
    """Run the CLI with an injected approval client and no credential file."""
    from uuid import UUID

    monkeypatch.setattr(cli, "read_token", lambda path: "t" * 48)
    monkeypatch.setattr(cli, "ApiClient", lambda url, token: client)
    identifier = str(UUID(client.review["request_id"]))
    return cli.main(["--json", "approvals", *argv[:1], identifier, *argv[1:]])


def test_approval_show_never_prints_the_review_nonce(monkeypatch, capsys):
    """Showing a review omits the one-time nonce so output cannot be replayed as a decision."""
    client = ApprovalClient()
    assert run_approvals(monkeypatch, client, ["show"]) == 0
    out = capsys.readouterr().out
    assert "n" * 43 not in out and "review_nonce" not in out
    assert client.review["scope_digest"] in out
    assert [call[0] for call in client.calls] == ["GET"]


def test_approval_decision_requires_a_terminal(monkeypatch, capsys):
    """A non-interactive stdin cannot approve, and nothing is posted."""
    client = ApprovalClient()
    monkeypatch.setattr(cli.sys, "stdin", Terminal(False))
    assert run_approvals(monkeypatch, client, ["decide", "approve"]) == 2
    assert "approval_requires_terminal" in capsys.readouterr().err
    assert [call[0] for call in client.calls] == ["GET"]


@pytest.mark.parametrize("decision", ["approve", "reject"])
def test_approval_decision_posts_digest_and_nonce_after_confirmation(
    monkeypatch, capsys, decision
):
    """Typing the digest prefix sends exactly the reviewed scope digest and nonce."""
    client = ApprovalClient()
    monkeypatch.setattr(cli.sys, "stdin", Terminal(True, " ab12cd34 \n"))
    assert run_approvals(monkeypatch, client, ["decide", decision]) == 0
    captured = capsys.readouterr()
    assert "synthetic artifact" in captured.err and "n" * 43 not in captured.err
    assert "Type the first 8" not in captured.out and "n" * 43 not in captured.out
    method, path, payload = client.calls[-1]
    assert method == "POST" and path.endswith("/decision")
    assert payload == dict(
        decision=decision,
        scope_digest=client.review["scope_digest"],
        review_nonce="n" * 43,
    )


def test_approval_decision_refuses_a_wrong_confirmation(monkeypatch, capsys):
    """A mismatched digest prefix stops before any decision is posted."""
    client = ApprovalClient()
    monkeypatch.setattr(cli.sys, "stdin", Terminal(True, "ab12cd35\n"))
    assert run_approvals(monkeypatch, client, ["decide", "approve"]) == 2
    assert "approval_confirmation_mismatch" in capsys.readouterr().err
    assert [call[0] for call in client.calls] == ["GET"]


@pytest.mark.parametrize("state", ["approved", "rejected", "expired"])
def test_approval_decision_refuses_a_settled_request(monkeypatch, capsys, state):
    """A request that is no longer pending is refused before any prompt or post."""
    client = ApprovalClient(state)
    terminal = Terminal(True, "ab12cd34\n")
    monkeypatch.setattr(cli.sys, "stdin", terminal)
    assert run_approvals(monkeypatch, client, ["decide", "approve"]) == 5
    assert "approval_not_pending" in capsys.readouterr().err
    assert [call[0] for call in client.calls] == ["GET"] and terminal.reads == 0


def test_approval_identifier_must_be_a_uuid(monkeypatch, capsys):
    """A malformed identifier is rejected by the parser before any request."""
    monkeypatch.setattr(cli, "read_token", lambda path: "t" * 48)
    with pytest.raises(SystemExit) as raised:
        cli.main(["approvals", "show", "../admin"])
    assert raised.value.code == 2


def test_approval_review_text_cannot_rewrite_the_terminal(monkeypatch, capsys):
    """Control and bidirectional characters in the artifact are escaped before display."""
    client = ApprovalClient()
    client.review["artifact"] = "safe\x1b[2K\rhidden\u202ecode\nnext"
    monkeypatch.setattr(cli.sys, "stdin", Terminal(True, "wrong\n"))
    assert run_approvals(monkeypatch, client, ["decide", "approve"]) == 2
    err = capsys.readouterr().err
    assert "\x1b" not in err and "\r" not in err and "\u202e" not in err
    assert "\\u001b[2K\\u000dhidden\\u202ecode\nnext" in err


@pytest.mark.parametrize("mode", [[], ["--json"]])
def test_approval_show_escapes_terminal_controls_without_changing_the_value(
    monkeypatch, capsys, mode
):
    """C1 controls, DEL and bidi overrides leave stdout as JSON escapes; the parsed artifact is identical."""
    import json
    from uuid import UUID

    client = ApprovalClient()
    artifact = "ok\u202edrowssap\u009b2K\u009d52;c\u009c\x7f\U000e0001 Việt\nnext"
    client.review["artifact"] = artifact
    monkeypatch.setattr(cli, "read_token", lambda path: "t" * 48)
    monkeypatch.setattr(cli, "ApiClient", lambda url, token: client)
    identifier = str(UUID(client.review["request_id"]))
    assert cli.main([*mode, "approvals", "show", identifier]) == 0
    out = capsys.readouterr().out
    for char in ("\u202e", "\u009b", "\u009d", "\u009c", "\x7f", "\U000e0001"):
        assert char not in out
    assert "Việt" in out
    assert json.loads(out)["artifact"] == artifact


def test_approval_decision_treats_a_closed_stdin_as_no_terminal(monkeypatch, capsys):
    """A closed stdin (sys.stdin is None) exits 2 without a traceback or a post."""
    client = ApprovalClient()
    monkeypatch.setattr(cli.sys, "stdin", None)
    assert run_approvals(monkeypatch, client, ["decide", "approve"]) == 2
    assert "approval_requires_terminal" in capsys.readouterr().err
    assert [call[0] for call in client.calls] == ["GET"]


def test_approval_decision_discards_typeahead_before_reading(monkeypatch, capsys):
    """Input queued before the review was printed is flushed, then the confirmation is read."""
    import termios

    events = []

    class Typed(Terminal):
        """Record the order of flush and read on a synthetic terminal."""

        def fileno(self):
            """Return a synthetic descriptor for the flush call."""
            return 99

        def readline(self):
            """Record the read after any flush."""
            events.append("read")
            return super().readline()

    def flush(descriptor, queue):
        """Record the flush of the synthetic descriptor's input queue."""
        assert descriptor == 99 and queue == termios.TCIFLUSH
        events.append("flush")

    monkeypatch.setattr(termios, "tcflush", flush)
    client = ApprovalClient()
    monkeypatch.setattr(cli.sys, "stdin", Typed(True, "ab12cd34\n"))
    assert run_approvals(monkeypatch, client, ["decide", "approve"]) == 0
    assert events == ["flush", "read"] and client.calls[-1][0] == "POST"


def test_review_text_keeps_real_and_literal_escapes_distinct():
    """A real control character and its literal escape text render differently; non-BMP escapes have a fixed width."""
    assert cli.terminal_text("\x1b[2J", review=True) == "\\u001b[2J"
    assert cli.terminal_text("\\u001b[2J", review=True) == "\\\\u001b[2J"
    assert cli.terminal_text("‮", review=True) != cli.terminal_text(
        "\\u202e", review=True
    )
    assert cli.terminal_text("\U000e0001", review=True) == "\\U000e0001"
    assert cli.terminal_text("" + "1", review=True) == "\\ue0001"


@pytest.mark.parametrize("body", ["text", ["list"], {"state": "pending"}])
@pytest.mark.parametrize("action", [["show"], ["decide", "approve"]])
def test_approval_commands_reject_a_malformed_review(monkeypatch, capsys, body, action):
    """A review that is not an object with state and digest exits 6 without a traceback or a post."""
    client = ApprovalClient()
    client.request = lambda method, path, payload=None: (
        client.calls.append((method, path, payload)) or body
    )
    monkeypatch.setattr(cli.sys, "stdin", Terminal(True, "ab12cd34\n"))
    assert run_approvals(monkeypatch, client, action) == 6
    assert "invalid_server_response" in capsys.readouterr().err
    assert [call[0] for call in client.calls] == ["GET"]


def test_plain_string_results_are_escaped_for_the_terminal(monkeypatch, capsys):
    """A server that returns a bare JSON string cannot send control sequences to the terminal."""
    from uuid import uuid4

    class Client:
        """Return one hostile string for any request."""

        def __init__(self, url, token):
            """Accept the CLI transport arguments."""

        def request(self, method, path, payload=None):
            """Return a string with OSC, CSI and bidi controls."""
            return "ok\x1b]0;title\x07\x1b[2J‮evil"

    monkeypatch.setattr(cli, "read_token", lambda path: "t" * 48)
    monkeypatch.setattr(cli, "ApiClient", Client)
    assert cli.main(["jobs", "show", str(uuid4())]) == 0
    out = capsys.readouterr().out
    assert "\x1b" not in out and "\x07" not in out and "‮" not in out
    assert out.strip() == "ok\\u001b]0;title\\u0007\\u001b[2J\\u202eevil"
