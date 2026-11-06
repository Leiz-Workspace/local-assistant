"""Validate versioned skill manifests and bind explicit owner-reviewed trust without registering tools or persisting prompt contents."""

import hashlib
import json
import logging
import math
import re
import threading
import time
from dataclasses import dataclass
from uuid import UUID, uuid4

from src.application.services.workspace_tool_contracts import TOOL_REGISTRY

logger = logging.getLogger(__name__)
MAX_MANIFEST_BYTES = 32768
MAX_REVIEWS = 32
MAX_INSTALLATIONS = 64
REVIEW_SECONDS = 120


class SkillError(Exception):
    """Expose finite schema/trust/runtime failures without untrusted prompt or exception text."""

    def __init__(self, code):
        """Keep caller-visible audit failures inside a closed error vocabulary."""
        self.code = (
            code
            if code
            in {
                "invalid_manifest",
                "invalid_scope",
                "review_required",
                "review_expired",
                "review_mismatch",
                "trust_required",
                "capacity",
                "already_installed",
                "not_installed",
                "permission_denied",
                "attempt_limit",
                "closed",
            }
            else "invalid_manifest"
        )
        super().__init__(self.code)
        logger.warning("skill_rejected code=%s", self.code)


def unique_object(pairs):
    """Reject duplicate JSON keys at every nesting level before schema validation."""
    result = {}
    for key, value in pairs:
        if key in result:
            raise SkillError("invalid_manifest")
        result[key] = value
    return result


@dataclass(frozen=True, slots=True, repr=False)
class SkillManifest:
    """Freeze a validated prompt package and finite declared tool permissions without executable authority."""

    identifier: str
    version: str
    description: str
    instructions: str
    permissions: tuple[str, ...]
    raw_sha256: str
    schema_version: int = 1


def parse_manifest(raw):
    """Require exact bounded UTF8 JSON and existing finite tools; manifest content cannot assert installation trust."""
    try:
        if type(raw) is not bytes or not 1 <= len(raw) <= MAX_MANIFEST_BYTES:
            raise ValueError()
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=unique_object)
        if type(value) is not dict or set(value) != {
            "schema_version",
            "id",
            "version",
            "description",
            "instructions",
            "permissions",
        }:
            raise ValueError()
        if type(value["schema_version"]) is not int or value["schema_version"] != 1:
            raise ValueError()
        if (
            type(value["id"]) is not str
            or re.fullmatch(r"[a-z][a-z0-9-]{0,63}", value["id"]) is None
        ):
            raise ValueError()
        if (
            type(value["version"]) is not str
            or len(value["version"]) > 32
            or re.fullmatch(
                r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)",
                value["version"],
            )
            is None
        ):
            raise ValueError()
        for name, bound in (("description", 512), ("instructions", 24000)):
            item = value[name]
            if (
                type(item) is not str
                or not item.strip()
                or len(item.encode()) > bound
                or any(ord(c) < 32 and c not in "\n\t" for c in item)
            ):
                raise ValueError()
        permissions = value["permissions"]
        if (
            type(permissions) is not list
            or not 1 <= len(permissions) <= len(TOOL_REGISTRY)
            or any(
                type(name) is not str or name not in TOOL_REGISTRY
                for name in permissions
            )
            or len(set(permissions)) != len(permissions)
        ):
            raise ValueError()
        manifest = SkillManifest(
            value["id"],
            value["version"],
            value["description"],
            value["instructions"],
            tuple(permissions),
            hashlib.sha256(raw).hexdigest(),
        )
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise SkillError("invalid_manifest") from None
    logger.info(
        "skill_manifest_validated digest=%s permission_count=%d",
        manifest.raw_sha256,
        len(manifest.permissions),
    )
    return manifest


@dataclass(frozen=True, slots=True)
class SkillReview:
    """Expose a finite owner/workspace/raw-digest-bound review without granting tool or installation authority."""

    identifier: UUID
    owner_id: UUID
    workspace_id: UUID
    manifest_sha256: str
    skill_id: str
    version: str
    permissions: tuple[str, ...]
    expires_at: float


@dataclass(frozen=True, slots=True, repr=False)
class InstalledSkill:
    """Represent one registry-owned exact installation whose identity must still be checked before every tool call."""

    identifier: UUID
    owner_id: UUID
    workspace_id: UUID
    manifest: SkillManifest


