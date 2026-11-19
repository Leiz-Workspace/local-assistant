"""Build a deterministic working state from user-marked lines with key supersession, lineage and lexical freshness."""

import hashlib
import json
import re
import unicodedata
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator

KINDS = {
    "goal": ("goal", "mục tiêu"),
    "constraint": ("rule", "constraint", "quy tắc", "quy ước", "ràng buộc"),
    "decision": ("decision", "quyết định"),
    "todo": ("todo", "việc cần làm"),
    "done": ("done", "đã xong"),
    "note": ("important", "remember", "quan trọng", "ghi nhớ"),
    "correction": ("correction", "update", "đính chính", "cập nhật"),
}
MARKER_KIND = {
    unicodedata.normalize("NFC", marker): kind
    for kind, markers in KINDS.items()
    for marker in markers
}
MARKERS = "|".join(
    re.escape(marker) for marker in sorted(MARKER_KIND, key=len, reverse=True)
)
LINE = re.compile(
    r"^\s*(?:[-*]\s+)?(?P<marker>"
    + MARKERS
    + r")\s*(?:\[(?P<key>[^\]\n]*)\])?\s*:\s*\S"
)
LOOSE = re.compile(r"^\s*(?:[-*]\s+)?(?:" + MARKERS + r")\s*[\[:]")
MAX_LINE = 500
MAX_KEY = 48
MAX_ITEMS = 64
MAX_CAPSULE_BYTES = 32768
MAX_MENTIONS = 3
MIN_SHARED_TERMS = 3
RENDERED = {"goal", "constraint", "decision", "todo", "note", "correction"}
STOPWORDS = {
    "the",
    "and",
    "for",
    "are",
    "was",
    "were",
    "with",
    "this",
    "that",
    "from",
    "into",
    "now",
    "not",
    "but",
    "you",
    "your",
    "our",
    "its",
    "has",
    "have",
    "will",
    "all",
    "any",
    "can",
    "use",
    "uses",
    "used",
    "on",
    "in",
    "at",
    "to",
    "of",
    "is",
    "it",
    "be",
    "as",
    "or",
    "by",
    "an",
    "we",
    "do",
    "if",
    "so",
    "của",
    "là",
    "và",
    "cho",
    "các",
    "những",
    "được",
    "có",
    "không",
    "này",
    "đó",
    "với",
    "trong",
    "khi",
    "thì",
    "để",
    "đã",
    "sẽ",
    "ở",
    "từ",
    "một",
    "mọi",
    "phải",
    "theo",
    "nào",
    "gì",
    "bằng",
    "lại",
    "vẫn",
    "giờ",
}
MARKER_WORDS = {word for marker in MARKER_KIND for word in marker.casefold().split()}


