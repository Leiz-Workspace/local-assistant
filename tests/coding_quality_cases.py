"""Verify the fresh CODE-EVAL-002 corpus and create explicit paired issues without changing production prompts or source/test bytes."""

import ast
import hashlib
import json
import logging
from pathlib import Path

from coding_mvp_cases import candidate_review

logger = logging.getLogger(__name__)
CORPUS_PATH = Path("tests/fixtures/coding/ce002-fresh-v1.json")
CORPUS_SHA256 = "e13c1baa6ff021ce696bb2a481e2f401797cb57f4541dca38c284fa80f0435b7"
CONCISE_HINT = (
    " Return exactly one concise plan entry. Before returning, privately verify all requirements, "
    "including applicable zero, empty, negative and boundary cases. Do not add a second attempt, "
    "claim execution, modify tests or reveal private reasoning."
)


def corpus():
    """Require the exact pre-inference twelve-case inventory, complete source digests and described pure utility variants."""
    raw = CORPUS_PATH.read_bytes()
    if hashlib.sha256(raw).hexdigest() != CORPUS_SHA256:
        raise ValueError("ce002_corpus_changed")
    value = json.loads(raw)
    cases = value["cases"]
    if len(cases) != 12 or len({row["id"] for row in cases}) != 12:
        raise ValueError("ce002_corpus_shape")
    for row in cases:
        if len(row["visible_examples"]) != 2 or len(row["heldout_examples"]) != 5:
            raise ValueError("ce002_examples_changed")
        for name, expected in row["sha256"].items():
            if hashlib.sha256(row[name].encode()).hexdigest() != expected:
                raise ValueError("ce002_source_changed")
            tree = ast.parse(row[name])
            if not ast.get_docstring(tree) or any(
                not ast.get_docstring(node)
                for node in ast.walk(tree)
                if isinstance(
                    node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
                )
            ):
                raise ValueError("ce002_description_missing")
        candidate_review(row, row["buggy_source"])
        candidate_review(row, row["reference_source"])
    logger.info("ce002_corpus_verified cases=12 visible=24 heldout=60")
    return value


def variant(case, arm):
    """Copy one frozen case and change only its explicit issue for the predeclared concise-prompt arm."""
    if arm not in {"baseline", "concise"}:
        raise ValueError("ce002_arm_invalid")
    copied = json.loads(json.dumps(case, ensure_ascii=False))
    if arm == "concise":
        copied["issue"] += CONCISE_HINT
    logger.info("ce002_variant_prepared case=%s arm=%s", case["id"], arm)
    return copied
