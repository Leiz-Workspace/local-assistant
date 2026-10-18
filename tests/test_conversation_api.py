"""Verify persistent-chat HTTP validation, security, error redaction and composition."""

import logging
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from apps.api.main import app
from apps.api.services.conversations import ConversationService
from apps.api.storage import lifecycle
from src.application.ports.inference import InferenceFailure
from src.application.services.conversation_manager import ConversationError

logger = logging.getLogger(__name__)


@pytest.fixture
def service():
    """Supply a domain-shaped fake at the HTTP dependency boundary."""
    now = datetime.now(timezone.utc)
    conversation = SimpleNamespace(
        id=uuid4(),
        title="Test",
        profile="core",
        preset_default="balanced",
        status="active",
        created_at=now,
        updated_at=now,
        metadata={"private": "must-not-appear"},
    )
    result = AsyncMock()
    result.for_owner = Mock(return_value=result)
    result.conversation = conversation
    result.create.return_value = conversation
    result.list.return_value = [conversation]
    result.get.return_value = conversation
    result.mutate.return_value = conversation
    result.history.return_value = [
        SimpleNamespace(
            id=uuid4(),
            conversation_id=conversation.id,
            sequence=2,
            role="assistant",
            content="  Exact transcript  ",
            created_at=now,
            metadata={"reasoning_content": "must-not-appear"},
        )
    ]
    result.send.return_value = SimpleNamespace(
        conversation_id=conversation.id,
        user_message_id=uuid4(),
        assistant_message_id=uuid4(),
        inference_run_id=uuid4(),
        content="  Exact answer  ",
        preset_requested="balanced",
        preset_selected="balanced",
        model_id="qwen3.5-9b-core",
        cached=False,
    )
    return result


@pytest.fixture
def client(service, monkeypatch, auth_settings):
    """Run application lifespan without real credentials and inject its service."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with TestClient(
        app, client=("127.0.0.1", 41000), headers=auth_settings["headers"][0]
    ) as connection:
        app.state.conversation_service = service
        yield connection
    logger.info("conversation_api_test_completed")


def test_lifecycle_contract(client, service):
    """Exercise all eight routes and verify pagination, exact content and metadata exclusion."""
    identifier = str(service.conversation.id)
    root = f"/api/v1/conversations/{identifier}"
    response = client.post("/api/v1/conversations", json={"title": " Test "})
    assert response.status_code == 201
    assert "metadata" not in response.json()
    service.create.assert_awaited_once_with(
        title="Test", profile="core", preset_default="balanced"
    )
    assert (
        client.get(
            "/api/v1/conversations?limit=2&offset=1&include_archived=true"
        ).status_code
        == 200
    )
    service.list.assert_awaited_once_with(limit=2, offset=1, include_archived=True)
    assert client.get(root).status_code == 200
    assert client.patch(root, json={"preset_default": "fast"}).status_code == 200
    service.mutate.assert_awaited_with(
        service.conversation.id, "update", preset_default="fast"
    )
    response = client.get(root + "/messages?limit=2&after_sequence=1")
    assert response.status_code == 200
    assert response.json()[0]["content"] == "  Exact transcript  "
    assert "must-not-appear" not in response.text
    service.history.assert_awaited_once_with(
        service.conversation.id, limit=2, after_sequence=1
    )
    response = client.post(
        root + "/messages", json={"content": "  Keep space  ", "request_key": "key-1"}
    )
    assert response.status_code == 200
    assert response.json()["content"] == "  Exact answer  "
    service.send.assert_awaited_once_with(
        service.conversation.id,
        content="  Keep space  ",
        preset=None,
        request_key="key-1",
        temperature=0.7,
        max_tokens=None,
    )
    assert client.post(root + "/archive").status_code == 200
    assert client.delete(root).status_code == 204


@pytest.mark.parametrize(
    "method,path,body",
    [
        ("post", "", {"profile": "other"}),
        ("post", "", {"title": " "}),
        ("post", "", {"metadata": {"owner": "fake"}}),
        ("get", "?limit=101", None),
        ("get", "?offset=-1", None),
        ("get", "/not-a-uuid", None),
        ("patch", "/{id}", {}),
        ("patch", "/{id}", {"title": None}),
        ("patch", "/{id}", {"profile": "unrestricted"}),
        ("post", "/{id}/messages", {"content": " "}),
        ("post", "/{id}/messages", {"content": "ok", "temperature": 3}),
        ("post", "/{id}/messages", {"content": "ok", "max_tokens": 0}),
        ("post", "/{id}/messages", {"content": "ok", "request_key": "x" * 129}),
        ("post", "/{id}/messages", {"content": "ok", "preset": "unknown"}),
        ("get", "/{id}/messages?after_sequence=-1", None),
    ],
)
def test_invalid_inputs(client, service, method, path, body):
    """Reject malformed and unsupported operations before calling the service."""
    path = path.replace("{id}", str(service.conversation.id))
    response = client.request(method, "/api/v1/conversations" + path, json=body)
    assert response.status_code == 422
    for name in ("create", "list", "get", "mutate", "history", "send"):
        getattr(service, name).assert_not_awaited()


@pytest.mark.parametrize(
    "headers",
    [
        {"Origin": "https://evil.example"},
        {"Origin": "null"},
        {"X-Forwarded-For": "127.0.0.1"},
        {"Forwarded": "for=127.0.0.1"},
        {"X-Real-IP": "127.0.0.1"},
    ],
)
def test_browser_and_proxy_denied(client, service, headers):
    """Reject indirect access even when its forwarding metadata claims localhost."""
    assert client.get("/api/v1/conversations", headers=headers).status_code == 403
    service.list.assert_not_awaited()


@pytest.mark.parametrize("peer,expected", [("203.0.113.2", 403), ("::1", 503)])
def test_peer_boundary(peer, expected, monkeypatch):
    """Trust the connection peer rather than the Host header."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with TestClient(app, client=(peer, 40000)) as connection:
        assert (
            connection.get(
                "/api/v1/conversations", headers={"Host": "localhost"}
            ).status_code
            == expected
        )


