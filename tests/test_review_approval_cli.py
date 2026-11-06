"""Verify explicit typed CLI consent, full escaped review, local URL boundaries and credential/nonce privacy."""

import json
import logging
import sys
from uuid import uuid4

import httpx
import pytest
from test_approvals import ARTIFACT
from test_workspace_reader import source_workspace as source_workspace

from scripts.review_approval import review_approval, validate_base_url
from src.application.services.approvals import ApprovalStore


@pytest.fixture
def cli_review(source_workspace):
    """Expose a real approval store through a controlled transport without making any external approval decision."""
    catalog, spec, _, _ = source_workspace
    store = ApprovalStore(catalog)
    raw = ARTIFACT + b"\nANSI-CANARY\x1b[31m"
    identifier = store.create(spec.owner_id, spec.workspace_id, "patch", raw)
    requests = []

    def handle(request):
        """Serve real review/decision transitions while retaining request metadata for privacy assertions."""
        requests.append(request)
        assert request.headers["Authorization"] == "Bearer PRIVATE-CLI-TOKEN"
        if request.method == "GET":
            return httpx.Response(200, json=store.review(spec.owner_id, identifier))
        body = json.loads(request.content)
        return httpx.Response(
            200,
            json=store.decide(
                spec.owner_id,
                identifier,
                body["decision"],
                body["scope_digest"],
                body["review_nonce"],
            ),
        )

    return store, spec, identifier, requests, httpx.MockTransport(handle)


@pytest.mark.parametrize("typed", ["approve", "reject", "empty", "partial", "wrong_id"])
def test_cli_requires_exact_typed_full_request_identity(cli_review, caplog, typed):
    """Display the complete escaped concrete artifact and submit only an exact deliberate owner decision."""
    store, spec, identifier, requests, transport = cli_review
    caplog.set_level(logging.INFO)
    nonce = store.review(spec.owner_id, identifier)["review_nonce"]
    values = dict(
        approve="APPROVE " + str(identifier),
        reject="REJECT " + str(identifier),
        empty="",
        partial="APPROVE",
        wrong_id="APPROVE " + str(uuid4()),
    )
    output = []
    result = review_approval(
        "http://127.0.0.1:9000/api/v1",
        identifier,
        "PRIVATE-CLI-TOKEN",
        read_line=lambda prompt: values[typed],
        write=output.append,
        transport=transport,
    )
    assert result == (0 if typed in {"approve", "reject"} else 2)
    assert [request.method for request in requests] == (
        ["GET", "POST"] if typed in {"approve", "reject"} else ["GET"]
    )
    rendered = "\n".join(output)
    assert (
        "ANSI-CANARY" in rendered and "\\u001b" in rendered and "\x1b" not in rendered
    )
    assert nonce not in rendered and "PRIVATE-CLI-TOKEN" not in rendered
    assert (
        nonce not in caplog.text
        and "PRIVATE-CLI-TOKEN" not in caplog.text
        and "ANSI-CANARY" not in caplog.text
    )
    assert store.review(spec.owner_id, identifier)["state"] == dict(
        approve="approved", reject="rejected"
    ).get(typed, "pending")


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/api/v1",
        "http://localhost/api/v1",
        "file:///api/v1",
        "http://127.0.0.1:9000/api/v1?token=x",
        "http://user:pass@127.0.0.1/api/v1",
        "http://127.0.0.1/api/v1#fragment",
        "http://127.0.0.1/other",
        "http://127.0.0.1:99999/api/v1",
    ],
)
def test_cli_remote_or_credential_urls_rejected_before_network(url):
    """Reject remote/DNS/credential/query/fragment/port/path targets rather than risking bearer-token forwarding."""
    with pytest.raises(ValueError, match="approval_cli_url_invalid"):
        validate_base_url(url)


