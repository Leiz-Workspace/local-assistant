"""Verify grounded extraction binding, refusals, fences, shared locks and joined lifecycle with fixture transports only."""

import asyncio
import json
import logging
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from grounded_extract_cases import (
    LABEL_QUOTE,
    LABEL_TEXT,
    LABEL_VALUE,
    PORT_QUOTE,
    PORT_TEXT,
    QUERY,
    QUOTA_TEXT,
    Native,
    OwnerRetrieval,
    Unused,
    fields_for,
    plain_hit,
    record_adapters,
    table_hit,
)
from test_grounded_service import Retrieval

from apps.api.routes.retrieval import RetrievalResponse
from apps.api.services.grounded import GroundedService
from apps.api.services.retrieval import RetrievalService
from src.application.services.file_storage_policy import StoragePolicyError


def service_for(rows, **options):
    """Build a real grounded service over owner-filtered fake retrieval."""
    dense = OwnerRetrieval(rows, change_at=options.pop("change_at", None))
    return dense, GroundedService(dense, inference=Unused(), **options)


async def refused(service, owner, fields, native, query=QUERY):
    """Run one extraction expected to fail and return the finite policy error."""
    with pytest.raises(StoragePolicyError) as caught:
        async with service.extraction(
            owner, query, fields, transport=httpx.MockTransport(native)
        ):
            pytest.fail("must not yield")
    return caught.value


def released(dense, service):
    """Report whether sources and grounded admission were fully released."""
    return not dense.held and not service.admission.locked() and not service.operations


@pytest.mark.asyncio
async def test_one_hit_per_declared_file_in_field_order(monkeypatch):
    """Bind each declared field to its own file's hit in request order, not retrieval rank order."""
    built = record_adapters(monkeypatch)
    owner = uuid4()
    port, label = plain_hit(PORT_TEXT), plain_hit(LABEL_TEXT)
    dense, service = service_for([(owner, port), (owner, label)])
    native = Native()
    fields = fields_for(("label", "string", label), ("port", "integer", port))
    async with service.extraction(
        owner, QUERY, fields, transport=httpx.MockTransport(native)
    ) as (payload, retained):
        assert dense.held and service.admission.locked()
        assert dense.options == dict(top_k=2, file_ids=[field[2] for field in fields])
        assert payload["facts"] == dict(label=LABEL_VALUE, port=7443)
        assert [row["field"] for row in payload["citations"]] == ["label", "port"]
        assert [row["file_id"] for row in payload["citations"]] == [
            label["file_id"],
            port["file_id"],
        ]
        assert [row["quote"] for row in payload["citations"]] == [
            LABEL_QUOTE,
            PORT_QUOTE,
        ]
        assert retained == ["retained"] and dense.validations == 2
    assert native.paths == [
        "/v1/models",
        "/apply-template",
        "/tokenize",
        "/v1/chat/completions",
    ]
    assert len(built) == 1 and built[0].calls == 1 and released(dense, service)


@pytest.mark.parametrize("case", ["same_file", "missing", "extra"])
@pytest.mark.asyncio
async def test_mismatched_sources_are_refused_before_any_adapter(
    monkeypatch, caplog, case
):
    """Refuse two hits from one file, a declared file without a hit, or an undeclared file."""
    caplog.set_level(logging.INFO)
    built = record_adapters(monkeypatch)
    port, label = plain_hit(PORT_TEXT), plain_hit(LABEL_TEXT)
    fields = fields_for(("port", "integer", port), ("label", "string", label))
    if case == "same_file":
        hits = [port, plain_hit(QUOTA_TEXT, file_id=port["file_id"])]
    elif case == "missing":
        hits = [port]
    else:
        hits = [port, plain_hit(QUOTA_TEXT)]
    dense = Retrieval(hits)
    service = GroundedService(dense, inference=Unused())
    native = Native()
    error = await refused(service, "owner", fields, native)
    assert (error.status_code, error.code) == (422, "extract_source_mismatch")
    assert native.calls == 0 and not built and dense.validations == 0
    assert "grounded_extract_source_refused code=extract_source_mismatch" in caplog.text
    assert released(dense, service)


