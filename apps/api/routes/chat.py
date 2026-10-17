
"""
Local Assistant - Chat API.

Endpoint:
    POST /api/v1/chat/completions

Model profiles:
    core
    unrestricted

Runtime presets:
    auto
    fast
    balanced (default)
    deep
    unlimited

Auto routes to Fast / Balanced / Deep and records its
decision in the response metadata.

The existing endpoint and model-profile selection remain
unchanged.
"""

from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from apps.api.core.model_config import (
    ModelConfigError,
    get_model_profile,
)
from apps.api.runtime.presets import RuntimePreset
from apps.api.services.llama_gateway import (
    GatewayError,
    LlamaGateway,
)


router = APIRouter(
    prefix="/chat",
    tags=["Chat"],
)


class ChatMessage(BaseModel):
    """One text-only chat message."""

    role: Literal[
        "system",
        "user",
        "assistant",
    ]

    content: str = Field(min_length=1)


class ChatRequest(BaseModel):
    """
    Chat completion request.

    profile:
        Which loaded model should serve the request.

    preset:
        auto | fast | balanced | deep | unlimited

    max_tokens:
        Optional per-request ceiling.
        If absent, the selected preset defines the ceiling.
        If provided, it cannot exceed the preset's limit.

    temperature:
        Generation randomness parameter.
    """

    profile: Literal[
        "core",
        "unrestricted",
    ] = "core"

    messages: list[ChatMessage] = Field(
        min_length=1,
    )

    # Keep Balanced as the default during Auto V1 rollout.
    preset: RuntimePreset = (
        RuntimePreset.BALANCED
    )

    temperature: float = Field(
        default=0.7,
        ge=0,
        le=2,
    )

    max_tokens: int | None = Field(
        default=None,
        ge=1,
        le=32768,
    )


@router.post("/completions")
async def chat_completion(request: ChatRequest):
    """
    Route user chat through the selected model gateway.

    Auto resolution, token counting, model verification and
    response completeness checks belong in the gateway.
    """

    try:
        config = get_model_profile(
            request.profile
        )

        gateway = LlamaGateway(
            base_url=config["base_url"],
            model_id=config["model_id"],
        )

        return await gateway.complete(
            messages=[
                message.model_dump()
                for message in request.messages
            ],
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            preset=request.preset,
        )

    except ModelConfigError as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        ) from exc

    except GatewayError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail=str(exc),
        ) from exc
