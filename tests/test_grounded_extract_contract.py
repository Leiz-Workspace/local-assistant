"""Verify the strict extraction request contract, the frozen D81 prompt protocol and response shapes without model calls."""

import hashlib
import json
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from grounded_extract_cases import (
    LABEL_TEXT,
    PORT_TEXT,
    QUERY,
    Native,
    OwnerRetrieval,
    Unused,
    body_for,
    extract_app,
    fields_for,
    plain_hit,
    record_adapters,
)
from pydantic import ValidationError

from apps.api.routes import grounded_extract as route
from apps.api.routes.grounded_extract import ExtractInput
from apps.api.services.grounded import GroundedService
from scripts import structured_excerpt_evaluation as evaluation
from src.application.ports.inference import CompletionResult
from src.application.services import grounded_extract
from src.application.services.mcp_adapter import canonical
from src.application.services.profile_prompts import (
    TEMPLATES,
    ProfilePromptRun,
    PromptInput,
    template_digest,
)
from src.infrastructure.inference.structured_excerpt_adapter import (
    StructuredExcerptAdapter,
)

INSTRUCTION_SHA256 = "6ea29bd2c819d823b78604285a60f2046380cebb5479d6374586a4c48e1cc3f5"


def valid():
    """Return one valid two-field request body."""
    return dict(
        query="cổng",
        fields=[
            dict(name="port", type="integer", file_id=str(uuid4())),
            dict(name="label", type="string", file_id=str(uuid4())),
        ],
    )


def oversized(hit):
    """Return a contract-valid JSON body whose escaped 4096-byte query exceeds the 16 KiB body cap."""
    body = body_for(("port", "integer", hit), query="\x01" * 4096)
    raw = json.dumps(body)
    assert len(raw.encode()) > route.BODY_LIMIT == 16384
    ExtractInput.model_validate(json.loads(raw))
    return raw


def chunks(data, size=4096):
    """Yield a body in fixed-size pieces so the client sends it with chunked transfer encoding."""
    for start in range(0, len(data), size):
        yield data[start : start + size]


def test_instruction_is_moved_byte_identical_from_the_evaluated_script():
    """Keep the exact evaluated instruction text in production and import it back into the script."""
    assert grounded_extract.INSTRUCTION is evaluation.INSTRUCTION
    assert len(grounded_extract.INSTRUCTION) == 786
    assert (
        hashlib.sha256(grounded_extract.INSTRUCTION.encode()).hexdigest()
        == INSTRUCTION_SHA256
    )
    assert grounded_extract.INSTRUCTION.endswith("Requested facts by source: ")


def test_protocol_constants_are_frozen():
    """Pin the unit mode, facts key, grammar flags, model and protocol name."""
    assert grounded_extract.PROTOCOL == "d81-grounded-extract-v1"
    assert grounded_extract.MODEL_ID == "qwen3.5-9b-core"
    assert grounded_extract.UNIT_MODE == "sentences"
    assert grounded_extract.FACTS_KEY == "facts"
    assert grounded_extract.SCHEMA_ENABLED is True
    assert grounded_extract.LITERAL_STRINGS is True
    assert grounded_extract.MAX_FIELDS == 3


@pytest.mark.parametrize("version", ["v1", "v2", "v3"])
def test_request_serialization_matches_evaluated_payload_for_every_corpus_case(
    version,
):
    """Serialize the field map with the exact separators and key order the evaluation used."""
    data = json.loads(
        evaluation.CORPUS.with_name(f"d81-typed-paired-{version}.json").read_text()
    )
    cases = data["cases"] + data["negative_cases"]
    assert cases
    for case in cases:
        rows = tuple(
            (row["source_id"], row["fact_key"], row["kind"]) for row in case["sources"]
        )
        assert (
            grounded_extract.extraction_request(rows)
            == evaluation.payload(case)["request"]
        )


