"""Validate frozen synthetic coding tasks and bounded full-file proposals without importing generated code."""

import ast
import logging
import re

from src.application.services.workspace_policy import WorkspaceAccessError
from src.application.services.workspace_requests import parse_workspace_json

logger = logging.getLogger(__name__)


def described_code(code):
    """AST-check bounded source descriptions and a top-level solve entry without running source on host."""
    try:
        if not isinstance(code, str) or not 1 <= len(code.encode("utf-8")) <= 8192:
            raise ValueError()
        tree = ast.parse(code)
        if not ast.get_docstring(tree) or not any(
            isinstance(node, ast.FunctionDef) and node.name == "solve"
            for node in tree.body
        ):
            raise ValueError()
        for node in ast.walk(tree):
            if isinstance(
                node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
            ) and not ast.get_docstring(node):
                raise ValueError()
    except (ValueError, TypeError, SyntaxError, UnicodeError, RecursionError):
        raise WorkspaceAccessError("coding_proposal_invalid", 422) from None
    logger.info("coding_candidate_descriptions_validated")
    return code


def parse_code_proposal(raw):
    """Accept exactly one bounded full-file code field without model-selected paths, commands or scope."""
    try:
        payload = parse_workspace_json(raw.encode("utf-8"))
        if set(payload) != {"code"}:
            raise ValueError()
        return described_code(payload["code"])
    except (WorkspaceAccessError, ValueError, TypeError, UnicodeError, AttributeError):
        raise WorkspaceAccessError("coding_proposal_invalid", 422) from None


def load_baseline_cases(raw):
    """Validate the finite pre-inference task/oracle artifact without exposing expected values to candidate execution."""
    value = parse_workspace_json(raw)
    if (
        set(value)
        != {"description", "version", "profile", "preset", "max_tokens", "tasks"}
        or type(value["version"]) is not int
        or value["version"] != 1
        or value["profile"] != "core"
        or value["preset"] != "fast"
        or type(value["max_tokens"]) is not int
        or value["max_tokens"] != 1024
    ):
        raise ValueError("coding_case_configuration")
    if (
        not isinstance(value["description"], str)
        or not value["description"].strip()
        or not isinstance(value["tasks"], list)
        or len(value["tasks"]) != 6
    ):
        raise ValueError("coding_case_count")
    names = set()
    for task in value["tasks"]:
        if not isinstance(task, dict) or set(task) != {
            "id",
            "requirements",
            "source",
            "inputs",
            "expected",
        }:
            raise ValueError("coding_case_shape")
        if (
            not isinstance(task["id"], str)
            or not re.fullmatch(r"[a-z][a-z0-9_]{1,39}", task["id"])
            or task["id"] in names
        ):
            raise ValueError("coding_case_identity")
        names.add(task["id"])
        if (
            not isinstance(task["requirements"], str)
            or not task["requirements"].strip()
            or len(task["requirements"].encode()) > 2048
        ):
            raise ValueError("coding_case_requirements")
        described_code(task["source"])
        if (
            not isinstance(task["inputs"], list)
            or not 1 <= len(task["inputs"]) <= 16
            or any(not isinstance(row, list) for row in task["inputs"])
        ):
            raise ValueError("coding_case_inputs")
        if not isinstance(task["expected"], list) or len(task["expected"]) != len(
            task["inputs"]
        ):
            raise ValueError("coding_case_oracles")
    logger.info("coding_baseline_cases_validated tasks=%d", len(value["tasks"]))
    return value
