"""Score complete authored D63 image answers without dropping unsupported numbers or repairing field associations."""

import logging
import re
import unicodedata

logger = logging.getLogger(__name__)


def golden_match(case, answer, uncertainties):
    """Check frozen whole-answer patterns, permitted numbers and required abstention uncertainty without rewriting output."""
    text = unicodedata.normalize("NFC", answer)
    required = all(re.search(p, text, re.IGNORECASE) for p in case["required_patterns"])
    forbidden = any(
        re.search(p, text, re.IGNORECASE) for p in case["forbidden_patterns"]
    )
    numbers = set(re.findall(r"\d+(?:[.,]\d+)?", text))
    passed = bool(
        required
        and not forbidden
        and numbers <= set(case["allowed_numbers"])
        and (not case["requires_uncertainty"] or bool(uncertainties))
    )
    logger.info("image_golden_scored passed=%s", passed)
    return passed
