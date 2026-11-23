"""Implement the Aevra CLI for local chat, bounded tasks, skills and native desktop access."""

import argparse
import getpass
import json
import logging
import os
import shutil
import sys
import time
import webbrowser
import tarfile
from pathlib import Path
from uuid import UUID

import httpx

from apps.cli.client import (
    ApiClient,
    ClientError,
    DEFAULT_TOKEN,
    DEFAULT_AUTH,
    initialize_auth,
    read_token,
    save_token,
)

LOGGER = logging.getLogger(__name__)
PREFIX = "/api/v1/harness"


def chat_policy(args):
    """Validate opt-in history flags locally while retaining the exact legacy request when absent."""
    from pydantic import ValidationError
    from src.application.services.context_reduction import HistoryPolicy

    if args.history_policy is None:
        if (
            args.history_window is not None
            or args.pin_turn
            or args.recall
            or args.compact_trigger is not None
            or args.working_state
            or args.evicted_summary
        ):
            raise ClientError("history_policy_required", 2)
        return None
    if args.history_policy == "token-budget" and args.history_window is not None:
        raise ClientError("invalid_history_policy", 2)
    values = dict(
        mode=args.history_policy, pinned_turns=args.pin_turn, recall_ids=args.recall
    )
    if args.history_window is not None:
        values["window_turns"] = args.history_window
    if args.compact_trigger is not None:
        values["trigger_ratio"] = args.compact_trigger
    if args.working_state:
        values["working_state"] = True
    if args.evicted_summary:
        values["evicted_summary"] = True
    try:
        result = HistoryPolicy.model_validate(values).model_dump(mode="json")
        if not result["working_state"]:
            result.pop("working_state")
            result.pop("carried_state")
        if not result["evicted_summary"]:
            result.pop("evicted_summary")
        if not (args.working_state or args.evicted_summary):
            result.pop("history_offset")
    except ValidationError:
        raise ClientError("invalid_history_policy", 2) from None
    LOGGER.info("cli_history_policy_selected mode=%s", result["mode"])
    return result


