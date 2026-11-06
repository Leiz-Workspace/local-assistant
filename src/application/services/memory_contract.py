"""Define strict four-class consent/provenance memory contracts without persistence, inference or source authorization."""

import hashlib
import logging
from datetime import datetime, timedelta
from typing import Annotated, Literal
from uuid import UUID

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

logger = logging.getLogger(__name__)
MemoryKind = Literal["session", "episodic", "preference", "project"]
SHA256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


def retention_cap(kind):
    """Return the declared class lifetime cap without choosing an expiry for the caller."""
    if kind not in ("session", "episodic", "preference", "project"):
        raise ValueError("memory_kind_invalid")
    return timedelta(hours=24) if kind == "session" else timedelta(days=365)


def bounded_text(value):
    """Reject blank or oversized lexical content without normalization, truncation or content logging."""
    if (
        not isinstance(value, str)
        or not value.strip()
        or "\0" in value
        or len(value.encode()) > 4096
    ):
        raise ValueError("memory_text_invalid")
    return value


class Contract(BaseModel):
    """Reject coercion and unknown fields while freezing typed memory snapshot values."""

    model_config = ConfigDict(
        extra="forbid", strict=True, frozen=True, revalidate_instances="always"
    )

    @model_validator(mode="after")
    def audit(self):
        """Record only schema identity on successful validation, excluding private values."""
        logger.info("memory_contract_validated schema=%s", type(self).__name__)
        return self


class MemorySettings(Contract):
    """Represent one current owner epoch with memory and extraction independently default-disabled."""

    owner_id: UUID
    revision: int = Field(ge=1)
    enabled: bool = False
    extraction_enabled: bool = False
    updated_at: AwareDatetime

    @model_validator(mode="after")
    def flags(self):
        """Prevent extraction enablement while all memory use is disabled."""
        if self.extraction_enabled and not self.enabled:
            raise ValueError("memory_extraction_requires_enablement")
        return self


class MemoryConsent(Contract):
    """Bind immutable consent identity to one owner, class, scope and settings epoch with explicit expiry."""

    id: UUID
    owner_id: UUID
    kind: MemoryKind
    scope_id: UUID
    settings_revision: int = Field(ge=1)
    policy_version: Literal[1] = 1
    allow_extraction: bool = False
    granted_at: AwareDatetime
    expires_at: AwareDatetime
    revoked_at: AwareDatetime | None = None

    @field_validator("policy_version", mode="before")
    @classmethod
    def policy_integer(cls, value):
        """Reject booleans that would otherwise compare equal to the fixed integer policy version."""
        if type(value) is not int:
            raise ValueError("memory_policy_version_invalid")
        return value

    @model_validator(mode="after")
    def scope_and_lifetime(self):
        """Bound owner-wide scope, class retention and ordered immutable receipt timestamps."""
        if self.kind in ("episodic", "preference") and self.scope_id != self.owner_id:
            raise ValueError("memory_scope_invalid")
        if (
            not timedelta(0)
            < self.expires_at - self.granted_at
            <= retention_cap(self.kind)
        ):
            raise ValueError("memory_consent_retention_invalid")
        if self.revoked_at is not None and self.revoked_at < self.granted_at:
            raise ValueError("memory_revocation_invalid")
        return self


class ManualEvidence(Contract):
    """Record exact stored manual UTF-8 content identity without inventing an external source or producer."""

    kind: Literal["manual"]
    content_sha256: SHA256


class QuoteEvidence(Contract):
    """Describe a literal Unicode source-field quote whose actual source must be revalidated by the service."""

    quote: str = Field(min_length=1, max_length=4096)
    start: int = Field(ge=0)
    end: int = Field(ge=1)

    @model_validator(mode="after")
    def quote_span(self):
        """Require complete bounded lexical text and exact code-point span length."""
        bounded_text(self.quote)
        if self.end - self.start != len(self.quote):
            raise ValueError("memory_quote_span_invalid")
        return self


class MessageEvidence(QuoteEvidence):
    """Bind an exact user-message quote to conversation/message IDs and the complete source content hash."""

    kind: Literal["conversation_message"]
    conversation_id: UUID
    message_id: UUID
    role: Literal["user"]
    content_sha256: SHA256


class FileEvidence(QuoteEvidence):
    """Bind a native lexical file field quote to the original file hash and file-specific locator."""

    kind: Literal["file_quote"]
    file_id: UUID
    source_sha256: SHA256
    locator: str = Field(min_length=1, max_length=1024)
    field: Literal["text", "value", "formula", "cached_value"]

    @model_validator(mode="after")
    def native_locator(self):
        """Reject cross-file or empty native locations before any source lookup is attempted."""
        prefix = "file:" + str(self.file_id) + "#"
        if (
            not self.locator.startswith(prefix)
            or len(self.locator) == len(prefix)
            or "\0" in self.locator
            or len(self.locator.encode()) > 1024
        ):
            raise ValueError("memory_file_locator_invalid")
        return self


