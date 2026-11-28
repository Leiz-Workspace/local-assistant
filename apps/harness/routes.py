"""Expose authenticated local run, context and exact-hash skill management contracts."""

import asyncio
import contextlib
import hashlib
import json
import logging
from typing import Literal
from uuid import UUID, uuid4

import anyio
import httpx
from fastapi import APIRouter, Request, Response, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, model_validator
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute

from apps.api.core.conversation_auth import authenticate_principal
from apps.api.core.model_config import ModelConfigError, get_model_catalog
from apps.api.services.llama_gateway import GatewayError
from apps.harness.inference import IncompleteCompletion
from apps.api.routes.conversations import require_local_client
from apps.api.routes.chat import PRIVATE_HEADERS
from apps.harness.service import HarnessError
from src.application.services.skill_contract import SkillError
from src.application.services.context_reduction import ContextError, HistoryPolicy
from src.application.services.special_literals import (
    SpecialLiteralsStale,
    require_current_binding,
)
from src.application.ports.inference import InferenceFailure
from src.infrastructure.summary_cache import BoundSummaryCache
from src.application.services.review_output_contract import (
    NAME as REVIEW_NAME,
    validate_target,
    QUOTE_FIRST_NAME,
)
from src.application.ports.media_generation import GenerationRequest
from src.application.services.workspace_tool_contracts import (
    TOOL_REGISTRY,
    ToolEnvelope,
)

LOGGER = logging.getLogger(__name__)
REQUEST_LIMIT = 262144
# Attachments are measured as the evidence bytes the composer receives, the same unit as its
# 64 KiB per-source cap, so nothing the API accepts is later dropped as source_byte_limit.
ATTACHMENT_BYTES = 65536
ATTACHMENTS_TOTAL_BYTES = 196608
# Routes whose bodies carry conversation text answer validation failures with a
# finite code instead of FastAPI's default detail, which echoes the input.
PRIVATE_VALIDATION = {
    "/api/v1/harness/chat": "invalid_context_request",
    "/api/v1/harness/chat/stream": "invalid_context_request",
}


def json_media(request):
    """Report whether the declared request media type is JSON."""
    media = request.headers.get("content-type", "").split(";", 1)[0]
    return media.strip().lower() == "application/json"


class HarnessRoute(APIRoute):
    """Authenticate, bound and audit product API requests without logging query strings, payloads or credentials."""

    def guarded_handler(self):
        """Wrap the endpoint with the direct-local principal policy and a bounded JSON body replay."""
        original = super().get_route_handler()

        async def guarded(request: Request):
            """Reject non-local, unauthenticated, oversized or non-JSON bodies; bodiless requests need no media type."""
            # Browser sessions were already checked for loopback, same-origin and CSRF.
            if getattr(request.state, "ui_owner", None) is None:
                await require_local_client(request)
                await authenticate_principal(request)
            chunks, length = [], 0
            async for chunk in request.stream():
                length += len(chunk)
                if length > REQUEST_LIMIT:
                    LOGGER.warning("product_api_request_bytes_rejected")
                    raise HTTPException(
                        413, detail=dict(code="request_limit"), headers=PRIVATE_HEADERS
                    )
                chunks.append(chunk)
            body = b"".join(chunks)
            if body and not json_media(request):
                LOGGER.warning("product_api_media_rejected")
                raise HTTPException(
                    415, detail=dict(code="json_required"), headers=PRIVATE_HEADERS
                )

            async def replay():
                """Replay only the bounded authenticated complete body to schema validation."""
                return dict(type="http.request", body=body, more_body=False)

            try:
                response = await original(Request(request.scope, receive=replay))
            except RequestValidationError as error:
                code = PRIVATE_VALIDATION.get(self.path)
                if code is None:
                    raise
                if any(
                    "attachment_too_large" in str(item.get("msg", ""))
                    for item in error.errors()
                ):
                    code = "attachment_too_large"
                LOGGER.warning("product_api_validation_failed code=%s", code)
                raise ContextError(code) from None
            response.headers.update(PRIVATE_HEADERS)
            return response

        return guarded

    def get_route_handler(self):
        """Wrap the authentication/body guard with a host-generated request identifier."""
        guarded = self.guarded_handler()

        async def audited(request: Request):
            """Log every completed or rejected product operation while preserving its original exception."""
            identifier, status_code = str(uuid4()), 500
            try:
                response = await guarded(request)
                status_code = response.status_code
                response.headers["X-Request-ID"] = identifier
                return response
            except HTTPException as error:
                status_code = error.status_code
                raise
            except (HarnessError, ContextError) as error:
                status_code = error.status
                raise
            except SpecialLiteralsStale:
                status_code = 503
                raise
            except SkillError as error:
                status_code = skill_error_reply(error)[1]
                raise
            except RequestValidationError:
                status_code = 422
                raise
            finally:
                LOGGER.info(
                    "product_api_request request_id=%s method=%s route=%s status=%d",
                    identifier,
                    request.method,
                    self.path,
                    status_code,
                )

        return audited


