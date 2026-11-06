"""Prepare bounded CORE speech and reuse the accepted Truc Ly phone policy without changing display text."""

import hashlib
import logging
import re
from dataclasses import dataclass
from src.infrastructure.voice.terms import SOURCE as API_SOURCE
from src.infrastructure.voice.terms import TARGET as API_TARGET
from src.infrastructure.voice.prosody import ProsodyAdapter
from src.infrastructure.voice.reading_text import protected_spans
from src.infrastructure.voice.terms import TERMS, TermsAdapter

LOGGER = logging.getLogger(__name__)
POLICY = "truc-ly-workflow-reading-1"
VOICE = "Trúc Ly"
MODEL = "vieneu-v3-turbo-truc-ly"
SPELLINGS = {
    "python": "python",
    "github": "git\\s+hub|github",
    "server": "server",
    "api": "a\\s+p\\s+i",
}
CONTROL = re.compile("<\\|\\s*|</?(?:en|vi)(?:\\s|>)", re.IGNORECASE)
TARGET_WORD = re.compile("(?<![^\\W_])(?:Python|GitHub|server|API)(?![^\\W_])", re.I)


@dataclass(frozen=True, slots=True, repr=False)
class ReadingTrace:
    """Bind original and spoken answers with content-redacted edits before pipeline publication."""

    original_sha256: str
    spoken_sha256: str
    policy: str
    edits: tuple
    render_seconds: float


def sha(value):
    """Hash a text value without emitting its private contents in audit logs."""
    return hashlib.sha256(value.encode()).hexdigest()


def check_text(value, limit):
    """Refuse invalid text and caller-supplied SDK language or phoneme controls before preparation."""
    if (
        type(value) is not str
        or not value.strip()
        or len(value.encode()) > limit
        or any((ord(char) < 32 and char not in "\n\t" for char in value))
        or CONTROL.search(value)
    ):
        LOGGER.warning("workflow_reading_rejected code=text_contract")
        raise ValueError("workflow_reading_text_contract")


def prepare_answer(answer):
    """Reuse exact accepted date/clause rendering while keeping protected target identifiers out of phone edits."""
    from src.infrastructure.voice.english_reading import render_english

    check_text(answer, 2048)
    if any(
        (
            TARGET_WORD.search(answer[start:end])
            for start, end in protected_spans(answer)
        )
    ):
        LOGGER.warning("workflow_reading_rejected code=protected_target")
        raise ValueError("workflow_reading_protected_target")
    rendered = render_english(answer)
    check_text(rendered.speech_text, 4096)
    edits = tuple(
        (
            (edit.start, edit.end, edit.kind, sha(edit.original), sha(edit.spoken))
            for edit in rendered.edits
        )
    )
    trace = ReadingTrace(
        rendered.source_sha256,
        rendered.speech_sha256,
        POLICY,
        edits,
        rendered.render_seconds,
    )
    LOGGER.info("workflow_answer_prepared")
    return (rendered.speech_text, trace)


def phone_matches(value, pattern):
    """Match complete phone words without rewriting a substring inside another pronunciation."""
    return list(
        re.finditer("(?<![\\wːˈˌ])" + re.escape(pattern) + "(?![\\wːˈˌ])", value)
    )


