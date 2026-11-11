"""Define model-neutral bounded image/video requests and host-owned generation output contracts."""

from dataclasses import dataclass
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator


class GenerationRequest(BaseModel):
    """Validate media job intent without accepting model selection, paths, providers or executable options."""

    model_config = ConfigDict(extra="forbid", strict=True)
    kind: Literal["image", "video"]
    prompt: str = Field(min_length=1, max_length=6000)
    width: int = Field(default=512, ge=256, le=1024, multiple_of=64)
    height: int = Field(default=512, ge=256, le=1024, multiple_of=64)
    seed: int | None = Field(default=None, ge=0, le=4294967295)
    seconds: int | None = Field(default=None, ge=1, le=8)
    fps: int | None = Field(default=None, ge=1, le=24)

    @model_validator(mode="after")
    def validate_duration(self):
        """Require an explicit finite video envelope and reject video controls on image jobs."""
        if not self.prompt.strip():
            raise ValueError("empty_prompt")
        if self.kind == "video" and (self.seconds is None or self.fps is None):
            raise ValueError("video_duration_required")
        if self.kind == "image" and (self.seconds is not None or self.fps is not None):
            raise ValueError("unexpected_video_options")
        return self


@dataclass(frozen=True)
class GeneratedMedia:
    """Carry bounded immutable output bytes and exact host-adapter provenance."""

    content: bytes
    mime_type: str
    model_id: str
    model_revision: str


class GenerationBackend(Protocol):
    """Describe an explicitly approved isolated adapter without supplying or selecting an implementation."""

    async def generate(self, request: GenerationRequest) -> GeneratedMedia:
        """Return one owned artifact or raise, releasing adapter-owned workers on cancellation."""
