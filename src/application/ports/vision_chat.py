"""Describe ephemeral normalized-image and unverified owner-associated vision replies without file access or action authority."""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from src.application.ports.inference import CompletionResult


@dataclass(frozen=True, slots=True, repr=False)
class NormalizedImage:
    """Bind one isolated normalized RGB PNG to exact source bytes and rendered pixel dimensions."""

    source_sha256: str
    png: bytes
    png_sha256: str
    width: int
    height: int
    processor: str


@dataclass(frozen=True, slots=True, repr=False)
class ImageChatReply:
    """Return ephemeral image-question provenance and unverified text without a reusable proof or persisted image."""

    owner_id: UUID
    question_sha256: str
    source_sha256: str
    normalized_sha256: str
    width: int
    height: int
    processor: str
    model_id: str
    answer: str
    uncertainties: tuple[str, ...]
    received_at: datetime
    model_attempts: int = 1
    native_attempts: int = 1
    content_trust: str = "untrusted"
    semantic_validation: bool = False
    confidence: None = None
    persisted: bool = False


class VisionChatPort(Protocol):
    """Accept only one already validated normalized image and explicit question for fixed local CORE inference."""

    async def complete_image(
        self, *, image: NormalizedImage, question: str
    ) -> CompletionResult:
        """Return one bounded fixed-model completion without caller-selectable tools, model or remote media."""
        ...
