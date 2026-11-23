"""Verify source-bound schemas, unmodified first-output validation and owner-only failure diagnostics."""

import hashlib
import json
import logging
from uuid import UUID, uuid4

import httpx
import pytest

from apps.api.core.model_config import get_model_profile
from apps.api.services.workspaces import WorkspaceService
from apps.api.services.workspace_tools import WorkspaceToolRun
from apps.harness.inference import ProductInference
from apps.harness.routes import RunInput
from apps.harness.service import ProductHarness, HarnessError
from src.application.services.source_output_contract import (
    NAME,
    INSTRUCTIONS,
    SourceContractError,
    quote_catalog,
    response_schema,
    validate_completion,
)
from src.infrastructure.harness_history import HarnessHistoryStore
from tests import test_workspace_reader

source_workspace = test_workspace_reader.source_workspace
LOGGER = logging.getLogger(__name__)


def source_bytes(text="    return values[-1]"):
    """Build an exact synthetic native workspace.read envelope without executing its source."""
    return json.dumps(
        {
            "run_id": str(uuid4()),
            "call_id": str(uuid4()),
            "name": "workspace.read",
            "data": {
                "workspace_id": str(uuid4()),
                "content_trust": "untrusted",
                "omitted": dict(hidden=0, unsafe=0, non_text=0, non_python=0),
                "lines": [
                    {
                        "path": "src/sample.py",
                        "source_sha256": "a" * 64,
                        "line_number": 4,
                        "line_text": text,
                        "content_trust": "untrusted",
                    }
                ],
            },
        }
    ).encode()


def selection(raw):
    """Reference one context-retained immutable evidence envelope by its real hash."""
    return [{"index": 0, "sha256": hashlib.sha256(raw).hexdigest()}]


def wire(content, finish="stop"):
    """Create one bounded native assistant completion for validation tests."""
    return {
        "choices": [
            {
                "finish_reason": finish,
                "message": {"role": "assistant", "content": content},
            }
        ]
    }


def test_catalog_canonicalizes_sources_before_inference_and_keeps_provenance():
    """Create a finite quote domain without rewriting any generated content or importing instructions."""
    raw = source_bytes()
    catalog = quote_catalog([raw], selection(raw))
    assert list(catalog) == ["return values[-1]"]
    assert catalog["return values[-1]"][0]["line_number"] == 4
    schema = response_schema(catalog)
    assert schema["anyOf"][0]["properties"]["quote"] == {"type": "null"}
    assert schema["anyOf"][1]["properties"]["quote"]["enum"] == ["return values[-1]"]
    LOGGER.info("test_source_catalog_pre_inference_canonicalization_verified")


@pytest.mark.parametrize(
    "damage",
    [
        "omitted",
        "hash",
        "wrong_tool",
        "oversized_line",
        "trusted",
        "wrong_fields",
        "reduced_envelope",
        "bad_metadata",
        "omission_count",
    ],
)
def test_catalog_refuses_unadmitted_or_unbounded_sources(damage):
    """Reject source drift, discarded evidence and shape/size/trust violations before generation."""
    raw = source_bytes()
    selected = selection(raw)
    if damage == "omitted":
        selected = []
    elif damage == "hash":
        selected[0]["sha256"] = "f" * 64
    else:
        payload = json.loads(raw)
        if damage == "wrong_tool":
            payload["name"] = "workspace.search"
        elif damage == "oversized_line":
            payload["data"]["lines"][0]["line_text"] = "x" * 1025
        elif damage == "trusted":
            payload["data"]["lines"][0]["content_trust"] = "trusted"
        elif damage == "reduced_envelope":
            del payload["run_id"]
        elif damage == "bad_metadata":
            payload["data"]["workspace_id"] = "not-a-uuid"
        elif damage == "omission_count":
            payload["data"]["omitted"]["unsafe"] = 1
        else:
            payload["data"]["lines"][0]["approval"] = True
        raw = json.dumps(payload).encode()
        selected = selection(raw)
    with pytest.raises(SourceContractError, match="source_contract_unavailable"):
        quote_catalog([raw], selected)


@pytest.mark.asyncio
async def test_real_workspace_tool_envelope_admits_exact_snapshot_lines(
    source_workspace,
):
    """Validate the complete native tool envelope including metadata, preventing fixture-only contract drift."""
    catalog, spec, _, source = source_workspace
    workspace = WorkspaceService(catalog)
    reader = WorkspaceToolRun(workspace, spec.owner_id, spec.workspace_id)
    try:
        raw = await reader.execute(
            json.dumps(
                {"name": "workspace.read", "arguments": {"path": "src/main.py"}}
            ).encode()
        )
        quotes = quote_catalog([raw], selection(raw))
        assert 'return "Xin chào 𝄞"' in quotes
        assert quotes['return "Xin chào 𝄞"'] == [
            {
                "path": "src/main.py",
                "source_sha256": hashlib.sha256(source).hexdigest(),
                "line_number": 4,
            }
        ]
    finally:
        await reader.close()
        await workspace.shutdown()


