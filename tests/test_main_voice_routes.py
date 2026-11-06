"""Exercise main-app voice authentication, CSRF, ownership, quota and shutdown with model-free runtimes."""

import asyncio
import hashlib
import json
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI

from apps.api.voice import compose, create_app
from src.infrastructure.voice.audio import encode_wave


class Runtime:
    """Stand in for native workers while retaining explicit ownership and joined lifecycle assertions."""

    def __init__(self, owner, admission, lease):
        """Record the authenticated principal and exclusive GPU capability supplied by the service."""
        self.owner, self.admission, self.lease = owner, admission, lease
        self.calls = []
        self.closed = False

    async def start(self):
        """Prepare immediately without importing or invoking any model SDK."""
        await asyncio.sleep(0)

    def health(self):
        """Expose a finite ready-state check for the owner watcher."""
        assert not self.closed

    async def ask(self, raw, operation):
        """Record one admitted body and return neutral complete output without inference."""
        self.calls.append((raw, operation))
        return dict(
            transcript="neutral question",
            answer="neutral answer",
            audio_base64="",
            stages={},
        )

    async def close(self):
        """Prove resource admission is still held until the owned runtime has joined."""
        assert self.admission.residency is self.lease
        self.closed = True


def fixture_app(tmp_path, monkeypatch):
    """Construct isolated auth/main app state with no real credentials, database, services or models."""
    principal = uuid4()
    token = "neutral-a" * 8
    foreign = "neutral-b" * 8
    path = tmp_path / "auth.json"
    path.write_text(
        json.dumps(
            {
                "principals": [
                    {
                        "id": str(principal),
                        "token_sha256": hashlib.sha256(token.encode()).hexdigest(),
                    },
                    {
                        "id": str(uuid4()),
                        "token_sha256": hashlib.sha256(foreign.encode()).hexdigest(),
                    },
                ]
            }
        )
    )
    path.chmod(0o600)
    monkeypatch.setenv("ASSISTANT_AUTH_FILE", str(path))
    instances = []

    def factory(owner, admission, lease):
        """Inject a controlled runtime and retain its ownership evidence for the test."""
        value = Runtime(owner, admission, lease)
        instances.append(value)
        return value

    base = FastAPI()

    @base.get("/api/v1/health")
    async def health():
        """Keep a representative non-inference health route available during voice residency."""
        return {"status": "ok"}

    app = compose(base, auth_file=path, runtime_factory=factory)
    return app, token, foreign, path, instances, principal


def test_default_off_returns_exact_legacy_main_app(monkeypatch):
    """Leave legacy routes/OpenAPI/lifespan intact and avoid native modules when voice is disabled."""
    from apps.api.main import app

    monkeypatch.delenv("ASSISTANT_VOICE_ENABLED", raising=False)
    before = app.openapi()
    assert create_app() is app
    assert app.openapi() == before
    assert not any("/voice" in path for path in app.openapi()["paths"])


def test_enabled_composition_preserves_every_legacy_openapi_operation(tmp_path):
    """Retain lazily included original routers through the installed FastAPI's public router composition."""
    from apps.api.main import app as base

    app = compose(base, auth_file=tmp_path / "auth", runtime_factory=Runtime)
    original, enabled = base.openapi()["paths"], app.openapi()["paths"]
    assert set(original) <= set(enabled)
    for path, methods in original.items():
        assert enabled[path] == methods


@pytest.mark.parametrize(
    "enabled,workers,purpose",
    [
        ("true", "1", "integration_evaluation"),
        ("1", "2", "integration_evaluation"),
        ("1", "1", "production"),
        ("1", "1", None),
    ],
)
def test_no_implicit_activation_or_multiworker_fallback(
    monkeypatch, enabled, workers, purpose
):
    """Reject unapproved flag/purpose/worker settings without instantiating a native group."""
    monkeypatch.setenv("ASSISTANT_VOICE_ENABLED", enabled)
    monkeypatch.setenv("WEB_CONCURRENCY", workers)
    if purpose is None:
        monkeypatch.delenv("ASSISTANT_VOICE_PURPOSE", raising=False)
    else:
        monkeypatch.setenv("ASSISTANT_VOICE_PURPOSE", purpose)
    with pytest.raises(RuntimeError):
        create_app()


@pytest.mark.asyncio
async def test_main_pairing_replay_csrf_stable_owner_and_release(tmp_path, monkeypatch):
    """Require bearer-issued UI pairing, deny replay/foreign owners, and release the exact resident group."""
    app, token, foreign, path, instances, principal = fixture_app(tmp_path, monkeypatch)
    auth = {"Authorization": "Bearer " + token}
    browser = {"Origin": "http://127.0.0.1:8099", "X-Voice-Submit": "1"}
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, client=("127.0.0.1", 123)),
            base_url="http://127.0.0.1:8099",
        ) as client:
            assert (await client.get("/voice")).status_code == 200
            assert not instances
            assert (await client.get("/ui/voice/status")).status_code == 401
            grant = await client.post("/api/v1/voice/pairing", headers=auth)
            assert grant.status_code == 200
            code = grant.json()["code"]
            assert token not in code
            assert (
                await client.post("/ui/voice/pair", json={"code": code})
            ).status_code == 403
            paired = await client.post(
                "/ui/voice/pair", headers=browser, json={"code": code}
            )
            assert (
                paired.status_code == 200
                and "HttpOnly" in paired.headers["set-cookie"]
                and "SameSite=strict" in paired.headers["set-cookie"]
            )
            assert (
                await client.post(
                    "/ui/voice/pair", headers=browser, json={"code": code}
                )
            ).status_code == 401
            assert (
                await client.post("/api/v1/voice/prepare", headers={**auth, **browser})
            ).status_code == 403
            assert (
                await client.post("/ui/voice/prepare", headers=browser)
            ).status_code == 202
            for _ in range(10):
                status = await client.get("/ui/voice/status")
                if status.json()["state"] == "ready":
                    break
                await asyncio.sleep(0)
            assert status.json()["state"] == "ready" and instances[0].owner == principal
            assert (await client.get("/api/v1/health")).status_code == 200
            operation = str(uuid4())
            denied = await client.post(
                "/api/v1/voice/cancel",
                headers={"Authorization": "Bearer " + foreign},
                json={"id": operation},
            )
            assert denied.status_code == 409
            response = await client.post(
                "/ui/voice/turn",
                headers={
                    **browser,
                    "Content-Type": "audio/wav",
                    "X-Voice-ID": operation,
                },
                content=encode_wave(b"\0\0" * 16000),
            )
            assert response.status_code == 200 and response.json()["id"] == operation
            assert len(instances[0].calls) == 1
            assert (
                await client.post("/ui/voice/release", headers=browser)
            ).status_code == 200
            assert (
                instances[0].closed
                and app.state.voice_service.admission.residency is None
            )


