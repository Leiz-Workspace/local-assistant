"""Render auditable Vietnamese speech-only text for isolated reading and prosody experiments."""

import hashlib
import logging
import re
import time
from dataclasses import dataclass
from datetime import date

LOGGER = logging.getLogger(__name__)
POLICY_VERSION = "vi-speech-research-1"
WORDS = ("không", "một", "hai", "ba", "bốn", "năm", "sáu", "bảy", "tám", "chín")
LEXICON = {"Python": "pai thờn", "API": "ây pi ai"}
PROTECTED = re.compile(
    r"```[\s\S]*?(?:```|$)|`[^`\n]*(?:`|$)"
    r"|\[[^\]\n]*\]\([^\s)]*\)"
    r"|(?:https?://|www\.)[^\s<>]+"
    r"|[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}"
    r"|(?<!\w)(?:\.{1,2}/|/|[A-Za-z]:\\)[^\s<>]+"
    r"|\{[^{}\n]*\}"
    r"|\b\w+(?:[._-]\w+)+\b"
)
CLOCK = re.compile(r"(?<![\w/:])(\d{1,2}):(\d{2})(?![\w/:]|\.\d)")
CLOCK_CUE = re.compile(r"\b(?:lúc|vào|từ|đến)\s+$", re.IGNORECASE)
DATE = re.compile(r"\bngày\s+(\d{1,2})/(\d{1,2})(?:/(\d{4}))?(?![\w/])", re.IGNORECASE)
TERM = re.compile(r"(?<![\w-])(?:Python|API)(?![\w-])")


@dataclass(frozen=True)
class Edit:
    """Bind one replacement to exact original Python character offsets, with no response text mutation."""

    start: int
    end: int
    kind: str
    original: str
    spoken: str


@dataclass(frozen=True)
class SpeechText:
    """Retain original/display text, experimental speech text, hashes, edit trace and rendering time."""

    source_text: str
    speech_text: str
    source_sha256: str
    speech_sha256: str
    policy: str
    policy_version: str
    edits: tuple[Edit, ...]
    render_seconds: float


def number(value):
    """Speak an integer from zero through9999 using an explicit Northern Vietnamese research convention."""
    if type(value) is not int or not 0 <= value <= 9999:
        raise ValueError("speech_number_bound")
    if value < 10:
        return WORDS[value]
    if value < 100:
        tens, ones = divmod(value, 10)
        prefix = "mười" if tens == 1 else WORDS[tens] + " mươi"
        suffix = (
            "mốt" if ones == 1 and tens > 1 else "lăm" if ones == 5 else WORDS[ones]
        )
        return prefix + (" " + suffix if ones else "")
    if value < 1000:
        hundreds, rest = divmod(value, 100)
        return (
            WORDS[hundreds]
            + " trăm"
            + ((" lẻ " if rest < 10 else " ") + number(rest) if rest else "")
        )
    thousands, rest = divmod(value, 1000)
    prefix = WORDS[thousands] + " nghìn"
    if rest == 0:
        return prefix
    if rest < 100:
        return prefix + " không trăm" + (" lẻ " if rest < 10 else " ") + number(rest)
    return prefix + " " + number(rest)


def protected_spans(text):
    """Identify code, links, paths and compound identifiers that this renderer must leave byte-equivalent."""
    return tuple((match.start(), match.end()) for match in PROTECTED.finditer(text))


def overlaps(start, end, spans):
    """Detect any character overlap with an immutable source region."""
    return any(start < upper and end > lower for lower, upper in spans)


def render_speech(text, policy="reading"):
    """Create a separate bounded speech rendering without changing displayed text or silently guessing unsupported formats."""
    started = time.perf_counter()
    if (
        type(text) is not str
        or not text.strip()
        or len(text.encode()) > 2048
        or any(ord(c) < 32 and c not in "\n\t" for c in text)
    ):
        raise ValueError("speech_text_bound")
    if policy not in {"raw", "reading", "clauses"}:
        raise ValueError("speech_policy")
    spans, edits = protected_spans(text), []
    if policy != "raw":
        for match in CLOCK.finditer(text):
            if not CLOCK_CUE.search(text[: match.start()]) or overlaps(
                *match.span(), spans
            ):
                continue
            hour, minute = (int(v) for v in match.groups())
            if hour > 23 or minute > 59:
                continue
            spoken = (
                number(hour)
                + " giờ"
                + (" " + number(minute) + " phút" if minute else "")
            )
            edits.append(Edit(*match.span(), "clock", match[0], spoken))
        for match in DATE.finditer(text):
            if overlaps(*match.span(), spans):
                continue
            day, month = int(match[1]), int(match[2])
            year = int(match[3]) if match[3] else None
            try:
                date(year if year is not None else 2000, month, day)
            except ValueError:
                continue
            start, end = match.start(1), match.end()
            spoken = (
                number(day)
                + " tháng "
                + number(month)
                + (" năm " + number(year) if year is not None else "")
            )
            edits.append(Edit(start, end, "date", text[start:end], spoken))
        for match in TERM.finditer(text):
            if not overlaps(*match.span(), spans):
                edits.append(
                    Edit(*match.span(), "lexicon", match[0], LEXICON[match[0]])
                )
        if policy == "clauses":
            for match in re.finditer(";", text):
                if not overlaps(*match.span(), spans):
                    edits.append(Edit(*match.span(), "clause_boundary", ";", "."))
    edits.sort(key=lambda edit: edit.start)
    cursor, parts = 0, []
    for edit in edits:
        if edit.start < cursor or text[edit.start : edit.end] != edit.original:
            raise ValueError("speech_edit_overlap")
        parts.extend((text[cursor : edit.start], edit.spoken))
        cursor = edit.end
    parts.append(text[cursor:])
    spoken = "".join(parts)
    if len(spoken.encode()) > 4096:
        raise ValueError("speech_output_bound")
    source_sha = hashlib.sha256(text.encode()).hexdigest()
    speech_sha = hashlib.sha256(spoken.encode()).hexdigest()
    LOGGER.info(
        "speech_text_rendered policy=%s version=%s edits=%d source_sha256=%s speech_sha256=%s",
        policy,
        POLICY_VERSION,
        len(edits),
        source_sha,
        speech_sha,
    )
    return SpeechText(
        text,
        spoken,
        source_sha,
        speech_sha,
        policy,
        POLICY_VERSION,
        tuple(edits),
        time.perf_counter() - started,
    )