@pytest.mark.parametrize(
    "error,status,code",
    [
        (
            ConversationError(
                "private", code="conversation_not_found", status_code=404
            ),
            404,
            "conversation_not_found",
        ),
        (
            ConversationError("private", code="idempotency_conflict", status_code=409),
            409,
            "idempotency_conflict",
        ),
        (InferenceFailure("private", status_code=502), 502, "inference_failed"),
        (InferenceFailure("private", status_code=503), 503, "inference_failed"),
        (InferenceFailure("private", status_code=504), 504, "inference_failed"),
        (
            OperationalError("private", {}, Exception("private password")),
            503,
            "storage_unavailable",
        ),
    ],
)
def test_safe_errors(client, service, error, status, code, caplog):
    """Keep driver statements, inference content and credentials out of responses and logs."""
    service.get.side_effect = error
    with caplog.at_level(logging.INFO):
        response = client.get(f"/api/v1/conversations/{service.conversation.id}")
    assert response.status_code == status
    assert response.json()["detail"]["code"] == code
    assert "private" not in response.text + caplog.text


def test_missing_storage_preserves_health(monkeypatch):
    """Keep stateless application routes available when persistent storage is disabled."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with TestClient(app, client=("127.0.0.1", 40000)) as connection:
        assert connection.get("/api/v1/conversations").status_code == 503
        assert connection.get("/api/v1/health").status_code == 200
        paths = connection.get("/openapi.json").json()["paths"]
        assert "/api/v1/chat/completions" in paths
        assert paths["/api/v1/conversations/{conversation_id}/archive"].get("post")


@pytest.mark.asyncio
async def test_pool_disposal(monkeypatch):
    """Dispose the single process pool even if the application body fails."""
    engine = AsyncMock()
    service = object()
    monkeypatch.setenv("DATABASE_URL", "private-value")
    monkeypatch.setattr(lifecycle, "create_database_engine", lambda: engine)
    observer = Mock()
    observer.sample = AsyncMock()
    monkeypatch.setattr(lifecycle, "PoolTelemetry", lambda engine: observer)
    monkeypatch.setattr(lifecycle, "create_session_factory", lambda value: object())
    monkeypatch.setattr(lifecycle, "ConversationService", lambda factory: service)
    with pytest.raises(RuntimeError, match="test failure"):
        async with lifecycle.conversation_lifespan(app):
            assert app.state.conversation_service is service
            raise RuntimeError("test failure")
    engine.dispose.assert_awaited_once()
    assert app.state.conversation_service is None


@pytest.mark.asyncio
async def test_invalid_bootstrap_is_redacted(monkeypatch, caplog):
    """Reject invalid configuration without exposing its secret-bearing exception."""
    monkeypatch.setenv("DATABASE_URL", "not-a-database")
    with pytest.raises(RuntimeError, match="initialization failed") as error:
        async with lifecycle.conversation_lifespan(app):
            pytest.fail("Invalid configuration must fail startup")
    assert "not-a-database" not in str(error.value) + caplog.text


@pytest.mark.asyncio
async def test_send_uses_stored_defaults(monkeypatch):
    """Delegate model identity, whitespace, idempotency and default preset to the manager."""
    service = ConversationService(object(), inference=object())
    service.get = AsyncMock(
        return_value=SimpleNamespace(profile="core", preset_default="deep")
    )
    service.manager = AsyncMock()
    identifier = uuid4()
    await service.send(identifier, content=" exact ", preset=None, request_key="key")
    service.manager.send_message.assert_awaited_once_with(
        conversation_id=identifier,
        profile="core",
        model_id="qwen3.5-9b-core",
        preset="deep",
        content=" exact ",
        request_key="key",
    )


@pytest.fixture
def repository_service(monkeypatch):
    """Compose the real service against isolated transaction and repository doubles."""
    from unittest.mock import MagicMock

    from apps.api.services import conversations

    session = AsyncMock()
    session.begin = MagicMock(return_value=AsyncMock())
    context = AsyncMock()
    context.__aenter__.return_value = session
    factory = MagicMock(return_value=context)
    repositories = SimpleNamespace(
        conversations=AsyncMock(), messages=AsyncMock(), runs=AsyncMock()
    )
    monkeypatch.setattr(
        conversations,
        "PostgresConversationRepository",
        lambda value: repositories.conversations,
    )
    monkeypatch.setattr(
        conversations, "PostgresMessageRepository", lambda value: repositories.messages
    )
    monkeypatch.setattr(
        conversations, "PostgresInferenceRunRepository", lambda value: repositories.runs
    )
    repositories.conversations.get.return_value = SimpleNamespace(status="active")
    repositories.conversations.lock_active.return_value = SimpleNamespace(
        status="active"
    )
    repositories.runs.get_pending.return_value = None
    return ConversationService(factory, inference=object()), repositories


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["update", "archive", "delete"])
async def test_busy_mutations_rejected(repository_service, action):
    """Prevent lifecycle changes from racing a pending inference reservation."""
    service, repositories = repository_service
    repositories.runs.get_pending.return_value = object()
    with pytest.raises(ConversationError) as error:
        await service.mutate(uuid4(), action)
    assert error.value.status_code == 409
    assert error.value.code == "conversation_busy"
    repositories.conversations.lock_active.assert_awaited_once()
    for name in ("update", "archive", "soft_delete"):
        getattr(repositories.conversations, name).assert_not_awaited()


@pytest.mark.asyncio
async def test_deleted_history_hidden(repository_service):
    """Check visibility before reading transcript rows for a missing conversation."""
    service, repositories = repository_service
    repositories.conversations.get.return_value = None
    with pytest.raises(ConversationError) as error:
        await service.history(uuid4(), limit=10, after_sequence=0)
    assert error.value.status_code == 404
    repositories.messages.list.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "action,method",
    [("update", "update"), ("archive", "archive"), ("delete", "soft_delete")],
)
async def test_idle_mutations_commit(repository_service, action, method):
    """Execute idle lifecycle mutations through the established transaction boundary."""
    service, repositories = repository_service
    identifier = uuid4()
    await service.mutate(identifier, action)
    getattr(repositories.conversations, method).assert_awaited_once_with(identifier)


@pytest.mark.asyncio
async def test_repository_reads_and_creation(repository_service):
    """Keep CRUD pagination and domain values intact through service composition."""
    service, repositories = repository_service
    identifier = uuid4()
    repositories.conversations.create.return_value = SimpleNamespace(id=identifier)
    repositories.conversations.list.return_value = []
    repositories.messages.list.return_value = []
    await service.create(title="Test", profile="core", preset_default="balanced")
    repositories.conversations.create.assert_awaited_once_with(
        title="Test", profile="core", preset_default="balanced"
    )
    assert await service.list(limit=5, offset=0, include_archived=True) == []
    repositories.conversations.list.assert_awaited_once_with(
        limit=5, offset=0, include_archived=True
    )
    assert await service.history(identifier, limit=3, after_sequence=2) == []
    repositories.messages.list.assert_awaited_once_with(
        identifier, limit=3, after_sequence=2
    )


def test_orm_domain_mapping():
    """Verify restored ORM sources map transcript and run state without losing fields."""
    from src.infrastructure.models.conversation_model import ConversationModel
    from src.infrastructure.models.inference_run_model import InferenceRunModel
    from src.infrastructure.models.message_model import MessageModel

    now = datetime.now(timezone.utc)
    identifier = uuid4()
    conversation = ConversationModel(
        id=identifier,
        title="Test",
        profile="core",
        preset_default="balanced",
        status="active",
        created_at=now,
        updated_at=now,
        metadata_={},
    ).to_entity()
    message = MessageModel(
        id=uuid4(),
        conversation_id=identifier,
        sequence=1,
        role="user",
        content=" exact ",
        created_at=now,
        metadata_={},
    ).to_entity()
    run = InferenceRunModel(
        id=uuid4(),
        conversation_id=identifier,
        user_message_id=message.id,
        preset_requested="balanced",
        preset_selected="balanced",
        model_id="test",
        status="pending",
        started_at=now,
        metadata_={},
    ).to_entity()
    assert conversation.id == message.conversation_id == run.conversation_id
    assert message.content == " exact "
    assert run.user_message_id == message.id
    assert run.status == "pending"


def test_stateless_route_contract_preserved(client, monkeypatch):
    """Verify the existing endpoint still delegates directly to its gateway."""
    from apps.api.routes import chat

    gateway = AsyncMock()
    gateway.complete.return_value = {
        "choices": [{"message": {"content": "STATELESS-OK"}}]
    }
    monkeypatch.setattr(chat, "LlamaGateway", lambda **values: gateway)
    response = client.post(
        "/api/v1/chat/completions",
        json={
            "messages": [{"role": "user", "content": "Hello"}],
            "preset": "fast",
        },
    )
    assert response.status_code == 200
    assert response.json() == gateway.complete.return_value
    gateway.complete.assert_awaited_once_with(
        messages=[{"role": "user", "content": "Hello"}],
        temperature=0.7,
        max_tokens=None,
        preset="fast",
    )