router = APIRouter(prefix="/api/v1/harness", route_class=HarnessRoute)


class Contract(BaseModel):
    """Reject unknown fields instead of silently accepting host-authority overrides."""

    model_config = ConfigDict(extra="forbid")


class RunInput(Contract):
    """Accept one bounded CORE task and optional existing read-only evidence calls."""

    workspace_id: UUID
    task: str = Field(min_length=1, max_length=24000)
    skill: UUID | None = None
    preset: Literal["fast", "balanced", "deep", "auto", "unlimited"] = "fast"
    max_tokens: int | None = Field(default=None, ge=512, le=32768)
    output_contract: Literal[
        "text", "source-value-quote-v1", "review-line-quote-v1", "review-quote-line-v1"
    ] = "text"
    review_target: str | None = Field(default=None, min_length=1, max_length=4096)
    tools: list[ToolEnvelope] = Field(default_factory=list, max_length=4)
    context_strategy: Literal["evidence-first", "recent-turns", "strict"] = (
        "evidence-first"
    )

    @model_validator(mode="after")
    def validate_tools(self):
        """Require host-registered read-only schemas before admitting any background operation."""
        if not self.task.strip():
            raise ValueError("empty_task")
        validate_target(self.output_contract, self.review_target)
        for tool in self.tools:
            if tool.name not in TOOL_REGISTRY:
                raise ValueError("readonly_tools_only")
            TOOL_REGISTRY[tool.name][1].model_validate(tool.arguments)
        if self.output_contract != "text" and (
            not self.tools or any(tool.name != "workspace.read" for tool in self.tools)
        ):
            raise ValueError("source_contract_requires_read_evidence")
        if self.output_contract in {REVIEW_NAME, QUOTE_FIRST_NAME} and not any(
            tool.arguments.get("path") == self.review_target for tool in self.tools
        ):
            raise ValueError("review_target_requires_explicit_read")
        return self


class ReviewInput(Contract):
    """Carry unchanged manifest bytes as UTF-8 text without accepting trust flags."""

    workspace_id: UUID
    manifest: str = Field(min_length=1, max_length=32768)


class InstallInput(Contract):
    """Require an exact owner-reviewed digest and an existing unconsumed review identifier."""

    workspace_id: UUID
    review_id: UUID
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class ChatMessage(Contract):
    """Accept one text turn in the closed role set the shared context composer admits."""

    role: Literal["system", "user", "assistant"]
    content: str = Field(min_length=1, max_length=REQUEST_LIMIT)

    @model_validator(mode="after")
    def require_text(self):
        """Reject whitespace-only turns, which the context composer refuses."""
        if not self.content.strip():
            raise ValueError("empty_message")
        return self


class ChatAttachment(Contract):
    """Carry one user-supplied text file that the composer treats as untrusted evidence."""

    name: str = Field(min_length=1, max_length=256)
    content: str = Field(min_length=1, max_length=65536)


class ChatSkill(Contract):
    """Name one exact owner-reviewed skill installation to apply to this chat turn."""

    installation_id: UUID
    workspace_id: UUID


class ChatInput(Contract):
    """Accept bounded CLI conversation turns using the shared context composer."""

    messages: list[ChatMessage] = Field(min_length=1, max_length=256)
    preset: Literal["fast", "balanced", "deep", "auto", "unlimited"] = "fast"
    context_strategy: Literal["evidence-first", "recent-turns", "strict"] = (
        "evidence-first"
    )
    history_policy: HistoryPolicy | None = None
    attachments: list[ChatAttachment] = Field(default_factory=list, max_length=4)
    skill: ChatSkill | None = None

    @model_validator(mode="after")
    def bound_attachments(self):
        """Refuse attachments the composer would otherwise drop silently for size."""
        sizes = [len(attachment_evidence(item)) for item in self.attachments]
        if any(size > ATTACHMENT_BYTES for size in sizes) or (
            sum(sizes) > ATTACHMENTS_TOTAL_BYTES
        ):
            raise ValueError("attachment_too_large")
        return self


