"""Verify memory management startup/auth/input/error contracts and joined owned-operation shutdown."""

import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from apps.api.main import app
from apps.api.routes.memory import ConsentInput, CreateInput, EditInput, SettingsInput
from apps.api.services.memory import MemoryService
from apps.api.storage.memory import initialize_memory_service
from src.application.services.memory_contract import MemoryPolicyError


def sessions_for(row):
    """Expose only the expected one-row schema query without a real pool or credential."""

    class Result:
        """Hold an explicit schema/privilege tuple for startup-boundary testing."""

        def one(self):
            """Return only the simulated startup privilege result."""
            return row

    @asynccontextmanager
    async def sessions():
        """Yield a one-query session to the production initializer."""
        yield SimpleNamespace(execute=AsyncMock(return_value=Result()))

    return sessions


@pytest.mark.asyncio
async def test_default_off_and_explicit_dependencies(monkeypatch):
    """Keep default startup inert and require existing sessions with exact reviewed immutable/mutable grants."""
    monkeypatch.delenv("ASSISTANT_MEMORY_ENABLED", raising=False)
    assert await initialize_memory_service(None) is None
    monkeypatch.setenv("ASSISTANT_MEMORY_ENABLED", "1")
    with pytest.raises(RuntimeError):
        await initialize_memory_service(None)
    service = await initialize_memory_service(
        sessions_for(("0006", False, True, False, True, False))
    )
    assert not service.closing and not service.operations
    await service.shutdown()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "row",
    [
        ("0004", False, True, False, True, False),
        ("0005", False, True, False, True, False),
        ("0007", False, True, False, True, False),
        ("0006", True, True, False, True, False),
        ("0006", False, False, False, True, False),
        ("0006", False, True, True, True, False),
        ("0006", False, True, False, True, True),
    ],
)
async def test_startup_refuses_unknown_schema_and_broadened_grants(monkeypatch, row):
    """Reject unreviewed or overprivileged runtime storage rather than silently enabling memory."""
    monkeypatch.setenv("ASSISTANT_MEMORY_ENABLED", "1")
    with pytest.raises(RuntimeError):
        await initialize_memory_service(sessions_for(row))


@pytest.mark.parametrize(
    "model,body",
    [
        (SettingsInput, dict(expected_revision=True, enabled=True)),
        (SettingsInput, dict(expected_revision=0, enabled="true")),
        (SettingsInput, dict(expected_revision=0, enabled=True, owner_id=str(uuid4()))),
        (ConsentInput, dict(kind="system", expected_revision=1)),
        (ConsentInput, dict(kind="project", scope_id="bad", expected_revision=1)),
        (ConsentInput, dict(kind="preference", expected_revision=1, seconds=True)),
        (CreateInput, dict(consent_id=str(uuid4()), text="x", provenance={})),
        (CreateInput, dict(consent_id=str(uuid4()), text="x", model_id="replacement")),
        (EditInput, dict(expected_version="1", text="x")),
        (EditInput, dict(expected_version=1, text="x", content_trust="system")),
    ],
)
def test_strict_management_inputs(model, body):
    """Deny primitive coercion and caller ownership/model/provenance/trust overrides."""
    with pytest.raises(ValueError):
        model.model_validate(body)


def test_auth_origin_default_off_and_uuid_json(auth_settings, monkeypatch):
    """Use real local/bearer/Origin guards before disabled-service access and accept JSON UUIDs only as IDs."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with TestClient(app, client=("127.0.0.1", 43000)) as client:
        assert client.get("/api/v1/memory/settings").status_code == 401
        assert (
            client.get(
                "/api/v1/memory/settings", headers=auth_settings["headers"][0]
            ).status_code
            == 503
        )
        assert (
            client.get(
                "/api/v1/memory/settings",
                headers={
                    **auth_settings["headers"][0],
                    "Origin": "http://foreign.invalid",
                },
            ).status_code
            == 403
        )
    identifier = uuid4()
    assert (
        CreateInput.model_validate_json(
            '{"consent_id":"' + str(identifier) + '","text":"x"}'
        ).consent_id
        == identifier
    )


@pytest.mark.parametrize(
    "error,status",
    [
        (MemoryPolicyError("memory_not_found"), 404),
        (MemoryPolicyError("memory_conflict"), 409),
        (MemoryPolicyError("memory_disabled"), 403),
        (MemoryPolicyError("memory_consent_limit"), 429),
        (ValueError("PRIVATE-DIAGNOSTIC"), 503),
    ],
)
def test_safe_management_errors(auth_settings, monkeypatch, error, status):
    """Translate storage/policy failures without exposing raw private diagnostic messages."""

    class Failed:
        """Provide an explicit exception boundary for the real authenticated route."""

        closing = False

        async def run(self, *args, **kwargs):
            """Raise only the controlled policy/storage error."""
            raise error

        async def shutdown(self):
            """Allow the actual app lifespan to finish without unrelated resources."""
            return None

    monkeypatch.delenv("DATABASE_URL", raising=False)
    with TestClient(app, client=("127.0.0.1", 43000)) as client:
        client.app.state.memory_service = Failed()
        response = client.get(
            "/api/v1/memory/settings", headers=auth_settings["headers"][0]
        )
        assert (
            response.status_code == status and "PRIVATE-DIAGNOSTIC" not in response.text
        )
        assert response.headers["cache-control"] == "private, no-store"


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["cancel", "repeated_cancel", "shutdown"])
async def test_management_operation_cleanup_precedes_shutdown(mode):
    """Join delayed repository cleanup instead of closing shared resources while SQL work remains owned."""
    entered, release, cleaning = asyncio.Event(), asyncio.Event(), asyncio.Event()

    class Blocking:
        """Simulate delayed rollback cleanup independently of the service task registry."""

        joined = False

        async def settings(self, owner):
            """Wait until cancelled and then complete observable cleanup."""
            entered.set()
            try:
                await release.wait()
            finally:
                cleaning.set()
                await asyncio.sleep(0.02)
                self.joined = True

    journal = Blocking()
    service = MemoryService(journal)
    work = asyncio.create_task(service.run(uuid4(), "settings"))
    await entered.wait()
    if mode == "shutdown":
        await service.shutdown()
    else:
        work.cancel()
        if mode == "repeated_cancel":
            await cleaning.wait()
            work.cancel()
    with pytest.raises(asyncio.CancelledError):
        await work
    assert journal.joined and not service.operations
    await service.shutdown()
    with pytest.raises(MemoryPolicyError, match="memory_unavailable"):
        await service.run(uuid4(), "settings")