def parser():
    """Declare the implemented command surface without advertising unsupported model operations."""
    root = argparse.ArgumentParser(
        prog="aevra", description="Aevra — local assistant CLI and native desktop"
    )
    root.add_argument("--url", default="http://127.0.0.1:7090")
    root.add_argument("--token-file", type=Path, default=DEFAULT_TOKEN)
    root.add_argument("--json", action="store_true")
    sub = root.add_subparsers(dest="command", required=True)
    initialize = sub.add_parser("init")
    initialize.add_argument("--auth-file", type=Path, default=DEFAULT_AUTH)
    sub.add_parser("doctor")
    sub.add_parser("status")
    sub.add_parser("logo")
    serve = sub.add_parser("serve")
    serve.add_argument("--port", type=int, default=7090)
    serve.add_argument("--auth-file", type=Path)
    serve.add_argument("--state-dir", type=Path)
    auth = sub.add_parser("auth").add_subparsers(dest="action", required=True)
    auth.add_parser("login")
    auth.add_parser("logout")
    chat = sub.add_parser("chat")
    chat.add_argument("--message")
    chat.add_argument(
        "--history-policy",
        choices=["sliding-window", "extractive-compact", "token-budget"],
    )
    chat.add_argument("--history-window", type=int)
    chat.add_argument("--pin-turn", action="append", type=int, default=[])
    chat.add_argument("--recall", action="append", type=UUID, default=[])
    chat.add_argument("--working-state", action="store_true")
    chat.add_argument("--evicted-summary", action="store_true")
    chat.add_argument(
        "--compact-trigger",
        "--history-budget-ratio",
        dest="compact_trigger",
        type=float,
    )
    chat.add_argument(
        "--context-strategy",
        choices=["evidence-first", "recent-turns", "strict"],
        default="evidence-first",
    )
    chat.add_argument(
        "--preset",
        choices=["fast", "balanced", "deep", "auto", "unlimited"],
        default="fast",
    )
    run = sub.add_parser("run")
    run.add_argument("--workspace", type=UUID, required=True)
    run.add_argument("--task-file", type=Path, required=True)
    run.add_argument("--skill")
    run.add_argument(
        "--preset",
        choices=["fast", "balanced", "deep", "auto", "unlimited"],
        default="fast",
    )
    run.add_argument("--max-tokens", type=int)
    run.add_argument(
        "--output-contract",
        choices=[
            "text",
            "source-value-quote-v1",
            "review-line-quote-v1",
            "review-quote-line-v1",
        ],
        default="text",
    )
    run.add_argument("--review-target")
    run.add_argument(
        "--context-strategy",
        choices=["evidence-first", "recent-turns", "strict"],
        default="evidence-first",
    )
    run.add_argument("--tools-file", type=Path)
    run.add_argument("--wait", action="store_true")
    runs = sub.add_parser("runs").add_subparsers(dest="action", required=True)
    runs.add_parser("list")
    for action in ("show", "cancel", "remove"):
        runs.add_parser(action).add_argument("id", type=UUID)
    context = sub.add_parser("context").add_subparsers(dest="action", required=True)
    context.add_parser("inspect").add_argument("id", type=UUID)
    context.add_parser("archives")
    for action in ("recall", "forget"):
        context.add_parser(action).add_argument("id", type=UUID)
    skills = sub.add_parser("skills").add_subparsers(dest="action", required=True)
    skills.add_parser("list")
    show = skills.add_parser("show")
    show.add_argument("id", type=UUID)
    show.add_argument("--workspace", type=UUID, required=True)
    review = skills.add_parser("review")
    review.add_argument("manifest", type=Path)
    review.add_argument("--workspace", type=UUID, required=True)
    install = skills.add_parser("install")
    install.add_argument("--review", type=UUID, required=True)
    install.add_argument("--sha256", required=True)
    install.add_argument("--workspace", type=UUID, required=True)
    remove = skills.add_parser("remove")
    remove.add_argument("id", type=UUID)
    remove.add_argument("--workspace", type=UUID, required=True)
    ui = sub.add_parser("ui").add_subparsers(dest="action", required=True)
    ui.add_parser("prepare")
    ui.add_parser("open")
    desktop = sub.add_parser("desktop")
    desktop.add_argument("--write-launcher", type=Path)
    desktop.add_argument("--auth-file", type=Path, default=DEFAULT_AUTH)
    generate = sub.add_parser("generate").add_subparsers(dest="kind", required=True)
    for kind in ("image", "video"):
        media = generate.add_parser(kind)
        media.add_argument("--prompt-file", type=Path, required=True)
        media.add_argument("--width", type=int, default=512)
        media.add_argument("--height", type=int, default=512)
        media.add_argument("--seed", type=int)
        if kind == "video":
            media.add_argument("--seconds", type=int, required=True)
            media.add_argument("--fps", type=int, required=True)
    approvals = sub.add_parser("approvals").add_subparsers(dest="action", required=True)
    approvals.add_parser("show").add_argument("id", type=UUID)
    decide = approvals.add_parser("decide")
    decide.add_argument("id", type=UUID)
    decide.add_argument("decision", choices=["approve", "reject"])
    jobs = sub.add_parser("jobs").add_subparsers(dest="action", required=True)
    jobs.add_parser("list")
    for action in ("show", "cancel", "remove"):
        jobs.add_parser(action).add_argument("id", type=UUID)
    return root


def read_text(path, limit):
    """Read finite UTF-8 task input without executing or importing its contents."""
    with Path(path).open("rb") as stream:
        value = stream.read(limit + 1)
    if len(value) > limit:
        raise ClientError("input_too_large", 2)
    return value.decode("utf-8")


def approval_view(review):
    """Return the owner-only review without its one-time nonce, so output cannot be replayed as a decision."""
    return {key: value for key, value in review.items() if key != "review_nonce"}


def escape_char(char):
    """Return a fixed-width Python-style escape for one code point."""
    code = ord(char)
    return f"\\U{code:08x}" if code > 0xFFFF else f"\\u{code:04x}"