def test_binding_assigns_server_source_ids_and_never_includes_the_query():
    """Assign s1..sN in declared order and compose system CORE plus canonical PromptInput only."""
    port, label = plain_hit(PORT_TEXT), plain_hit(LABEL_TEXT)
    fields = fields_for(("label", "string", label), ("port", "integer", port))
    binding = grounded_extract.bind_sources(fields, [port, label])
    assert binding.request == grounded_extract.INSTRUCTION + json.dumps(
        {
            "s1": {"key": "label", "type": "string"},
            "s2": {"key": "port", "type": "integer"},
        },
        ensure_ascii=False,
    )
    assert binding.adapter_fields == (
        ("label", "string", "s1"),
        ("port", "integer", "s2"),
    )
    assert binding.source_modes == dict(s1="sentences", s2="sentences")
    assert binding.messages[0] == dict(role="system", content=TEMPLATES["core"])
    user = PromptInput.model_validate_json(binding.messages[1]["content"])
    assert user.request == binding.request
    assert [(row.source_id, row.text) for row in user.sources] == [
        ("s1", LABEL_TEXT),
        ("s2", PORT_TEXT),
    ]
    assert binding.messages[1]["content"] == canonical(
        user.model_dump(mode="json")
    ).decode("utf-8")
    assert QUERY not in json.dumps(binding.messages, ensure_ascii=False)
    assert [unit["hit"]["file_id"] for unit in binding.units] == [
        label["file_id"],
        port["file_id"],
    ]


@pytest.mark.asyncio
async def test_prompt_digest_equals_profile_prompt_run_composition():
    """Reproduce the exact ProfilePromptRun messages and prompt digest the evaluation used."""
    port, label = plain_hit(PORT_TEXT), plain_hit(LABEL_TEXT)
    binding = grounded_extract.bind_sources(
        fields_for(("port", "integer", port), ("label", "string", label)),
        [port, label],
    )
    seen = []

    class Capture:
        """Record the composed messages and return a fixed complete result."""

        async def complete(self, **kwargs):
            """Capture one call without any model."""
            seen.append(kwargs["messages"])
            return CompletionResult("{}", "qwen3.5-9b-core", "fast", "stop", 1, 1)

    owner, workspace = uuid4(), uuid4()
    run = ProfilePromptRun(
        owner,
        workspace,
        profile="core",
        model_id="qwen3.5-9b-core",
        template_sha256=template_digest("core"),
        inference=Capture(),
    )
    raw = canonical(
        dict(
            request=binding.request,
            sources=[
                dict(source_id=unit["source_id"], text=unit["text"])
                for unit in binding.units
            ],
        )
    )
    try:
        reply = await run.complete(owner, workspace, raw)
    finally:
        await run.close()
    assert seen == [binding.messages]
    assert reply.prompt_sha256 == binding.prompt_sha256
    assert (
        binding.prompt_sha256
        == hashlib.sha256(canonical(dict(messages=binding.messages))).hexdigest()
    )


@pytest.mark.asyncio
async def test_prompt_digest_equals_real_adapter_provenance_and_service_extraction(
    monkeypatch,
):
    """Bind ProfilePromptRun, the unchanged adapter and the service extraction digest to one prompt."""
    port, label = plain_hit(PORT_TEXT), plain_hit(LABEL_TEXT)
    fields = fields_for(("port", "integer", port), ("label", "string", label))
    binding = grounded_extract.bind_sources(fields, [port, label])
    native = Native()
    adapter = StructuredExcerptAdapter(
        request=binding.request,
        fields=binding.adapter_fields,
        source_modes=dict(binding.source_modes),
        model_id="qwen3.5-9b-core",
        facts_key="facts",
        schema_enabled=True,
        literal_strings=True,
        transport=httpx.MockTransport(native),
    )
    owner, workspace = uuid4(), uuid4()
    run = ProfilePromptRun(
        owner,
        workspace,
        profile="core",
        model_id="qwen3.5-9b-core",
        template_sha256=template_digest("core"),
        inference=adapter,
    )
    raw = canonical(
        dict(
            request=binding.request,
            sources=[
                dict(source_id=unit["source_id"], text=unit["text"])
                for unit in binding.units
            ],
        )
    )
    try:
        reply = await run.complete(owner, workspace, raw)
    finally:
        await run.close()
    assert adapter.provenance.prompt_sha256 == reply.prompt_sha256
    assert reply.prompt_sha256 == binding.prompt_sha256

    built = record_adapters(monkeypatch)
    owner = uuid4()
    dense = OwnerRetrieval([(owner, port), (owner, label)])
    service = GroundedService(dense, inference=Unused())
    async with service.extraction(
        owner, QUERY, fields, transport=httpx.MockTransport(Native())
    ) as (payload, _):
        assert payload["extraction"] == dict(
            protocol="d81-grounded-extract-v1",
            schema_sha256=built[0].provenance.schema_sha256,
            prompt_sha256=binding.prompt_sha256,
        )
        assert built[0].provenance.schema_sha256 == adapter.provenance.schema_sha256


