"""Load the exact twelve fresh CODE-EVAL-004 utility repairs and independently validate source/oracle descriptions without executing candidates."""

import ast
import hashlib
import json
import logging
from pathlib import Path

from coding_mvp_cases import candidate_review

logger = logging.getLogger(__name__)
PATH = Path("tests/fixtures/coding/ce004-reasoning-fresh-v2.json")
SHA = "e2e31c24ede46729893a8fd32a6e3e58acf39873f3e9629285744aaedcd04505"


def corpus():
    """Require exact pre-inference examples and hashes, described pure APIs and no reuse of an older case identity or specification."""
    raw = PATH.read_bytes()
    if hashlib.sha256(raw).hexdigest() != SHA:
        raise ValueError("ce004_corpus_changed")
    value = json.loads(raw)
    cases = value["cases"]
    if len(cases) != 12 or len({row["id"] for row in cases}) != 12:
        raise ValueError("ce004_inventory_invalid")
    old = [
        row
        for path in [
            "d46-utility-repairs.json",
            "ce002-fresh-v1.json",
            "ce003-feedback-fresh-v1.json",
        ]
        for row in json.loads(PATH.with_name(path).read_text())["cases"]
    ]
    for case in cases:
        if (
            len(case["visible_examples"]) != 2
            or len(case["heldout_examples"]) != 5
            or any(
                case["id"] == row["id"]
                or case["function"] == row["function"]
                or case["issue"] == row["issue"]
                for row in old
            )
        ):
            raise ValueError("ce004_old_case_or_examples_invalid")
        for key, sha in case["sha256"].items():
            if hashlib.sha256(case[key].encode()).hexdigest() != sha:
                raise ValueError("ce004_source_hash_changed")
            tree = ast.parse(case[key])
            if not ast.get_docstring(tree) or any(
                not ast.get_docstring(node)
                for node in ast.walk(tree)
                if isinstance(
                    node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
                )
            ):
                raise ValueError("ce004_descriptions_missing")
        candidate_review(case, case["buggy_source"])
        candidate_review(case, case["reference_source"])
    logger.info("ce004_corpus_verified cases=12 visible=24 hidden=60")
    return value
