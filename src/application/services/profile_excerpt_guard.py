"""Reject profile replies outside host-pinned literal excerpt boundaries without rewriting content or invoking inference."""

import hashlib
import logging
import re
from dataclasses import dataclass
from uuid import UUID

from src.application.ports.inference import CompletionResult
from src.application.services.profile_prompts import ProfileReply, template_digest
from src.application.services.workspace_requests import parse_workspace_json

logger = logging.getLogger(__name__)


class ExcerptError(Exception):
    """Expose finite rejection codes without including source text, reply content or actor identifiers."""

    def __init__(self, code):
        """Restrict audit output to declared policy, provenance and formatting outcomes."""
        self.code = (
            code
            if code
            in {
                "invalid_policy",
                "invalid_scope",
                "invalid_reply",
                "invalid_json",
                "invalid_citations",
                "excerpt_mismatch",
            }
            else "invalid_reply"
        )
        super().__init__(self.code)
        logger.warning("profile_excerpt_rejected code=%s", self.code)


@dataclass(frozen=True, slots=True, repr=False)
class ExcerptReceipt:
    """Bind unchanged reply bytes to verified literal Unicode spans, without certifying answer semantics or granting capabilities."""

    prompt_sha256: str
    reply_sha256: str
    spans: tuple[tuple[str, str, int, int], ...]


@dataclass(frozen=True, slots=True, repr=False, init=False)
class ProfileExcerptGuard:
    """Snapshot one trusted host's exact source/excerpt contract for a scoped text-only prompt, with no inference or repair path."""

    owner: UUID
    workspace: UUID
    profile: str
    model_id: str
    template_sha256: str
    prompt_sha256: str
    source_sha256: tuple[tuple[str, str], ...]
    excerpts: tuple[tuple[str, str, int, int], ...]
    answer_fields: tuple[str, ...]

    def __init__(
        self,
        owner,
        workspace,
        *,
        profile,
        model_id,
        prompt_sha256,
        sources,
        excerpts,
        answer_fields,
    ):
        """Require bounded immutable host inputs and unambiguous codepoint spans before accepting any model reply."""
        try:
            if (
                type(owner) is not UUID
                or type(workspace) is not UUID
                or type(profile) is not str
                or profile not in {"core", "unrestricted"}
                or type(model_id) is not str
                or not 1 <= len(model_id) <= 200
                or not model_id.isascii()
                or type(prompt_sha256) is not str
                or re.fullmatch(r"[0-9a-f]{64}", prompt_sha256) is None
                or type(sources) is not tuple
                or not 1 <= len(sources) <= 8
                or type(excerpts) is not tuple
                or len(excerpts) != len(sources)
                or type(answer_fields) is not tuple
                or not 1 <= len(answer_fields) <= 16
            ):
                raise ValueError()
            fields = set()
            for field in answer_fields:
                if (
                    type(field) is not str
                    or re.fullmatch(r"[A-Za-z0-9_]{1,64}", field) is None
                    or field == "citations"
                    or field in fields
                ):
                    raise ValueError()
                fields.add(field)
            texts, hashes, size = {}, [], 0
            for source in sources:
                if type(source) is not tuple or len(source) != 2:
                    raise ValueError()
                identifier, text = source
                if (
                    type(identifier) is not str
                    or re.fullmatch(r"[A-Za-z0-9_-]{1,64}", identifier) is None
                    or identifier in texts
                    or type(text) is not str
                    or not 1 <= len(text) <= 4096
                    or not text.strip()
                ):
                    raise ValueError()
                encoded = text.encode("utf-8")
                size += len(encoded)
                texts[identifier] = text
                hashes.append((identifier, hashlib.sha256(encoded).hexdigest()))
            if size > 16384:
                raise ValueError()
            pinned, seen = [], set()
            for excerpt in excerpts:
                if type(excerpt) is not tuple or len(excerpt) != 3:
                    raise ValueError()
                identifier, start, end = excerpt
                if (
                    type(identifier) is not str
                    or identifier not in texts
                    or identifier in seen
                    or type(start) is not int
                    or type(end) is not int
                    or not 0 <= start < end <= len(texts[identifier])
                ):
                    raise ValueError()
                text = texts[identifier]
                quote = text[start:end]
                if (
                    not quote.strip()
                    or text.find(quote) != start
                    or text.find(quote, start + 1) != -1
                ):
                    raise ValueError()
                seen.add(identifier)
                pinned.append((identifier, quote, start, end))
            values = dict(
                owner=owner,
                workspace=workspace,
                profile=profile,
                model_id=model_id,
                template_sha256=template_digest(profile),
                prompt_sha256=prompt_sha256,
                source_sha256=tuple(hashes),
                excerpts=tuple(pinned),
                answer_fields=answer_fields,
            )
        except (ValueError, TypeError, UnicodeError):
            raise ExcerptError("invalid_policy") from None
        for key, value in values.items():
            object.__setattr__(self, key, value)
        logger.info("profile_excerpt_policy_bound sources=%d", len(self.excerpts))

    def validate(self, owner, workspace, reply):
        """Verify host scope/provenance and exact JSON excerpts; withhold any mismatch without changing or retrying the reply."""
        if (
            type(owner) is not UUID
            or type(workspace) is not UUID
            or (owner, workspace) != (self.owner, self.workspace)
        ):
            raise ExcerptError("invalid_scope")
        if type(reply) is not ProfileReply or (
            reply.owner_id,
            reply.workspace_id,
            reply.profile,
            reply.model_id,
            reply.template_sha256,
            reply.prompt_sha256,
            reply.source_sha256,
        ) != (
            self.owner,
            self.workspace,
            self.profile,
            self.model_id,
            self.template_sha256,
            self.prompt_sha256,
            self.source_sha256,
        ):
            raise ExcerptError("invalid_reply")
        result = reply.result
        if (
            type(result) is not CompletionResult
            or result.model_id != self.model_id
            or result.preset_selected != "fast"
            or result.finish_reason != "stop"
            or type(result.content) is not str
            or len(result.content) > 16384
            or any(
                value is not None and (type(value) is not int or value < 0)
                for value in (
                    result.input_tokens,
                    result.output_tokens,
                    result.reasoning_tokens,
                    result.latency_ms,
                )
            )
        ):
            raise ExcerptError("invalid_reply")
        try:
            raw = result.content.encode("utf-8")
            body = parse_workspace_json(raw)
        except Exception:
            raise ExcerptError("invalid_json") from None
        if set(body) != {*self.answer_fields, "citations"}:
            raise ExcerptError("invalid_json")
        citations = body["citations"]
        if type(citations) is not list or len(citations) != len(self.excerpts):
            raise ExcerptError("invalid_citations")
        expected = {identifier: quote for identifier, quote, _, _ in self.excerpts}
        seen = set()
        for citation in citations:
            if type(citation) is not dict or set(citation) != {"source_id", "quote"}:
                raise ExcerptError("invalid_citations")
            identifier, quote = citation["source_id"], citation["quote"]
            if (
                type(identifier) is not str
                or identifier not in expected
                or identifier in seen
                or type(quote) is not str
            ):
                raise ExcerptError("invalid_citations")
            if quote != expected[identifier]:
                raise ExcerptError("excerpt_mismatch")
            seen.add(identifier)
        hashes = dict(self.source_sha256)
        receipt = ExcerptReceipt(
            self.prompt_sha256,
            hashlib.sha256(raw).hexdigest(),
            tuple(
                (identifier, hashes[identifier], start, end)
                for identifier, _, start, end in self.excerpts
            ),
        )
        logger.info("profile_excerpt_verified sources=%d", len(receipt.spans))
        return receipt
