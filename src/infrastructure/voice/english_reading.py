"""Preserve accepted date/clause rendering while retaining original English spelling."""

import hashlib
import logging
import time
from dataclasses import replace
from src.infrastructure.voice.reading_text import render_speech

LOGGER = logging.getLogger(__name__)


def render_english(text):
    """Keep accepted date/clause edits while removing only the experimental Vietnamese term substitutions."""
    started = time.perf_counter()
    previous = render_speech(text, "clauses")
    edits = tuple((edit for edit in previous.edits if edit.kind != "lexicon"))
    cursor, parts = (0, [])
    for edit in edits:
        parts.extend((text[cursor : edit.start], edit.spoken))
        cursor = edit.end
    parts.append(text[cursor:])
    speech = "".join(parts)
    result = replace(
        previous,
        speech_text=speech,
        speech_sha256=hashlib.sha256(speech.encode()).hexdigest(),
        policy="clauses_english",
        policy_version="vi-english-research-1",
        edits=edits,
        render_seconds=time.perf_counter() - started,
    )
    LOGGER.info("english_speech_rendered")
    return result
