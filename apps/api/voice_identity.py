"""Bind temporary browser pairing and sessions to reloadable existing principal credentials."""

import hashlib
import logging
import secrets
import time
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from apps.api.core.conversation_auth import load_principals

LOGGER = logging.getLogger(__name__)


class IdentityDenied(RuntimeError):
    """Reject missing, expired or revoked voice identities without revealing credentials."""


@dataclass(frozen=True, slots=True, repr=False)
class Actor:
    """Identify an authenticated principal and its revocable credential digest, never its token."""

    principal: UUID
    credential: str


class VoiceIdentity:
    """Own finite single-use pairing grants and opaque principal-bound in-memory UI sessions."""

    def __init__(self, path, clock=time.monotonic):
        """Bind an operator-supplied private principal file without reading it at page creation."""
        self.path, self.clock = Path(path), clock
        self.grants, self.sessions = {}, {}

    def valid(self, actor):
        """Revalidate the exact credential-to-principal mapping on every privileged action."""
        try:
            return load_principals(self.path).get(actor.credential) == actor.principal
        except (OSError, ValueError, TypeError, KeyError):
            LOGGER.warning("voice_identity_store_unavailable")
            return False

    def prune(self):
        """Expire stale credentials and TTLs without retaining user content or unbounded records."""
        now = self.clock()
        for store in (self.grants, self.sessions):
            for key, (actor, expiry) in list(store.items()):
                if expiry <= now or not self.valid(actor):
                    del store[key]

    def issue(self, actor):
        """Mint one short-lived pairing code only for a currently authenticated operator."""
        self.prune()
        if not self.valid(actor) or len(self.grants) >= 64:
            raise IdentityDenied("authentication_required")
        code = secrets.token_urlsafe(32)
        key = hashlib.sha256(code.encode()).hexdigest()
        self.grants[key] = (actor, self.clock() + 120)
        LOGGER.info("voice_pairing_issued")
        return code

    def redeem(self, code):
        """Consume a pairing grant exactly once and return an opaque bounded session cookie."""
        self.prune()
        if type(code) is not str or not 32 <= len(code) <= 128:
            raise IdentityDenied("authentication_required")
        item = self.grants.pop(hashlib.sha256(code.encode()).hexdigest(), None)
        if item is None or len(self.sessions) >= 64 or not self.valid(item[0]):
            LOGGER.warning("voice_pairing_denied")
            raise IdentityDenied("authentication_required")
        cookie = secrets.token_urlsafe(32)
        self.sessions[hashlib.sha256(cookie.encode()).hexdigest()] = (
            item[0],
            self.clock() + 900,
        )
        LOGGER.info("voice_pairing_redeemed")
        return cookie

    def resolve(self, cookie):
        """Resolve only a live principal-bound session after checking current revocation state."""
        self.prune()
        if type(cookie) is not str or not 32 <= len(cookie) <= 128:
            raise IdentityDenied("authentication_required")
        item = self.sessions.get(hashlib.sha256(cookie.encode()).hexdigest())
        if item is None or not self.valid(item[0]):
            raise IdentityDenied("authentication_required")
        return item[0]

    def clear(self):
        """Erase all temporary grant/session capabilities during joined application shutdown."""
        self.grants.clear()
        self.sessions.clear()
        LOGGER.info("voice_identity_closed")