def oversized_native_text(index):
    """Build a plain source whose prompt and schema pass but whose native frame exceeds 32 KiB."""
    return " ".join(
        " ".join(f"w{index}x{sentence}y{word}" for word in range(5)) + "."
        for sentence in range(32)
    )


def unsupported(case):
    """Return (rows of (name, kind, hit), adapter_built) for one out-of-bound source shape."""
    if case == "table":
        return [("port", "integer", table_hit())], False
    if case == "other_structure":
        hit = plain_hit(PORT_TEXT)
        hit["provenance"]["structure"] = dict(heading="x")
        return [("port", "integer", hit)], False
    if case == "blank":
        return [("port", "integer", plain_hit("   "))], False
    if case == "chars":
        return [("port", "integer", plain_hit("Port 7443 is set. " * 228))], False
    if case == "bytes":
        return [
            ("port", "integer", plain_hit("ế" * 2800 + ". Port 7443 is set."))
        ], False
    if case == "messages":
        text = " ".join(f"Mục {i} {'ế' * 120} 74{i:02d} đây." for i in range(20))
        rows = [(f"f{i}", "integer", plain_hit(text + f" Hết {i}.")) for i in range(3)]
        return rows, False
    if case == "unit_chars":
        return [("port", "integer", plain_hit("x" * 513 + ". Port 7443 is set."))], True
    if case == "unit_count":
        text = " ".join(f"Port {i} is set." for i in range(33))
        return [("port", "integer", plain_hit(text))], True
    if case == "literal_choices":
        text = " ".join(
            " ".join(f"v{s}w{w}" for w in range(12)) + "." for s in range(20)
        )
        return [("label", "string", plain_hit(text))], True
    assert case == "native_frame"
    return [
        (f"f{i}", "string", plain_hit(oversized_native_text(i))) for i in range(3)
    ], True


@pytest.mark.parametrize(
    "case",
    [
        "table",
        "other_structure",
        "blank",
        "chars",
        "bytes",
        "messages",
        "unit_chars",
        "unit_count",
        "literal_choices",
        "native_frame",
    ],
)
@pytest.mark.asyncio
async def test_unsupported_sources_are_refused_with_zero_transport_calls(
    monkeypatch, caplog, case
):
    """Refuse table/cell structure and every adapter bound before the first transport request."""
    caplog.set_level(logging.INFO)
    built = record_adapters(monkeypatch)
    rows, adapter_built = unsupported(case)
    owner = uuid4()
    dense, service = service_for([(owner, hit) for _, _, hit in rows])
    native = Native()
    error = await refused(service, owner, fields_for(*rows), native)
    assert (error.status_code, error.code) == (422, "extract_source_unsupported")
    assert native.calls == 0 and dense.validations == 0
    assert len(built) == int(adapter_built)
    assert all(adapter.calls == 0 for adapter in built)
    assert "grounded_extract_source_refused code=extract_source_unsupported" in (
        caplog.text
    )
    assert "grounded_extract_admitted" not in caplog.text
    assert released(dense, service)


@pytest.mark.asyncio
async def test_no_sources_never_constructs_an_adapter(monkeypatch):
    """Return no_sources without inference when owner-scoped retrieval yields nothing."""
    built = record_adapters(monkeypatch)
    dense, service = service_for([])
    native = Native()
    port = plain_hit(PORT_TEXT)
    async with service.extraction(
        uuid4(),
        QUERY,
        fields_for(("port", "integer", port)),
        transport=httpx.MockTransport(native),
    ) as (payload, retained):
        assert retained == []
        assert payload == dict(
            status="no_sources",
            facts=None,
            citations=[],
            answer_trust="model_generated",
            content_trust="untrusted",
            extraction=None,
        )
    assert native.calls == 0 and not built and released(dense, service)


