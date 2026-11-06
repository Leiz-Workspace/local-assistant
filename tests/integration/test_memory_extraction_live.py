"""Verify actual CORE user-message selection and real SQL source/control/delivery fences with explicit port boundaries."""

import asyncio
import hashlib
import json
import logging
import os
from pathlib import Path
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import text
from test_memory_http import memory_client as memory_client
from test_memory_journal_postgres import memory_context as memory_context
from test_message_memory_journal import extraction_receipt, message_source
from test_message_memory_journal import message_context as message_context
from test_reranker_tcp_trial import localhost_server

from apps.api.core.model_config import get_model_profile
from apps.api.routes.memory import MemorySelectionResponse
from apps.api.services.memory import MemoryService
from apps.api.services.memory_extraction import MemoryExtractor
from src.application.ports.inference import CompletionResult
from src.application.services.memory_contract import MemoryPolicyError

logger = logging.getLogger(__name__)


class ControlledCore:
    """Delay a declared protocol reply for real database lifecycle faults without claiming model inference."""

    def __init__(self, *, blocking=True):
        """Expose deterministic model-entry/release/cleanup signals for owner/source races."""
        self.blocking = blocking
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        self.joined = False

    async def complete(self, **kwargs):
        """Return the exact supplied fixture source only after the explicit control barrier."""
        self.entered.set()
        try:
            if self.blocking:
                await self.release.wait()
            value = json.loads(kwargs["messages"][1]["content"])["source_text"]
            return CompletionResult(
                json.dumps(dict(status="selected", quote=value)),
                "controlled-core",
                "fast",
                "stop",
            )
        finally:
            await asyncio.sleep(0.01)
            self.joined = True


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["source", "deleted", "disabled", "revoked"])
async def test_actual_sql_changes_during_controlled_model_delay(
    message_context, change
):
    """Prevent actual capture after source or consent changes occurring while the controlled model is delayed."""
    context = message_context
    journal = context["journal"]
    owner = context["owners"][0]
    conversation, message, value = await message_source(context)
    receipt = await extraction_receipt(context)
    port = ControlledCore()
    extractor = MemoryExtractor(journal, inference=port)

    async def consume():
        """Require a source/control fence before any generated payload enters delivery."""
        async with extractor.operation(owner, receipt.id, conversation, message):
            pytest.fail("must reject stale capture")

    task = asyncio.create_task(consume())
    await asyncio.wait_for(port.entered.wait(), 5)
    if change in ("source", "deleted"):
        async with context["sessions"]() as session, session.begin():
            if change == "source":
                await session.execute(
                    text(
                        "UPDATE assistant.messages SET content='changed' WHERE id=:id"
                    ),
                    dict(id=message),
                )
            else:
                await session.execute(
                    text(
                        "UPDATE assistant.conversations SET deleted_at=clock_timestamp() WHERE id=:id"
                    ),
                    dict(id=conversation),
                )
    elif change == "disabled":
        await journal.configure(
            owner, expected_revision=1, enabled=False, extraction_enabled=False
        )
    else:
        await journal.revoke(owner, receipt.id)
    port.release.set()
    with pytest.raises(MemoryPolicyError):
        await task
    assert not await journal.list(owner) and port.joined and not extractor.operations


