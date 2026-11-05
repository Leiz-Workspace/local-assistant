"""Test loopback session security, finite explicit admission and joined cancellation without models or microphones."""

import asyncio
import base64
import logging
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio

from apps.voice_trial.audio import encode_wave
from apps.voice_trial.main import create_app
from src.application.services.voice_pipeline import VoiceError

ORIGIN = "http://127.0.0.1:8092"
HEADERS = {"Origin": ORIGIN, "X-Voice-Submit": "1"}
WAVE = encode_wave(b"\0\0" * 16000)


class Runtime:
    """Represent finite authored model behavior while exposing observable native-lifetime disposal."""

    def __init__(self):
        """Initialize independent startup, active-call and shutdown observations."""
        self.started = False
        self.closed = False
        self.entered = asyncio.Event()
        self.wait = None
        self.failure = None
        self.expired = False

    async def start(self):
        """Expose startup without any model, device or external service access."""
        self.started = True

    async def ask(self, raw, identity):
        """Return an authored full result or wait for cancellation/failure with no native work."""
        self.entered.set()
        if self.wait:
            await self.wait.wait()
        if self.failure:
            raise VoiceError(self.failure)
        return dict(
            transcript="private-transcript",
            answer="private-answer",
            audio_base64=base64.b64encode(WAVE).decode(),
            buffered_seconds=0.1,
            stages={},
        )

    def health(self):
        """Expose an independently simulated idle expiry without a real resource monitor."""
        if self.expired:
            raise VoiceError("closed")

    async def close(self):
        """Record completed disposal for cancellation, failure, expiry and service shutdown assertions."""
        self.closed = True


@pytest_asyncio.fixture
async def surface():
    """Own a finite fake-runtime ASGI surface with a genuine loopback cookie and joined lifespan cleanup."""
    runtimes = []

    def factory():
        """Track every explicitly requested runtime without creating it at page load."""
        value = Runtime()
        runtimes.append(value)
        return value

    app = create_app(factory)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url=ORIGIN
        ) as client:
            await client.get("/")
            yield app, client, runtimes


async def ready(app, client):
    """Explicitly prepare and await genuine controller readiness with no inference calls."""
    response = await client.post("/api/prepare", headers=HEADERS)
    assert response.status_code == 202
    while app.state.controller.preparation:
        await asyncio.sleep(0)
    assert app.state.controller.state == "ready"


def turn_headers(operation=None):
    """Build one canonical submission capability without model/profile/path selection fields."""
    return {
        **HEADERS,
        "Content-Type": "audio/wav",
        "X-Voice-ID": operation or str(uuid4()),
    }


@pytest.mark.asyncio
async def test_opening_page_only_sets_private_session_without_loading(surface):
    """Keep static capture resources accessible and require explicit preparation before native work."""
    app, client, runtimes = surface
    page = await client.get("/")
    assert page.status_code == 200 and not runtimes
    assert (
        "HttpOnly" in page.headers["set-cookie"]
        and "SameSite=strict" in page.headers["set-cookie"]
    )
    assert (
        "no-store" in page.headers["cache-control"]
        and "frame-ancestors 'none'" in page.headers["content-security-policy"]
    )
    for asset in ("/page.mjs", "/trial.mjs", "/recorder.mjs", "/capture-worklet.js"):
        assert (await client.get(asset)).status_code == 200
    assert (await client.get("/api/status")).json()["state"] == "idle"
    assert (await client.get("/unknown-file")).status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "headers",
    [
        {"Host": "attacker.example"},
        {"X-Forwarded-For": "127.0.0.1"},
        {"Origin": "http://attacker.example"},
        {"Sec-Fetch-Site": "cross-site"},
    ],
)
async def test_rebinding_proxy_cross_origin_and_subresource_requests_are_denied(
    surface, headers
):
    """Reject network and browser-origin authority changes without starting a runtime."""
    _, client, runtimes = surface
    assert (await client.get("/api/status", headers=headers)).status_code == 403
    assert not runtimes


@pytest.mark.asyncio
async def test_top_navigation_can_open_link_but_unauthenticated_API_cannot(surface):
    """Allow a real clicked public page while keeping API access behind its own HttpOnly cookie."""
    app, client, _ = surface
    assert (
        await client.get(
            "/",
            headers={
                "Sec-Fetch-Site": "cross-site",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Dest": "document",
            },
        )
    ).status_code == 200
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url=ORIGIN
    ) as stranger:
        assert (await stranger.get("/api/status")).status_code == 403
    assert (await client.get("/api/status?token=forbidden")).status_code == 403


@pytest.mark.asyncio
async def test_post_requires_origin_custom_header_and_empty_prepare_body(surface):
    """Prevent implicit cross-site model startup and body-based preparation options."""
    _, client, runtimes = surface
    assert (await client.post("/api/prepare")).status_code == 403
    assert (
        await client.post("/api/prepare", headers={"Origin": ORIGIN})
    ).status_code == 403
    assert (
        await client.post("/api/prepare", headers=HEADERS, content=b"x")
    ).status_code == 422
    assert not runtimes


@pytest.mark.asyncio
async def test_one_explicit_turn_returns_complete_current_result_and_redacted_logs(
    surface, caplog
):
    """Preserve complete output with no prompt/answer logging or model creation on reload."""
    app, client, runtimes = surface
    caplog.set_level(logging.INFO)
    await ready(app, client)
    operation = str(uuid4())
    response = await client.post(
        "/api/turn", content=WAVE, headers=turn_headers(operation)
    )
    assert response.status_code == 200 and response.json()["id"] == operation
    assert response.json()["answer"] == "private-answer"
    assert base64.b64decode(response.json()["audio_base64"]) == WAVE
    assert (
        "private-answer" not in caplog.text and "private-transcript" not in caplog.text
    )
    assert app.state.controller.attempts == 1 and len(runtimes) == 1
    assert (
        await client.post("/api/turn", content=WAVE, headers=turn_headers(operation))
    ).status_code == 409
    assert app.state.controller.attempts == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", ["format", "body", "size", "identity"])
