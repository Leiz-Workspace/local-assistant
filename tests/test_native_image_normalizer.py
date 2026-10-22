"""Exercise actual accepted native image isolation, metadata stripping, sizing, orientation and single-frame refusal."""

import io
import logging
from pathlib import Path

import pytest
from PIL import Image, PngImagePlugin

from src.application.services.file_storage_policy import StoragePolicyError
from src.application.services.vision_chat_policy import digest, validate_image
from src.infrastructure.native_image_normalizer import NativeImageNormalizer


def test_real_native_normalization_strips_source_metadata_and_preserves_pixel_provenance():
    """Normalize an authored PNG through the actual namespace and retain separate complete original/output fingerprints."""
    metadata = PngImagePlugin.PngInfo()
    metadata.add_text("Comment", "PRIVATE-METADATA-CANARY")
    output = io.BytesIO()
    Image.new("RGB", (2500, 100), "white").save(output, "PNG", pnginfo=metadata)
    raw = output.getvalue()
    normalized = NativeImageNormalizer().normalize(raw, "png")
    assert normalized.source_sha256 == digest(raw) and normalized.png_sha256 == digest(
        normalized.png
    )
    assert (
        normalized.width == 2000
        and normalized.height == 80
        and b"PRIVATE-METADATA" not in normalized.png
    )
    assert normalized.png != raw
    validate_image(normalized, digest(raw))


def test_real_native_jpeg_exif_orientation_is_applied_before_metadata_removal():
    """Prove image sizing uses normalized orientation while the original EXIF/private metadata stays out of model input."""
    output = io.BytesIO()
    picture = Image.new("RGB", (20, 10), "white")
    exif = Image.Exif()
    exif[274] = 6
    exif[270] = "PRIVATE-EXIF-CANARY"
    picture.save(output, "JPEG", exif=exif)
    normalized = NativeImageNormalizer().normalize(output.getvalue(), "jpeg")
    assert (normalized.width, normalized.height) == (
        10,
        20,
    ) and b"PRIVATE-EXIF" not in normalized.png


@pytest.mark.parametrize("case", ["mismatched", "malformed", "animated"])
def test_real_native_rejects_wrong_type_broken_image_and_multiple_frames(case):
    """Keep invalid complete image input inside original type/multiframe policy instead of silently using its first frame."""
    raw = Path("tests/fixtures/ocr/clean.png").read_bytes()
    suffix = "jpeg"
    if case == "malformed":
        raw = b"\x89PNG\r\n\x1a\ninvalid"
        suffix = "png"
    elif case == "animated":
        output = io.BytesIO()
        Image.new("RGB", (10, 10), "white").save(
            output,
            "PNG",
            save_all=True,
            append_images=[Image.new("RGB", (10, 10), "black")],
            duration=100,
        )
        raw = output.getvalue()
        suffix = "png"
    with pytest.raises(StoragePolicyError, match="invalid_ocr_content"):
        NativeImageNormalizer().normalize(raw, suffix)
    logging.getLogger(__name__).info(
        "actual_native_image_denial_verified case=%s", case
    )
