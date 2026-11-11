"""Exercise explicit context policies through authenticated product HTTP, CLI and native transport contracts."""

import json
import logging
from uuid import uuid4

import httpx
import pytest

from apps.cli import main as cli
from apps.api.core.model_config import get_model_profile
from apps.harness.inference import ProductInference
from src.application.services.context_composer import compose_context
from tests import test_product_harness as harness_tests
from tests.test_context_reduction import count, dialogue

product_client = harness_tests.product_client
bearer = harness_tests.bearer
PREFIX = harness_tests.PREFIX
LOGGER = logging.getLogger(__name__)


def test_authenticated_compaction_recall_delete_and_cross_owner(
    product_client, monkeypatch, caplog
):
    """Bind cache writes/reads to server identity and deny cross-owner cache use without returning raw history."""
    caplog.set_level(logging.INFO)
    client, inference, settings, _ = product_client

    async def complete(messages, **options):
        """Use the actual composer/cache callbacks with a deterministic test tokenizer and no generation."""
        _, report = await compose_context(
            messages,
            count_tokens=count,
            preset=options["preset"],
            strategy=options["context_strategy"],
            history_policy=options.get("history_policy"),
            archive=options.get("archive"),
            recall=options.get("recall"),
        )
        return {"choices": [{"message": {"content": "fixture"}}]}, report

    monkeypatch.setattr(inference, "complete", complete)
    rows = dialogue(2)
    rows[1]["content"] += " PRIVATE_API_HISTORY"
    body = dict(
        messages=rows, history_policy=dict(mode="extractive-compact", window_turns=1)
    )
    assert client.post(PREFIX + "/chat", json=body).status_code == 401
    response = client.post(PREFIX + "/chat", json=body, headers=bearer(settings))
    assert response.status_code == 200
    assert "PRIVATE_API_HISTORY" not in response.text
    handle = response.json()["context"]["history_policy"]["archive"]["id"]
    path = PREFIX + "/context/archives/" + handle
    raw = client.get(path, headers=bearer(settings))
    assert raw.status_code == 200 and "PRIVATE_API_HISTORY" in raw.text
    assert raw.headers["cache-control"] == "private, no-store"
    assert client.get(path).status_code == 401
    foreign = client.get(path, headers=bearer(settings, 1))
    absent = client.get(
        PREFIX + "/context/archives/" + str(uuid4()), headers=bearer(settings, 1)
    )
    assert (
        foreign.status_code == absent.status_code == 404
        and foreign.json() == absent.json()
    )
    recalled = dict(
        messages=[rows[-1]],
        history_policy=dict(mode="extractive-compact", recall_ids=[handle]),
    )
    assert (
        client.post(
            PREFIX + "/chat", json=recalled, headers=bearer(settings, 1)
        ).status_code
        == 404
    )
    own = client.post(PREFIX + "/chat", json=recalled, headers=bearer(settings))
    assert own.status_code == 200
    assert own.json()["context"]["history_policy"]["recalled"][0]["id"] == handle
    assert client.delete(path, headers=bearer(settings, 1)).status_code == 404
    assert client.delete(path, headers=bearer(settings)).json() == {"removed": True}
    assert (
        client.post(
            PREFIX + "/chat", json=recalled, headers=bearer(settings)
        ).status_code
        == 404
    )
    assert "PRIVATE_API_HISTORY" not in caplog.text
    LOGGER.info("test_context_http_owner_lifecycle_verified")


def test_context_api_closed_configuration_and_overflow(product_client, monkeypatch):
    """Reject unsupported policy authority and return a finite 422 for irreducible pinned overflow."""
    client, inference, settings, _ = product_client

    async def complete(messages, **options):
        """Apply the explicit sliding policy with real budget arithmetic and a deterministic input count."""
        return await compose_context(
            messages,
            count_tokens=count,
            preset=options["preset"],
            history_policy=options["history_policy"],
        )

    monkeypatch.setattr(inference, "complete", complete)
    invalid = dict(messages=dialogue(1), history_policy=dict(owner=str(uuid4())))
    assert (
        client.post(
            PREFIX + "/chat", json=invalid, headers=bearer(settings)
        ).status_code
        == 422
    )
    body = dict(messages=dialogue(1, 17000), history_policy=dict(pinned_turns=[1]))
    response = client.post(PREFIX + "/chat", json=body, headers=bearer(settings))
    assert response.status_code == 422 and response.json() == {
        "detail": {"code": "context_overflow"}
    }