def plan_chunk(normalized, raw, frame_cap):
    """Plan zero or bounded repeated known terms with exact lexical counts and conservative original budgets."""
    if type(raw) is not str or not raw.strip() or len(raw.encode()) > 8192:
        raise ValueError("workflow_reading_phone_contract")
    changes, counts = ([], {})
    targets = dict(TERMS, api=(API_SOURCE, API_TARGET))
    for term, (before, after) in targets.items():
        count = len(
            re.findall(
                "(?<![\\w-])(?:" + SPELLINGS[term] + ")(?![\\w-])", normalized, re.I
            )
        )
        counts[term] = count
        if count == 0:
            continue
        old, already = (phone_matches(raw, before), phone_matches(raw, after))
        if count > 16 or len(old) + len(already) != count:
            LOGGER.warning(
                "workflow_reading_rejected code=ambiguous_phone_mapping term=%s", term
            )
            raise ValueError("workflow_reading_ambiguous_phone_mapping")
        changes.extend(
            (
                dict(
                    start=match.start(),
                    end=match.end(),
                    term=term,
                    before=before,
                    after=after,
                )
                for match in old
            )
        )
    changes.sort(key=lambda edit: edit["start"])
    cursor, parts = (0, [])
    for edit in changes:
        if edit["start"] < cursor:
            raise ValueError("workflow_reading_overlapping_edits")
        parts.extend((raw[cursor : edit["start"]], edit["after"]))
        cursor = edit["end"]
    parts.append(raw[cursor:])
    phones = "".join(parts)
    original_cap, reading_cap = (frame_cap(raw), frame_cap(phones))
    if (
        type(original_cap) is not int
        or type(reading_cap) is not int
        or min(original_cap, reading_cap) < 1
    ):
        raise ValueError("workflow_reading_invalid_cap")
    original_cap, reading_cap = (min(300, original_cap), min(300, reading_cap))
    LOGGER.info(
        "workflow_chunk_planned edits=%d chunks_before_generation=True", len(changes)
    )
    return dict(
        normalized=normalized,
        raw=raw,
        phones=phones,
        edits=changes,
        lexical_counts=counts,
        original_cap=original_cap,
        reading_cap=reading_cap,
        shared_cap=min(original_cap, reading_cap),
    )


class WorkflowReadingAdapter(TermsAdapter):
    """Apply the retained phone policy to bounded non-whitelisted answers with original native generation."""

    def __init__(self, wrapper, dependencies=None):
        """Reuse original speaker/reference audit and keep every synthesis dependency except explicit phone planning."""
        super().__init__(wrapper, "us", dependencies)
        self.plans = []
        self.token_checks = []

    def phonemize(self, text, punc_norm):
        """Build one audited chunk plan before the original adapter starts any neural generation."""
        raw = self.original["phonemize"](text, punc_norm=punc_norm)
        plan = plan_chunk(text, raw, self.original["frame_cap"])
        tokenizer = self.original.get("tokenizer") or getattr(
            self.wrapper.engine, "tokenizer", None
        )
        if tokenizer is None:
            raise ValueError("workflow_reading_tokenizer_required")
        ids = tokenizer.encode(plan["phones"], add_special_tokens=False).ids
        if (
            tokenizer.token_to_id("<|unk|>") in ids
            or tokenizer.decode(ids, skip_special_tokens=False) != plan["phones"]
        ):
            raise ValueError("workflow_reading_token_roundtrip")
        self.token_checks.append(
            dict(token_ids=ids, decoded_exact=True, unknown_tokens=0)
        )
        self.plans.append(plan)
        return plan["phones"]

    def frame_cap(self, phones):
        """Return only the conservative allowance associated with a fully prepared chunk."""
        caps = {plan["shared_cap"] for plan in self.plans if plan["phones"] == phones}
        if len(caps) != 1:
            raise ValueError("workflow_reading_cap_binding")
        return caps.pop()

    def infer(self, text, *, voice):
        """Use only retained Truc Ly and original complete chunk generation, never display-text rewriting."""
        check_text(text, 4096)
        if voice != VOICE:
            raise ValueError("workflow_reading_voice")
        self.plans, self.token_checks, self.binding = ([], [], None)
        result = ProsodyAdapter.infer(self, text, voice=voice)
        if self.binding is None or len(self.last_chunks) != len(self.plans):
            raise ValueError("workflow_reading_native_binding")
        self.last_trace.update(
            reading_policy=POLICY,
            spoken_input_sha256=sha(text),
            reading_plans=self.plans,
            reading_tokens=self.token_checks,
            voice_binding=self.binding,
        )
        LOGGER.info("workflow_reading_native_complete chunks=%d", len(self.plans))
        return result