async def owner_service(request):
    """Resolve the authenticated owner and the optional product coordinator."""
    owner = getattr(request.state, "ui_owner", None)
    if owner is None:
        owner = await authenticate_principal(request)
    service = getattr(request.app.state, "product_harness", None)
    if service is None:
        raise HarnessError("harness_unavailable", 503)
    return owner, service


@router.get("/status")
async def status(request: Request):
    """Publish actual implemented capabilities without claiming model or quality readiness."""
    owner, service = await owner_service(request)
    LOGGER.info("product_status_read owner_id=%s", owner)
    generation = request.app.state.generation_jobs
    return dict(
        schema_version=1,
        product="Aevra",
        profile="core",
        persistence="metadata-only" if service.history is not None else "process-local",
        history_healthy=not service.history_broken,
        raw_results_persisted=False,
        skills_persistent=False,
        readonly_runs=True,
        skills=True,
        context="whole-turn-evidence-v1",
        context_policies=["sliding-window", "extractive-compact", "token-budget"],
        context_archive="owner-private-process-memory-1800s",
        context_working_state="opt-in-user-marked-lines-client-carried",
        context_evicted_summary="opt-in-experimental-v2-measured-gain",
        workspace_tools=service.workspace is not None,
        image_generation="image" in generation.backends,
        video_generation="video" in generation.backends,
        autonomous_tool_selection=False,
        durable_resume=False,
    )


@router.post("/runs")
async def start_run(body: RunInput, request: Request):
    """Start one admitted readonly task under the current bearer principal."""
    owner, service = await owner_service(request)
    return service.start(owner, body)


def skill_error_reply(error):
    """Return the public code and status for a skill registry rejection; a missing or expired review asks for a new one."""
    if error.code in {"review_required", "review_expired"}:
        return "review_required", 404
    return "skill_operation_denied", 409


def attachment_evidence(attachment):
    """Encode one attachment as raw evidence bytes; the composer wraps and neutralizes it as untrusted."""
    return f"Attached file: {attachment.name}\n\n{attachment.content}".encode("utf-8")


def chat_options(body, owner, service):
    """Build composer options shared by /chat and /chat/stream, resolving an exact skill grant."""
    options = dict(preset=body.preset, context_strategy=body.context_strategy)
    if body.history_policy is not None:

        def archive(raw):
            """Bind all raw history writes to the authenticated caller, never a client-supplied owner."""
            return service.context_archive.put(owner, raw)

        def recall(identifier):
            """Resolve explicit cache handles under the same authenticated principal."""
            return service.context_archive.get(owner, identifier)

        options.update(
            history_policy=body.history_policy, archive=archive, recall=recall
        )
        if body.history_policy.evicted_summary:
            options.update(
                summary_deadline=asyncio.get_running_loop().time() + 120,
                summary_cache=BoundSummaryCache(service.summary_cache, owner),
            )
    if body.attachments:
        options["evidence"] = [attachment_evidence(item) for item in body.attachments]
    installed = None
    if body.skill is not None:
        installed = service.installed(
            owner, body.skill.workspace_id, body.skill.installation_id
        )
        options["skill"] = installed.manifest
    return options, installed


def authorize_skill(service, owner, body, installed):
    """Re-check the exact grant around inference, as runs do, so a revoked skill fails closed."""
    if installed is not None:
        service.skills.authorize(
            owner,
            body.skill.workspace_id,
            installed,
            installed.manifest.permissions[0],
        )


@router.post("/chat")
async def chat(body: ChatInput, request: Request):
    """Complete CLI chat under the same CORE admission and context policy as specialist runs."""
    owner, service = await owner_service(request)
    require_current_binding()
    options, installed = chat_options(body, owner, service)
    try:
        async with asyncio.timeout(120):
            async with service.admission:
                authorize_skill(service, owner, body, installed)
                result, context = await service.inference.complete(
                    [message.model_dump() for message in body.messages],
                    **options,
                )
                authorize_skill(service, owner, body, installed)
    except (ContextError, SpecialLiteralsStale, SkillError):
        raise
    except InferenceFailure as error:
        if body.history_policy is not None:
            raise ContextError(error.code, error.status_code) from None
        raise HarnessError("inference_unavailable", 502) from None
    except ValueError:
        if body.history_policy is not None:
            raise ContextError("invalid_context_request") from None
        raise HarnessError("inference_unavailable", 502) from None
    except Exception:
        raise HarnessError("inference_unavailable", 502) from None
    LOGGER.info(
        "product_cli_chat_completed owner_id=%s attachments=%d skill=%s",
        owner,
        len(body.attachments),
        installed is not None,
    )
    return dict(result=result, context=context)


