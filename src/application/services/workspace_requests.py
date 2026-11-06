"""Validate strict bounded workspace read operations independently of HTTP or future model tool callers."""

import json
import logging
import math

from src.application.services.workspace_policy import WorkspaceAccessError, clean_parts

logger = logging.getLogger(__name__)


def validate_workspace_request(operation, parameters):
    """Normalize only declared defaults while refusing extra fields, coercions, unsafe paths and unbounded literal queries."""
    shapes = {
        "discover": set(),
        "inventory": {"directory"},
        "symbols": {"directory"},
        "search": {"directory", "query"},
        "read": {"path", "start_line", "end_line"},
    }
    if (
        not isinstance(operation, str)
        or operation not in shapes
        or not isinstance(parameters, dict)
        or set(parameters) - shapes[operation]
    ):
        raise WorkspaceAccessError("workspace_request_invalid", 422)
    result = dict(parameters)
    if operation in {"inventory", "symbols", "search"}:
        result.setdefault("directory", None)
        if result["directory"] is not None:
            clean_parts(result["directory"])
    if operation == "search":
        query = result.get("query")
        try:
            valid = (
                isinstance(query, str)
                and bool(query.strip())
                and 1 <= len(query.encode("utf-8")) <= 256
            )
        except UnicodeError:
            valid = False
        if not valid:
            raise WorkspaceAccessError("workspace_query_invalid", 422)
    if operation == "read":
        clean_parts(result.get("path"))
        result.setdefault("start_line", 1)
        result.setdefault("end_line", 200)
        start, end = result["start_line"], result["end_line"]
        if (
            type(start) is not int
            or type(end) is not int
            or not 1 <= start <= end <= 2147483647
            or end - start >= 200
        ):
            raise WorkspaceAccessError("workspace_line_range", 422)
    logger.info("workspace_request_validated operation=%s", operation)
    return result


def parse_workspace_json(raw):
    """Reject malformed, ambiguous, nonfinite, deep or invalid-Unicode JSON before framework error serialization."""

    def unique(pairs):
        """Reject duplicate keys at every depth instead of silently replacing requested paths or operations."""
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate_key")
            result[key] = value
        return result

    def invalid_constant(value):
        """Reject nonfinite JSON tokens without echoing their spelling or surrounding source data."""
        raise ValueError("nonfinite_json")

    def validate(value, depth=0):
        """Require valid Unicode and finite numbers within a bounded JSON nesting depth."""
        if depth > 16:
            raise ValueError("json_depth")
        if isinstance(value, str):
            value.encode("utf-8")
        elif isinstance(value, float) and not math.isfinite(value):
            raise ValueError("nonfinite_json")
        elif isinstance(value, dict):
            for key, child in value.items():
                validate(key, depth + 1)
                validate(child, depth + 1)
        elif isinstance(value, list):
            for child in value:
                validate(child, depth + 1)

    try:
        if not isinstance(raw, bytes) or len(raw) > 16384:
            raise ValueError("json_bytes")
        payload = json.loads(
            raw, object_pairs_hook=unique, parse_constant=invalid_constant
        )
        if not isinstance(payload, dict):
            raise ValueError("json_object_required")
        validate(payload)
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise WorkspaceAccessError("workspace_json_invalid", 422) from None
    logger.info("workspace_json_validated")
    return payload
