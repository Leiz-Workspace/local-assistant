from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID


@dataclass(slots=True)
class Conversation:
    id: UUID
    title: str | None
    profile: str
    preset_default: str
    status: str
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
