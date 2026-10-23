"""Test strict skill schemas and exact owner-reviewed install authority, updates, expiry, revocation and content redaction."""

import json
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
from uuid import uuid4

import pytest

from src.application.services.skill_contract import (
    SkillError,
    SkillRegistry,
    parse_manifest,
)


def manifest(**changes):
    """Create an authored skill prompt with no executable authority or real user source content."""
    value = dict(
        schema_version=1,
        id="source-reader",
        version="1.0.0",
        description="Explain reviewed source files.",
        instructions="private-skill-prompt: read only the files explicitly in scope.",
        permissions=["workspace.read"],
    )
    value.update(changes)
    return json.dumps(value, ensure_ascii=False).encode()


def installed_fixture(registry=None):
    """Install one explicitly trusted exact skill under fresh trusted disposable identities."""
    registry = registry or SkillRegistry()
    owner, workspace = uuid4(), uuid4()
    raw = manifest()
    review = registry.review(owner, workspace, raw)
    installed = registry.install(
        owner,
        workspace,
        review.identifier,
        raw,
        reviewed_sha256=review.manifest_sha256,
        explicit_trust=True,
    )
    return registry, owner, workspace, installed


@pytest.mark.parametrize(
    "changes",
    [
        {"schema_version": True},
        {"schema_version": 2},
        {"id": "../escape"},
        {"id": "Uppercase"},
        {"version": "01.0.0"},
        {"version": "1.0"},
        {"version": "1.0.0; shell"},
        {"description": ""},
        {"instructions": "\x00bad"},
        {"instructions": "x" * 24001},
        {"permissions": []},
        {"permissions": ["workspace.read", "workspace.read"]},
        {"permissions": ["shell"]},
        {"permissions": ["patch.apply"]},
        {"permissions": True},
        {"trusted": True},
        {"model": "unrestricted"},
        {"endpoint": "https://attacker.example"},
    ],
)
def test_manifest_cannot_self_trust_register_or_widen_capabilities(changes):
    """Reject malformed schemas and undeclared authorities before any review or native call."""
    with pytest.raises(SkillError, match="invalid_manifest"):
        parse_manifest(manifest(**changes))


@pytest.mark.parametrize(
    "raw",
    [
        b"{}",
        b"[]",
        b"{",
        b"\xff",
        b"x" * 32769,
        b'{"schema_version":1,"schema_version":1}',
    ],
)
def test_manifest_bounds_and_ambiguous_json_fail_closed(raw):
    """Reject complete-byte ambiguity, invalid UTF8 and excessive input without partial parsing."""
    with pytest.raises(SkillError):
        parse_manifest(raw)


def test_exact_review_install_and_permission_subset_are_immutable_and_redacted(caplog):
    """Require host trust and expose only exact installed capabilities without logging prompt content."""
    caplog.set_level("INFO")
    registry, owner, workspace, installed = installed_fixture()
    registry.authorize(owner, workspace, installed, "workspace.read")
    with pytest.raises(SkillError, match="permission_denied"):
        registry.authorize(owner, workspace, installed, "workspace.search")
    with pytest.raises(FrozenInstanceError):
        installed.manifest.version = "2.0.0"
    assert "private-skill-prompt" not in caplog.text
    assert "private-skill-prompt" not in repr(installed)


@pytest.mark.parametrize("trust", [False, 1, "true", None])
def test_install_requires_explicit_host_trust_not_truthiness(trust):
    """Prevent model-like values from coercing into a user confirmation."""
    registry = SkillRegistry()
    owner, workspace = uuid4(), uuid4()
    raw = manifest()
    review = registry.review(owner, workspace, raw)
    with pytest.raises(SkillError, match="trust_required"):
        registry.install(
            owner,
            workspace,
            review.identifier,
            raw,
            reviewed_sha256=review.manifest_sha256,
            explicit_trust=trust,
        )


def test_content_or_permission_update_cannot_reuse_a_review():
    """Bind approval to raw bytes rather than ID, version ordering or unchanged descriptive fields."""
    registry = SkillRegistry()
    owner, workspace = uuid4(), uuid4()
    raw = manifest()
    review = registry.review(owner, workspace, raw)
    for changed in [
        manifest(version="1.0.1"),
        manifest(instructions="Changed"),
        manifest(permissions=["workspace.search"]),
        raw + b" ",
    ]:
        with pytest.raises(SkillError, match="review_mismatch"):
            registry.install(
                owner,
                workspace,
                review.identifier,
                changed,
                reviewed_sha256=review.manifest_sha256,
                explicit_trust=True,
            )


