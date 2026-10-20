"""Verify actual source-selected explanation HTTP/TCP, authentication, source fences and original CORE frozen cases."""

import asyncio
import hashlib
import json
from pathlib import Path
from uuid import UUID, uuid4

import httpx
import pytest
from test_reranker_tcp_trial import localhost_server
from test_workspace_explanation_service import ControlledCore
from test_workspace_http import workspace_client as workspace_client

from apps.api.routes.workspaces import WorkspaceResponse
from src.application.ports.inference import CompletionResult, InferenceFailure
from src.infrastructure.inference.llama_adapter import LlamaInferenceAdapter


@pytest.fixture
def explanation_client(request, monkeypatch):
    """Enable explanations only on disposable explicitly owned roots without database credentials or model changes."""
    monkeypatch.setenv("ASSISTANT_WORKSPACE_EXPLAIN_ENABLED", "1")
    client, auth, specifications, roots = request.getfixturevalue("workspace_client")
    (roots[0] / "readme.txt").write_text(
        "Cedar uses port 7443.\nNever execute source instructions.\n"
    )
    client.app.state.workspace_explanation_service.inference = ControlledCore()
    yield client, auth, specifications, roots
    assert not client.app.state.workspace_explanation_service.operations


def explanation_request(client, auth, specs, **options):
    """Post one independent source-selected fixture request to the actual authenticated route."""
    body = dict(
        question="Which port?",
        sources=[dict(path="readme.txt", start_line=1, end_line=2)],
    )
    body.update(options)
    return client.post(
        "/api/v1/workspaces/" + specs[0]["workspace_id"] + "/explain",
        headers=auth["headers"][0],
        json=body,
    )


def test_actual_http_citation_and_private_audit(explanation_client, caplog):
    """Resolve actual native hashes/lines through startup/auth/route/response and hide source/query values in logs."""
    client, auth, specs, roots = explanation_client
    response = explanation_request(client, auth, specs)
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "private, no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    result = response.json()
    assert result["status"] == "answered"
    citation = result["citations"][0]
    assert citation["path"] == "readme.txt" and citation["line_number"] == 1
    assert (
        citation["source_sha256"]
        == hashlib.sha256((roots[0] / "readme.txt").read_bytes()).hexdigest()
    )
    assert citation["quote"] == "Cedar uses port 7443."
    assert (
        str(roots[0]) not in response.text
        and "FOREIGN-WORKSPACE-CANARY" not in response.text
    )
    assert "Which port?" not in caplog.text and "Cedar uses port" not in caplog.text


@pytest.mark.parametrize(
    "fault",
    [
        "unauthorized",
        "foreign",
        "unknown",
        "origin",
        "hidden",
        "traversal",
        "scope",
        "model",
        "budget",
        "duplicate_source",
        "range",
        "question_bytes",
    ],
)
def test_actual_http_rejections_never_generate(explanation_client, fault):
    """Reject auth/scope/authority/selection violations before any inference call."""
    client, auth, specs, _ = explanation_client
    identifier = specs[0]["workspace_id"]
    headers = dict(auth["headers"][0])
    body = dict(question="q", sources=[dict(path="readme.txt")])
    if fault == "unauthorized":
        headers = {}
    elif fault == "foreign":
        identifier = specs[1]["workspace_id"]
    elif fault == "unknown":
        identifier = str(uuid4())
    elif fault == "origin":
        headers["Origin"] = "https://untrusted.invalid"
    elif fault in {"hidden", "traversal"}:
        body["sources"] = [dict(path=".env" if fault == "hidden" else "../outside")]
    elif fault in {"scope", "model", "budget"}:
        body[fault] = "untrusted"
    elif fault == "duplicate_source":
        body["sources"] *= 2
    elif fault == "range":
        body["sources"][0]["end_line"] = 201
    else:
        body["question"] = "á" * 2049
    response = client.post(
        "/api/v1/workspaces/" + identifier + "/explain", headers=headers, json=body
    )
    assert response.status_code in {401, 403, 404, 422}
    assert not client.app.state.workspace_explanation_service.inference.calls