async def test_invalid_submission_never_reaches_runtime(surface, bad):
    """Reject alternate codecs, invalid WAV, oversized input and caller-chosen paths before any model call."""
    app, client, runtimes = surface
    await ready(app, client)
    headers = turn_headers()
    raw = WAVE
    if bad == "format":
        headers["Content-Type"] = "application/json"
    elif bad == "body":
        raw = b"not-wave"
    elif bad == "size":
        raw = b"x" * 640045
    else:
        headers["X-Voice-ID"] = "../../secret"
    assert (
        await client.post("/api/turn", content=raw, headers=headers)
    ).status_code == 422
    assert not runtimes[0].entered.is_set()


@pytest.mark.asyncio
async def test_busy_admission_and_cancel_join_before_new_prepare(surface):
    """Hold one active slot, reject queued turns and return no delayed audio after matched cancellation."""
    app, client, runtimes = surface
    await ready(app, client)
    runtimes[0].wait = asyncio.Event()
    operation = str(uuid4())
    actor = asyncio.create_task(
        client.post("/api/turn", content=WAVE, headers=turn_headers(operation))
    )
    await asyncio.wait_for(runtimes[0].entered.wait(), 1)
    assert (
        await client.post("/api/turn", content=WAVE, headers=turn_headers())
    ).status_code == 409
    assert app.state.controller.attempts == 1
    cancel = await client.post("/api/cancel", headers=HEADERS, json={"id": operation})
    assert cancel.status_code == 200
    response = await actor
    assert response.status_code == 409 and response.json() == {"code": "cancelled"}
    assert runtimes[0].closed and app.state.controller.state == "idle"


@pytest.mark.asyncio
async def test_early_cancel_blocks_delayed_submission_and_wrong_cancel_leaves_other_turn(
    surface,
):
    """Remember bounded cancellation tombstones rather than executing a late body or cancelling a different owner turn."""
    app, client, runtimes = surface
    await ready(app, client)
    operation = str(uuid4())
    await client.post("/api/cancel", headers=HEADERS, json={"id": operation})
    assert (
        await client.post("/api/turn", content=WAVE, headers=turn_headers(operation))
    ).status_code == 409
    assert app.state.controller.attempts == 0 and not runtimes[0].closed


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure,retired", [("no_speech", False), ("dependency_failed", True)]
)
async def test_silence_is_distinct_from_runtime_failure_and_no_automatic_reload(
    surface, failure, retired
):
    """Keep a proper no-speech refusal reusable but close a failed native lane without retries."""
    app, client, runtimes = surface
    await ready(app, client)
    runtimes[0].failure = failure
    response = await client.post("/api/turn", content=WAVE, headers=turn_headers())
    assert response.json()["code"] == failure and runtimes[0].closed is retired
    assert len(runtimes) == 1


@pytest.mark.asyncio
async def test_idle_expiry_releases_group_and_finite_preparation_budget(surface):
    """Sample idle health and require a new explicit Prepare within the three-lifetime cap."""
    app, client, runtimes = surface
    await ready(app, client)
    runtimes[0].expired = True
    for _ in range(30):
        if runtimes[0].closed:
            break
        await asyncio.sleep(0.05)
    assert runtimes[0].closed
    for _ in range(2):
        await ready(app, client)
        await client.post("/api/release", headers=HEADERS)
    assert (await client.post("/api/prepare", headers=HEADERS)).status_code == 409
    assert len(runtimes) == 3


@pytest.mark.asyncio
async def test_submit_disconnect_joins_actor_and_retires_group(surface):
    """Cancel a true disconnected request without returning audio or retaining a running fake native operation."""
    app, client, runtimes = surface
    await ready(app, client)
    runtimes[0].wait = asyncio.Event()

    class Request:
        """Expose one complete uploaded WAV followed by an actual disconnect signal."""

        async def stream(self):
            """Yield exactly the canonical bounded input body."""
            yield WAVE

        async def is_disconnected(self):
            """Report the disconnected socket while native work is still active."""
            return True

    with pytest.raises(asyncio.CancelledError):
        await app.state.controller.submit(Request(), str(uuid4()))
    assert runtimes[0].closed and app.state.controller.active is None


@pytest.mark.asyncio
async def test_release_joins_pending_prepare_without_automatic_restart(surface):
    """Retire a partially loaded group when the owner cancels preparation or leaves the page."""
    app, client, runtimes = surface
    entered = asyncio.Event()

    class Loading(Runtime):
        """Represent a model load awaiting bounded external completion."""

        async def start(self):
            """Pause startup until explicit release cancels and joins it."""
            entered.set()
            await asyncio.Event().wait()

    app.state.controller.factory = Loading
    await client.post("/api/prepare", headers=HEADERS)
    await asyncio.wait_for(entered.wait(), 1)
    runtime = app.state.controller.runtime
    assert (await client.post("/api/release", headers=HEADERS)).status_code == 200
    assert runtime.closed and app.state.controller.preparation is None
    assert app.state.controller.state == "idle"


@pytest.mark.asyncio
async def test_total_attempt_budget_never_refunds_failed_turns(surface):
    """Refuse new work after24 admitted requests without reloading the runtime or resetting quotas."""
    app, client, runtimes = surface
    await ready(app, client)
    app.state.controller.attempts = 24
    response = await client.post("/api/turn", content=WAVE, headers=turn_headers())
    assert response.status_code == 409 and not runtimes[0].entered.is_set()
