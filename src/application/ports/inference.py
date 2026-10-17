from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class CompletionResult:
    content: str
    model_id: str
    preset_selected: str
    finish_reason: str

    input_tokens: int | None = None
    output_tokens: int | None = None
    reasoning_tokens: int | None = None
    latency_ms: int | None = None


class InferencePort(Protocol):
    async def complete(
        self,
        *,
        profile: str,
        messages: list[dict[str, str]],
        preset: str,
        temperature: float,
        max_tokens: int | None,
    ) -> CompletionResult:
        ...


class InferenceFailure(Exception):
    def __init__(
        self,
        message: str,
        *,
        code: str = "inference_failed",
        status_code: int = 502,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code