@pytest.mark.parametrize("mode", [None, "sliding-window", "extractive-compact"])
def test_cli_preserves_legacy_and_forwards_explicit_policy(mode, monkeypatch, capsys):
    """Keep default body compatibility while sending validated policy flags only when explicitly selected."""
    calls = []

    class Client:
        """Capture finite CLI requests without a service or credentials."""

        def __init__(self, url, token):
            """Accept existing client arguments without network use."""

        def request(self, method, path, payload=None):
            """Retain a transport-level copy so later interactive mutations cannot alter the assertion."""
            calls.append((method, path, json.loads(json.dumps(payload))))
            return {
                "result": {"choices": [{"message": {"content": "answer"}}]},
                "context": {},
            }

    monkeypatch.setattr(cli, "ApiClient", Client)
    monkeypatch.setattr(cli, "read_token", lambda path: "t" * 48)
    args = ["--json", "chat", "--message", "Atlas?"]
    if mode:
        args += ["--history-policy", mode, "--history-window", "2", "--pin-turn", "1"]
    assert cli.main(args) == 0
    body = calls[0][2]
    if mode:
        assert (
            body["history_policy"]["mode"] == mode
            and body["history_policy"]["window_turns"] == 2
        )
        assert body["history_policy"]["pinned_turns"] == []
    else:
        assert set(body) == {"messages", "preset", "context_strategy"}
    assert "answer" in capsys.readouterr().out


def test_cli_interactive_pins_survive_and_capacity_is_explicit(monkeypatch, capsys):
    """Retain numbered original pairs for explicit policies and stop at the API bound without silent local truncation."""
    lengths, pins = [], []

    class Client:
        """Record successive interactive messages without actually sending raw text."""

        def __init__(self, url, token):
            """Bind no external resources for the local capacity test."""

        def request(self, method, path, payload):
            """Observe the actual request length and pin references before returning synthetic text."""
            lengths.append(len(payload["messages"]))
            pins.append(list(payload["history_policy"]["pinned_turns"]))
            return {
                "result": {"choices": [{"message": {"content": "answer"}}]},
                "context": {},
            }

    monkeypatch.setattr(cli, "ApiClient", Client)
    monkeypatch.setattr(cli, "read_token", lambda path: "t" * 48)
    monkeypatch.setattr("builtins.input", lambda prompt: "question")
    assert (
        cli.main(["chat", "--history-policy", "sliding-window", "--pin-turn", "1"]) == 2
    )
    assert lengths == list(range(1, 256, 2))
    assert pins[0] == [] and all(value == [1] for value in pins[1:])
    assert "client_history_capacity" in capsys.readouterr().err


@pytest.mark.parametrize("action,method", [("recall", "GET"), ("forget", "DELETE")])
def test_cli_archive_operations_are_explicit(action, method, monkeypatch):
    """Route explicit raw recall and deletion only through the authenticated cache endpoint."""
    calls, handle = [], str(uuid4())

    class Client:
        """Capture one protected archive operation without reading live credentials."""

        def __init__(self, url, token):
            """Accept the finite constructor contract."""

        def request(self, verb, path):
            """Record the explicit operation and return no raw test text."""
            calls.append((verb, path))
            return {"ok": True}

    monkeypatch.setattr(cli, "ApiClient", Client)
    monkeypatch.setattr(cli, "read_token", lambda path: "t" * 48)
    assert cli.main(["context", action, handle]) == 0
    assert calls == [(method, PREFIX + "/context/archives/" + handle)]


@pytest.mark.parametrize(
    "flags",
    [
        ["--history-window", "2"],
        ["--history-policy", "sliding-window", "--recall", str(uuid4())],
        ["--history-policy", "sliding-window", "--history-window", "0"],
    ],
)
def test_cli_policy_errors_are_local_and_finite(flags, monkeypatch, capsys):
    """Reject incoherent flags without sending text or displaying validation payloads."""
    monkeypatch.setattr(cli, "read_token", lambda path: "t" * 48)
    assert cli.main(["chat", "--message", "PRIVATE_INPUT"] + flags) == 2
    assert "PRIVATE_INPUT" not in capsys.readouterr().err