@pytest.mark.parametrize(
    "content",
    [
        '```json\n{"value":4,"quote":"return values[-1]"}\n```',
        '{"value":null,"quote":"return values[-1]"}',
        '{"value":4,"quote":"    return values[-1]"}',
        '{"value":4,"quote":"invented"}',
        '{"value":true,"quote":"return values[-1]"}',
        '{"value":4,"value":3,"quote":"return values[-1]"}',
        '{"value":4,"quote":"return values[-1]","line":4}',
    ],
)
def test_first_invalid_outputs_are_not_repaired(content):
    """Retain raw invalid answers while refusing normalization, coercion and unknown schema fields."""
    raw = source_bytes()
    result = wire(content)
    with pytest.raises(SourceContractError) as caught:
        validate_completion(result, quote_catalog([raw], selection(raw)))
    assert caught.value.raw_result == result


def test_null_pair_valid_quote_and_semantic_limit_are_explicit():
    """Validate finite syntax/provenance without declaring an arbitrary selected value semantically correct."""
    raw = source_bytes()
    catalog = quote_catalog([raw], selection(raw))
    assert (
        validate_completion(wire('{"value":null,"quote":null}'), catalog)[
            "quote_origins"
        ]
        == []
    )
    result = validate_completion(
        wire('{"value":999,"quote":"return values[-1]"}'), catalog
    )
    assert (
        result["status"] == "VALID"
        and result["semantic_correctness"] == "not_established"
    )
    with pytest.raises(SourceContractError):
        validate_completion(
            wire('{"value":4,"quote":"return values[-1]"}', finish="length"), catalog
        )


@pytest.mark.asyncio
async def test_structured_native_payload_uses_schema_and_exact_budget():
    """Use real gateway preparation with a synthetic transport and check the native first output unchanged."""
    model = get_model_profile("core")["model_id"]
    raw = source_bytes()
    requests = []
    content = '{"value":4,"quote":"return values[-1]"}'

    def respond(request):
        """Serve model/template/tokenizer contracts and inspect the one actual completion request."""
        if request.url.path == "/v1/models":
            return httpx.Response(200, json={"data": [{"id": model}]})
        if request.url.path == "/apply-template":
            messages = json.loads(request.content)["messages"]
            assert INSTRUCTIONS in messages[0]["content"]
            return httpx.Response(200, json={"prompt": "contract prompt"})
        if request.url.path == "/tokenize":
            return httpx.Response(200, json={"tokens": [1, 2, 3]})
        if request.url.path == "/v1/chat/completions":
            payload = json.loads(request.content)
            requests.append(payload)
            assert set(payload["response_format"]) == {"type", "json_schema"}
            assert payload["response_format"]["type"] == "json_schema"
            schema = payload["response_format"]["json_schema"]["schema"]
            assert schema == response_schema(quote_catalog([raw], selection(raw)))
            assert schema["anyOf"][1]["properties"]["quote"]["enum"] == [
                "return values[-1]"
            ]
            assert payload["max_tokens"] == 512 and payload["stream"] is False
            assert payload["chat_template_kwargs"]["enable_thinking"] is False
            return httpx.Response(200, json=wire(content))
        raise AssertionError(request.url.path)

    inference = ProductInference(transport=httpx.MockTransport(respond))
    result, report = await inference.complete(
        [{"role": "user", "content": "Review source."}],
        evidence=[raw],
        max_tokens=512,
        output_contract=NAME,
    )
    assert result["choices"][0]["message"]["content"] == content
    assert report["output_contract"]["status"] == "VALID" and len(requests) == 1


def test_api_contract_requires_existing_read_tools_only():
    """Keep caller schemas, unknown contracts and non-read evidence outside the product surface."""
    from uuid import uuid4

    for values in (
        {"output_contract": NAME},
        {
            "output_contract": NAME,
            "tools": [{"name": "workspace.search", "arguments": {"query": "x"}}],
        },
        {"output_contract": "arbitrary-json"},
        {"response_schema": {}},
    ):
        with pytest.raises(ValueError):
            RunInput(workspace_id=uuid4(), task="Task", **values)


@pytest.mark.asyncio
async def test_failed_contract_retains_owner_diagnostic_but_history_stores_only_digest(
    source_workspace, tmp_path, caplog
):
    """Publish no successful result on contract failure and keep diagnostic text out of signed history."""
    catalog, spec, _, _ = source_workspace
    workspace = WorkspaceService(catalog)
    history = HarnessHistoryStore(tmp_path / "history")
    result = wire("PRIVATE_INVALID_COMPLETION_CANARY")

    class InvalidInference:
        """Raise one controlled native contract failure without making a model call."""

        async def complete(self, messages, **options):
            """Retain the first invalid native completion as diagnostic evidence only."""
            raise SourceContractError("source_contract_invalid", result)

    service = ProductHarness(InvalidInference(), workspace, history=history)
    request = RunInput(
        workspace_id=spec.workspace_id,
        task="Review",
        output_contract=NAME,
        tools=[{"name": "workspace.read", "arguments": {"path": "src/main.py"}}],
    )
    identifier = UUID(service.start(spec.owner_id, request)["id"])
    await service.tasks[identifier]
    row = service.get(spec.owner_id, identifier)
    assert row["state"] == "failed" and not row["result_available"]
    assert row["diagnostic"]["raw_result"] == result and row["result_sha256"]
    with pytest.raises(HarnessError, match="run_not_found"):
        service.get(uuid4(), identifier)
    saved = (tmp_path / "history" / (str(identifier) + ".json")).read_bytes()
    assert b"CANARY" not in saved
    assert "CANARY" not in caplog.text
    await service.close()
    history.close()
    await workspace.shutdown()
