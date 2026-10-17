from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID


@dataclass(slots=True)
class InferenceRun:
    id: UUID
    conversation_id: UUID
    user_message_id: UUID
    assistant_message_id: UUID | None

    preset_requested: str
    preset_selected: str
    model_id: str
    status: str

    started_at: datetime
    completed_at: datetime | None = None

    input_tokens: int | None = None
    output_tokens: int | None = None
    reasoning_tokens: int | None = None
    latency_ms: int | None = None

    finish_reason: str | None = None
    error_code: str | None = None

    metadata: dict[str, Any] = field(default_factory=dict)