ADMISSION_SECONDS = 120
STREAM_MESSAGES = {
    "inference_unavailable": "Local inference could not complete.",
    "context_overflow": "The input does not fit the model context.",
    "incomplete_completion": "The answer stopped before it was complete.",
    "special_literals_stale": "Local inference is refused for this model.",
    "stream_limit": "The answer exceeded the stream size limit.",
    "skill_operation_denied": "The skill is no longer authorized.",
    "inference_busy": "Another request is still using the local model.",
    "stream_timeout": "The answer took too long and was stopped.",
}


class ClosingStreamingResponse(StreamingResponse):
    """Close the body iterator however the response ends, so admission and upstream never wait for GC."""

    async def __call__(self, scope, receive, send):
        """Run the normal response, then close the generator even after a cancelled send."""
        try:
            await super().__call__(scope, receive, send)
        finally:
            with anyio.CancelScope(shield=True):
                await self.body_iterator.aclose()


def stream_error_code(error, policy, started=False):
    """Map a stream failure to the same finite codes /chat uses, plus the stream-only ones.

    Only failures before the first stream frame (composition and validation) can be the
    client's history-policy fault; later faults come from CORE or the transport.
    """
    if isinstance(error, ContextError):
        return error.code
    if isinstance(error, SpecialLiteralsStale):
        return "special_literals_stale"
    if isinstance(error, SkillError):
        return "skill_operation_denied"
    if isinstance(error, IncompleteCompletion):
        return "incomplete_completion"
    if isinstance(error, GatewayError):
        reason = str(error)
        if reason in {"stream_limit", "stream_timeout"}:
            return reason
        if reason == "incomplete_stream":
            return "incomplete_completion"
        return "inference_unavailable"
    if isinstance(error, TimeoutError):
        return "stream_timeout"
    if isinstance(error, InferenceFailure):
        if policy:
            return error.code
        return (
            "context_overflow"
            if error.code == "context_overflow"
            else "inference_unavailable"
        )
    if isinstance(error, ValueError) and str(error) == "strict_context_would_trim":
        return "strict_context_would_trim"
    # A non-JSON answer from CORE is a CORE fault, never the client's history policy.
    if isinstance(error, json.JSONDecodeError):
        return "inference_unavailable"
    if isinstance(error, ValueError) and policy and not started:
        return "invalid_context_request"
    return "inference_unavailable"


@router.post("/chat/stream")
async def chat_stream(body: ChatInput, request: Request):
    """Stream one chat turn with the /chat options; [DONE] only after a verified complete answer."""
    owner, service = await owner_service(request)
    require_current_binding()
    options, installed = chat_options(body, owner, service)
    messages = [message.model_dump() for message in body.messages]
    policy = body.history_policy is not None

    async def events():
        """Hold admission for the whole stream; a disconnect cancels and releases it."""
        acquired = started = False
        try:
            try:
                async with asyncio.timeout(ADMISSION_SECONDS):
                    await service.admission.acquire()
            except TimeoutError:
                code = "inference_busy"
                LOGGER.warning("product_chat_stream_failed code=%s", code)
                yield error_frame(code)
                return
            acquired = True
            authorize_skill(service, owner, body, installed)
            async with contextlib.aclosing(
                service.inference.stream(messages, product=True, **options)
            ) as chunks:
                async for chunk in chunks:
                    started = True
                    if chunk == b"data: [DONE]\n\n":
                        authorize_skill(service, owner, body, installed)
                        LOGGER.info(
                            "product_chat_stream_completed owner_id=%s attachments=%d skill=%s",
                            owner,
                            len(body.attachments),
                            installed is not None,
                        )
                    yield chunk
        except (asyncio.CancelledError, GeneratorExit):
            LOGGER.info("product_chat_stream_cancelled owner_id=%s", owner)
            raise
        except Exception as error:
            code = stream_error_code(error, policy, started)
            LOGGER.warning("product_chat_stream_failed code=%s", code)
            yield error_frame(code)
        finally:
            if acquired:
                service.admission.release()

    return ClosingStreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "private, no-store", "X-Accel-Buffering": "no"},
    )


