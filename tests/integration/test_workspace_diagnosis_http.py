"""Verify native authenticated diagnostic plans and actual frozen CORE bug proposals without executing them."""

import hashlib
import json
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from test_reranker_tcp_trial import localhost_server
from test_workspace_diagnosis import proposed_diagnosis
from test_workspace_diagnosis_service import ControlledDiagnosticCore
from test_workspace_explanation_http import explanation_client as explanation_client
from test_workspace_http import workspace_client as workspace_client

from apps.api.routes.workspaces import WorkspaceResponse
from src.application.ports.inference import CompletionResult
from src.infrastructure.inference.llama_adapter import LlamaInferenceAdapter


@pytest.fixture
def diagnosis_client(request, monkeypatch):
    """Enable only disposable scoped diagnosis and bind an explicitly controlled model port for transport cases."""
    monkeypatch.setenv("ASSISTANT_WORKSPACE_DIAGNOSE_ENABLED", "1")
    client, auth, specs, roots = request.getfixturevalue("explanation_client")
    (roots[0] / "calc.py").write_text(
        '"""Arithmetic fixture."""\ndef double(value):\n    return value + 1\n'
    )
    client.app.state.workspace_diagnosis_service.inference = ControlledDiagnosticCore()
    yield client, auth, specs, roots
    assert not client.app.state.workspace_diagnosis_service.operations


def diagnose(client, auth, specs, **options):
    """Post a concrete supplied symptom and explicit source selection to the real local diagnosis route."""
    body = dict(
        symptom="double(3) returned4, expected6",
        sources=[dict(path="calc.py", start_line=1, end_line=10)],
    )
    body.update(options)
    return client.post(
        "/api/v1/workspaces/" + specs[0]["workspace_id"] + "/diagnose",
        headers=auth["headers"][0],
        json=body,
    )


def test_actual_http_plan_quotes_and_unchanged_source(diagnosis_client, caplog):
    """Resolve exact native bug lines and return only an unexecuted manual plan without source mutation."""
    client, auth, specs, roots = diagnosis_client
    before = (roots[0] / "calc.py").read_bytes()
    response = diagnose(client, auth, specs)
    assert response.status_code == 200, response.text
    result = response.json()
    assert (
        result["status"] == "diagnosed" and result["execution_status"] == "not_executed"
    )
    assert result["plan"][0]["step"] == 1 and "3" in result["reproduction"]["input"]
    citation = result["citations"][0]
    assert citation["path"] == "calc.py" and citation["line_number"] == 3
    assert citation["source_sha256"] == hashlib.sha256(before).hexdigest()
    assert citation["quote"] == "return value + 1"
    assert (roots[0] / "calc.py").read_bytes() == before
    assert response.headers["cache-control"] == "private, no-store"
    assert (
        str(roots[0]) not in response.text
        and "FOREIGN-WORKSPACE-CANARY" not in response.text
    )
    assert "returned4" not in caplog.text and "return value + 1" not in caplog.text


@pytest.mark.parametrize(
    "fault",
    [
        "unauthorized",
        "foreign",
        "unknown",
        "origin",
        "execute",
        "patch",
        "model",
        "hidden",
        "bytes",
    ],
)
def test_http_diagnosis_scope_authority_rejection_before_generation(
    diagnosis_client, fault
):
    """Reject identity/source/execution/model overrides before any model operation."""
    client, auth, specs, _ = diagnosis_client
    identifier = specs[0]["workspace_id"]
    headers = dict(auth["headers"][0])
    body = dict(symptom="q", sources=[dict(path="calc.py")])
    if fault == "unauthorized":
        headers = {}
    elif fault == "foreign":
        identifier = specs[1]["workspace_id"]
    elif fault == "unknown":
        identifier = str(uuid4())
    elif fault == "origin":
        headers["Origin"] = "https://untrusted.invalid"
    elif fault in {"execute", "patch", "model"}:
        body[fault] = "untrusted"
    elif fault == "hidden":
        body["sources"] = [dict(path=".env")]
    else:
        body["symptom"] = "á" * 2049
    response = client.post(
        "/api/v1/workspaces/" + identifier + "/diagnose", headers=headers, json=body
    )
    assert response.status_code in {401, 403, 404, 422}
    assert not client.app.state.workspace_diagnosis_service.inference.calls


def test_extra_generated_execution_claim_fails_closed(diagnosis_client):
    """Reject a controlled model claiming execution without changing files or returning fabricated runtime results."""
    client, auth, specs, _ = diagnosis_client

    async def invented_execution(**options):
        """Inject an authority-claiming generated field into an otherwise correctly cited synthetic plan."""
        payload = proposed_diagnosis("L3")
        payload["executed"] = True
        return CompletionResult(json.dumps(payload), "controlled", "fast", "stop")

    client.app.state.workspace_diagnosis_service.inference.complete = invented_execution
    response = diagnose(client, auth, specs)
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "diagnosis_answer_invalid"
    assert not client.app.state.workspace_diagnosis_service.operations


