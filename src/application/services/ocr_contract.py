"""Validate page OCR results, normalized pixel provenance and uncalibrated vision uncertainty."""

import base64
import logging
import math
from importlib.metadata import version
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from src.application.services.file_storage_policy import StoragePolicyError

logger = logging.getLogger(__name__)
OCR_VERSION = "page-ocr-v1:pypdf-" + version("pypdf") + ":pillow-" + version("pillow")
MAX_TEXT_BYTES = 64 * 1024
MAX_IMAGE_BYTES = 4 * 1024 * 1024
MAX_REPLY_BYTES = 1024 * 1024
MAX_WORKER_BYTES = 8 * 1024 * 1024


class StrictModel(BaseModel):
    """Reject coercion and unknown fields at parser/model boundaries."""

    model_config = ConfigDict(strict=True, extra="forbid")


class Word(StrictModel):
    """Locate one recognized token in normalized rendered pixels with its raw engine score."""

    text: str = Field(max_length=4096)
    score: float = Field(ge=0, le=100)
    left: int = Field(ge=0)
    top: int = Field(ge=0)
    width: int = Field(ge=0)
    height: int = Field(ge=0)
    block: int = Field(ge=0)
    paragraph: int = Field(ge=0)
    line: int = Field(ge=0)


class Table(StrictModel):
    """Expose unverified model table rows while bounding every collection dimension."""

    rows: list[list[str]] = Field(max_length=100)


class VisionResult(StrictModel):
    """Require structured transcription only, with explicit uncertain regions and no model actions."""

    text: str = Field(max_length=MAX_TEXT_BYTES)
    tables: list[Table] = Field(max_length=20)
    uncertain_regions: list[str] = Field(max_length=100)


class Page(StrictModel):
    """Represent one native/OCR/rendered page with honest confidence and structural limitations."""

    processor: str
    page_number: int = Field(ge=1, le=1000)
    page_count: int = Field(ge=1, le=1000)
    method: Literal["native_pdf", "tesseract", "vlm_pending", "local_vlm"]
    engine: str
    text: str
    width: int = Field(ge=0, le=2048)
    height: int = Field(ge=0, le=2048)
    words: list[Word] = Field(max_length=5000)
    confidence_score: float | None = Field(ge=0, le=100)
    confidence_basis: str
    review_required: bool
    uncertainties: list[str] = Field(max_length=110)
    tables: list[Table] = Field(max_length=20)
    table_structure_status: Literal["not_inferred", "unverified_vlm"]
    coordinate_space: Literal["none", "rendered_pixels"]
    image_base64: str | None


def validate_vision(payload):
    """Bound model transcription/table text without accepting self-reported confidence or commands."""
    try:
        result = VisionResult.model_validate(payload)
        texts = [result.text, *result.uncertain_regions]
        for table in result.tables:
            for row in table.rows:
                if len(row) > 20:
                    raise ValueError("Table width limit")
                texts.extend(row)
        if sum(len(text.encode("utf-8")) for text in texts) > MAX_TEXT_BYTES:
            raise ValueError("Text budget exceeded")
    except (ValueError, UnicodeError, ValidationError):
        raise StoragePolicyError("vision_invalid_result", 502) from None
    return result.model_dump()


def validate_page(payload):
    """Check page numbering, pixel boxes, text budgets and confidence semantics independently."""
    try:
        page = Page.model_validate(payload)
        if (
            page.processor != OCR_VERSION
            or page.page_number > page.page_count
            or page.width * page.height > 4_000_000
        ):
            raise ValueError("Invalid page provenance")
        total = len(page.text.encode("utf-8"))
        for word in page.words:
            total += len(word.text.encode("utf-8"))
            if (
                not math.isfinite(word.score)
                or word.left + word.width > page.width
                or word.top + word.height > page.height
            ):
                raise ValueError("Invalid pixel box")
        for table in page.tables:
            for row in table.rows:
                if len(row) > 20:
                    raise ValueError("Table limit")
                total += sum(len(value.encode("utf-8")) for value in row)
        if total > MAX_TEXT_BYTES or (
            page.confidence_score is not None
            and not math.isfinite(page.confidence_score)
        ):
            raise ValueError("Text/score budget exceeded")
        if page.method in ("vlm_pending", "local_vlm") and (
            page.confidence_score is not None or not page.review_required
        ):
            raise ValueError("Uncalibrated model confidence")
        if (
            page.method == "tesseract"
            and (
                not page.text.strip()
                or page.confidence_score is None
                or page.confidence_score < 85
            )
            and not page.review_required
        ):
            raise ValueError("Missing low-confidence review")
        if page.method == "vlm_pending":
            data = base64.b64decode(page.image_base64 or "", validate=True)
            if not data.startswith(b"\x89PNG\r\n\x1a\n") or len(data) > MAX_IMAGE_BYTES:
                raise ValueError("Invalid sanitized image")
        elif page.image_base64 is not None:
            raise ValueError("Unexpected image payload")
    except (ValueError, UnicodeError, ValidationError):
        raise StoragePolicyError("ocr_processing_unavailable", 503) from None
    return page.model_dump()


def empty_page(number, count):
    """Initialize a bounded result without inventing confidence or table structure."""
    return dict(
        processor=OCR_VERSION,
        page_number=number,
        page_count=count,
        method="native_pdf",
        engine="pypdf",
        text="",
        width=0,
        height=0,
        words=[],
        confidence_score=None,
        confidence_basis="not_applicable_native_text",
        review_required=False,
        uncertainties=["native_text_may_omit_images_or_order"],
        tables=[],
        table_structure_status="not_inferred",
        coordinate_space="none",
        image_base64=None,
    )
