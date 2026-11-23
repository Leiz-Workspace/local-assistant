"""Verify target-bound schema pairs, real read provenance, unchanged first replies and owner-private failure handling."""

import hashlib
import json
import logging
from uuid import UUID, uuid4

import httpx
import pytest

from apps.api.core.model_config import get_model_profile
from apps.api.services.workspaces import WorkspaceService
from apps.api.services.workspace_tools import WorkspaceToolRun
from apps.cli import main as cli
from apps.harness.inference import ProductInference
from apps.harness.routes import RunInput
from apps.harness.service import ProductHarness, HarnessError
from src.application.services import review_output_contract as review
from src.application.services.source_output_contract import (
    SourceContractError,
    quote_catalog,
)
from src.infrastructure.harness_history import HarnessHistoryStore
from tests.test_source_output_contract import source_bytes, selection, wire
from tests import test_workspace_reader

source_workspace = test_workspace_reader.source_workspace
LOGGER = logging.getLogger(__name__)


def catalog_fixture():
    """Include identical text at distinct target lines plus a different context-only source."""
    return {
        "return result": [
            dict(path="src/target.py", source_sha256="a" * 64, line_number=12),
            dict(path="src/target.py", source_sha256="a" * 64, line_number=29),
            dict(path="src/context.py", source_sha256="b" * 64, line_number=99),
        ],
        "return other": [
            dict(path="src/context.py", source_sha256="b" * 64, line_number=13)
        ],
    }


def test_schema_pairs_each_original_line_and_does_not_choose_a_duplicate():
    """Retain both target occurrences and exclude context-only origins without asserting semantic correctness."""
    catalog = review.target_catalog(catalog_fixture(), "src/target.py")
    schema = review.response_schema(catalog)
    assert len(schema["anyOf"]) == 3
    assert [
        branch["properties"]["value"].get("const") for branch in schema["anyOf"]
    ] == [None, 12, 29]
    for number in (12, 29):
        result = wire(json.dumps(dict(value=number, quote="return result")))
        report = review.validate_review(result, catalog, "src/target.py")
        assert report["quote_origins"] == [
            dict(path="src/target.py", source_sha256="a" * 64, line_number=number)
        ]
        assert (
            report["name"] == review.NAME
            and report["semantic_correctness"] == "not_established"
        )
    assert (
        review.validate_review(
            wire('{"value":null,"quote":null}'), catalog, "src/target.py"
        )["line_binding"]
        == "not_applicable"
    )
    LOGGER.info("test_review_original_line_pairs_verified")


@pytest.mark.parametrize(
    "value,quote",
    [
        (13, "return result"),
        (99, "return result"),
        (12, "return other"),
        ("12", "return result"),
        (True, "return result"),
        (None, "return result"),
        (12, None),
    ],
)
def test_wrong_first_pair_is_rejected_without_repair(value, quote):
    """Refuse numeric, file, type and null mismatches even when the quote exists in another source."""
    catalog = review.target_catalog(catalog_fixture(), "src/target.py")
    result = wire(json.dumps(dict(value=value, quote=quote)))
    with pytest.raises(SourceContractError) as caught:
        review.validate_review(result, catalog, "src/target.py")
    assert caught.value.raw_result == result


@pytest.mark.parametrize("damage", ["absent", "hash", "line", "empty", "size"])
def test_missing_conflicting_or_oversized_target_never_selects_a_fallback(damage):
    """Fail unavailable/ambiguous target domains and schema overflow before model generation."""
    catalog = catalog_fixture()
    target = "src/target.py"
    if damage == "absent":
        target = "src/missing.py"
    elif damage == "hash":
        catalog["return result"][1]["source_sha256"] = "c" * 64
    elif damage == "line":
        catalog["different"] = [
            dict(path=target, source_sha256="a" * 64, line_number=12)
        ]
    elif damage == "empty":
        catalog = {}
    else:
        catalog = {
            ("é" * 1000) + str(index): [
                dict(path=target, source_sha256="a" * 64, line_number=index + 1)
            ]
            for index in range(20)
        }
    with pytest.raises(SourceContractError, match="source_contract_unavailable"):
        review.response_schema(review.target_catalog(catalog, target))


