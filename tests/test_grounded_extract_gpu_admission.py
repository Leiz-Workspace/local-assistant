"""Verify the ADR175 forward guard for extraction with a directly bound GPUAdmission and no wrappers otherwise."""

import asyncio
import functools
import importlib
import logging
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from grounded_extract_cases import (
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

from apps.api.services.grounded import GroundedService
from apps.api.voice_admission import TARGETS, ManagedGPUCalls
from src.application.services import gpu_admission
from src.application.services.file_storage_policy import StoragePolicyError
from src.application.services.gpu_admission import AdmissionBusy, GPUAdmission
from src.infrastructure.inference.structured_excerpt_adapter import (
    StructuredExcerptAdapter,
)

PATH = "/api/v1/grounded/extract"


def targets():
    """Return the current callable bound at every declared GPU entry point."""
    result = []
    for module_name, class_name, name in TARGETS:
        module = importlib.import_module(module_name)
        owner = getattr(module, class_name) if class_name else module
        result.append(getattr(owner, name))
    return result


@pytest.mark.parametrize("state", ["residency", "quarantine"])
def test_extraction_during_residency_or_quarantine_is_gpu_busy(
    auth_settings, monkeypatch, caplog, state
):
    """Return 409 gpu_busy, not grounded_unavailable, with zero transport calls and released resources."""
    caplog.set_level(logging.INFO)
    built = record_adapters(monkeypatch)
    principal = auth_settings["principals"][0]
    port = plain_hit(PORT_TEXT)
    native = Native()
    app, dense, service = extract_app([(principal, port)], native)
    with TestClient(app, client=("127.0.0.1", 43000)) as client:
        gate = GPUAdmission()
        guards = ManagedGPUCalls(gate)
        guards.start()
        lease = gate.acquire() if state == "residency" else None
        try:
            if state == "quarantine":
                gate.quarantine()
            assert StructuredExcerptAdapter.complete.__wrapped__ is not None
            response = client.post(
                PATH,
                json=body_for(("port", "integer", port)),
                headers=auth_settings["headers"][0],
            )
            assert not gate.calls and not gate.authorized
            assert gate.poisoned is (state == "quarantine")
        finally:
            if lease is not None:
                gate.release(lease)
            guards.close()
    assert response.status_code == 409
    assert response.json() == {"detail": {"code": "gpu_busy"}}
    assert "grounded_unavailable" not in response.text
    assert native.calls == 0 and len(built) == 1 and built[0].calls == 0
    assert dense.validations == 1
    assert not dense.held and not service.admission.locked() and not service.operations
    assert "grounded_extract_gpu_busy" in caplog.text
    assert gpu_admission._coordinator is None
    assert not hasattr(StructuredExcerptAdapter.__dict__["complete"], "__wrapped__")


def quarantining(native, gate):
    """Wrap a native fixture so the gate is quarantined during the adapter's first backend request."""

    async def handler(request):
        """Poison admission mid-call, as another task's unborrowed cancellation would."""
        if request.url.path == "/v1/models":
            gate.quarantine()
        return await native(request)

    return handler


def test_mid_call_quarantine_is_gpu_busy_over_http(auth_settings, monkeypatch, caplog):
    """Map a guarded inner refusal after mid-call quarantine to 409 gpu_busy, not extract_model_unavailable."""
    caplog.set_level(logging.INFO)
    built = record_adapters(monkeypatch)
    principal = auth_settings["principals"][0]
    port = plain_hit(PORT_TEXT)
    native = Native()
    app, dense, service = extract_app([(principal, port)], native)
    with TestClient(app, client=("127.0.0.1", 43000)) as client:
        gate = GPUAdmission()
        guards = ManagedGPUCalls(gate)
        guards.start()
        try:
            service.extraction = functools.partial(
                service.extraction.func,
                transport=httpx.MockTransport(quarantining(native, gate)),
            )
            response = client.post(
                PATH,
                json=body_for(("port", "integer", port)),
                headers=auth_settings["headers"][0],
            )
            assert gate.poisoned and not gate.calls and not gate.authorized
        finally:
            guards.close()
    assert response.status_code == 409
    assert response.json() == {"detail": {"code": "gpu_busy"}}
    assert native.paths == ["/v1/models"] and not native.generations
    assert len(built) == 1 and built[0].calls == 1 and built[0].provenance is None
    assert dense.validations == 1
    assert not dense.held and not service.admission.locked() and not service.operations
    assert "grounded_extract_gpu_busy" in caplog.text
    assert "grounded_extract_failed" not in caplog.text
    assert gpu_admission._coordinator is None


@pytest.mark.asyncio
async def test_mid_call_quarantine_raises_admission_busy_from_the_service(monkeypatch):
    """Raise AdmissionBusy from the service after mid-call quarantine and release every resource."""
    built = record_adapters(monkeypatch)
    owner = uuid4()
    port = plain_hit(PORT_TEXT)
    dense = OwnerRetrieval([(owner, port)])
    service = GroundedService(dense, inference=Unused())
    native = Native()
    gate = GPUAdmission()
    guards = ManagedGPUCalls(gate)
    guards.start()
    try:
        with pytest.raises(AdmissionBusy, match="gpu_busy"):
            async with service.extraction(
                owner,
                QUERY,
                fields_for(("port", "integer", port)),
                transport=httpx.MockTransport(quarantining(native, gate)),
            ):
                pytest.fail("must not yield after quarantine")
        assert gate.poisoned and not gate.calls
    finally:
        guards.close()
    assert native.paths == ["/v1/models"] and [a.calls for a in built] == [1]
    assert not dense.held and not service.admission.locked() and not service.operations


@pytest.mark.asyncio
async def test_bound_unpoisoned_gate_keeps_adapter_rejection_mapping(monkeypatch):
    """Keep 503 extract_model_unavailable for an ordinary adapter rejection while a healthy gate is bound."""
    record_adapters(monkeypatch)
    owner = uuid4()
    port = plain_hit(PORT_TEXT)
    dense = OwnerRetrieval([(owner, port)])
    service = GroundedService(dense, inference=Unused())
    native = Native(fault="http")
    gate = GPUAdmission()
    guards = ManagedGPUCalls(gate)
    guards.start()
    try:
        with pytest.raises(StoragePolicyError) as caught:
            async with service.extraction(
                owner,
                QUERY,
                fields_for(("port", "integer", port)),
                transport=httpx.MockTransport(native),
            ):
                pytest.fail("must not yield after an adapter rejection")
        assert not gate.poisoned and not gate.calls
    finally:
        guards.close()
    assert (caught.value.status_code, caught.value.code) == (
        503,
        "extract_model_unavailable",
    )
    assert len(native.generations) == 1
    assert not dense.held and not service.admission.locked() and not service.operations


@pytest.mark.asyncio
async def test_admission_busy_propagates_unchanged_from_the_service():
    """Keep AdmissionBusy distinct from policy errors so the route can map it to gpu_busy."""
    owner = uuid4()
    port = plain_hit(PORT_TEXT)
    dense = OwnerRetrieval([(owner, port)])
    service = GroundedService(dense, inference=Unused())
    native = Native()
    gate = GPUAdmission()
    guards = ManagedGPUCalls(gate)
    guards.start()
    lease = gate.acquire()
    try:
        with pytest.raises(AdmissionBusy, match="gpu_busy"):
            async with service.extraction(
                owner,
                QUERY,
                fields_for(("port", "integer", port)),
                transport=httpx.MockTransport(native),
            ):
                pytest.fail("must not yield during residency")
    finally:
        gate.release(lease)
        guards.close()
    assert native.calls == 0 and not gate.poisoned
    assert not dense.held and not service.admission.locked() and not service.operations


@pytest.mark.asyncio
async def test_unborrowed_cancelled_extraction_quarantines_and_later_requests_refuse(
    monkeypatch,
):
    """Quarantine admission when an unborrowed guarded call is cancelled, then refuse the next extraction."""
    built = record_adapters(monkeypatch)
    owner = uuid4()
    port = plain_hit(PORT_TEXT)
    dense = OwnerRetrieval([(owner, port)])
    service = GroundedService(dense, inference=Unused())
    native = Native(block=True)
    native.observe = lambda: dense.held
    fields = fields_for(("port", "integer", port))
    gate = GPUAdmission()
    guards = ManagedGPUCalls(gate)
    guards.start()
    try:

        async def consume():
            """Hold one guarded extraction until it is cancelled."""
            async with service.extraction(
                owner, QUERY, fields, transport=httpx.MockTransport(native)
            ):
                await asyncio.sleep(30)

        task = asyncio.create_task(consume())
        await asyncio.wait_for(native.entered.wait(), 5)
        assert sum(gate.calls.values()) == 1
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert gate.poisoned and not gate.calls
        assert native.closed and native.observed == [True]
        later = Native()
        with pytest.raises(AdmissionBusy):
            async with service.extraction(
                owner, QUERY, fields, transport=httpx.MockTransport(later)
            ):
                pytest.fail("quarantined admission must refuse")
        assert later.calls == 0 and [adapter.calls for adapter in built] == [1, 0]
    finally:
        guards.close()
    assert not dense.held and not service.admission.locked() and not service.operations


def test_extraction_only_app_installs_no_wrappers(auth_settings, monkeypatch):
    """Compose and serve extraction without binding a coordinator or wrapping any GPU entry point."""
    before = targets()
    original = StructuredExcerptAdapter.__dict__["complete"]
    assert not hasattr(original, "__wrapped__")
    assert gpu_admission._coordinator is None
    for name, value in dict(
        ASSISTANT_GROUNDED_EXTRACT_ENABLED="1",
        DATABASE_URL="postgresql+asyncpg://neutral.invalid/fixture",
        ASSISTANT_FILES_ENABLED="1",
        ASSISTANT_INGESTION_ENABLED="1",
        ASSISTANT_INGESTION_CONFIG_FILE="/nonexistent/neutral-ingestion.json",
        ASSISTANT_RETRIEVAL_ENABLED="1",
        ASSISTANT_GROUNDED_ENABLED="1",
    ).items():
        monkeypatch.setenv(name, value)
    monkeypatch.delenv("ASSISTANT_VOICE_ENABLED", raising=False)
    from apps.api.grounded_extract import create_app

    created = create_app()
    assert PATH in created.openapi()["paths"]
    assert targets() == before and gpu_admission._coordinator is None
    principal = auth_settings["principals"][0]
    port = plain_hit(PORT_TEXT)
    native = Native()
    app, _, _ = extract_app([(principal, port)], native)
    with TestClient(app, client=("127.0.0.1", 43000)) as client:
        response = client.post(
            PATH,
            json=body_for(("port", "integer", port)),
            headers=auth_settings["headers"][0],
        )
        assert response.status_code == 200 and response.json()["status"] == "extracted"
        assert StructuredExcerptAdapter.__dict__["complete"] is original
        assert gpu_admission._coordinator is None
    assert targets() == before and gpu_admission._coordinator is None
    assert len(native.generations) == 1