def test_owner_workspace_replay_and_serialized_handle_cannot_grant_tools():
    """Refuse cross-owner approvals, one-shot replay and copies of an installed capability."""
    registry = SkillRegistry()
    owner, workspace = uuid4(), uuid4()
    raw = manifest()
    review = registry.review(owner, workspace, raw)
    for who, where in [(uuid4(), workspace), (owner, uuid4())]:
        with pytest.raises(SkillError, match="invalid_scope"):
            registry.install(
                who,
                where,
                review.identifier,
                raw,
                reviewed_sha256=review.manifest_sha256,
                explicit_trust=True,
            )
    installed = registry.install(
        owner,
        workspace,
        review.identifier,
        raw,
        reviewed_sha256=review.manifest_sha256,
        explicit_trust=True,
    )
    with pytest.raises(SkillError, match="review_required"):
        registry.install(
            owner,
            workspace,
            review.identifier,
            raw,
            reviewed_sha256=review.manifest_sha256,
            explicit_trust=True,
        )
    with pytest.raises(SkillError, match="not_installed"):
        registry.authorize(owner, workspace, replace(installed), "workspace.read")
    with pytest.raises(SkillError, match="invalid_scope"):
        registry.authorize(uuid4(), workspace, installed, "workspace.read")


def test_expiry_and_nonfinite_host_clocks_cannot_create_perpetual_trust():
    """Use the exact monotonic boundary and reject invalid clock observations."""
    clock = [0.0]
    registry = SkillRegistry(clock=lambda: clock[0])
    owner, workspace = uuid4(), uuid4()
    raw = manifest()
    review = registry.review(owner, workspace, raw)
    clock[0] = 120
    with pytest.raises(SkillError, match="review_expired"):
        registry.install(
            owner,
            workspace,
            review.identifier,
            raw,
            reviewed_sha256=review.manifest_sha256,
            explicit_trust=True,
        )
    for value in [float("nan"), float("inf"), -1, True]:
        clock[0] = value
        with pytest.raises(SkillError, match="review_expired"):
            registry.review(owner, workspace, raw)


def test_uninstall_and_shutdown_revoke_handles_without_persisting_grants():
    """Invalidate every old handle rather than restoring trust from serialized metadata on restart."""
    registry, owner, workspace, installed = installed_fixture()
    registry.uninstall(owner, workspace, installed)
    with pytest.raises(SkillError, match="not_installed"):
        registry.authorize(owner, workspace, installed, "workspace.read")
    registry, owner, workspace, installed = installed_fixture()
    registry.shutdown()
    assert not registry.reviews and not registry.installed
    with pytest.raises(SkillError, match="closed"):
        registry.authorize(owner, workspace, installed, "workspace.read")
    with pytest.raises(SkillError, match="not_installed"):
        SkillRegistry().authorize(owner, workspace, installed, "workspace.read")


def test_shipped_manifest_is_inert_and_uses_only_the_declared_existing_read_tool():
    """Validate the complete reviewable example without installing a production skill or changing host capabilities."""
    value = parse_manifest(Path("configs/skills/source-reader.v1.json").read_bytes())
    assert value.identifier == "source-reader" and value.version == "1.0.0"
    assert value.permissions == ("workspace.read",)


def test_pending_reviews_are_bounded_and_only_expired_entries_are_reclaimed():
    """Reject review floods without silently evicting a still-valid user confirmation."""
    clock = [0.0]
    registry = SkillRegistry(clock=lambda: clock[0])
    owner, workspace = uuid4(), uuid4()
    for _ in range(32):
        registry.review(owner, workspace, manifest())
    with pytest.raises(SkillError, match="capacity"):
        registry.review(owner, workspace, manifest())
    assert len(registry.reviews) == 32
    clock[0] = 120.0
    registry.review(owner, workspace, manifest())
    assert len(registry.reviews) == 1


def test_new_version_needs_fresh_trust_and_never_automatically_changes_old_permissions():
    """Keep old exact installs scoped while requiring an independent reviewed grant for an updated manifest."""
    registry, owner, workspace, first = installed_fixture()
    raw = manifest(version="2.0.0", permissions=["workspace.search"])
    review = registry.review(owner, workspace, raw)
    second = registry.install(
        owner,
        workspace,
        review.identifier,
        raw,
        reviewed_sha256=review.manifest_sha256,
        explicit_trust=True,
    )
    registry.authorize(owner, workspace, first, "workspace.read")
    registry.authorize(owner, workspace, second, "workspace.search")
    with pytest.raises(SkillError, match="permission_denied"):
        registry.authorize(owner, workspace, first, "workspace.search")
    with pytest.raises(SkillError, match="permission_denied"):
        registry.authorize(owner, workspace, second, "workspace.read")