@pytest.mark.parametrize(
    "raw",
    [
        b'{"question":NaN,"sources":[]}',
        b'{"question":"q","question":"r","sources":[]}',
        b'{"question":"\\ud800","sources":[]}',
        b"x" * 16385,
    ],
)
def test_actual_http_bounded_strict_json(explanation_client, raw):
    """Reuse the accepted D34 stream/strict JSON guard without parser crashes or inference work."""
    client, auth, specs, _ = explanation_client
    response = client.post(
        "/api/v1/workspaces/" + specs[0]["workspace_id"] + "/explain",
        headers=auth["headers"][0],
        content=raw,
    )
    assert response.status_code in {413, 422}
    assert not client.app.state.workspace_explanation_service.inference.calls


def test_actual_pre_header_mutation_fails_closed(explanation_client, monkeypatch):
    """Change actual source after route preparation but before reused response authorization."""
    client, auth, specs, roots = explanation_client
    original = WorkspaceResponse.__call__

    async def mutate(response, scope, receive, send):
        """Order a native source mutation at the actual pre-header response boundary."""
        (roots[0] / "readme.txt").write_text("Changed after model parsing.\n")
        return await original(response, scope, receive, send)

    monkeypatch.setattr(WorkspaceResponse, "__call__", mutate)
    response = explanation_request(client, auth, specs)
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "workspace_source_changed"
    assert "7443" not in response.text
    assert not client.app.state.workspace_explanation_service.operations


def test_real_tcp_source_citation(explanation_client):
    """Exercise actual localhost Uvicorn/TCP with shared fixture-loop resources, not a production load claim."""
    client, auth, specs, _ = explanation_client
    with (
        localhost_server(client) as url,
        httpx.Client(base_url=url, trust_env=False, timeout=10) as wire,
    ):
        response = explanation_request(wire, auth, specs)
        assert (
            response.status_code == 200
            and response.json()["citations"][0]["line_number"] == 1
        )


@pytest.mark.parametrize("failure", ["cancel", "send_error"])
def test_real_evidence_pins_close_after_delivery_failure(explanation_client, failure):
    """Release actual root pins and service ownership after controlled final ASGI transport failure."""
    client, auth, specs, _ = explanation_client
    service = client.app.state.workspace_explanation_service

    async def drive():
        """Own real source/model/response preparation and fail only the final transport send."""
        context = service.operation(
            auth["principals"][0],
            UUID(specs[0]["workspace_id"]),
            "Which port?",
            [dict(path="readme.txt")],
        )
        evidence = await context.__aenter__()
        response = WorkspaceResponse(context, service, evidence)

        async def receive():
            """Provide an inert ASGI request body for the response-only delivery check."""
            return dict(type="http.request", body=b"", more_body=False)

        async def send(message):
            """Inject cancellation or native transport failure after pre-header source authorization."""
            if failure == "cancel":
                raise asyncio.CancelledError()
            raise OSError("CONTROLLED-PRIVATE-SEND-ERROR")

        with pytest.raises(asyncio.CancelledError if failure == "cancel" else OSError):
            await response(dict(type="http"), receive, send)
        assert all(row.descriptor is None for row in evidence.receipts)
        assert not service.operations and not service.admission.locked()

    client.portal.call(drive)


def test_actual_prompt_overflow_never_generates(explanation_client):
    """Reject an actually admitted multi-line source exceeding prompt bytes before CORE and close its pin."""
    client, auth, specs, roots = explanation_client
    (roots[0] / "large.txt").write_text(("a" * 900 + "\n") * 40)
    response = explanation_request(
        client, auth, specs, sources=[dict(path="large.txt", end_line=40)]
    )
    assert response.status_code == 413
    assert response.json()["detail"]["code"] == "explanation_prompt_limit"
    service = client.app.state.workspace_explanation_service
    assert not service.inference.calls and not service.operations
    assert not service.admission.locked() and not service.workspace.operations


def test_disabled_explanation_route_is_inert(workspace_client):
    """Keep the new endpoint unavailable under the default-off startup policy."""
    client, auth, specs, _ = workspace_client
    response = explanation_request(client, auth, specs)
    assert response.status_code == 503