@pytest.mark.parametrize(
    "mode,target,tools",
    [
        (review.NAME, None, []),
        (review.NAME, "../private.py", []),
        (review.NAME, "/tmp/private.py", []),
        (
            review.NAME,
            "src/target.py",
            [{"name": "workspace.read", "arguments": {"path": "src/context.py"}}],
        ),
        ("text", "src/target.py", []),
        ("source-value-quote-v1", "src/target.py", []),
    ],
)
def test_api_target_never_grants_a_read_or_changes_other_contracts(mode, target, tools):
    """Require a clean, explicitly read target only in the new review contract."""
    with pytest.raises(ValueError):
        RunInput(
            workspace_id=uuid4(),
            task="Review",
            output_contract=mode,
            review_target=target,
            tools=tools,
        )


@pytest.mark.asyncio
async def test_real_range_keeps_absolute_line_numbers_and_omitted_target_is_unavailable(
    source_workspace,
):
    """Read actual CRLF source lines 3–4 without renumbering them or admitting a discarded target."""
    catalog, spec, _, _ = source_workspace
    service = WorkspaceService(catalog)
    reader = WorkspaceToolRun(service, spec.owner_id, spec.workspace_id)
    try:
        raw = await reader.execute(
            json.dumps(
                dict(
                    name="workspace.read",
                    arguments=dict(path="src/main.py", start_line=3, end_line=4),
                )
            ).encode()
        )
        full = quote_catalog([raw], selection(raw))
        selected = review.target_catalog(full, "src/main.py")
        numbers = {
            origin["line_number"] for origins in selected.values() for origin in origins
        }
        assert numbers == {3, 4}
        with pytest.raises(SourceContractError):
            review.target_catalog({}, "src/main.py")
    finally:
        await reader.close()
        await service.shutdown()


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", [False, True])
@pytest.mark.parametrize("mode", [review.NAME, review.QUOTE_FIRST_NAME])
async def test_native_payload_pairs_numbers_and_preserves_first_completion(bad, mode):
    """Check exact native schema/policy/budget and independently reject a wrong line from a fake backend."""
    raw = source_bytes()
    calls = []
    content = json.dumps(dict(value=5 if bad else 4, quote="return values[-1]"))

    def respond(request):
        """Serve verified native preparation and capture only one completion with no fallback or retry."""
        if request.url.path == "/v1/models":
            return httpx.Response(
                200, json={"data": [{"id": get_model_profile("core")["model_id"]}]}
            )
        if request.url.path == "/apply-template":
            assert (
                review.INSTRUCTIONS.replace(review.NAME, mode)
                in json.loads(request.content)["messages"][0]["content"]
            )
            return httpx.Response(200, json={"prompt": "prepared"})
        if request.url.path == "/tokenize":
            return httpx.Response(200, json={"tokens": [1, 2, 3]})
        assert request.url.path == "/v1/chat/completions"
        payload = json.loads(request.content)
        pairs = payload["response_format"]["json_schema"]["schema"]["anyOf"]
        assert list(pairs[1]["properties"]) == (
            ["quote", "value"]
            if mode == review.QUOTE_FIRST_NAME
            else ["value", "quote"]
        )
        assert pairs[1]["properties"] == dict(
            value=dict(type="integer", const=4),
            quote=dict(type="string", const="return values[-1]"),
        )
        assert (
            payload["max_tokens"] == 512
            and not payload["chat_template_kwargs"]["enable_thinking"]
        )
        calls.append(payload)
        return httpx.Response(200, json=wire(content))

    inference = ProductInference(transport=httpx.MockTransport(respond))
    args = dict(
        evidence=[raw],
        max_tokens=512,
        output_contract=mode,
        review_target="src/sample.py",
    )
    if bad:
        with pytest.raises(SourceContractError) as caught:
            await inference.complete(
                [dict(role="user", content="Review the target.")], **args
            )
        assert caught.value.raw_result["choices"][0]["message"]["content"] == content
    else:
        result, report = await inference.complete(
            [dict(role="user", content="Review the target.")], **args
        )
        assert result["choices"][0]["message"]["content"] == content
        assert report["output_contract"]["line_binding"] == "matched"
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_failed_review_retains_owner_diagnostic_and_only_hash_in_history(
    source_workspace, tmp_path, caplog
):
    """Exercise service forwarding and prevent a wrong native line from becoming a successful or cross-owner result."""
    caplog.set_level(logging.INFO)
    catalog, spec, _, _ = source_workspace
    workspace = WorkspaceService(catalog)
    history = HarnessHistoryStore(tmp_path / "history")
    raw = wire("PRIVATE_REVIEW_LINE_CANARY")

    class InvalidInference:
        """Produce a controlled first contract rejection without loading a model."""

        async def complete(self, messages, **options):
            """Verify exact host target forwarding before retaining bounded native evidence."""
            assert (
                options["review_target"] == "src/main.py"
                and options["output_contract"] == review.NAME
            )
            raise SourceContractError("source_contract_invalid", raw)

    service = ProductHarness(InvalidInference(), workspace, history=history)
    try:
        request = RunInput(
            workspace_id=spec.workspace_id,
            task="Review",
            output_contract=review.NAME,
            review_target="src/main.py",
            tools=[dict(name="workspace.read", arguments=dict(path="src/main.py"))],
        )
        identifier = UUID(service.start(spec.owner_id, request)["id"])
        await service.tasks[identifier]
        row = service.get(spec.owner_id, identifier)
        assert (
            row["state"] == "failed"
            and not row["result_available"]
            and row["diagnostic"]["raw_result"] == raw
        )
        assert (
            row["result_sha256"]
            == hashlib.sha256(
                json.dumps(
                    raw, sort_keys=True, separators=(",", ":"), allow_nan=False
                ).encode()
            ).hexdigest()
        )
        with pytest.raises(HarnessError):
            service.get(uuid4(), identifier)
        assert (
            b"CANARY"
            not in (tmp_path / "history" / (str(identifier) + ".json")).read_bytes()
        )
        assert "CANARY" not in caplog.text
    finally:
        await service.close()
        history.close()
        await workspace.shutdown()