def terminal_text(value, *, review=False):
    """Escape non-printable characters so text cannot drive the terminal; review mode also doubles backslashes, so literal escapes stay distinguishable."""
    return "".join(
        "\\\\"
        if review and char == "\\"
        else char
        if char in "\n\t" or char.isprintable()
        else escape_char(char)
        for char in str(value)
    )


def terminal_json(value, **options):
    """Dump JSON with non-printable characters as JSON escapes; the parsed value is unchanged but cannot drive the terminal."""
    text = json.dumps(value, ensure_ascii=False, **options)
    return "".join(
        char if char == "\n" or char.isprintable() else json.dumps(char)[1:-1]
        for char in text
    )


def discard_typeahead(stdin):
    """Drop input queued before the review was shown, so only a reply typed after it can confirm."""
    try:
        import termios
    except ImportError:
        return
    try:
        termios.tcflush(stdin.fileno(), termios.TCIFLUSH)
    except (termios.error, AttributeError, OSError, ValueError):
        return


def decide_approval(client, identifier, decision, review, *, stdin=None):
    """Send one explicit human decision only after the exact scope is shown and confirmed on a terminal."""
    stdin = stdin or sys.stdin
    if review.get("state") != "pending":
        raise ClientError("approval_not_pending", 5)
    if stdin is None or not stdin.isatty():
        raise ClientError("approval_requires_terminal", 2)
    digest = review["scope_digest"]
    lines = [
        f"Approval request {identifier}",
        "Kind: " + terminal_text(review.get("kind"), review=True),
        "Workspace: " + terminal_text(review.get("workspace_id"), review=True),
        "Expires: " + terminal_text(review.get("expires_at"), review=True),
        "Scope digest: " + terminal_text(digest, review=True),
        "--- artifact ---",
        terminal_text(review.get("artifact"), review=True),
        "--- end ---",
        f"Type the first 8 characters of the scope digest to {decision}: ",
    ]
    print("\n".join(lines), end="", file=sys.stderr, flush=True)
    discard_typeahead(stdin)
    if stdin.readline().strip() != digest[:8]:
        raise ClientError("approval_confirmation_mismatch", 2)
    LOGGER.info("cli_approval_decision_sent decision=%s", decision)
    return client.request(
        "POST",
        f"/api/v1/approvals/{identifier}/decision",
        dict(
            decision=decision, scope_digest=digest, review_nonce=review["review_nonce"]
        ),
    )


def open_ui(client, *, desktop=False, auth_file=DEFAULT_AUTH):
    """Open the authenticated web UI or run Aevra's independent native application without a browser fallback."""
    if desktop:
        from apps.desktop.launcher import launch

        return launch(client, auth_file=auth_file)
    pairing = client.request("POST", PREFIX + "/ui-pairings", {})
    url = client.url + "/pair/#" + pairing["code"]
    if not webbrowser.open(url):
        raise ClientError("browser_open_failed", 6)
    LOGGER.info("cli_ui_opened desktop=False")
    return {
        "product": "Aevra",
        "opened": True,
        "desktop": False,
        "pairing_expires_in_seconds": 60,
    }


