"""Define bounded signed-checkpoint references and metadata validation independently of a filesystem implementation."""

import logging
import math
from dataclasses import dataclass
from uuid import UUID

logger = logging.getLogger(__name__)
FIELDS = frozenset(
    {
        "owner_id",
        "workspace_id",
        "profile",
        "plan_sha256",
        "catalog_sha256",
        "created_at",
        "observed_at",
        "expires_at",
        "next_step",
        "attempts",
        "step_attempts",
        "output_bytes",
        "outputs",
        "status",
    }
)


class CheckpointError(Exception):
    """Expose finite storage/recovery failures without paths, signing keys or checkpoint contents."""

    def __init__(self, code):
        """Keep audit metadata inside the bounded storage error vocabulary."""
        self.code = (
            code
            if code in {"invalid", "unavailable", "busy", "stale", "capacity", "closed"}
            else "invalid"
        )
        super().__init__(self.code)
        logger.warning("plan_checkpoint_rejected code=%s", self.code)


@dataclass(frozen=True, slots=True)
class PlanCheckpoint:
    """Reference an exact latest signed snapshot without containing prompt, output or approval authority."""

    run_id: UUID
    revision: int
    sha256: str


def validate_state(value):
    """Reject raw bodies, forged shapes, invalid budgets and inconsistent step progress before signing or recovering state."""
    try:
        if type(value) is not dict or set(value) != FIELDS:
            raise ValueError()
        for name in ["owner_id", "workspace_id"]:
            if type(value[name]) is not str or str(UUID(value[name])) != value[name]:
                raise ValueError()
        for name in ["plan_sha256", "catalog_sha256"]:
            if (
                type(value[name]) is not str
                or len(value[name]) != 64
                or any(c not in "0123456789abcdef" for c in value[name])
            ):
                raise ValueError()
        if (
            value["profile"] != "core"
            or type(value["status"]) is not str
            or value["status"]
            not in {
                "ready",
                "inflight",
                "failed",
                "cancelled",
                "uncertain_write",
                "complete",
            }
        ):
            raise ValueError()
        for name in ["created_at", "observed_at", "expires_at"]:
            if (
                type(value[name]) not in (float, int)
                or not math.isfinite(value[name])
                or value[name] < 0
            ):
                raise ValueError()
        if (
            value["observed_at"] < value["created_at"]
            or value["expires_at"] != value["created_at"] + 120
        ):
            raise ValueError()
        attempts = value["step_attempts"]
        index = value["next_step"]
        if (
            type(attempts) is not list
            or not 1 <= len(attempts) <= 8
            or any(
                type(number) is not int or not 0 <= number <= 2 for number in attempts
            )
        ):
            raise ValueError()
        if (
            type(index) is not int
            or not 0 <= index <= len(attempts)
            or type(value["attempts"]) is not int
            or not 0 <= value["attempts"] <= 12
            or value["attempts"] != sum(attempts)
        ):
            raise ValueError()
        if (
            type(value["output_bytes"]) is not int
            or not 0 <= value["output_bytes"] <= 327680
        ):
            raise ValueError()
        outputs = value["outputs"]
        if (
            type(outputs) is not list
            or len(outputs) != index
            or len({item["step_id"] for item in outputs}) != len(outputs)
        ):
            raise ValueError()
        for item in outputs:
            if (
                type(item) is not dict
                or set(item) != {"step_id", "sha256"}
                or type(item["step_id"]) is not str
                or not 1 <= len(item["step_id"]) <= 64
                or type(item["sha256"]) is not str
                or len(item["sha256"]) != 64
                or any(c not in "0123456789abcdef" for c in item["sha256"])
            ):
                raise ValueError()
        if (value["status"] == "complete") != (index == len(attempts)):
            raise ValueError()
    except (ValueError, TypeError, KeyError):
        raise CheckpointError("invalid") from None


def validate_transition(previous, current):
    """Require forward-only immutable scope/budget transitions, including a durably charged explicit in-flight read retry."""
    validate_state(current)
    if previous is None:
        if (
            current["status"] != "ready"
            or current["attempts"]
            or current["next_step"]
            or current["output_bytes"]
            or current["outputs"]
        ):
            raise CheckpointError("invalid")
        return
    validate_state(previous)
    frozen = [
        "owner_id",
        "workspace_id",
        "profile",
        "plan_sha256",
        "catalog_sha256",
        "created_at",
        "expires_at",
    ]
    if (
        any(previous[name] != current[name] for name in frozen)
        or current["observed_at"] < previous["observed_at"]
        or len(current["step_attempts"]) != len(previous["step_attempts"])
        or current["output_bytes"] < previous["output_bytes"]
    ):
        raise CheckpointError("invalid")
    index = previous["next_step"]
    if current["status"] == "inflight":
        attempts = list(previous["step_attempts"])
        if index >= len(attempts):
            raise CheckpointError("invalid")
        attempts[index] += 1
        valid = (
            previous["status"] in {"ready", "failed", "cancelled", "inflight"}
            and current["next_step"] == index
            and current["attempts"] == previous["attempts"] + 1
            and current["step_attempts"] == attempts
            and current["outputs"] == previous["outputs"]
            and current["output_bytes"] == previous["output_bytes"]
        )
    elif current["status"] in {"ready", "complete"}:
        valid = (
            previous["status"] == "inflight"
            and current["next_step"] == index + 1
            and current["attempts"] == previous["attempts"]
            and current["step_attempts"] == previous["step_attempts"]
            and current["outputs"][:-1] == previous["outputs"]
        )
    else:
        valid = (
            previous["status"] == "inflight"
            and current["next_step"] == index
            and current["attempts"] == previous["attempts"]
            and current["step_attempts"] == previous["step_attempts"]
            and current["outputs"] == previous["outputs"]
        )
    if not valid:
        raise CheckpointError("invalid")
