"""Verify six fresh CODE-EVAL-003 utility cases and exact source/oracle hashes without executing candidates."""

import ast
import hashlib
import json
import logging
from pathlib import Path

from coding_mvp_cases import candidate_review

logger = logging.getLogger(__name__)
CORPUS_PATH = Path("tests/fixtures/coding/ce003-feedback-fresh-v1.json")
CORPUS_SHA256 = "cbe231d750a90ca1e350498485827a88b28dbd3e8a55d3b1e6c8c3623640d27d"


def corpus():
    """Require the exact pre-inference six-case inventory, complete source digests and described pure utility variants."""
    raw = CORPUS_PATH.read_bytes()
    if hashlib.sha256(raw).hexdigest() != CORPUS_SHA256:
        raise ValueError("ce003_corpus_changed")
    value = json.loads(raw)
    cases = value["cases"]
    if len(cases) != 6 or len({row["id"] for row in cases}) != 6:
        raise ValueError("ce003_corpus_shape")
    for row in cases:
        if len(row["visible_examples"]) != 2 or len(row["heldout_examples"]) != 5:
            raise ValueError("ce003_examples_changed")
        for name, expected in row["sha256"].items():
            if hashlib.sha256(row[name].encode()).hexdigest() != expected:
                raise ValueError("ce003_source_changed")
            tree = ast.parse(row[name])
            if not ast.get_docstring(tree) or any(
                not ast.get_docstring(node)
                for node in ast.walk(tree)
                if isinstance(
                    node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
                )
            ):
                raise ValueError("ce003_description_missing")
        candidate_review(row, row["buggy_source"])
        candidate_review(row, row["reference_source"])
    logger.info("ce003_corpus_verified cases=6 visible=12 heldout=30")
    return value