class StateItem(BaseModel):
    """Validate one carried item returned by an earlier response; it stays untrusted client data."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: Literal[
        "goal", "constraint", "decision", "todo", "done", "note", "correction"
    ]
    key: str | None = Field(default=None, min_length=1, max_length=48)
    text: str = Field(min_length=1, max_length=MAX_LINE)
    turn: StrictInt = Field(ge=1, le=1_000_128)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    status: Literal["active", "superseded", "closed", "record", "dropped"] = "active"
    superseded_by: StrictInt | None = Field(default=None, ge=1, le=1_000_128)
    origin: Literal["window", "carried"] = "window"

    @field_validator("key")
    @classmethod
    def fold_key(cls, value):
        """Fold carried keys exactly like keys parsed from history so supersession matches."""
        folded = normalize_key(value)
        if value is not None and folded is None:
            raise ValueError("invalid_state_key")
        return folded


def pair_sha256(messages):
    """Hash one exact user/assistant pair with the same deterministic encoding as the history archive."""
    raw = json.dumps(
        messages, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    return hashlib.sha256(raw).hexdigest()


def normalize_key(value):
    """Return a case-insensitive key with collapsed inner spaces, or None for unkeyed items."""
    if value is None:
        return None
    key = " ".join(value.split()).casefold()
    return key or None


def extract(turns, offset):
    """Return items from marked user lines (never assistant text) and every marked line that could not become an item."""
    items, skipped = [], []
    for turn in turns:
        sha = None
        absolute = offset + turn["number"]
        text = unicodedata.normalize("NFC", turn["messages"][0]["content"])
        for line in text.splitlines():
            folded = unicodedata.normalize("NFC", line.casefold())
            match = LINE.match(folded)
            if match is None:
                if LOOSE.match(folded):
                    skipped.append(dict(turn=absolute, reason="malformed_marker_line"))
                continue
            key = normalize_key(match["key"])
            content = line.strip()
            if match["key"] is not None and (key is None or len(key) > MAX_KEY):
                skipped.append(dict(turn=absolute, reason="invalid_key"))
                continue
            if len(content) > MAX_LINE:
                skipped.append(dict(turn=absolute, reason="line_too_long"))
                continue
            sha = sha or pair_sha256(turn["messages"])
            items.append(
                dict(
                    kind=MARKER_KIND[match["marker"]],
                    key=key,
                    text=content,
                    turn=absolute,
                    sha256=sha,
                    origin="window",
                )
            )
    return items, skipped


def resolve(items):
    """Apply keyed supersession and todo closing in pair order; unkeyed items are never superseded automatically."""
    state = []
    for item in sorted(items, key=lambda entry: entry["turn"]):
        current = {**item, "status": "active", "superseded_by": None}
        if current["kind"] == "done":
            current["status"] = "record"
        if item["origin"] == "carried" and item.get("status") in {
            "superseded",
            "closed",
            "dropped",
        }:
            current.update(
                status=item["status"], superseded_by=item.get("superseded_by")
            )
        if current["key"] is not None:
            for prior in state:
                if prior["key"] != current["key"] or prior["status"] != "active":
                    continue
                if current["kind"] == "done":
                    if prior["kind"] == "todo":
                        prior.update(status="closed", superseded_by=current["turn"])
                elif current["kind"] == "todo":
                    if prior["kind"] == "todo":
                        prior.update(status="superseded", superseded_by=current["turn"])
                elif prior["kind"] != "todo":
                    prior.update(status="superseded", superseded_by=current["turn"])
        state.append(current)
    return state


def rows(state, mentions):
    """Return the rendered rows for active items, with freshness where found."""
    out = []
    for index, item in enumerate(state):
        if item["status"] != "active" or item["kind"] not in RENDERED:
            continue
        row = dict(kind=item["kind"], text=item["text"], turn=item["turn"])
        if item["key"] is not None:
            row["key"] = item["key"]
        if index in mentions:
            row["newer_mentions"] = mentions[index]
        out.append(row)
    return out


def encode_capsule(rendered):
    """Serialize the rendered rows deterministically as the untrusted capsule."""
    return json.dumps(
        dict(
            untrusted_working_state=dict(
                version=1, trust="untrusted-user-marked-history", items=rendered
            )
        ),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def limit(state, mentions):
    """Drop active items, notes and corrections first and oldest first, until at most 64 render within 32 KiB; report them."""
    order = sorted(
        (index for index, item in enumerate(state) if item["status"] == "active"),
        key=lambda index: (
            state[index]["kind"] not in {"note", "correction"},
            state[index]["turn"],
        ),
    )
    dropped = []
    for index in order:
        active = sum(item["status"] == "active" for item in state)
        size = len(encode_capsule(rows(state, mentions)).encode())
        if active <= MAX_ITEMS and size <= MAX_CAPSULE_BYTES:
            break
        state[index]["status"] = "dropped"
        dropped.append(state[index]["turn"])
    return dropped


def prune(state):
    """Keep at most 64 items in the carried record: every active item, then the newest inactive ones."""
    active = [item for item in state if item["status"] == "active"]
    inactive = [item for item in state if item["status"] != "active"]
    room = MAX_ITEMS - len(active)
    keep = (
        {id(item) for item in inactive[len(inactive) - room :]} if room > 0 else set()
    )
    return [item for item in state if item["status"] == "active" or id(item) in keep]


def terms(text):
    """Return significant lowercase letter-only words, without stopwords or marker words."""
    words = re.findall(r"[^\W\d_]{2,}", unicodedata.normalize("NFC", text).casefold())
    return set(words) - STOPWORDS - MARKER_WORDS


def newer_mentions(item, indexed):
    """List up to three newer pairs, newest first, that share at least three significant terms with the item."""
    wanted = terms(item["text"])
    hits = []
    if len(wanted) < MIN_SHARED_TERMS:
        return hits
    for absolute, words in indexed:
        if absolute <= item["turn"]:
            break
        if len(wanted & words) >= MIN_SHARED_TERMS:
            hits.append(absolute)
            if len(hits) == MAX_MENTIONS:
                break
    return hits


def build_state(turns, *, offset, carried):
    """Merge carried items from dropped pairs with items re-derived from this request, then apply freshness and limits."""
    window, skipped = extract(turns, offset)
    kept_carried = [
        {**dict(item), "origin": "carried"}
        for item in carried
        if item["turn"] <= offset
    ]
    state = resolve(kept_carried + window)
    indexed = [
        (
            offset + turn["number"],
            terms(" ".join(row["content"] for row in turn["messages"])),
        )
        for turn in reversed(turns)
    ]
    mentions = {}
    for index, item in enumerate(state):
        if item["status"] == "active" and item["kind"] in RENDERED:
            found = newer_mentions(item, indexed)
            if found:
                mentions[index] = found
    dropped = limit(state, mentions)
    rendered = rows(state, mentions)
    raw = encode_capsule(rendered) if rendered else None
    kept = prune(state)
    positions = {id(item): position for position, item in enumerate(kept)}
    return dict(
        items=kept,
        mentions={
            positions[id(state[index])]: hits
            for index, hits in mentions.items()
            if state[index]["status"] == "active"
        },
        raw=raw,
        skipped_lines=skipped,
        dropped_active=dropped,
        carried=len(kept_carried),
        carried_recomputed=len(carried) - len(kept_carried),
    )


def render(built):
    """Return the capsule computed by build_state, or None when no active item exists."""
    return built["raw"]
