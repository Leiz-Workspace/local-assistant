"""Review an exact local approval artifact with private credentials and explicit typed consent, without executing its action."""

import argparse
import getpass
import hashlib
import json
import logging
import re
from urllib.parse import urlsplit
from uuid import UUID

import httpx

from src.application.services.approvals import ApprovalError, scope_for

logger = logging.getLogger(__name__)


def validate_base_url(value):
    """Require an explicit literal loopback API base without credentials, query, fragment or remote/DNS destinations."""
    try:
        parsed = urlsplit(value)
        if (
            parsed.scheme not in {"http", "https"}
            or parsed.hostname not in {"127.0.0.1", "::1"}
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or parsed.path.rstrip("/") != "/api/v1"
        ):
            raise ValueError()
        if parsed.port is not None and not 1 <= parsed.port <= 65535:
            raise ValueError()
    except (ValueError, TypeError):
        raise ValueError("approval_cli_url_invalid") from None
    logger.info("approval_cli_loopback_validated")
    return value.rstrip("/")


def review_approval(
    base_url, identifier, token, *, read_line=input, write=print, transport=None
):
    """Fetch/display the full exact scope and require explicit typed owner consent without redirects, autoapproval or execution."""
    try:
        base_url = validate_base_url(base_url)
        if (
            type(identifier) is not UUID
            or not isinstance(token, str)
            or not 1 <= len(token) <= 512
            or any(ord(char) < 33 or ord(char) > 126 for char in token)
        ):
            raise ValueError()
        with httpx.Client(
            trust_env=False,
            follow_redirects=False,
            timeout=10,
            transport=transport,
            headers={"Authorization": "Bearer " + token},
        ) as client:
            url = base_url + "/approvals/" + str(identifier)
            response = client.get(url)
            if response.status_code != 200 or len(response.content) > 262144:
                raise ValueError()
            review = response.json()
            if not isinstance(review, dict) or review.get("request_id") != str(
                identifier
            ):
                raise ValueError()
            scope, raw = scope_for(
                UUID(review["owner_id"]),
                UUID(review["workspace_id"]),
                review["kind"],
                review["artifact"].encode("utf-8"),
            )
            if (
                scope.digest != review["scope_digest"]
                or hashlib.sha256(raw).hexdigest() != review["artifact_sha256"]
            ):
                raise ValueError()
            visible = {
                key: value for key, value in review.items() if key != "review_nonce"
            }
            write(json.dumps(visible, ensure_ascii=True, indent=2))
            if review["state"] != "pending":
                logger.info("approval_cli_not_pending request_id=%s", identifier)
                return 2
            if not isinstance(review.get("review_nonce"), str) or not re.fullmatch(
                r"[A-Za-z0-9_-]{43}", review["review_nonce"]
            ):
                raise ValueError()
            typed = read_line(
                "Type APPROVE "
                + str(identifier)
                + " or REJECT "
                + str(identifier)
                + ": "
            )
            if typed not in {"APPROVE " + str(identifier), "REJECT " + str(identifier)}:
                logger.info("approval_cli_cancelled request_id=%s", identifier)
                return 2
            decision = "approve" if typed.startswith("APPROVE ") else "reject"
            result = client.post(
                url + "/decision",
                json=dict(
                    decision=decision,
                    scope_digest=review["scope_digest"],
                    review_nonce=review["review_nonce"],
                ),
            )
            if result.status_code != 200:
                raise ValueError()
            event = result.json()
            if (
                event.get("request_id") != str(identifier)
                or event.get("scope_digest") != scope.digest
                or event.get("state")
                != ("approved" if decision == "approve" else "rejected")
            ):
                raise ValueError()
            write("Decision recorded. No action executed.")
            logger.info("approval_cli_decision_recorded request_id=%s", identifier)
            return 0
    except (EOFError, KeyboardInterrupt):
        logger.info("approval_cli_cancelled")
        return 2
    except (
        ApprovalError,
        httpx.HTTPError,
        OSError,
        ValueError,
        TypeError,
        KeyError,
        UnicodeError,
        AttributeError,
        RecursionError,
    ):
        logger.warning("approval_cli_failed_safely")
        try:
            write("Approval review failed; no action executed.")
        except OSError:
            logger.info("approval_cli_output_unavailable")
        return 1


def main():
    """Read a bearer token privately and invoke the fixed human review workflow without a token or autoapprove argument."""
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(
        description="Review an exact expiring local approval request."
    )
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--request-id", type=UUID, required=True)
    arguments = parser.parse_args()
    try:
        token = getpass.getpass("Bearer token: ")
    except (EOFError, KeyboardInterrupt):
        logger.info("approval_cli_cancelled")
        return 2
    return review_approval(arguments.base_url, arguments.request_id, token)


if __name__ == "__main__":
    raise SystemExit(main())