@pytest.mark.asyncio
async def test_auth_before_body_bad_types_early_cancel_and_revocation(
    tmp_path, monkeypatch
):
    """Refuse unauthorized body reads, unsafe origins, cancelled submissions and revoked sessions before inference."""
    app, token, foreign, path, instances, principal = fixture_app(tmp_path, monkeypatch)
    auth = {"Authorization": "Bearer " + token}
    consumed = []

    async def body():
        """Detect any unauthorized request-body consumption by the ASGI application."""
        consumed.append(True)
        yield b"x" * 640045

    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, client=("127.0.0.1", 123)),
            base_url="http://127.0.0.1:8099",
        ) as client:
            result = await client.post(
                "/api/v1/voice/turn",
                headers={"Content-Type": "audio/wav", "X-Voice-ID": str(uuid4())},
                content=body(),
            )
            assert result.status_code == 401 and not consumed
            assert (
                await client.get(
                    "/api/v1/voice/status",
                    headers={**auth, "X-Forwarded-For": "127.0.0.1"},
                )
            ).status_code == 403
            assert (
                await client.post("/api/v1/voice/prepare", headers=auth)
            ).status_code == 202
            await asyncio.sleep(0.01)
            operation = str(uuid4())
            assert (
                await client.post(
                    "/api/v1/voice/cancel", headers=auth, json={"id": operation}
                )
            ).status_code == 200
            result = await client.post(
                "/api/v1/voice/turn",
                headers={**auth, "Content-Type": "audio/wav", "X-Voice-ID": operation},
                content=body(),
            )
            assert result.status_code == 409 and not consumed and not instances[0].calls
            path.write_text('{"principals":[]}')
            assert (
                await client.get("/api/v1/voice/status", headers=auth)
            ).status_code == 503
            await asyncio.sleep(1.05)
            assert instances[0].closed and app.state.voice_service.owner is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "headers,raw",
    [
        ({"Content-Type": "audio/mpeg"}, b"x"),
        ({"Content-Type": "audio/wav"}, b"x"),
        ({"Content-Type": "audio/wav", "Content-Encoding": "gzip"}, b"x"),
        ({"Content-Type": "audio/wav", "Content-Length": "640045"}, b"x"),
        ({"Content-Type": "audio/wav", "Content-Length": "-1"}, b"x"),
        ({"Content-Type": "audio/wav", "Content-Length": "9" * 20}, b"x"),
        ({"Content-Type": "audio/wav", "Content-Length": "0"}, b"x"),
        ({"Content-Type": "audio/wav"}, encode_wave(b"\0\0" * 320001)),
    ],
)
async def test_invalid_audio_never_reaches_runtime(tmp_path, monkeypatch, headers, raw):
    """Refuse malformed, compressed, ambiguous and oversized uploads before any native stage dispatch."""
    app, token, foreign, path, instances, principal = fixture_app(tmp_path, monkeypatch)
    auth = {"Authorization": "Bearer " + token}
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, client=("127.0.0.1", 123)),
            base_url="http://127.0.0.1:8099",
        ) as client:
            await client.post("/api/v1/voice/prepare", headers=auth)
            await asyncio.sleep(0.01)
            response = await client.post(
                "/api/v1/voice/turn",
                headers={**auth, **headers, "X-Voice-ID": str(uuid4())},
                content=raw,
            )
            assert (
                response.status_code == 422
                and response.json()["code"] == "invalid_input"
            )
            assert not instances[0].calls


@pytest.mark.asyncio
async def test_pair_json_is_unambiguous_and_no_bearer_can_enter_bff(
    tmp_path, monkeypatch
):
    """Refuse duplicate JSON keys and browser bearer credentials instead of bypassing pairing."""
    app, token, foreign, path, instances, principal = fixture_app(tmp_path, monkeypatch)
    origin = {"Origin": "http://127.0.0.1:8099", "X-Voice-Submit": "1"}
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, client=("127.0.0.1", 123)),
            base_url="http://127.0.0.1:8099",
        ) as client:
            response = await client.post(
                "/ui/voice/pair",
                headers={**origin, "Content-Type": "application/json"},
                content=b'{"code":"a","code":"b"}',
            )
            assert response.status_code == 422
            response = await client.get(
                "/ui/voice/status", headers={"Authorization": "Bearer " + token}
            )
            assert response.status_code == 401 and not instances