@pytest.mark.asyncio
async def test_explicit_refusal_publishes_nothing(monkeypatch):
    """Map the adapter's explicit refusal to insufficient_evidence with no facts, citations or provenance."""
    built = record_adapters(monkeypatch)
    owner = uuid4()
    port, label = plain_hit(PORT_TEXT), plain_hit(LABEL_TEXT)
    dense, service = service_for([(owner, port), (owner, label)])
    native = Native(refusal=True)
    fields = fields_for(("port", "integer", port), ("label", "string", label))
    async with service.extraction(
        owner, QUERY, fields, transport=httpx.MockTransport(native)
    ) as (payload, _):
        assert payload == dict(
            status="insufficient_evidence",
            facts=None,
            citations=[],
            answer_trust="model_generated",
            content_trust="untrusted",
            extraction=None,
        )
        assert dense.validations == 2
    assert len(native.generations) == 1 and built[0].provenance is None
    assert released(dense, service)


@pytest.mark.parametrize("fault", ["malformed", "http", "model"])
@pytest.mark.asyncio
async def test_adapter_rejections_map_to_extract_model_unavailable(monkeypatch, fault):
    """Expose only 503 extract_model_unavailable for every non-refusal adapter rejection, without retry."""
    built = record_adapters(monkeypatch)
    owner = uuid4()
    port = plain_hit(PORT_TEXT)
    dense, service = service_for([(owner, port)])
    native = Native(fault=fault)
    error = await refused(service, owner, fields_for(("port", "integer", port)), native)
    assert (error.status_code, error.code) == (503, "extract_model_unavailable")
    assert len(native.generations) == 1 and len(built) == 1 and built[0].calls == 1
    assert released(dense, service)


@pytest.mark.parametrize("stage,generations", [(1, 0), (2, 1)])
@pytest.mark.asyncio
async def test_source_changes_before_and_after_inference_are_fenced(stage, generations):
    """Reject a changed source before any model call and again after generation without yielding."""
    owner = uuid4()
    port = plain_hit(PORT_TEXT)
    dense, service = service_for([(owner, port)], change_at=stage)
    native = Native()
    error = await refused(service, owner, fields_for(("port", "integer", port)), native)
    assert (error.status_code, error.code) == (409, "retrieval_source_changed")
    assert len(native.generations) == generations
    assert native.calls == (0 if stage == 1 else 4)
    assert released(dense, service)


@pytest.mark.parametrize("fault", ["changed", "send_failure"])
@pytest.mark.asyncio
async def test_delivery_fence_and_send_cleanup(fault):
    """Send 409 retrieval_source_changed before headers without any quote, and release on send failure."""
    owner = uuid4()
    port = plain_hit(PORT_TEXT)
    dense, service = service_for([(owner, port)])
    context = service.extraction(
        owner,
        QUERY,
        fields_for(("port", "integer", port)),
        transport=httpx.MockTransport(Native()),
    )
    payload, retained = await context.__aenter__()
    assert payload["status"] == "extracted"
    response = RetrievalResponse(context, service, owner, payload, retained)
    messages = []

    async def send(message):
        """Capture delivered ASGI messages or raise a controlled transport failure."""
        if fault == "send_failure":
            raise OSError("controlled transport failure")
        messages.append(message)

    if fault == "changed":
        dense.changed = True
        await response({"type": "http"}, None, send)
        body = b"".join(row.get("body", b"") for row in messages)
        assert messages[0]["status"] == 409
        assert json.loads(body) == {"detail": {"code": "retrieval_source_changed"}}
        assert PORT_QUOTE.encode() not in body and b"7443" not in body
    else:
        with pytest.raises(OSError):
            await response({"type": "http"}, None, send)
    assert released(dense, service)