def test_cli_forwards_target_only_when_explicit_and_rejects_invalid_pairing(
    tmp_path, monkeypatch, capsys
):
    """Preserve old default request shape while forwarding a valid explicit review target without local reads."""
    calls = []

    class Client:
        """Capture a finite CLI task request without using credentials or network."""

        def __init__(self, *args):
            """Accept local client setup without opening a socket."""

        def request(self, method, path, payload):
            """Return a created run after capturing caller-selected input fields."""
            calls.append(payload)
            return dict(id=str(uuid4()), state="created")

    task, tools = tmp_path / "task.md", tmp_path / "tools.json"
    task.write_text("Review the supplied target.")
    tools.write_text('[{"name":"workspace.read","arguments":{"path":"src/main.py"}}]')
    monkeypatch.setattr(cli, "ApiClient", Client)
    monkeypatch.setattr(cli, "read_token", lambda path: "t" * 48)
    base = [
        "--json",
        "run",
        "--workspace",
        str(uuid4()),
        "--task-file",
        str(task),
        "--tools-file",
        str(tools),
    ]
    assert (
        cli.main(
            base + ["--output-contract", review.NAME, "--review-target", "src/main.py"]
        )
        == 0
    )
    assert (
        calls[-1]["review_target"] == "src/main.py"
        and calls[-1]["output_contract"] == review.NAME
    )
    assert (
        cli.main(base) == 0
        and "review_target" not in calls[-1]
        and "output_contract" not in calls[-1]
    )
    previous = len(calls)
    assert cli.main(base + ["--review-target", "src/main.py"]) == 2
    assert cli.main(base + ["--output-contract", review.NAME]) == 2
    assert len(calls) == previous


def test_quote_first_schema_changes_order_only_and_keeps_both_targets_authorized():
    """Keep the same JSON pair domain while requiring a target for both independent opt-in variants."""
    catalog = review.target_catalog(catalog_fixture(), "src/target.py")
    first = review.response_schema(catalog)
    second = review.response_schema(catalog, quote_first=True)
    for left, right in zip(first["anyOf"], second["anyOf"], strict=True):
        assert left["properties"] == right["properties"]
        assert set(left["required"]) == set(right["required"])
        assert list(left["properties"]) == ["value", "quote"]
        assert list(right["properties"]) == ["quote", "value"]
    request = RunInput(
        workspace_id=uuid4(),
        task="Review",
        output_contract=review.QUOTE_FIRST_NAME,
        review_target="src/target.py",
        tools=[dict(name="workspace.read", arguments=dict(path="src/target.py"))],
    )
    assert request.output_contract == review.QUOTE_FIRST_NAME
    with pytest.raises(ValueError):
        RunInput(
            workspace_id=uuid4(), task="Review", output_contract=review.QUOTE_FIRST_NAME
        )