def write_launcher(
    path, url, token_path, auth_file=DEFAULT_AUTH, *, icon_directory=None
):
    """Write an exclusive Linux shortcut and its versioned transparent theme icon without embedding credentials."""
    from apps.branding.identity import install_desktop_icon
    from apps.desktop.identity import APPLICATION_ID

    ApiClient(url)
    if Path(path).exists() or Path(path).is_symlink():
        raise FileExistsError(path)
    uv = shutil.which("uv")
    if uv is None:
        raise ClientError("uv_required", 6)
    arguments = [
        uv,
        "run",
        "--project",
        str(Path(__file__).resolve().parents[2]),
        "--no-sync",
        "aevra",
        "--url",
        url,
        "--token-file",
        str(token_path.absolute()),
        "desktop",
        "--auth-file",
        str(Path(auth_file).absolute()),
    ]
    quoted = []
    for value in arguments:
        if any(character in value for character in "\n\r\x00"):
            raise ClientError("invalid_launcher_argument", 2)
        quoted.append(
            '"'
            + value.replace("\\", "\\\\")
            .replace('"', '\\"')
            .replace("`", "\\`")
            .replace("$", "\\$")
            .replace("%", "%%")
            + '"'
        )
    icon = install_desktop_icon(icon_directory)
    descriptor = os.open(
        path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o700
    )
    with os.fdopen(descriptor, "w") as output:
        output.write(
            "[Desktop Entry]\nType=Application\nName=Aevra\nComment=Open Aevra native desktop\nTerminal=false\nExec="
            + " ".join(quoted)
            + "\nIcon="
            + icon["path"]
            + "\nStartupWMClass=aevra\nCategories=Utility;\n"
        )
    LOGGER.info("cli_desktop_launcher_written")
    return {
        "product": "Aevra",
        "launcher": str(path.absolute()),
        "backend_managed_when_missing": True,
        "external_browser": False,
        "icon_name": icon["name"],
        "application_id": APPLICATION_ID,
    }


