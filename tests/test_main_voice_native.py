"""Verify native ownership, borrowed-CORE retirement, scope and physical-resource guards without model calls."""

import asyncio
from types import SimpleNamespace
from uuid import uuid4

import pytest

from src.application.services.gpu_admission import GPUAdmission
from src.application.services.voice_pipeline import VoiceError
from src.infrastructure.voice.core import BorrowedCore
from src.infrastructure.voice.native import NativeRuntime
from src.infrastructure.voice.worker import LIMIT, MODELS, POLICIES, validate_scope


def runtime():
    """Create a model-free owner-bound runtime with an injected exact loopback CORE descriptor."""
    gate = GPUAdmission()
    lease = gate.acquire()
    settings = SimpleNamespace(
        value={
            "core": {"URL": "http://127.0.0.1:18080", "identity": {"pid": 123}},
            "reading_binding": {
                "speaker_sha256": "a" * 64,
                "reference_codes_sha256": "b" * 64,
            },
        }
    )
    return NativeRuntime(settings, uuid4(), gate, lease), gate, lease


@pytest.mark.asyncio
async def test_core_cancel_waits_for_real_response_and_quiescence(monkeypatch):
    """Keep exclusive residency while an already dispatched shared CORE request completes after cancellation."""
    value, gate, lease = runtime()
    started = asyncio.Event()
    release = asyncio.Event()
    observed = []
    monkeypatch.setattr(value.core, "check", lambda: None)

    async def idle():
        """Record the bounded backend idle check after the actual response has completed."""
        observed.append("idle")

    class Gateway:
        """Expose a controllable complete response that must not be aborted with its caller."""

        async def complete(self, **kwargs):
            """Observe explicit current-task authority and remain active until the backend signals completion."""
            assert gate.authorized[asyncio.current_task()] is lease
            started.set()
            await release.wait()
            observed.append("complete")
            return {"ok": True}

    monkeypatch.setattr(value.core, "quiesce", idle)
    task = asyncio.create_task(value.core_complete(Gateway(), []))
    await started.wait()
    task.cancel()
    await asyncio.sleep(0.01)
    assert not task.done() and gate.residency is lease
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert observed == ["complete", "idle"] and not value.uncertain
    gate.release(lease)


@pytest.mark.asyncio
async def test_unknown_core_completion_never_releases_safety_lease(monkeypatch):
    """Refuse cleanup acceptance after transport failure even if a later slot poll could look idle."""
    value, gate, lease = runtime()
    monkeypatch.setattr(value.core, "check", lambda: None)

    class Gateway:
        """Simulate a failed connection after an unknown amount of server work."""

        async def complete(self, **kwargs):
            """Fail the request without asserting that the native backend stopped."""
            raise RuntimeError("neutral_transport_failure")

    with pytest.raises(RuntimeError):
        await value.core_complete(Gateway(), [])
    assert value.uncertain
    with pytest.raises(VoiceError):
        await value.close()
    assert gate.residency is lease and not value.closed


@pytest.mark.parametrize("role", list(MODELS))
def test_only_fixed_approved_roles_can_be_dispatched(role):
    """Admit the retained lane and reject changed precision, budget, model and voice before SDK imports."""
    scope = dict(
        role=role,
        native_authorized=True,
        max_requests=LIMIT,
        model=MODELS[role],
        policy=POLICIES[role],
        cpu_threads=2 if role == "vad" else 8,
        mode="voice",
        scope_sha256="a" * 64,
        voice="Trúc Ly",
        execution_backend="cuda-original-precision",
    )
    assert validate_scope(scope) == scope
    for key, bad in [
        ("max_requests", 25),
        ("max_requests", True),
        ("cpu_threads", 1),
        ("model", "other"),
        ("role", "whisper-small-ct2"),
        ("scope_sha256", "x" * 64),
        ("native_authorized", False),
    ]:
        with pytest.raises(ValueError):
            validate_scope(dict(scope, **{key: bad}))


@pytest.mark.parametrize(
    "URL",
    [
        "https://127.0.0.1:1",
        "http://localhost:1",
        "http://example.com:1",
        "http://127.0.0.1:1/path",
        "http://a:b@127.0.0.1:1",
        "http://127.0.0.1:1?secret=x",
    ],
)
def test_borrowed_core_refuses_unapproved_network_authority(URL):
    """Prevent model/user content from being sent to remote, credentialed or path-overridden endpoints."""
    with pytest.raises(ValueError):
        BorrowedCore({"URL": URL, "identity": {"pid": 123}})
