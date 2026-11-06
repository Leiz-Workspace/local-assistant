"""Expose bounded authenticated localhost stateless chat while preserving existing model profiles, runtime presets and gateway responses."""

import logging
from typing import Literal

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.routing import APIRoute
from pydantic import BaseModel, Field

from apps.api.core.conversation_auth import authenticate_principal
from apps.api.core.model_config import ModelConfigError, get_model_profile
from apps.api.routes.conversations import require_local_client
from apps.api.runtime.presets import RuntimePreset
from apps.api.services.llama_gateway import GatewayError, LlamaGateway

logger = logging.getLogger(__name__)
PRIVATE_HEADERS = {
    "Cache-Control": "private, no-store",
    "X-Content-Type-Options": "nosniff",
}


class ProtectedStatelessRoute(APIRoute):
    """Authenticate direct local callers before parsing a finite complete stateless request body."""

    def get_route_handler(self):
        """Wrap only this stateless route with unchanged local/principal policy and bounded JSON replay."""
        original = super().get_route_handler()

        async def guarded(request: Request):
            """Reject unauthenticated, browser, proxy, unsupported-media or oversized requests before model work."""
            await require_local_client(request)
            await authenticate_principal(request)
            if (
                request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
                != "application/json"
            ):
                logger.warning("stateless_media_rejected")
                raise HTTPException(
                    415, detail=dict(code="json_required"), headers=PRIVATE_HEADERS
                )
            chunks, length = [], 0
            async for chunk in request.stream():
                length += len(chunk)
                if length > 262144:
                    logger.warning("stateless_request_bytes_rejected")
                    raise HTTPException(
                        413, detail=dict(code="request_limit"), headers=PRIVATE_HEADERS
                    )
                chunks.append(chunk)
            body = b"".join(chunks)

            async def replay():
                """Replay only the bounded authenticated complete body to normal FastAPI schema validation."""
                return dict(type="http.request", body=body, more_body=False)

            response = await original(Request(request.scope, receive=replay))
            response.headers.update(PRIVATE_HEADERS)
            return response

        return guarded


router = APIRouter(prefix="/chat", tags=["Chat"], route_class=ProtectedStatelessRoute)


class ChatMessage(BaseModel):
    """Accept one existing text-only stateless message without adding tool execution capabilities."""

    role: Literal["system", "user", "assistant"]
    content: str = Field(min_length=1)


class ChatRequest(BaseModel):
    """Preserve original profile, preset, temperature and optional output ceiling for authenticated local stateless callers."""

    profile: Literal["core", "unrestricted"] = "core"
    messages: list[ChatMessage] = Field(min_length=1)
    preset: RuntimePreset = RuntimePreset.BALANCED
    temperature: float = Field(default=0.7, ge=0, le=2)
    max_tokens: int | None = Field(default=None, ge=1, le=32768)


@router.post("/completions")
async def chat_completion(request: ChatRequest, response: Response):
    """Delegate the unchanged stateless request to the verified gateway and expose only finite safe failure codes."""
    response.headers.update(PRIVATE_HEADERS)
    try:
        config = get_model_profile(request.profile)
        gateway = LlamaGateway(base_url=config["base_url"], model_id=config["model_id"])
        result = await gateway.complete(
            messages=[message.model_dump() for message in request.messages],
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            preset=request.preset,
        )
        logger.info("stateless_inference_completed profile=%s", request.profile)
        return result
    except ModelConfigError:
        logger.error("stateless_model_configuration_unavailable")
        raise HTTPException(
            503,
            detail=dict(
                code="model_configuration_error",
                message="Model configuration unavailable.",
            ),
            headers=PRIVATE_HEADERS,
        ) from None
    except GatewayError as exc:
        status = (
            exc.status_code
            if type(exc.status_code) is int and 400 <= exc.status_code <= 599
            else 502
        )
        logger.warning("stateless_inference_failed status=%d", status)
        raise HTTPException(
            status,
            detail=dict(
                code="inference_unavailable",
                message="Inference could not be completed.",
            ),
            headers=PRIVATE_HEADERS,
        ) from None