@pytest.mark.asyncio
async def test_service_builds_adapter_with_fixed_unit_mode_and_flags(monkeypatch):
    """Construct the unchanged adapter with sentences units, facts key, schema and literal strings only."""
    built = record_adapters(monkeypatch)
    port, label = plain_hit(PORT_TEXT), plain_hit(LABEL_TEXT)
    owner = uuid4()
    dense = OwnerRetrieval([(owner, port), (owner, label)])
    service = GroundedService(dense, inference=Unused())
    native = Native()
    fields = fields_for(("port", "integer", port), ("label", "string", label))
    async with service.extraction(
        owner, QUERY, fields, transport=httpx.MockTransport(native)
    ) as (payload, _):
        assert payload["status"] == "extracted"
    (adapter,) = built
    assert dict(adapter.source_modes) == dict(s1="sentences", s2="sentences")
    assert adapter.facts_key == "facts" and adapter.model_id == "qwen3.5-9b-core"
    assert adapter.schema_enabled is True and adapter.literal_strings is True
    assert adapter.fields == (("port", "integer", "s1"), ("label", "string", "s2"))
    assert adapter.calls == 1 and adapter.transport is not None
    sent = native.generations[0]
    assert sent["max_tokens"] <= 512 and sent["temperature"] == 0
    assert sent["chat_template_kwargs"] == dict(enable_thinking=False)
    assert sent["response_format"]["type"] == "json_object"
    user = PromptInput.model_validate_json(sent["messages"][1]["content"])
    assert user.request == adapter.request
    assert sent["messages"][0] == dict(role="system", content=TEMPLATES["core"])


@pytest.mark.parametrize(
    "change",
    [
        *(
            dict(top={key: value})
            for key, value in dict(
                profile="core",
                model="qwen3.5-9b-core",
                preset="fast",
                schema={},
                enum=["x"],
                expected={"port": 1},
                text="source",
                sources=[],
                owner_id=str(uuid4()),
                citations=[],
                top_k=1,
                file_ids=[str(uuid4())],
            ).items()
        ),
        *(
            dict(field={key: value})
            for key, value in dict(
                source_id="s1",
                text="source",
                quote="q",
                value=1,
                expected=1,
                enum=["x"],
                mode="lines",
            ).items()
        ),
        dict(field=dict(type="number")),
        dict(field=dict(type="Integer")),
        dict(field=dict(name="citations")),
        dict(field=dict(name="1a")),
        dict(field=dict(name="a\n")),
        dict(field=dict(name="a-b")),
        dict(field=dict(name="x" * 65)),
        dict(field=dict(name="")),
        dict(field=dict(file_id="not-a-uuid")),
        dict(field=dict(file_id=7)),
        dict(field=dict(name=7)),
        dict(duplicate="name"),
        dict(duplicate="file_id"),
        dict(count=0),
        dict(count=4),
        dict(query=""),
        dict(query="   "),
        dict(query="é" * 2049),
        dict(query="x" * 4097),
        dict(query=7),
    ],
)
def test_strict_request_model_rejects_overrides_and_invalid_fields(change):
    """Reject caller model/schema/source/citation overrides and invalid names, types and counts."""
    data = valid()
    if "top" in change:
        data.update(change["top"])
    if "field" in change:
        data["fields"][0].update(change["field"])
    if change.get("duplicate"):
        key = change["duplicate"]
        data["fields"][1][key] = data["fields"][0][key]
    if "count" in change:
        data["fields"] = [
            dict(name=f"f{i}", type="string", file_id=str(uuid4()))
            for i in range(change["count"])
        ]
    if "query" in change:
        data["query"] = change["query"]
    with pytest.raises(ValidationError):
        ExtractInput.model_validate(data)


