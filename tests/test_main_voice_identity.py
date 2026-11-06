"""Verify principal-bound pairing, expiry, replay, revocation and private-store denial without model calls."""

import hashlib
import json
from uuid import uuid4

import pytest

from apps.api.voice_identity import Actor, IdentityDenied, VoiceIdentity


def store(path, actors):
    """Write a disposable owner-only principal mapping with no real repository credentials."""
    path.write_text(
        json.dumps(
            {
                "principals": [
                    {"id": str(a.principal), "token_sha256": a.credential}
                    for a in actors
                ]
            }
        )
    )
    path.chmod(0o600)


def test_pairing_replay_expiry_revocation_and_opaque_cookie(tmp_path):
    """Reject reused grants and expired/rebound credentials while preserving stable principal identity."""
    actor = Actor(uuid4(), hashlib.sha256(b"neutral-test-credential").hexdigest())
    path = tmp_path / "identities.json"
    store(path, [actor])
    clock = [100.0]
    identities = VoiceIdentity(path, clock=lambda: clock[0])
    grant = identities.issue(actor)
    cookie = identities.redeem(grant)
    assert identities.resolve(cookie) == actor and grant != cookie
    assert actor.credential not in repr(identities.sessions)
    with pytest.raises(IdentityDenied):
        identities.redeem(grant)
    clock[0] = 1001.0
    with pytest.raises(IdentityDenied):
        identities.resolve(cookie)
    grant = identities.issue(actor)
    clock[0] += 121
    with pytest.raises(IdentityDenied):
        identities.redeem(grant)
    grant = identities.issue(actor)
    cookie = identities.redeem(grant)
    store(path, [Actor(uuid4(), actor.credential)])
    with pytest.raises(IdentityDenied):
        identities.resolve(cookie)
    assert not identities.valid(actor)


@pytest.mark.parametrize("value", [None, 123, "", "x" * 129, "x" * 32])
def test_invalid_grants_and_cookies_are_finite(tmp_path, value):
    """Reject malformed and unknown capabilities without opening a model or exposing store contents."""
    identities = VoiceIdentity(tmp_path / "missing")
    with pytest.raises(IdentityDenied):
        identities.redeem(value)
    with pytest.raises(IdentityDenied):
        identities.resolve(value)


def test_store_permissions_and_finite_grants(tmp_path):
    """Enforce the existing private-file requirements and refuse unbounded outstanding UI grants."""
    actor = Actor(uuid4(), "a" * 64)
    path = tmp_path / "store"
    store(path, [actor])
    identities = VoiceIdentity(path)
    for _ in range(64):
        identities.issue(actor)
    with pytest.raises(IdentityDenied):
        identities.issue(actor)
    path.chmod(0o644)
    assert not identities.valid(actor)
    path.chmod(0o600)
    identities.clear()
    assert not identities.grants and not identities.sessions