@pytest.mark.asyncio
async def test_inference_uses_native_template_and_same_approved_model():
    """Carry explicit reduction into the real inference adapter using protocol doubles, not model-quality claims."""
    templates, completions = [], []
    model = get_model_profile("core")["model_id"]

    def respond(request):
        """Expose exact template/tokenizer/completion routes and capture the final native payload."""
        payload = json.loads(request.content) if request.content else {}
        if request.url.path == "/v1/models":
            return httpx.Response(200, json={"data": [{"id": model}]})
        if request.url.path == "/apply-template":
            templates.append(payload)
            return httpx.Response(200, json={"prompt": json.dumps(payload["messages"])})
        if request.url.path == "/tokenize":
            return httpx.Response(
                200, json={"tokens": list(range(len(payload["content"]) // 4 + 1))}
            )
        if request.url.path == "/v1/chat/completions":
            completions.append(payload)
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {"role": "assistant", "content": "G-17"},
                            "finish_reason": "stop",
                        }
                    ]
                },
            )
        raise AssertionError(request.url.path)

    result, report = await ProductInference(
        transport=httpx.MockTransport(respond)
    ).complete(
        dialogue(3),
        history_policy={"window_turns": 1, "pinned_turns": [1]},
        preset="fast",
    )
    assert result["choices"][0]["message"]["content"] == "G-17"
    assert report["history_policy"]["retained_turns"] == [1, 3]
    assert len(completions) == 1 and completions[0]["model"] == model
    assert all(
        payload["chat_template_kwargs"]["enable_thinking"] is False
        for payload in templates
    )
    assert completions[0]["messages"][-1]["content"] == dialogue(3)[-1]["content"]


def test_cache_metadata_list_and_failed_completion_cleanup(product_client, monkeypatch):
    """Leave interrupted preparation snapshots discoverable only to the owner for explicit cache cleanup."""
    client, inference, settings, _ = product_client

    async def complete(messages, **options):
        """Create a real bounded snapshot and then simulate an unavailable model completion."""
        await compose_context(
            messages,
            count_tokens=count,
            preset=options["preset"],
            history_policy=options["history_policy"],
            archive=options["archive"],
        )
        raise RuntimeError("private_failure_detail")

    monkeypatch.setattr(inference, "complete", complete)
    body = dict(
        messages=dialogue(2),
        history_policy=dict(mode="extractive-compact", window_turns=1),
    )
    response = client.post(PREFIX + "/chat", json=body, headers=bearer(settings))
    assert response.status_code == 502 and "private_failure_detail" not in response.text
    path = PREFIX + "/context/archives"
    own = client.get(path, headers=bearer(settings))
    assert own.status_code == 200 and len(own.json()) == 1
    assert (
        "payload" not in own.text
        and own.headers["cache-control"] == "private, no-store"
    )
    assert client.get(path, headers=bearer(settings, 1)).json() == []
    assert client.get(path).status_code == 401
    assert (
        client.delete(
            path + "/" + own.json()[0]["id"], headers=bearer(settings)
        ).status_code
        == 200
    )
    assert client.get(path, headers=bearer(settings)).json() == []


def test_malformed_explicit_context_is_422_with_no_payload_echo(
    product_client, monkeypatch
):
    """Return a finite context error for unsupported message roles under an explicit policy."""
    client, inference, settings, _ = product_client

    async def complete(messages, **options):
        """Pass malformed client messages through the actual production validation boundary."""
        return await compose_context(
            messages,
            count_tokens=count,
            preset=options["preset"],
            history_policy=options["history_policy"],
        )

    monkeypatch.setattr(inference, "complete", complete)
    response = client.post(
        PREFIX + "/chat",
        headers=bearer(settings),
        json=dict(
            messages=[dict(role="tool", content="PRIVATE_MALFORMED")], history_policy={}
        ),
    )
    assert response.status_code == 422
    assert response.json() == {"detail": {"code": "invalid_context_request"}}
