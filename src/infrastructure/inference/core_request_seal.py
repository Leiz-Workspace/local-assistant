"""Seal every outbound CORE request body so no content string carries a pinned special-token literal (ADR-195 Layer 2).

seal_payload(payload, site) returns (payload, counts):
- payload is the same object when nothing needs a substitution; otherwise a shallow
  copy in the same key order whose changed messages and parts are new objects. The
  input is never mutated.
- counts is a SealCounts with the neutralized content literals and the literals left
  under the exempt fields, each split by kind (control, user_defined).

It raises SpecialLiteralsStale first when this process recorded a stale model binding,
and CoreRequestRejected (closed reason codes) for any message key other than role and
content, any role outside ROLES, any part type other than text and image_url, any
top-level key outside ALLOWED_TOP_LEVEL, or chat_template_kwargs other than exactly
{"enable_thinking": bool}. Roles are closed because a non-Jinja chat format would
insert the role text verbatim; every builder sends only these three.

The template joins adjacent text parts without a separator, so a literal can be split
across parts. Each run of consecutive text parts (empty parts included; an image part
ends a run) is neutralized as one joined string with the shared neutralizer, and every
substitution is written back into the part that holds the literal's leading "<". The
re-split parts therefore concatenate to exactly neutralize(joined), which is checked.

The exempt fields become a grammar under the pinned template handler and are never
rendered into the prompt; re-check that when the template or the llama.cpp pin changes.
"""

import logging
import re
from dataclasses import dataclass

from src.application.services.special_literals import (
    CORE_SPECIAL_TOKENS,
    ESCAPED_LT,
    SpecialLiteralsStale,
    neutralize,
    require_current_binding,
)

logger = logging.getLogger(__name__)

# The ten outbound bodies, plus the grounded frame precheck that bounds the excerpt body.
SITES = frozenset(
    {
        "gateway_apply_template",
        "gateway_classifier",
        "gateway_complete",
        "harness_structured",
        "harness_stream",
        "summarizer",
        "structured_profile",
        "structured_excerpt",
        "core_vision_chat",
        "vision_ocr",
        "grounded_precheck",
    }
)
# Never rendered into the prompt by the pinned template handler; literals stay and are counted.
EXEMPT_FIELDS = frozenset({"response_format", "json_schema", "grammar"})
# Known risky keys; the allowlist below already rejects them, they are named for the tests.
REJECTED_TOP_LEVEL = (
    "tools",
    "reasoning_budget_message",
    "reasoning_effort",
    "continue_final_message",
    "add_generation_prompt",
)


def _number(value):
    """Accept a finite JSON number that is not a boolean."""
    return type(value) in (int, float) and value == value and abs(value) != float("inf")


def _integer(value):
    """Accept a JSON integer that is not a boolean."""
    return type(value) is int


def _boolean(value):
    """Accept a JSON boolean."""
    return type(value) is bool


def _string(value):
    """Accept a string that carries no pinned literal."""
    return type(value) is str and not _find(value)


def _stream_options(value):
    """Accept only the usage switch that the structured profile stream sends."""
    return (
        type(value) is dict
        and set(value) == {"include_usage"}
        and type(value["include_usage"]) is bool
    )


# Every top-level key today's builders send, with the value shape each may carry.
SCALAR_FIELDS = {
    "model": _string,
    "temperature": _number,
    "max_tokens": _integer,
    "stream": _boolean,
    "stream_options": _stream_options,
    "cache_prompt": _boolean,
    "seed": _integer,
    "thinking_budget_tokens": _integer,
    "reasoning_format": _string,
    "reasoning_budget_tokens": _integer,
}
ALLOWED_TOP_LEVEL = frozenset(
    {"messages", "chat_template_kwargs", *SCALAR_FIELDS, *EXEMPT_FIELDS}
)
ROLES = frozenset({"system", "user", "assistant"})
PART_KEYS = {
    "text": frozenset({"type", "text"}),
    "image_url": frozenset({"type", "image_url"}),
}
REASONS = frozenset(
    {
        "unknown_site",
        "payload_shape",
        "top_level_key",
        "field_value",
        "chat_template_kwargs",
        "messages_shape",
        "message_key",
        "message_value",
        "part_type",
        "part_shape",
        "exempt_value",
        "seal_mismatch",
    }
)

_KIND_BY_TAIL = {text[1:]: kind for _, kind, text in CORE_SPECIAL_TOKENS}
_FINDER = re.compile(
    "<(?=("
    + "|".join(
        re.escape(tail)
        for tail in sorted(_KIND_BY_TAIL, key=lambda tail: (-len(tail), tail))
    )
    + "))"
)


class CoreRequestRejected(Exception):
    """Refuse an outbound CORE request whose shape the seal does not cover."""

    code = "core_request_rejected"

    def __init__(self, reason):
        """Keep only a closed reason code, never request text."""
        self.reason = reason if reason in REASONS else "payload_shape"
        super().__init__(self.reason)


@dataclass(frozen=True, slots=True)
class SealCounts:
    """Count neutralized content literals and literals left under exempt fields, per kind."""

    control: int = 0
    user_defined: int = 0
    exempt_control: int = 0
    exempt_user_defined: int = 0

    @property
    def neutralized(self):
        """Return the number of literals neutralized in message content."""
        return self.control + self.user_defined

    @property
    def exempt(self):
        """Return the number of literals kept under the exempt fields."""
        return self.exempt_control + self.exempt_user_defined


def _find(text):
    """Return the kind of every pinned literal in text, in order."""
    if "<" not in text:
        return []
    return [_KIND_BY_TAIL[match.group(1)] for match in _FINDER.finditer(text)]