@pytest.mark.asyncio
@pytest.mark.parametrize("control", ["configure", "revoke"])
async def test_actual_owner_control_commits_then_joins_selection(
    message_context, control
):
    """Cancel model/client ownership only after the actual disable/revoke transaction has committed."""
    context = message_context
    journal = context["journal"]
    owner = context["owners"][0]
    conversation, message, value = await message_source(context)
    receipt = await extraction_receipt(context)
    port = ControlledCore()
    extractor = MemoryExtractor(journal, inference=port)
    service = MemoryService(journal, extractor=extractor)

    async def consume():
        """Hold an actual authorized selection until the owning controller cancels it."""
        async with extractor.operation(owner, receipt.id, conversation, message):
            pytest.fail("must not yield")

    task = asyncio.create_task(consume())
    await asyncio.wait_for(port.entered.wait(), 5)
    if control == "configure":
        await service.run(
            owner,
            "configure",
            expected_revision=1,
            enabled=False,
            extraction_enabled=False,
        )
    else:
        await service.run(owner, "revoke", receipt.id)
    with pytest.raises(asyncio.CancelledError):
        await task
    assert port.joined and not extractor.operations and not service.operations
    assert await journal.list(owner) == []
    await service.shutdown()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "change", ["source", "disabled", "record_edit", "record_delete"]
)
async def test_actual_final_response_fence_after_capture(message_context, change):
    """Recheck current source/receipt/record before headers even after an earlier valid capture committed."""
    context = message_context
    journal = context["journal"]
    owner = context["owners"][0]
    conversation, message, value = await message_source(context)
    receipt = await extraction_receipt(context)
    extractor = MemoryExtractor(journal, inference=ControlledCore(blocking=False))
    operation = extractor.operation(owner, receipt.id, conversation, message)
    payload, retained = await operation.__aenter__()
    record = payload["record"]
    if change == "source":
        async with context["sessions"]() as session, session.begin():
            await session.execute(
                text("UPDATE assistant.messages SET content='different' WHERE id=:id"),
                dict(id=message),
            )
    elif change == "disabled":
        await journal.configure(
            owner, expected_revision=1, enabled=False, extraction_enabled=False
        )
    elif change == "record_edit":
        await journal.edit_manual(
            owner, record.id, "manual replacement", expected_version=1
        )
    else:
        await journal.delete(owner, record.id, expected_version=1)
    response = MemorySelectionResponse(
        operation, extractor, owner, receipt.id, payload, retained
    )
    frames = []

    async def send(frame):
        """Capture actual ASGI frames to verify no selected text is delivered after the final fence."""
        frames.append(frame)

    await response({"type": "http"}, None, send)
    assert frames[0]["status"] == 409 and value.encode() not in b"".join(
        frame.get("body", b"") for frame in frames
    )
    assert not extractor.operations and not extractor.admission.locked()


class RecordingCore:
    """Record only synthetic model replies/numeric metadata while returning the unchanged actual CORE result."""

    def __init__(self, inner):
        """Wrap the existing verified adapter without replacing inference or reading operator credentials."""
        self.inner = inner
        self.calls = []

    async def complete(self, **kwargs):
        """Run actual CORE and retain declared profile/usage/stop and synthetic selection output for audit."""
        result = await self.inner.complete(**kwargs)
        self.calls.append(
            dict(
                profile=kwargs["profile"],
                preset=kwargs["preset"],
                temperature=kwargs["temperature"],
                max_tokens=kwargs["max_tokens"],
                model_id=result.model_id,
                finish_reason=result.finish_reason,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                latency_ms=result.latency_ms,
                synthetic_reply=result.content,
            )
        )
        return result


def http_receipt(client, headers, kind="preference"):
    """Explicitly enable independent owner extraction and grant one bounded source-selection receipt."""
    settings = client.get("/api/v1/memory/settings", headers=headers).json()
    if not settings["extraction_enabled"]:
        response = client.put(
            "/api/v1/memory/settings",
            headers=headers,
            json=dict(
                expected_revision=settings["revision"],
                enabled=True,
                extraction_enabled=True,
            ),
        )
        assert response.status_code == 200, response.text
        settings = response.json()
    body = dict(
        kind=kind,
        expected_revision=settings["revision"],
        allow_extraction=True,
        seconds=300,
    )
    if kind == "project":
        body["scope_id"] = str(uuid4())
    response = client.post("/api/v1/memory/consents", headers=headers, json=body)
    assert response.status_code == 201, response.text
    return response.json()


def http_source(client, headers, value):
    """Create an actual owned API conversation and insert only a synthetic user message on its existing pool."""
    response = client.post(
        "/api/v1/conversations",
        headers=headers,
        json=dict(
            title="Memory selection source", profile="core", preset_default="fast"
        ),
    )
    assert response.status_code == 201, response.text
    conversation = UUID(response.json()["id"])
    message = uuid4()

    async def persist():
        """Persist fixture content on the app event loop without sharing an engine across loops."""
        async with (
            client.app.state.conversation_service.session_factory() as session,
            session.begin(),
        ):
            await session.execute(
                text(
                    "INSERT INTO assistant.messages(id,conversation_id,sequence,role,content) VALUES (:id,:conversation,1,'user',:content)"
                ),
                dict(id=message, conversation=conversation, content=value),
            )

    client.portal.call(persist)
    return dict(conversation_id=str(conversation), message_id=str(message))


def verify_literal_record(record, source, identity):
    """Independently resolve stored selected text/hash/native Unicode span against the synthetic source oracle."""
    assert record["method"] == "extracted" and record["content_trust"] == "untrusted"
    assert record["model_id"] == get_model_profile("core")["model_id"]
    evidence = record["provenance"]
    assert evidence["kind"] == "conversation_message" and evidence["role"] == "user"
    assert (
        evidence["conversation_id"] == identity["conversation_id"]
        and evidence["message_id"] == identity["message_id"]
    )
    assert evidence["content_sha256"] == hashlib.sha256(source.encode()).hexdigest()
    assert (
        evidence["quote"]
        == record["text"]
        == source[evidence["start"] : evidence["end"]]
    )
    assert source.find(record["text"], source.find(record["text"]) + 1) < 0