class SkillRegistry:
    """Own bounded process-local trust reviews and installations with exact scope, expiry, replay and revocation controls."""

    def __init__(self, *, clock=time.monotonic):
        """Initialize empty trusted state without reading packages, contacting providers or opening workspace roots."""
        self.clock = clock
        self.reviews, self.installed = {}, {}
        self.closed = False
        self.lock = threading.RLock()
        logger.info("skill_registry_initialized")

    def scope(self, owner, workspace):
        """Require trusted typed scope and refuse all operations after shutdown."""
        if self.closed:
            raise SkillError("closed")
        if type(owner) is not UUID or type(workspace) is not UUID:
            raise SkillError("invalid_scope")

    def now(self):
        """Refuse nonfinite or invalid trusted clock values instead of creating nonexpiring install grants."""
        value = self.clock()
        if type(value) not in (float, int) or not math.isfinite(value) or value < 0:
            raise SkillError("review_expired")
        return value

    def review(self, owner, workspace, raw):
        """Publish the exact immutable review the host must show before explicit trust confirmation."""
        manifest = parse_manifest(raw)
        with self.lock:
            self.scope(owner, workspace)
            now = self.now()
            self.reviews = {
                key: row for key, row in self.reviews.items() if now < row.expires_at
            }
            if len(self.reviews) >= MAX_REVIEWS:
                raise SkillError("capacity")
            review = SkillReview(
                uuid4(),
                owner,
                workspace,
                manifest.raw_sha256,
                manifest.identifier,
                manifest.version,
                manifest.permissions,
                now + REVIEW_SECONDS,
            )
            self.reviews[review.identifier] = review
        logger.info("skill_review_created review_id=%s", review.identifier)
        return review

    def install(
        self, owner, workspace, review_id, raw, *, reviewed_sha256, explicit_trust
    ):
        """Consume one exact reviewed host trust confirmation and install only its unchanged scope/content/permissions."""
        manifest = parse_manifest(raw)
        with self.lock:
            self.scope(owner, workspace)
            if type(review_id) is not UUID or review_id not in self.reviews:
                raise SkillError("review_required")
            review = self.reviews[review_id]
            if review.owner_id != owner or review.workspace_id != workspace:
                raise SkillError("invalid_scope")
            if self.now() >= review.expires_at:
                del self.reviews[review_id]
                raise SkillError("review_expired")
            if explicit_trust is not True:
                raise SkillError("trust_required")
            if (
                type(reviewed_sha256) is not str
                or reviewed_sha256 != review.manifest_sha256
                or manifest.raw_sha256 != review.manifest_sha256
                or manifest.permissions != review.permissions
            ):
                raise SkillError("review_mismatch")
            key = (owner, workspace, manifest.identifier, manifest.version)
            if key in self.installed:
                raise SkillError("already_installed")
            if len(self.installed) >= MAX_INSTALLATIONS:
                raise SkillError("capacity")
            installed = InstalledSkill(uuid4(), owner, workspace, manifest)
            del self.reviews[review_id]
            self.installed[key] = installed
        logger.info(
            "skill_installed install_id=%s digest=%s",
            installed.identifier,
            manifest.raw_sha256,
        )
        return installed

    def authorize(self, owner, workspace, installed, permission):
        """Narrow runtime admission to a still-installed exact host-owned capability and its reviewed permission subset."""
        with self.lock:
            self.scope(owner, workspace)
            if (
                type(installed) is not InstalledSkill
                or type(installed.manifest) is not SkillManifest
                or installed.owner_id != owner
                or installed.workspace_id != workspace
            ):
                raise SkillError("invalid_scope")
            key = (
                owner,
                workspace,
                installed.manifest.identifier,
                installed.manifest.version,
            )
            if self.installed.get(key) is not installed:
                raise SkillError("not_installed")
            if (
                type(permission) is not str
                or permission not in installed.manifest.permissions
            ):
                raise SkillError("permission_denied")
        logger.info(
            "skill_tool_authorized install_id=%s permission=%s",
            installed.identifier,
            permission,
        )

    def uninstall(self, owner, workspace, installed):
        """Revoke one exact owner installation so stale handles can no longer authorize new work."""
        with self.lock:
            self.scope(owner, workspace)
            if (
                type(installed) is not InstalledSkill
                or type(installed.manifest) is not SkillManifest
                or installed.owner_id != owner
                or installed.workspace_id != workspace
            ):
                raise SkillError("invalid_scope")
            key = (
                owner,
                workspace,
                installed.manifest.identifier,
                installed.manifest.version,
            )
            if self.installed.get(key) is not installed:
                raise SkillError("not_installed")
            del self.installed[key]
        logger.info("skill_uninstalled install_id=%s", installed.identifier)

    def shutdown(self):
        """Invalidate every review/install in this process without persisting grants or prompt text."""
        with self.lock:
            self.closed = True
            self.reviews.clear()
            self.installed.clear()
        logger.info("skill_registry_closed")
