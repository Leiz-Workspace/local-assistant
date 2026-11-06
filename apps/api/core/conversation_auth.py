"""Authenticate local conversation principals from protected, reloadable token digests."""

import hashlib
import hmac
import json
import logging
import os
import re
import stat
from pathlib import Path
from uuid import UUID

from fastapi import HTTPException, Request

logger = logging.getLogger(__name__)


def load_principals(path: Path) -> dict[str, UUID]:
    """Load digest-to-principal bindings from an owner-only regular file without symlinks."""
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, "r", encoding="utf-8") as source:
        info = os.fstat(source.fileno())
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.geteuid()
            or info.st_mode & 0o077
            or info.st_size > 65536
        ):
            raise ValueError("Authentication file must be a private regular file")
        payload = json.load(source)
    if (
        not isinstance(payload, dict)
        or set(payload) != {"principals"}
        or not isinstance(payload["principals"], list)
        or not 1 <= len(payload["principals"]) <= 100
    ):
        raise ValueError("Invalid principal configuration")
    result = {}
    for item in payload["principals"]:
        if not isinstance(item, dict) or set(item) != {"id", "token_sha256"}:
            raise ValueError("Invalid principal record")
        if not isinstance(item["id"], str):
            raise ValueError("Invalid principal identity")
        digest = item["token_sha256"]
        if (
            not isinstance(digest, str)
            or re.fullmatch(r"[0-9a-f]{64}", digest) is None
            or digest in result
        ):
            raise ValueError("Invalid or duplicate token digest")
        result[digest] = UUID(item["id"])
    return result


async def authenticate_principal(request: Request) -> UUID:
    """Require a valid bearer credential and fail closed if identity configuration is absent."""
    path = os.environ.get("ASSISTANT_AUTH_FILE")
    try:
        if not path:
            raise ValueError("Missing principal configuration")
        principals = load_principals(Path(path))
    except (OSError, ValueError, TypeError, KeyError):
        logger.error("conversation_auth_configuration_unavailable")
        raise HTTPException(
            503,
            detail={
                "code": "auth_unavailable",
                "message": "Conversation authentication unavailable.",
            },
        ) from None
    headers = request.headers.getlist("authorization")
    value = headers[0] if len(headers) == 1 else ""
    scheme, separator, token = value.partition(" ")
    digest = hashlib.sha256(token.encode()).hexdigest()
    principal = None
    if (
        separator
        and scheme.lower() == "bearer"
        and 32 <= len(token) <= 512
        and token.isascii()
        and not any(character.isspace() for character in token)
    ):
        for expected, identity in principals.items():
            if hmac.compare_digest(digest, expected):
                principal = identity
    if principal is None:
        logger.warning("conversation_authentication_denied")
        raise HTTPException(
            401,
            headers={"WWW-Authenticate": "Bearer"},
            detail={
                "code": "authentication_required",
                "message": "Valid bearer credential required.",
            },
        )
    logger.info("conversation_principal_authenticated principal_id=%s", principal)
    return principal