def test_strict_request_model_accepts_the_bounded_contract():
    """Accept 1-3 distinct identifier fields and a 4096-byte query."""
    data = valid()
    data["query"] = "é" * 2048
    data["fields"].append(dict(name="_quota_9", type="integer", file_id=str(uuid4())))
    body = ExtractInput.model_validate(data)
    assert [row.name for row in body.fields] == ["port", "label", "_quota_9"]
    assert all(isinstance(row.file_id, UUID) for row in body.fields)


@pytest.mark.parametrize(
    "raw,content_type",
    [
        (None, "text/plain"),
        (None, None),
        ('{"query":"a","query":"b","fields":[]}', "application/json"),
        ("DUPLICATE_FIELD", "application/json"),
        ("NAN", "application/json"),
        ("[]", "application/json"),
        ("{", "application/json"),
        ("OVERSIZED", "application/json"),
        ("OVERSIZED_CHUNKED", "application/json"),
        ("EXTRA", "application/json"),
    ],
)
def test_http_contract_failures_are_finite_and_never_echo_input(
    auth_settings, monkeypatch, raw, content_type
):
    """Map every malformed body to 422 extract_contract_invalid without echoing or reaching sources."""
    built = record_adapters(monkeypatch)
    native = Native()
    principal = auth_settings["principals"][0]
    port = plain_hit(PORT_TEXT)
    app, dense, service = extract_app([(principal, port)], native)
    good = json.dumps(body_for(("port", "integer", port)))
    chunked = raw == "OVERSIZED_CHUNKED"
    if raw is None:
        raw = good
    elif raw == "DUPLICATE_FIELD":
        raw = good[:-1] + ',"query":"' + QUERY + '"}'
    elif raw == "NAN":
        raw = good[:-1] + ',"extra":NaN}'
    elif raw.startswith("OVERSIZED"):
        raw = oversized(port)
    elif raw == "EXTRA":
        raw = good[:-1] + ',"model":"' + QUERY + '"}'
    headers = dict(auth_settings["headers"][0])
    if content_type is not None:
        headers["Content-Type"] = content_type
    data = raw.encode()
    content = chunks(data) if chunked else data
    with TestClient(app, client=("127.0.0.1", 43000)) as client:
        response = client.post(
            "/api/v1/grounded/extract", content=content, headers=headers
        )
    assert response.status_code == 422
    assert response.json() == {"detail": {"code": "extract_contract_invalid"}}
    assert "PRIVATE-QUERY-MARKER" not in response.text
    assert native.calls == 0 and not built and dense.options is None
    assert not service.admission.locked() and not service.operations


def spy_contract(monkeypatch):
    """Count route contract validations while delegating to the real request model."""
    calls = []

    class Contract:
        """Stand in for ExtractInput inside the route module only."""

        @staticmethod
        def model_validate(value):
            """Record and delegate one contract validation."""
            calls.append("ExtractInput")
            return ExtractInput.model_validate(value)

    monkeypatch.setattr(route, "ExtractInput", Contract)
    return calls


def spy_parser(monkeypatch):
    """Count route JSON parses while delegating to the real bounded parser."""
    calls, original = [], route.parse_workspace_json

    def parse(raw):
        """Record and delegate one JSON parse."""
        calls.append("parse_workspace_json")
        return original(raw)

    monkeypatch.setattr(route, "parse_workspace_json", parse)
    return calls


def post_extract(app, auth_settings, content):
    """Send one raw JSON body to the extract route over loopback with the first bearer."""
    headers = dict(auth_settings["headers"][0], **{"Content-Type": "application/json"})
    with TestClient(app, client=("127.0.0.1", 43000)) as client:
        return client.post("/api/v1/grounded/extract", content=content, headers=headers)


@pytest.mark.parametrize("chunked", [False, True])
def test_streaming_body_cap_refuses_a_contract_valid_oversized_body(
    auth_settings, monkeypatch, chunked
):
    """Refuse a >16 KiB contract-valid body in the streaming read, before the JSON parser runs."""
    built = record_adapters(monkeypatch)
    native = Native()
    port = plain_hit(PORT_TEXT)
    app, dense, service = extract_app([(auth_settings["principals"][0], port)], native)
    parsed = spy_parser(monkeypatch)
    data = oversized(port).encode()
    response = post_extract(app, auth_settings, chunks(data) if chunked else data)
    assert response.status_code == 422
    assert response.json() == {"detail": {"code": "extract_contract_invalid"}}
    assert parsed == [] and native.calls == 0 and not built and dense.options is None
    assert not service.admission.locked() and not service.operations