@pytest.mark.parametrize(
    "fault", ["redirect", "digest", "artifact", "nonce", "oversized", "eof"]
)
def test_cli_invalid_or_changed_review_never_submits(cli_review, fault):
    """Abort redirects, corrupted/oversized review and cancelled input without an approval POST or execution."""
    store, spec, identifier, _, _ = cli_review
    calls = []

    def handle(request):
        """Return only a controlled invalid review and forbid any decision request."""
        calls.append(request.method)
        assert request.method == "GET"
        if fault == "redirect":
            return httpx.Response(
                302, headers={"Location": "https://untrusted.invalid"}
            )
        if fault == "oversized":
            return httpx.Response(200, content=b"x" * 262145)
        review = store.review(spec.owner_id, identifier)
        if fault == "digest":
            review["scope_digest"] = "0" * 64
        elif fault == "artifact":
            review["artifact"] += " changed"
        elif fault == "nonce":
            review["review_nonce"] = None
        return httpx.Response(200, json=review)

    def input_line(prompt):
        """Simulate an explicit cancellation or fail if invalid review ever reaches a consent prompt."""
        if fault == "eof":
            raise EOFError()
        pytest.fail("invalid review reached consent prompt")

    output = []
    result = review_approval(
        "http://127.0.0.1:9000/api/v1",
        identifier,
        "PRIVATE-CLI-TOKEN",
        read_line=input_line,
        write=output.append,
        transport=httpx.MockTransport(handle),
    )
    assert result == (2 if fault == "eof" else 1) and calls == ["GET"]
    assert store.review(spec.owner_id, identifier)["state"] == "pending"


@pytest.mark.parametrize("phase", ["review", "receipt"])
def test_broken_output_does_not_invent_or_execute_consent(cli_review, phase):
    """Abort before consent if full review cannot display and preserve actual server state if receipt display fails."""
    store, spec, identifier, requests, transport = cli_review
    writes = []

    def output(text):
        """Fail a disclosed terminal-output phase without executing any proposed action."""
        writes.append(text)
        if phase == "review" or len(writes) > 1:
            raise BrokenPipeError()

    result = review_approval(
        "http://127.0.0.1:9000/api/v1",
        identifier,
        "PRIVATE-CLI-TOKEN",
        read_line=lambda prompt: "APPROVE " + str(identifier),
        write=output,
        transport=transport,
    )
    assert result == 1
    assert [request.method for request in requests] == (
        ["GET"] if phase == "review" else ["GET", "POST"]
    )
    assert store.review(spec.owner_id, identifier)["state"] == (
        "pending" if phase == "review" else "approved"
    )


def test_full_maximum_review_is_displayed_before_explicit_consent(source_workspace):
    """Show all32768 UTF-8 review bytes before requesting consent, without truncating or hiding the ending marker."""
    store = ApprovalStore(source_workspace[0])
    spec = source_workspace[1]
    artifact = b"x" * 32760 + b"END-MARK"
    identifier = store.create(spec.owner_id, spec.workspace_id, "patch", artifact)
    output = []

    def handle(request):
        """Serve the real maximum bounded review and exact synthetic explicit decision."""
        if request.method == "GET":
            return httpx.Response(200, json=store.review(spec.owner_id, identifier))
        body = json.loads(request.content)
        return httpx.Response(
            200,
            json=store.decide(
                spec.owner_id,
                identifier,
                body["decision"],
                body["scope_digest"],
                body["review_nonce"],
            ),
        )

    def consent(prompt):
        """Require the complete artifact to have been rendered before simulating explicit fixture consent."""
        visible = json.loads(output[0])
        assert visible["artifact"].encode() == artifact and visible[
            "artifact"
        ].endswith("END-MARK")
        return "APPROVE " + str(identifier)

    assert (
        review_approval(
            "http://127.0.0.1:9000/api/v1",
            identifier,
            "PRIVATE-CLI-TOKEN",
            read_line=consent,
            write=output.append,
            transport=httpx.MockTransport(handle),
        )
        == 0
    )


def test_private_token_prompt_cancellation_and_ipv6_loopback(monkeypatch):
    """Cancel the operator token prompt before any request and allow only a valid explicit IPv6 loopback base."""
    from scripts import review_approval as module

    assert validate_base_url("http://[::1]:9000/api/v1/") == "http://[::1]:9000/api/v1"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "review_approval",
            "--base-url",
            "http://127.0.0.1:9000/api/v1",
            "--request-id",
            str(uuid4()),
        ],
    )

    def cancel(prompt):
        """Simulate operator cancellation without providing or printing a credential."""
        raise EOFError()

    monkeypatch.setattr(module.getpass, "getpass", cancel)
    assert module.main() == 2