@pytest.mark.asyncio
async def test_grounded_busy_is_shared_with_answer_in_both_directions():
    """Refuse extraction while /answer holds admission and refuse /answer while extraction holds it."""
    owner = uuid4()
    port = plain_hit(PORT_TEXT)
    dense = OwnerRetrieval([(owner, port)])
    service = GroundedService(dense, inference=Unused())
    fields = fields_for(("port", "integer", port))
    async with service.operation(owner, "query", top_k=1, file_ids=[fields[0][2]]):
        native = Native()
        error = await refused(service, owner, fields, native)
        assert (error.status_code, error.code) == (429, "grounded_busy")
        assert native.calls == 0
    async with service.extraction(
        owner, QUERY, fields, transport=httpx.MockTransport(Native())
    ):
        with pytest.raises(StoragePolicyError) as caught:
            async with service.operation(owner, "query"):
                pytest.fail("must not admit /answer")
        assert (caught.value.status_code, caught.value.code) == (429, "grounded_busy")
    assert released(dense, service)


@pytest.mark.asyncio
async def test_retrieval_busy_is_shared_with_retrieval_search(monkeypatch):
    """Inherit 429 retrieval_busy from the real retrieval admission and release grounded admission."""
    built = record_adapters(monkeypatch)
    files = SimpleNamespace(closing=False)
    retrieval = RetrievalService(
        SimpleNamespace(
            files=files, journal=None, vectors=None, closing=False, model=None
        ),
        encoder=object(),
    )
    service = GroundedService(retrieval, inference=Unused())
    await retrieval.admission.acquire()
    native = Native()
    try:
        error = await refused(
            service,
            uuid4(),
            fields_for(("port", "integer", plain_hit(PORT_TEXT))),
            native,
        )
    finally:
        retrieval.admission.release()
    assert (error.status_code, error.code) == (429, "retrieval_busy")
    assert native.calls == 0 and not built
    assert not service.admission.locked() and not service.operations


@pytest.mark.parametrize("mode", ["cancel", "repeated_cancel", "shutdown", "timeout"])
@pytest.mark.asyncio
async def test_owned_extraction_is_joined_before_readers_close(monkeypatch, mode):
    """Join the per-request adapter task under cancel, repeated cancel, shutdown and timeout."""
    built = record_adapters(monkeypatch)
    owner = uuid4()
    port = plain_hit(PORT_TEXT)
    dense, service = service_for(
        [(owner, port)], model_timeout=0.5 if mode == "timeout" else 60
    )
    native = Native(block=True)
    native.observe = lambda: dense.held
    fields = fields_for(("port", "integer", port))

    async def consume():
        """Hold the extraction context while the native generation is blocked."""
        async with service.extraction(
            owner, QUERY, fields, transport=httpx.MockTransport(native)
        ):
            await asyncio.sleep(30)

    task = asyncio.create_task(consume())
    await asyncio.wait_for(native.entered.wait(), 5)
    assert task in service.operations and service.admission.locked()
    if mode == "shutdown":
        await service.shutdown()
    elif mode != "timeout":
        task.cancel()
        if mode == "repeated_cancel":
            asyncio.get_running_loop().call_later(0.005, task.cancel)
    with pytest.raises((asyncio.CancelledError, StoragePolicyError)) as caught:
        await task
    if mode == "timeout":
        assert (caught.value.status_code, caught.value.code) == (
            504,
            "grounded_model_timeout",
        )
    assert native.closed and native.observed == [True]
    assert built[0].provenance is None and built[0].calls == 1
    assert released(dense, service)
    await service.shutdown()
    with pytest.raises(StoragePolicyError) as caught:
        async with service.extraction(owner, QUERY, fields):
            pytest.fail("closed service must not admit")
    assert caught.value.code == "grounded_unavailable"