def test_actual_core_literal_vi_en_absence_and_foreign_refusal(memory_client):
    """Measure actual existing CORE selection on frozen synthetic facts/absence through authenticated SQL/source APIs."""
    if os.environ.get("LOCAL_ASSISTANT_LIVE_E2E") != "1":
        pytest.skip("explicit existing live CORE acceptance flag required")
    client, auth = memory_client
    headers, foreign = auth["headers"]
    extractor = client.app.state.memory_service.extractor
    recorder = RecordingCore(extractor.inference)
    extractor.inference = recorder
    cases = []
    for kind, value, expected in [
        ("project", "Project Cedar uses port 7443.", "7443"),
        ("preference", "Tôi muốn câu trả lời bằng tiếng Việt.", "tiếng Việt"),
        ("preference", "Hello!", None),
    ]:
        receipt = http_receipt(client, headers, kind)
        identity = http_source(client, headers, value)
        response = client.post(
            "/api/v1/memory/extractions",
            headers=headers,
            json=dict(consent_id=receipt["id"], **identity),
        )
        assert response.status_code == 200, response.text
        assert response.headers["cache-control"] == "private, no-store"
        data = response.json()
        if expected is None:
            assert data["status"] == "insufficient_evidence" and data["record"] is None
        else:
            assert data["status"] == "captured" and expected in data["record"]["text"]
            verify_literal_record(data["record"], value, identity)
            inspected = client.get(
                "/api/v1/memory/records/" + data["record"]["id"], headers=headers
            )
            assert inspected.status_code == 200 and inspected.json() == data["record"]
        cases.append(dict(kind=kind, source=value, identity=identity, result=data))
    foreign_source = http_source(client, foreign, "Foreign private port 9333.")
    before = len(recorder.calls)
    assert (
        client.post(
            "/api/v1/memory/extractions",
            headers=headers,
            json=dict(consent_id=receipt["id"], **foreign_source),
        ).status_code
        == 404
    )
    assert len(recorder.calls) == before == 3
    assert all(
        call["profile"] == "core"
        and call["preset"] == "fast"
        and call["finish_reason"] == "stop"
        for call in recorder.calls
    )
    assert not extractor.operations and not extractor.admission.locked()
    report = dict(
        description="Actual unchanged CORE/fast source-literal message selection on same-agent synthetic English/Vietnamese facts and greeting absence; no human-independent/general quality or confidence claim.",
        cases=cases,
        actual_core_calls=recorder.calls,
        foreign_source_refused_before_model=True,
        new_model_or_schema_change=False,
    )
    path = Path("data/backups/d30-t03-memory-core.json")
    path.touch(mode=0o600, exist_ok=True)
    path.chmod(0o600)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    logger.info("memory_actual_core_selection_verified calls=%d", len(recorder.calls))


def test_actual_core_memory_selection_tcp(memory_client):
    """Deliver actual existing CORE source selection over loopback TCP and join request ownership afterward."""
    if os.environ.get("LOCAL_ASSISTANT_LIVE_E2E") != "1":
        pytest.skip("explicit existing live CORE acceptance flag required")
    client, auth = memory_client
    headers = auth["headers"][0]
    receipt = http_receipt(client, headers)
    value = "I prefer concise replies."
    identity = http_source(client, headers, value)
    with (
        localhost_server(client) as base_url,
        httpx.Client(
            base_url=base_url, trust_env=False, timeout=90, follow_redirects=False
        ) as wire,
    ):
        response = wire.post(
            "/api/v1/memory/extractions",
            headers=headers,
            json=dict(consent_id=receipt["id"], **identity),
        )
        assert response.status_code == 200, response.text
        assert response.headers["cache-control"] == "private, no-store"
        data = response.json()
        assert data["status"] == "captured" and "concise" in data["record"]["text"]
        verify_literal_record(data["record"], value, identity)
    extractor = client.app.state.memory_service.extractor
    assert not extractor.operations and not extractor.admission.locked()
    report = dict(
        description="Actual existing CORE quote selection and source proof delivered over ephemeral loopback Uvicorn on fixture event loop; not load/separate-process certification.",
        actual_tcp=True,
        source=value,
        identity=identity,
        result=data,
        temporary_server_joined=True,
        request_ownership_joined=True,
    )
    path = Path("data/backups/d30-t03-memory-core-tcp.json")
    path.touch(mode=0o600, exist_ok=True)
    path.chmod(0o600)
    path.write_text(json.dumps(report, indent=2) + "\n")