def test_parser_byte_cap_refuses_an_oversized_body_without_the_streaming_cap(
    auth_settings, monkeypatch
):
    """Keep the parser's own 16 KiB cap effective if the streaming cap were ever raised."""
    built = record_adapters(monkeypatch)
    native = Native()
    port = plain_hit(PORT_TEXT)
    app, dense, service = extract_app([(auth_settings["principals"][0], port)], native)
    data = oversized(port).encode()
    monkeypatch.setattr(route, "BODY_LIMIT", 1 << 20)
    validated = spy_contract(monkeypatch)
    response = post_extract(app, auth_settings, data)
    assert response.status_code == 422
    assert response.json() == {"detail": {"code": "extract_contract_invalid"}}
    assert validated == [] and native.calls == 0 and not built and dense.options is None
    assert not service.admission.locked() and not service.operations


@pytest.mark.parametrize(
    "raw",
    [
        '{"query":NaN,"fields":[]}',
        '{"query":"a","fields":[{"name":"port","type":"integer","file_id":Infinity}]}',
        '{"query":"a","query":"b","fields":[]}',
    ],
)
def test_parser_rejections_never_reach_the_contract_model(
    auth_settings, monkeypatch, raw
):
    """Reject nonfinite numbers and duplicate keys in the parser, before contract validation."""
    native = Native()
    port = plain_hit(PORT_TEXT)
    app, dense, _ = extract_app([(auth_settings["principals"][0], port)], native)
    validated = spy_contract(monkeypatch)
    response = post_extract(app, auth_settings, raw.encode())
    assert response.status_code == 422
    assert response.json() == {"detail": {"code": "extract_contract_invalid"}}
    assert validated == [] and native.calls == 0 and dense.options is None


def test_contract_spy_sees_a_valid_body(auth_settings, monkeypatch):
    """Show the contract spy observes ordinary bodies, so the empty-call assertions are meaningful."""
    native = Native()
    port = plain_hit(PORT_TEXT)
    app, _, _ = extract_app([(auth_settings["principals"][0], port)], native)
    validated = spy_contract(monkeypatch)
    parsed = spy_parser(monkeypatch)
    body = json.dumps(body_for(("port", "integer", port))).encode()
    response = post_extract(app, auth_settings, body)
    assert response.status_code == 200
    assert validated == ["ExtractInput"] and parsed == ["parse_workspace_json"]


@pytest.mark.asyncio
async def test_extraction_provenance_present_only_for_extracted(monkeypatch):
    """Return extraction metadata for extracted only; refusal and no_sources carry null facts and metadata."""
    record_adapters(monkeypatch)
    owner = uuid4()
    port = plain_hit(PORT_TEXT)
    fields = fields_for(("port", "integer", port))
    keys = {
        "status",
        "facts",
        "citations",
        "answer_trust",
        "content_trust",
        "extraction",
    }
    results = {}
    for name, rows, native in [
        ("extracted", [(owner, port)], Native()),
        ("insufficient_evidence", [(owner, port)], Native(refusal=True)),
        ("no_sources", [], Native()),
    ]:
        service = GroundedService(OwnerRetrieval(rows), inference=Unused())
        async with service.extraction(
            owner, QUERY, fields, transport=httpx.MockTransport(native)
        ) as (payload, _):
            assert set(payload) == keys and payload["status"] == name
            results[name] = payload
    assert results["extracted"]["extraction"]["protocol"] == "d81-grounded-extract-v1"
    assert results["extracted"]["facts"] == dict(port=7443)
    for name in ("insufficient_evidence", "no_sources"):
        assert results[name]["extraction"] is None
        assert results[name]["facts"] is None and results[name]["citations"] == []
    # ADR177 Response (200): every status carries the same trust labels.
    assert all(row["answer_trust"] == "model_generated" for row in results.values())
    assert all(row["content_trust"] == "untrusted" for row in results.values())
