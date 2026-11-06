"""Compose opt-in authenticated voice into the original main API while leaving default entry points intact."""

import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.responses import JSONResponse

from apps.api.voice_admission import ManagedGPUCalls
from apps.api.voice_identity import IdentityDenied, VoiceIdentity
from apps.api.voice_routes import HEADERS, routes
from src.application.services.gpu_admission import AdmissionBusy, GPUAdmission
from src.application.services.voice_pipeline import VoiceError
from src.application.services.voice_session import VoiceSession
from src.application.services.web_fetch_tasks import finish_owned, spawn_owned

LOGGER = logging.getLogger(__name__)


def compose(base, *, auth_file, runtime_factory, finalizer=None):
    """Build an additive application using original main API routes and an injected trusted runtime."""
    identities, admission = VoiceIdentity(auth_file), GPUAdmission()
    service = VoiceSession(runtime_factory, admission, identities.valid)
    guards = ManagedGPUCalls(admission)

    @asynccontextmanager
    async def lifespan(app):
        """Initialize voice outside database requirements and join it before legacy shutdown resources."""
        watcher = None
        guards.start()
        try:
            async with base.router.lifespan_context(app):
                watcher = spawn_owned(service.watch())
                try:
                    yield
                finally:
                    watcher.cancel()
                    await asyncio.gather(watcher, return_exceptions=True)
                    await finish_owned(spawn_owned(service.close()))
                    identities.clear()
        finally:
            if (
                service.runtime is None
                and not admission.calls
                and not admission.poisoned
            ):
                guards.close()
                if finalizer is not None:
                    finalizer()
            else:
                admission.quarantine()
                LOGGER.error("voice_shutdown_quarantined")

    app = FastAPI(
        title=base.title,
        version=base.version,
        description=base.description,
        docs_url=base.docs_url,
        redoc_url=base.redoc_url,
        lifespan=lifespan,
    )
    legacy = APIRouter(
        routes=[
            route
            for route in base.router.routes
            if getattr(route, "name", None)
            not in {"openapi", "swagger_ui_html", "swagger_ui_redirect", "redoc_html"}
        ]
    )
    app.include_router(legacy)
    app.dependency_overrides.update(base.dependency_overrides)
    app.exception_handlers.update(base.exception_handlers)
    app.state.voice_service, app.state.voice_identities = service, identities
    app.include_router(routes(service, identities))

    @app.exception_handler(VoiceError)
    async def voice_failure(request, error):
        """Expose only finite voice failures without user audio, content or native diagnostics."""
        return JSONResponse(
            {"code": error.code},
            status_code=422 if error.code in {"invalid_input", "no_speech"} else 409,
            headers=HEADERS,
        )

    @app.exception_handler(IdentityDenied)
    async def identity_failure(request, error):
        """Deny unauthenticated browser voice access without disclosing principal-store state."""
        LOGGER.warning("voice_identity_denied")
        return JSONResponse(
            {"code": "authentication_required"}, status_code=401, headers=HEADERS
        )

    @app.exception_handler(AdmissionBusy)
    async def busy_failure(request, error):
        """Return a bounded nonqueued GPU-busy result while health/static routes remain available."""
        return JSONResponse({"code": "gpu_busy"}, status_code=409, headers=HEADERS)

    LOGGER.info("main_voice_composed default_model_change=False")
    return app


def create_app():
    """Return the unchanged original main app unless the owner explicitly enables evaluated voice composition."""
    from apps.api.main import app as base

    value = os.environ.get("ASSISTANT_VOICE_ENABLED", "0")
    if value == "0":
        LOGGER.info("main_voice_disabled")
        return base
    if value != "1" or os.environ.get("WEB_CONCURRENCY", "1") != "1":
        raise RuntimeError("voice_requires_explicit_single_worker")
    auth_file = os.environ.get("ASSISTANT_AUTH_FILE")
    manifest = os.environ.get("ASSISTANT_VOICE_MANIFEST")
    purpose = os.environ.get("ASSISTANT_VOICE_PURPOSE")
    if not auth_file or not manifest or purpose != "integration_evaluation":
        raise RuntimeError("voice_evaluation_configuration_required")
    from src.infrastructure.voice.native import NativeRuntime
    from src.infrastructure.voice.manifest import VoiceManifest

    settings = VoiceManifest.load(manifest)

    def factory(owner, admission, lease):
        """Bind exactly the operator-approved evaluation manifest to one authenticated voice group."""
        return NativeRuntime(settings, owner, admission, lease)

    return compose(
        base, auth_file=auth_file, runtime_factory=factory, finalizer=settings.close
    )