def error_frame(code):
    """Encode the closed error event; a failed stream never sends [DONE] after it."""
    message = STREAM_MESSAGES.get(code, "The request could not complete.")
    return (
        "event: error\ndata: " + json.dumps({"code": code, "message": message}) + "\n\n"
    ).encode()


MODELS_PROBE_SECONDS = 1.5
MODELS_RESPONSE_BYTES = 65536
MODEL_REASONS = {
    "core": "Approved CORE profile used by Aevra.",
    "other": "Switching profiles restarts the shared CORE and needs owner approval.",
}


@router.get("/models")
async def models(request: Request):
    """List configured profiles and which alias CORE reports, without loading or switching models."""
    owner, service = await owner_service(request)
    try:
        catalog = get_model_catalog()
    except ModelConfigError:
        raise HarnessError("model_config_unavailable", 503) from None
    core = catalog[0]
    online, loaded_ids = False, None
    try:
        # One bound for the whole probe: a slow-drip CORE cannot stretch it read by read.
        async with asyncio.timeout(MODELS_PROBE_SECONDS):
            async with httpx.AsyncClient(
                base_url=core["base_url"],
                transport=getattr(service.inference, "transport", None),
                timeout=MODELS_PROBE_SECONDS,
                trust_env=False,
            ) as client:
                async with client.stream("GET", "/v1/models") as response:
                    response.raise_for_status()
                    raw = bytearray()
                    async for part in response.aiter_bytes():
                        raw.extend(part)
                        if len(raw) > MODELS_RESPONSE_BYTES:
                            raise ValueError("models_response_too_large")
        data = json.loads(bytes(raw)).get("data")
        loaded_ids = {
            item["id"]
            for item in (data if isinstance(data, list) else [])
            if isinstance(item, dict) and isinstance(item.get("id"), str)
        }
        online = True
    except (
        httpx.HTTPError,
        ValueError,
        AttributeError,
        TypeError,
        TimeoutError,
        RecursionError,
    ):
        online, loaded_ids = False, None
    rows = [
        dict(
            profile=item["profile"],
            id=item["model_id"],
            status=item["status"],
            selectable=item["profile"] == "core",
            loaded=None if loaded_ids is None else item["model_id"] in loaded_ids,
            online=online,
            reason=MODEL_REASONS["core" if item["profile"] == "core" else "other"],
        )
        for item in catalog
    ]
    LOGGER.info(
        "product_models_read owner_id=%s online=%s core_loaded=%s",
        owner,
        online,
        rows[0]["loaded"],
    )
    return dict(active="core", models=rows)


@router.get("/context/archives")
async def list_context_archives(request: Request):
    """List only the caller's live cache handles, never raw dialogue or another owner's identifiers."""
    owner, service = await owner_service(request)
    from fastapi.responses import JSONResponse

    return JSONResponse(
        service.context_archive.list_owned(owner),
        headers={"Cache-Control": "private, no-store"},
    )


@router.get("/context/archives/{identifier}")
async def recall_context(identifier: UUID, request: Request):
    """Return exact raw history only to its authenticated owner through an explicit no-store read."""
    owner, service = await owner_service(request)
    from fastapi.responses import JSONResponse

    return JSONResponse(
        service.context_archive.get(owner, identifier),
        headers={"Cache-Control": "private, no-store"},
    )


@router.delete("/context/archives/{identifier}")
async def forget_context(identifier: UUID, request: Request):
    """Delete only the owner's ephemeral cache copy without deleting authoritative conversation records."""
    owner, service = await owner_service(request)
    return service.context_archive.remove(owner, identifier)


@router.delete("/context/summaries")
async def purge_summaries(request: Request):
    """Delete only the caller's cached summary outputs from process memory."""
    owner, service = await owner_service(request)
    return dict(purged=service.summary_cache.purge(owner))


@router.get("/runs")
async def list_runs(request: Request):
    """List finite owner-visible runs without returning result bodies."""
    owner, service = await owner_service(request)
    return [
        {
            key: value
            for key, value in service.get(owner, identifier).items()
            if key not in {"result", "context"}
        }
        for identifier, row in service.runs.items()
        if row["owner"] == owner
    ]


@router.get("/runs/{identifier}")
async def get_run(identifier: UUID, request: Request):
    """Return a scoped result, metadata events and context receipt."""
    owner, service = await owner_service(request)
    return service.get(owner, identifier)


@router.post("/runs/{identifier}/cancel")
async def cancel_run(identifier: UUID, request: Request):
    """Join the exact owner run before acknowledging cancellation."""
    owner, service = await owner_service(request)
    return await service.cancel(owner, identifier)


