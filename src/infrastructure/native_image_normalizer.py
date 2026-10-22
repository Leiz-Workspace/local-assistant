"""Normalize explicit image bytes through the accepted isolated page worker while keeping native descriptors private and scoped."""

import base64
import logging
import tempfile

from src.application.ports.vision_chat import NormalizedImage
from src.application.services.vision_chat_policy import (
    digest,
    image_input,
    validate_image,
)
from src.infrastructure.page_ocr import prepare_page

logger = logging.getLogger(__name__)


class NativeImageNormalizer:
    """Reuse original page1/VLM raster preparation without host image decoding, paths, OCR or model disclosure."""

    def normalize(self, raw, suffix):
        """Hold one anonymous source descriptor until the original bounded native process and children have retired."""
        source_sha = image_input(raw, suffix)
        with tempfile.TemporaryFile() as source:
            source.write(raw)
            source.flush()
            source.seek(0)
            page = prepare_page(source, suffix, 1, "vlm")
        png = base64.b64decode(page["image_base64"], validate=True)
        image = NormalizedImage(
            source_sha,
            png,
            digest(png),
            page["width"],
            page["height"],
            page["processor"],
        )
        validate_image(image, source_sha)
        logger.info(
            "native_image_normalization_complete source_bytes=%d png_bytes=%d",
            len(raw),
            len(png),
        )
        return image