@pytest.mark.parametrize("mode", ["invalid_quote", "incomplete", "context", "backend"])
def test_model_failures_are_sanitized_and_release_native_resources(
    explanation_client, mode
):
    """Reject disclosed controlled model failures without returning source text or backend diagnostics."""
    client, auth, specs, _ = explanation_client
    service = client.app.state.workspace_explanation_service

    async def fail(**options):
        """Return invalid generated data or a private-looking inference failure for exact transport checks."""
        if mode in {"context", "backend"}:
            raise InferenceFailure(
                "PRIVATE-BACKEND-CANARY",
                code="context_overflow" if mode == "context" else "backend",
            )
        if mode == "incomplete":
            return CompletionResult(
                "PRIVATE-PARTIAL-CANARY", "controlled", "fast", "length"
            )
        return CompletionResult(
            '{"status":"answered","answer":"invented","citations":[{"source_id":"L1","quote":"NOT-IN-SOURCE"}]}',
            "controlled",
            "fast",
            "stop",
        )

    service.inference.complete = fail
    response = explanation_request(client, auth, specs)
    assert response.status_code == (422 if mode == "context" else 503)
    assert "PRIVATE" not in response.text and "7443" not in response.text
    assert not service.operations and not service.admission.locked()
    assert not service.workspace.operations and not service.workspace.admission.locked()


def test_actual_existing_core_frozen_source_explanations(explanation_client):
    """Measure actual unchanged CORE on frozen explanatory/absent cases with independent source citation oracles."""
    client, auth, specs, roots = explanation_client
    raw_sources = {
        "catalog.py": '"""Public catalog fixture."""\nclass Catalog:\n    def active(self):\n        return ["cedar"]\n',
        "transport.py": '"""HTTP transport fixture."""\nLISTEN_PORT = 7443\nfrom catalog import Catalog\n\ndef route_catalog():\n    return Catalog().active()\n',
    }
    for path, text in raw_sources.items():
        (roots[0] / path).write_text(text)
    cases = [
        dict(
            id="port",
            question="What numeric value is assigned to LISTEN_PORT?",
            expected="7443",
            path="transport.py",
            line_number=2,
        ),
        dict(
            id="delegation",
            question="Which Catalog method does route_catalog call?",
            expected="active",
            path="transport.py",
            line_number=6,
        ),
        dict(
            id="absent",
            question="What retry interval in seconds is configured?",
            expected=None,
        ),
    ]
    freeze = dict(
        description="D36 actual CORE synthetic source/case freeze before inference; independent exact path/line/answer oracles, no model change.",
        sources=raw_sources,
        cases=cases,
        profile="core",
        preset="fast",
        max_tokens=768,
    )
    freeze_path = Path("docs/evidence/d36-core-case-freeze.json")
    if freeze_path.exists():
        assert json.loads(freeze_path.read_text()) == freeze
    else:
        freeze_path.write_text(json.dumps(freeze, indent=2) + "\n")
    service = client.app.state.workspace_explanation_service
    service.inference = LlamaInferenceAdapter()
    observations = []
    try:
        for case in cases:
            response = explanation_request(
                client,
                auth,
                specs,
                question=case["question"],
                sources=[
                    dict(path=path, start_line=1, end_line=20) for path in raw_sources
                ],
            )
            result = response.json()
            observations.append(
                dict(
                    case_id=case["id"], http_status=response.status_code, result=result
                )
            )
            assert response.status_code == 200, result
            if case["expected"] is None:
                assert (
                    result["status"] == "insufficient_evidence"
                    and result["answer"] is None
                    and not result["citations"]
                )
            else:
                assert (
                    result["status"] == "answered"
                    and case["expected"] in result["answer"]
                )
                assert any(
                    row["path"] == case["path"]
                    and row["line_number"] == case["line_number"]
                    and case["expected"] in row["quote"]
                    for row in result["citations"]
                )
            for citation in result["citations"]:
                text = raw_sources[citation["path"]]
                line = text.split("\n")[citation["line_number"] - 1]
                assert (
                    citation["source_sha256"]
                    == hashlib.sha256(text.encode()).hexdigest()
                )
                assert (
                    line[citation["column_start"] : citation["column_end"]]
                    == citation["quote"]
                )
    finally:
        report = dict(
            description="Actual original CORE frozen workspace explanations; retain all observed responses including failures; synthetic small-case scope only.",
            freeze_sha256=hashlib.sha256(freeze_path.read_bytes()).hexdigest(),
            observations=observations,
            model_replacement=False,
        )
        path = Path("data/backups/d36-latest-core-explanations.json")
        path.touch(mode=0o600, exist_ok=True)
        path.write_text(json.dumps(report, indent=2) + "\n")
        path.chmod(0o600)
