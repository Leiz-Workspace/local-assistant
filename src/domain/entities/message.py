from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID


@dataclass(slots=True)
class Message:
    id: UUID
    conversation_id: UUID
    sequence: int
    role: str
    content: str
    created_at: datetime
    request_key: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