def test_actual_diagnosis_pre_header_source_mutation(diagnosis_client, monkeypatch):
    """Order a native source change after model parsing and reject stale diagnostic output at delivery."""
    client, auth, specs, roots = diagnosis_client
    original = WorkspaceResponse.__call__

    async def mutate(response, scope, receive, send):
        """Change only disposable source at the actual response fence boundary."""
        (roots[0] / "calc.py").write_text("changed\n")
        return await original(response, scope, receive, send)

    monkeypatch.setattr(WorkspaceResponse, "__call__", mutate)
    response = diagnose(client, auth, specs)
    assert response.status_code == 409 and "diagnosis" not in response.json()


def test_actual_tcp_manual_diagnostic_plan(diagnosis_client):
    """Exercise real loopback Uvicorn/TCP using shared fixture resources and no source execution."""
    client, auth, specs, _ = diagnosis_client
    with (
        localhost_server(client) as url,
        httpx.Client(base_url=url, trust_env=False, timeout=10) as wire,
    ):
        response = diagnose(wire, auth, specs)
        assert (
            response.status_code == 200
            and response.json()["execution_status"] == "not_executed"
        )


def test_default_off_diagnosis_is_unavailable(workspace_client):
    """Keep the authenticated route inert without explicit diagnosis enablement."""
    client, auth, specs, _ = workspace_client
    assert diagnose(client, auth, specs).status_code == 503


def test_actual_existing_core_frozen_diagnostic_plan(diagnosis_client):
    """Evaluate real unchanged CORE against authored source/bug/reproducer oracles without executing its steps."""
    client, auth, specs, roots = diagnosis_client
    source = (roots[0] / "calc.py").read_bytes()
    cases = [
        dict(
            id="increment_instead_of_double",
            symptom="The supplied function double(3) returns4 but must return6. Identify the source cause and give a concrete manual reproduction plan.",
            expected_status="diagnosed",
            path="calc.py",
            line_number=3,
            quote="return value + 1",
            input_contains="3",
            expected_contains="6",
        ),
        dict(
            id="absent_retry",
            symptom="Why does the configured retry interval sleep2 seconds instead of1?",
            expected_status="insufficient_evidence",
        ),
    ]
    freeze = dict(
        description="D37 synthetic source/bug/manual reproduction oracles fixed before actual CORE; generated steps never executed.",
        source=source.decode(),
        source_sha256=hashlib.sha256(source).hexdigest(),
        cases=cases,
        profile="core",
        preset="fast",
        max_tokens=768,
    )
    freeze_path = Path("docs/evidence/d37-core-case-freeze.json")
    if freeze_path.exists():
        assert json.loads(freeze_path.read_text()) == freeze
    else:
        freeze_path.write_text(json.dumps(freeze, indent=2) + "\n")
    client.app.state.workspace_diagnosis_service.inference = LlamaInferenceAdapter()
    observations = []
    try:
        for case in cases:
            response = diagnose(client, auth, specs, symptom=case["symptom"])
            result = response.json()
            observations.append(
                dict(
                    case_id=case["id"], http_status=response.status_code, result=result
                )
            )
            assert response.status_code == 200, result
            assert result["status"] == case["expected_status"]
            assert result["execution_status"] == "not_executed"
            if case["expected_status"] == "diagnosed":
                assert any(
                    row["path"] == case["path"]
                    and row["line_number"] == case["line_number"]
                    and case["quote"] in row["quote"]
                    for row in result["citations"]
                )
                assert case["input_contains"] in result["reproduction"]["input"]
                assert (
                    case["expected_contains"]
                    in result["reproduction"]["expected_result"]
                )
                assert result["plan"] and result["reproduction"]["steps"]
                assert any(
                    word in result["diagnosis"].lower()
                    for word in ("add", "increment", "+", "cộng")
                )
            else:
                assert (
                    result["diagnosis"] is None
                    and not result["plan"]
                    and not result["citations"]
                )
            assert (roots[0] / "calc.py").read_bytes() == source
    finally:
        report = dict(
            description="Actual original CORE diagnostic proposals on frozen authored synthetic cases; no proposed source/test/command executed.",
            freeze_sha256=hashlib.sha256(freeze_path.read_bytes()).hexdigest(),
            observations=observations,
            execution_status="not_executed",
            model_replacement=False,
        )
        path = Path("data/backups/d37-latest-core-diagnoses.json")
        path.touch(mode=0o600, exist_ok=True)
        path.write_text(json.dumps(report, indent=2) + "\n")
        path.chmod(0o600)