def seal_run(texts):
    """Neutralize adjacent text segments as one joined string; return the new segments and literal kinds.

    Unchanged segments come back as the same objects.
    """
    joined = "".join(texts)
    if "<" not in joined:
        return list(texts), []
    hits = [
        (match.start(), _KIND_BY_TAIL[match.group(1)])
        for match in _FINDER.finditer(joined)
    ]
    if not hits:
        return list(texts), []
    out, offset, index = [], 0, 0
    for text in texts:
        end = offset + len(text)
        pieces, last = [], 0
        while index < len(hits) and hits[index][0] < end:
            local = hits[index][0] - offset
            pieces += [text[last:local], ESCAPED_LT]
            last = local + 1
            index += 1
        out.append("".join(pieces) + text[last:] if pieces else text)
        offset = end
    expected, count = neutralize(joined)
    if count != len(hits) or "".join(out) != expected:
        raise CoreRequestRejected("seal_mismatch")
    return out, [kind for _, kind in hits]


def _seal_content(content, kinds):
    """Seal one message content (a string or a list of parts) and return the possibly new value."""
    if type(content) is str:
        (sealed,), found = seal_run([content])
        kinds += found
        return sealed
    if type(content) is not list:
        raise CoreRequestRejected("message_value")
    runs, run = [], []
    for index, part in enumerate(content):
        if type(part) is not dict or part.get("type") not in PART_KEYS:
            raise CoreRequestRejected("part_type")
        if set(part) != PART_KEYS[part["type"]]:
            raise CoreRequestRejected("part_shape")
        if part["type"] == "text":
            if type(part["text"]) is not str:
                raise CoreRequestRejected("part_shape")
            run.append(index)
            continue
        if type(part["image_url"]) is not dict:
            raise CoreRequestRejected("part_shape")
        if run:
            runs.append(run)
        run = []
    if run:
        runs.append(run)
    sealed = None
    for run in runs:
        texts = [content[index]["text"] for index in run]
        new_texts, found = seal_run(texts)
        kinds += found
        for index, old, new in zip(run, texts, new_texts):
            if new is not old:
                if sealed is None:
                    sealed = list(content)
                part = dict(content[index])
                part["text"] = new
                sealed[index] = part
    return content if sealed is None else sealed


def _seal_messages(messages, kinds):
    """Seal every message and return the possibly new list."""
    if type(messages) is not list:
        raise CoreRequestRejected("messages_shape")
    sealed = None
    for index, message in enumerate(messages):
        if type(message) is not dict:
            raise CoreRequestRejected("messages_shape")
        if set(message) != {"role", "content"}:
            raise CoreRequestRejected("message_key")
        if type(message["role"]) is not str or message["role"] not in ROLES:
            raise CoreRequestRejected("message_value")
        content = _seal_content(message["content"], kinds)
        if content is not message["content"]:
            if sealed is None:
                sealed = list(messages)
            changed = dict(message)
            changed["content"] = content
            sealed[index] = changed
    return messages if sealed is None else sealed


def _count_exempt(value, kinds, depth=0):
    """Count literals in every string key and value of an exempt JSON field without changing it."""
    if depth > 64:
        raise CoreRequestRejected("exempt_value")
    if type(value) is str:
        kinds += _find(value)
    elif type(value) is dict:
        for key, item in value.items():
            if type(key) is not str:
                raise CoreRequestRejected("exempt_value")
            kinds += _find(key)
            _count_exempt(item, kinds, depth + 1)
    elif type(value) is list:
        for item in value:
            _count_exempt(item, kinds, depth + 1)
    elif value is not None and type(value) not in (bool, int, float):
        raise CoreRequestRejected("exempt_value")


def seal_payload(payload, site):
    """Refuse a stale binding or an uncovered shape, then neutralize every content literal of one CORE body."""
    label = site if site in SITES else "unknown"
    try:
        require_current_binding()
    except SpecialLiteralsStale as error:
        logger.warning(
            "core_request_refused site=%s code=%s roles=%d",
            label,
            error.code,
            len(error.roles),
        )
        raise
    try:
        if site not in SITES:
            raise CoreRequestRejected("unknown_site")
        if type(payload) is not dict or "messages" not in payload:
            raise CoreRequestRejected("payload_shape")
        content, exempt, sealed = [], [], None
        for key, value in payload.items():
            if key not in ALLOWED_TOP_LEVEL:
                raise CoreRequestRejected("top_level_key")
            if key == "messages":
                messages = _seal_messages(value, content)
                if messages is not value:
                    sealed = dict(payload)
                    sealed["messages"] = messages
            elif key == "chat_template_kwargs":
                if (
                    type(value) is not dict
                    or set(value) != {"enable_thinking"}
                    or type(value["enable_thinking"]) is not bool
                ):
                    raise CoreRequestRejected("chat_template_kwargs")
            elif key in EXEMPT_FIELDS:
                _count_exempt(value, exempt)
            elif not SCALAR_FIELDS[key](value):
                raise CoreRequestRejected("field_value")
    except CoreRequestRejected as error:
        logger.warning("core_request_rejected site=%s reason=%s", label, error.reason)
        raise
    counts = SealCounts(
        content.count("control"),
        content.count("user_defined"),
        exempt.count("control"),
        exempt.count("user_defined"),
    )
    logger.info(
        "core_request_sealed site=%s neutralized=%d control=%d user_defined=%d "
        "exempt=%d exempt_control=%d exempt_user_defined=%d",
        site,
        counts.neutralized,
        counts.control,
        counts.user_defined,
        counts.exempt,
        counts.exempt_control,
        counts.exempt_user_defined,
    )
    return (payload if sealed is None else sealed), counts
