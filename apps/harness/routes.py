"""Expose authenticated local run, context and exact-hash skill management contracts."""

import asyncio
import logging
from typing import Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Request, Response, HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator
from fastapi.exceptions import RequestValidationError

from apps.api.core.conversation_auth import authenticate_principal
from apps.api.routes.chat import ProtectedStatelessRoute
from apps.harness.service import HarnessError
from src.application.services.skill_contract import SkillError
from src.application.services.context_reduction import ContextError, HistoryPolicy
from src.application.ports.inference import InferenceFailure
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


class HarnessRoute(ProtectedStatelessRoute):
    """Audit finite route templates and status codes without logging query strings, payloads or credentials."""

    def get_route_handler(self):
        """Wrap the unchanged authentication/body guard with a host-generated request identifier."""
        guarded = super().get_route_handler()

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
            except SkillError:
                status_code = 409
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


class ChatInput(Contract):
    """Accept bounded CLI conversation turns using the shared context composer."""

    messages: list[dict[str, str]] = Field(min_length=1, max_length=256)
    preset: Literal["fast", "balanced", "deep", "auto", "unlimited"] = "fast"
    context_strategy: Literal["evidence-first", "recent-turns", "strict"] = (
        "evidence-first"
    )
    history_policy: HistoryPolicy | None = None


async def owner_service(request):
    """Resolve the authenticated owner and the optional product coordinator."""
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


@router.post("/chat")
async def chat(body: ChatInput, request: Request):
    """Complete CLI chat under the same CORE admission and context policy as specialist runs."""
    owner, service = await owner_service(request)
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
    try:
        async with asyncio.timeout(120):
            async with service.admission:
                result, context = await service.inference.complete(
                    body.messages,
                    **options,
                )
    except ContextError:
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
    LOGGER.info("product_cli_chat_completed owner_id=%s", owner)
    return dict(result=result, context=context)


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