Evidence = Annotated[
    ManualEvidence | MessageEvidence | FileEvidence, Field(discriminator="kind")
]


class MemoryRecord(Contract):
    """Represent bounded untrusted memory with class/scope, explicit receipt, provenance and retention."""

    id: UUID
    owner_id: UUID
    kind: MemoryKind
    scope_id: UUID
    consent_id: UUID
    text: str = Field(min_length=1, max_length=4096)
    method: Literal["manual", "extracted"]
    model_id: str | None = Field(default=None, min_length=1, max_length=256)
    provenance: Evidence
    created_at: AwareDatetime
    updated_at: AwareDatetime
    expires_at: AwareDatetime
    version: int = Field(default=1, ge=1)
    content_trust: Literal["untrusted"] = "untrusted"

    @model_validator(mode="after")
    def capture_contract(self):
        """Validate manual hashes, extracted provenance, source scope and bounded capture timestamps."""
        bounded_text(self.text)
        if self.model_id is not None and (
            "\0" in self.model_id or len(self.model_id.encode()) > 256
        ):
            raise ValueError("memory_producer_invalid")
        if self.kind in ("episodic", "preference") and self.scope_id != self.owner_id:
            raise ValueError("memory_scope_invalid")
        if (
            not timedelta(0)
            < self.expires_at - self.created_at
            <= retention_cap(self.kind)
            or self.updated_at < self.created_at
        ):
            raise ValueError("memory_record_retention_invalid")
        if self.method == "manual":
            if (
                not isinstance(self.provenance, ManualEvidence)
                or self.model_id is not None
                or hashlib.sha256(self.text.encode()).hexdigest()
                != self.provenance.content_sha256
            ):
                raise ValueError("memory_manual_provenance_invalid")
        elif isinstance(self.provenance, ManualEvidence) or not (
            self.model_id and self.model_id.strip()
        ):
            raise ValueError("memory_extracted_provenance_invalid")
        if (
            self.kind == "session"
            and isinstance(self.provenance, MessageEvidence)
            and self.scope_id != self.provenance.conversation_id
        ):
            raise ValueError("memory_session_source_invalid")
        return self


class MemoryBundle(Contract):
    """Bind structural snapshots without claiming they were freshly read or owner-authorized by storage."""

    settings: MemorySettings
    consent: MemoryConsent
    record: MemoryRecord

    @model_validator(mode="after")
    def binding(self):
        """Reject mismatched receipts, owners, classes, scopes and capture outside the receipt lifetime."""
        record, consent = self.record, self.consent
        if (
            self.settings.owner_id != record.owner_id
            or record.owner_id != consent.owner_id
            or record.consent_id != consent.id
            or record.kind != consent.kind
            or record.scope_id != consent.scope_id
            or record.created_at < consent.granted_at
            or record.expires_at > consent.expires_at
            or (record.method == "extracted" and not consent.allow_extraction)
        ):
            raise ValueError("memory_consent_binding_invalid")
        return self


class MemoryPolicyError(Exception):
    """Expose only a stable policy rejection code without retaining private text, hashes or identifiers."""

    def __init__(self, code):
        """Attach and audit one content-free rejection code."""
        super().__init__(code)
        self.code = code
        logger.warning("memory_policy_rejected code=%s", code)


def authorize_memory(bundle, principal, now, *, action):
    """Authorize supplied current write/use snapshots; callers must independently lock state and verify real sources."""
    if (
        not isinstance(bundle, MemoryBundle)
        or not isinstance(principal, UUID)
        or not isinstance(now, datetime)
        or now.tzinfo is None
        or now.utcoffset() is None
        or action not in ("write", "use")
    ):
        raise MemoryPolicyError("memory_authorization_invalid")
    try:
        bundle = MemoryBundle.model_validate(bundle)
    except ValueError:
        raise MemoryPolicyError("memory_authorization_invalid") from None
    settings, consent, record = bundle.settings, bundle.consent, bundle.record
    if principal != record.owner_id:
        raise MemoryPolicyError("memory_not_found")
    if not settings.enabled:
        raise MemoryPolicyError("memory_disabled")
    if (
        consent.settings_revision != settings.revision
        or consent.revoked_at is not None
        or settings.updated_at > consent.granted_at
        or not consent.granted_at <= now < consent.expires_at
        or settings.updated_at > now
        or not record.created_at <= record.updated_at <= now
        or now >= record.expires_at
    ):
        raise MemoryPolicyError("memory_consent_inactive")
    if (
        action == "write"
        and record.method == "extracted"
        and not (settings.extraction_enabled and consent.allow_extraction)
    ):
        raise MemoryPolicyError("memory_extraction_disabled")
    logger.info("memory_authorized action=%s kind=%s", action, record.kind)
    return record