@pytest.mark.asyncio
async def test_each_request_uses_a_new_single_use_adapter(monkeypatch):
    """Construct one adapter per extraction and never reuse a consumed adapter."""
    built = record_adapters(monkeypatch)
    owner = uuid4()
    port = plain_hit(PORT_TEXT)
    dense, service = service_for([(owner, port)])
    fields = fields_for(("port", "integer", port))
    native = Native()
    for _ in range(2):
        async with service.extraction(
            owner, QUERY, fields, transport=httpx.MockTransport(native)
        ) as (payload, _):
            assert payload["status"] == "extracted"
    assert len(built) == 2 and built[0] is not built[1]
    assert [adapter.calls for adapter in built] == [1, 1]
    assert len(native.generations) == 2
    assert not hasattr(service, "adapter") and released(dense, service)


@pytest.mark.asyncio
async def test_citation_spans_map_to_exact_codepoints_without_private_provenance():
    """Offset split-chunk source spans, keep combining/astral codepoints and drop provenance internals."""
    owner = uuid4()
    port = plain_hit(PORT_TEXT, start=100)
    label = plain_hit(LABEL_TEXT)
    dense, service = service_for([(owner, port), (owner, label)])
    fields = fields_for(("port", "integer", port), ("label", "string", label))
    async with service.extraction(
        owner, QUERY, fields, transport=httpx.MockTransport(Native())
    ) as (payload, _):
        first, second = payload["citations"]
    assert set(first) == {
        "field",
        "quote",
        "quote_span",
        "file_id",
        "chunk_id",
        "source_sha256",
        "generation",
        "source_span",
    }
    for cite, hit in ((first, port), (second, label)):
        span = cite["quote_span"]
        assert hit["text"][span["start"] : span["end"]] == cite["quote"]
        assert span["start"] == hit["text"].index(cite["quote"])
        assert span["unit"] == "unicode_code_points"
        assert span["reference"] == "chunk_text"
        source = cite["source_span"]
        base = hit["provenance"]["spans"][0]["start"]
        assert (source["start"], source["end"]) == (
            base + span["start"],
            base + span["end"],
        )
        assert source["locator"] == hit["provenance"]["locator"]
        assert source["field"] == "text" and source["unit"] == "unicode_code_points"
        assert (cite["chunk_id"], cite["source_sha256"], cite["generation"]) == (
            hit["chunk_id"],
            hit["source_sha256"],
            hit["generation"],
        )
    assert first["source_span"]["start"] == 100
    assert second["quote"] == LABEL_QUOTE and "é" in second["quote"]
    rendered = json.dumps(payload, ensure_ascii=False)
    for private in ("point_id", "provenance", "owner_id", "source_id", "score"):
        assert private not in rendered
    assert port["point_id"] not in rendered


@pytest.mark.asyncio
async def test_astral_offsets_count_codepoints():
    """Count an astral character as one codepoint before the cited sentence."""
    owner = uuid4()
    text = "𝄞 Ghi chú. " + PORT_TEXT
    port = plain_hit(text)
    dense, service = service_for([(owner, port)])
    async with service.extraction(
        owner,
        QUERY,
        fields_for(("port", "integer", port)),
        transport=httpx.MockTransport(Native()),
    ) as (payload, _):
        (cite,) = payload["citations"]
    assert cite["quote_span"]["start"] == len("𝄞 Ghi chú. ") == 11
    assert text[cite["quote_span"]["start"] : cite["quote_span"]["end"]] == PORT_QUOTE


@pytest.mark.parametrize(
    "fields",
    [
        (),
        "port",
        (("port", "integer"),),
        (("citations", "integer", uuid4()),),
        (("port", "number", uuid4()),),
        (("port", "integer", "not-uuid"),),
        tuple((f"f{i}", "string", uuid4()) for i in range(4)),
    ],
)
@pytest.mark.asyncio
async def test_service_rejects_invalid_field_declarations_before_admission(fields):
    """Apply the extraction contract at the service boundary before retrieval or admission."""
    dense, service = service_for([])
    error = await refused(service, uuid4(), fields, Native())
    assert (error.status_code, error.code) == (422, "extract_contract_invalid")
    assert dense.options is None and released(dense, service)
