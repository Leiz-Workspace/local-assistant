"""Verify private image/result values cannot leak through repr or be mutated into a different operation."""

import logging
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from test_vision_chat_policy import completion
from test_vision_chat_policy import image as image

from src.application.services.vision_chat_policy import resolve_answer


def test_private_image_and_answer_are_frozen_and_do_not_expose_content_in_repr(image):
    """Keep source/image/owner/answer values out of incidental diagnostics without claiming cryptographic authority."""
    owner = uuid4()
    result = resolve_answer(
        completion(),
        "fixture-core",
        owner,
        "PRIVATE-QUESTION",
        image,
        datetime.now(UTC),
    )
    assert str(owner) not in repr(result) and result.answer not in repr(result)
    assert image.png_sha256 not in repr(image) and "PNG" not in repr(image)
    with pytest.raises(FrozenInstanceError):
        image.width = 1
    with pytest.raises(FrozenInstanceError):
        result.owner_id = uuid4()
    logging.getLogger(__name__).info("vision_private_value_contract_verified")
