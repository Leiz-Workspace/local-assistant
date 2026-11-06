"""Validate factual diagnostic responses inside the sealed worker without parent-only source identities, preparation code or expected labels."""

import logging
import re

logger = logging.getLogger(__name__)
QUESTION = "Does this audio contain any intelligible human speech? Answer exactly yes, no, or uncertain."
MAX_TOKENS = 16


def parse_answer(raw):
    """Accept exact lowercase factual labels without repairing JSON, prose, punctuation or uncertain answers into success."""
    if type(raw) is not str or raw.strip() not in {"yes", "no", "uncertain"}:
        raise ValueError("local_diagnostic_answer")
    return raw.strip()


def audit_events(request, events):
    """Require complete source-bound factual responses and genuine termination while never conferring naturalness qualification."""
    rows = [event for event in events if event.get("event") == "diagnostic"]
    if len(request["cases"]) != 4 or [row.get("id") for row in rows] != [row["id"] for row in request["cases"]]:
        return False
    if any(sum(event.get("event") == name for event in events) != 1 for name in ["ready", "complete"]):
        return False
    if any(event.get("event") == "review" for event in events):
        return False
    for source, event in zip(request["cases"], rows, strict=True):
        expected = dict(source_sha256=source["sha256"], sample_count=source["sample_count"], sample_rate=16000, generation_complete=True, question=QUESTION, maximum_new_tokens=MAX_TOKENS)
        if any(event.get(key) != value for key, value in expected.items()):
            return False
        tokens = event.get("generated_token_ids", [])
        if type(tokens) is not list or not tokens or len(tokens) > MAX_TOKENS or any(type(token) is not int or token < 0 for token in tokens) or tokens[-1] != 151645 or event.get("audio_tokens", 0) <= 0 or event.get("feature_frames", 0) <= 0:
            return False
        feature_hash = event.get("feature_sha256")
        shape = event.get("feature_shape")
        if type(feature_hash) is not str or re.fullmatch(r"[0-9a-f]{64}", feature_hash) is None or type(shape) is not list or len(shape) != 3 or shape[:2] != [1, 128] or type(shape[2]) is not int or shape[2] < event["feature_frames"]:
            return False
        if event.get("generation_complete") is not True or event.get("parse_error") is not None:
            return False
        try:
            if parse_answer(event.get("raw_text")) != event.get("answer"):
                return False
        except ValueError:
            return False
    logger.info("local_audio_presence_diagnostic_observations_verified cases=4 naturalness_qualification=False")
    return True