def execute(args):
    """Dispatch explicit user commands while keeping startup read-only and credentials out of output."""
    if args.command == "logo":
        from apps.branding.identity import metadata, terminal_logo

        return metadata() if args.json else terminal_logo()
    if args.command == "init":
        return initialize_auth(args.token_file, args.auth_file)
    if args.command == "doctor":
        from apps.harness.assets import asset_status

        return dict(
            schema_version=1,
            python=sys.version.split()[0],
            ui=asset_status(),
            models_changed=False,
            services_started=False,
        )
    if args.command == "serve":
        import uvicorn

        if not 1024 <= args.port <= 65535:
            raise ClientError("invalid_port", 2)
        os.environ["ASSISTANT_HARNESS_ENABLED"] = "1"
        if args.state_dir is not None:
            os.environ["ASSISTANT_HARNESS_STATE_DIR"] = str(args.state_dir.absolute())
        if args.auth_file is not None:
            os.environ["ASSISTANT_AUTH_FILE"] = str(args.auth_file.absolute())
        elif not os.environ.get("ASSISTANT_AUTH_FILE"):
            os.environ["ASSISTANT_AUTH_FILE"] = str(DEFAULT_AUTH)
        uvicorn.run(
            "apps.harness.main:create_app",
            factory=True,
            host="127.0.0.1",
            port=args.port,
            proxy_headers=False,
            access_log=False,
        )
        return {"stopped": True}
    if args.command == "ui" and args.action == "prepare":
        from apps.harness.assets import prepare_assets

        return prepare_assets()
    if args.command == "auth":
        if args.action == "logout":
            if args.token_file.exists():
                read_token(args.token_file)
            args.token_file.unlink(missing_ok=True)
            LOGGER.info("cli_local_credential_removed")
            return {"local_credential_removed": True, "server_sessions_revoked": False}
        value = getpass.getpass("Token API (không hiển thị): ")
        ApiClient(args.url, value).request("GET", PREFIX + "/status")
        save_token(args.token_file, value)
        return {"authenticated": True}
    if args.command == "desktop" and args.write_launcher is not None:
        return write_launcher(
            args.write_launcher, args.url, args.token_file, args.auth_file
        )
    client = ApiClient(args.url, read_token(args.token_file))
    if args.command == "status":
        return client.request("GET", PREFIX + "/status")
    if args.command == "generate":
        body = dict(
            kind=args.kind,
            prompt=read_text(args.prompt_file, 24000),
            width=args.width,
            height=args.height,
            seed=args.seed,
        )
        if args.kind == "video":
            body.update(seconds=args.seconds, fps=args.fps)
        return client.request("POST", PREFIX + "/generations", body)
    if args.command == "jobs":
        if args.action == "list":
            return client.request("GET", PREFIX + "/generations")
        if args.action == "cancel":
            return client.request("POST", PREFIX + f"/generations/{args.id}/cancel", {})
        return client.request(
            "DELETE" if args.action == "remove" else "GET",
            PREFIX + f"/generations/{args.id}",
        )
    if args.command == "desktop" or args.command == "ui":
        return open_ui(
            client,
            desktop=args.command == "desktop",
            auth_file=getattr(args, "auth_file", DEFAULT_AUTH),
        )
    if args.command == "chat":
        if args.json and args.message is None:
            raise ClientError("json_chat_requires_message", 2)
        policy = chat_policy(args)
        if args.message is None and not args.json and sys.stdout.isatty():
            from apps.branding.identity import terminal_logo

            print(terminal_logo())
        messages, carried, offset = [], [], 0
        while True:
            text = (
                args.message
                if args.message is not None
                else input("Bạn (/exit để thoát): ")
            )
            if text.strip() == "/exit":
                return {"closed": True}
            if policy is not None and len(messages) >= 256:
                droppable = policy.get("working_state") or policy.get("evicted_summary")
                if not droppable or policy["pinned_turns"]:
                    raise ClientError("client_history_capacity", 2)
                messages, offset = messages[64:], offset + 32
                LOGGER.info("cli_history_window_dropped pairs=32 offset=%d", offset)
            messages.append(dict(role="user", content=text))
            body = dict(
                messages=messages,
                preset=args.preset,
                context_strategy=args.context_strategy,
            )
            if policy is not None:
                body["history_policy"] = {
                    **policy,
                    "pinned_turns": [
                        number
                        for number in policy["pinned_turns"]
                        if number <= (len(messages) - 1) // 2
                    ],
                }
                if policy.get("working_state"):
                    body["history_policy"].update(
                        carried_state=[
                            item for item in carried if item["turn"] <= offset
                        ],
                        history_offset=offset,
                    )
                elif policy.get("evicted_summary"):
                    body["history_policy"]["history_offset"] = offset
            result = client.request(
                "POST",
                PREFIX + "/chat",
                body,
            )
            if args.message is not None:
                return result
            answer = result["result"]["choices"][0]["message"]["content"]
            print(answer)
            if policy is not None:
                receipt = result.get("context", {}).get("history_policy", {})
                if policy.get("working_state"):
                    carried = receipt.get("working_state", {}).get("items", carried)
                if receipt.get("evicted_turns"):
                    print(
                        "Context: đã đưa ra ngoài cửa sổ các lượt "
                        + ", ".join(str(n + offset) for n in receipt["evicted_turns"]),
                        file=sys.stderr,
                    )
                dropped = receipt.get("working_state_summary", {}).get("dropped_active")
                if dropped:
                    print(
                        "Working state: đã bỏ các mục ở lượt "
                        + ", ".join(map(str, dropped))
                        + " vì vượt giới hạn 64 mục/32 KiB",
                        file=sys.stderr,
                    )
                if receipt.get("archive"):
                    print(
                        "Context archive (tạm thời): " + receipt["archive"]["id"],
                        file=sys.stderr,
                    )
            messages.append(dict(role="assistant", content=answer))
            if policy is None:
                messages = messages[-22:]
    if args.command == "run":
        from src.application.services.review_output_contract import validate_target

        try:
            validate_target(args.output_contract, args.review_target)
        except ValueError:
            raise ClientError("invalid_review_contract_options", 2) from None
        skill = args.skill
        if skill:
            rows = client.request("GET", PREFIX + "/skills")
            matches = [
                row["installation_id"]
                for row in rows
                if row["workspace_id"] == str(args.workspace)
                and (row["id"] == skill or row["installation_id"] == skill)
            ]
            if len(matches) != 1:
                raise ClientError("skill_not_found_or_ambiguous", 2)
            skill = matches[0]
        tools = json.loads(read_text(args.tools_file, 32768)) if args.tools_file else []
        payload = dict(
            workspace_id=str(args.workspace),
            task=read_text(args.task_file, 24000),
            skill=skill,
            tools=tools,
            context_strategy=args.context_strategy,
            preset=args.preset,
            max_tokens=args.max_tokens,
        )
        if args.output_contract != "text":
            payload["output_contract"] = args.output_contract
        if args.review_target is not None:
            payload["review_target"] = args.review_target
        result = client.request(
            "POST",
            PREFIX + "/runs",
            payload,
        )
        if args.wait:
            try:
                deadline = time.monotonic() + 125
                while result["state"] not in {
                    "succeeded",
                    "failed",
                    "cancelled",
                    "interrupted",
                }:
                    if time.monotonic() > deadline:
                        client.request(
                            "POST", PREFIX + "/runs/" + result["id"] + "/cancel", {}
                        )
                        raise ClientError("wait_timeout", 7)
                    time.sleep(0.2)
                    result = client.request("GET", PREFIX + "/runs/" + result["id"])
            except KeyboardInterrupt:
                client.request("POST", PREFIX + "/runs/" + result["id"] + "/cancel", {})
                raise
            if result["state"] != "succeeded":
                raise ClientError("task_" + result["state"], 1)
        return result
    if args.command == "context":
        if args.action == "archives":
            return client.request("GET", PREFIX + "/context/archives")
        if args.action in {"recall", "forget"}:
            return client.request(
                "GET" if args.action == "recall" else "DELETE",
                PREFIX + f"/context/archives/{args.id}",
            )
        return client.request("GET", PREFIX + f"/runs/{args.id}").get(
            "context", {"available": False}
        )
    if args.command == "approvals":
        review = client.request("GET", f"/api/v1/approvals/{args.id}")
        if not isinstance(review, dict) or not all(
            isinstance(review.get(key), str) for key in ("state", "scope_digest")
        ):
            raise ClientError("invalid_server_response", 6)
        if args.action == "show":
            return approval_view(review)
        return decide_approval(client, args.id, args.decision, review)
    if args.command == "runs":
        if args.action == "list":
            return client.request("GET", PREFIX + "/runs")
        if args.action == "cancel":
            return client.request("POST", PREFIX + f"/runs/{args.id}/cancel", {})
        return client.request(
            "DELETE" if args.action == "remove" else "GET", PREFIX + f"/runs/{args.id}"
        )
    if args.command == "skills":
        if args.action == "list":
            return client.request("GET", PREFIX + "/skills")
        if args.action == "show":
            return client.request(
                "GET",
                PREFIX
                + f"/skills/installations/{args.id}?workspace_id={args.workspace}",
            )
        if args.action == "review":
            return client.request(
                "POST",
                PREFIX + "/skills/reviews",
                dict(
                    workspace_id=str(args.workspace),
                    manifest=read_text(args.manifest, 32768),
                ),
            )
        if args.action == "install":
            return client.request(
                "POST",
                PREFIX + "/skills/installations",
                dict(
                    workspace_id=str(args.workspace),
                    review_id=str(args.review),
                    sha256=args.sha256,
                ),
            )
        return client.request(
            "DELETE",
            PREFIX + f"/skills/installations/{args.id}?workspace_id={args.workspace}",
        )
    raise ClientError("unsupported_command", 2)


def main(argv=None):
    """Print reusable output and stable exit codes while suppressing credential-bearing exception details."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(name)s %(message)s",
        stream=sys.stderr,
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    args = parser().parse_args(argv)
    try:
        result = execute(args)
        if isinstance(result, str) and not args.json:
            print(terminal_text(result))
        else:
            print(terminal_json(result, indent=None if args.json else 2))
        return 0
    except ClientError as error:
        LOGGER.warning("cli_command_failed code=%s", error.code)
        print(json.dumps({"error": error.code}), file=sys.stderr)
        return error.exit_code
    except (httpx.HTTPError, tarfile.TarError):
        LOGGER.warning("cli_asset_dependency_unavailable")
        print('{"error":"asset_dependency_unavailable"}', file=sys.stderr)
        return 6
    except (OSError, ValueError):
        LOGGER.warning("cli_input_or_configuration_failed")
        print('{"error":"invalid_input_or_configuration"}', file=sys.stderr)
        return 2
    except (KeyboardInterrupt, EOFError):
        LOGGER.info("cli_interrupted")
        return 130

if __name__ == "__main__":
    raise SystemExit(main())