@router.delete("/runs/{identifier}")
async def remove_run(identifier: UUID, request: Request):
    """Release only terminal run metadata and retained result capacity."""
    owner, service = await owner_service(request)
    return service.remove(owner, identifier)


@router.get("/skills")
async def list_skills(request: Request):
    """List this owner's process-local skill installations."""
    owner, service = await owner_service(request)
    return service.list_skills(owner)


@router.post("/skills/reviews")
async def review_skill(body: ReviewInput, request: Request):
    """Create an existing expiring review and return all material needed for explicit inspection."""
    owner, service = await owner_service(request)
    return service.review(owner, body.workspace_id, body.manifest.encode())


@router.post("/skills/installations")
async def install_skill(body: InstallInput, request: Request):
    """Consume one explicit exact-hash installation request without granting side effects."""
    owner, service = await owner_service(request)
    return service.install(owner, body.workspace_id, body.review_id, body.sha256)


@router.delete("/skills/installations/{identifier}")
async def remove_skill(identifier: UUID, workspace_id: UUID, request: Request):
    """Revoke one scoped installation so subsequent calls and in-flight publication fail closed."""
    owner, service = await owner_service(request)
    installed = service.installed(owner, workspace_id, identifier)
    service.skills.uninstall(owner, workspace_id, installed)
    return {"removed": True}


@router.get("/skills/installations/{identifier}")
async def show_skill(identifier: UUID, workspace_id: UUID, request: Request):
    """Show exact owner-reviewed installed instructions and permissions without logging their body."""
    owner, service = await owner_service(request)
    installed = service.installed(owner, workspace_id, identifier)
    manifest = installed.manifest
    LOGGER.info("product_skill_inspected install_id=%s", identifier)
    return dict(
        installation_id=str(identifier),
        id=manifest.identifier,
        version=manifest.version,
        description=manifest.description,
        instructions=manifest.instructions,
        permissions=manifest.permissions,
        sha256=manifest.raw_sha256,
    )


@router.post("/generations")
async def start_generation(body: GenerationRequest, request: Request):
    """Admit generation only when the host explicitly supplied an approved backend."""
    owner, _ = await owner_service(request)
    return request.app.state.generation_jobs.start(owner, body)


@router.get("/generations")
async def list_generations(request: Request):
    """List owned generation metadata without returning prompts or artifact bytes."""
    owner, _ = await owner_service(request)
    jobs = request.app.state.generation_jobs
    return [
        jobs.get(owner, identifier)
        for identifier, row in jobs.jobs.items()
        if row["owner"] == owner
    ]


@router.get("/generations/{identifier}")
async def get_generation(identifier: UUID, request: Request):
    """Return one scoped generation status and provenance receipt."""
    owner, _ = await owner_service(request)
    return request.app.state.generation_jobs.get(owner, identifier)


@router.post("/generations/{identifier}/cancel")
async def cancel_generation(identifier: UUID, request: Request):
    """Cancel and join only the current owner's generation worker."""
    owner, _ = await owner_service(request)
    return await request.app.state.generation_jobs.cancel(owner, identifier)


@router.delete("/generations/{identifier}")
async def remove_generation(identifier: UUID, request: Request):
    """Release terminal owned generation metadata and artifact bytes."""
    owner, _ = await owner_service(request)
    return request.app.state.generation_jobs.remove(owner, identifier)


@router.get("/generations/{identifier}/artifact")
async def generation_artifact(identifier: UUID, request: Request):
    """Download an owned completed artifact without arbitrary paths or public sharing."""
    owner, _ = await owner_service(request)
    result = request.app.state.generation_jobs.artifact(owner, identifier)
    suffix = "png" if result.mime_type == "image/png" else "mp4"
    return Response(
        result.content,
        media_type=result.mime_type,
        headers={
            "Content-Disposition": f'attachment; filename="{identifier}.{suffix}"',
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.post("/ui-pairings")
async def ui_pairing(request: Request):
    """Mint a one-use browser pairing for the bearer principal without exposing the bearer to the UI."""
    owner = await authenticate_principal(request)
    sessions = getattr(request.app.state, "browser_sessions", None)
    if sessions is None:
        raise HarnessError("harness_unavailable", 503)
    digest = hashlib.sha256(
        request.headers["authorization"].partition(" ")[2].encode()
    ).hexdigest()
    return {"code": sessions.pairing(owner, digest), "expires_in_seconds": 60}
