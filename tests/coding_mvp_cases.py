"""Load frozen D46 utility cases, apply trusted fixture reviews without host source execution and retain exclusive bounded private evidence."""

import ast
import hashlib
import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)
CORPUS_PATH = Path("tests/fixtures/coding/d46-utility-repairs.json")
CORPUS_SHA256 = "63e0a05b2b6f1a9d3d85210b09931d74d015ce6f53dfeb27f66c2936b74849d4"
PURE_CALLS = frozenset(
    {
        "abs",
        "all",
        "any",
        "bool",
        "dict",
        "enumerate",
        "float",
        "int",
        "isinstance",
        "len",
        "list",
        "max",
        "min",
        "range",
        "reversed",
        "round",
        "set",
        "sorted",
        "str",
        "sum",
        "tuple",
        "zip",
        "ValueError",
        "TypeError",
        "KeyError",
        "IndexError",
    }
)
PURE_METHODS = frozenset(
    {
        "add",
        "append",
        "casefold",
        "copy",
        "count",
        "discard",
        "endswith",
        "extend",
        "find",
        "fromkeys",
        "get",
        "index",
        "intersection",
        "isalpha",
        "isdecimal",
        "isdigit",
        "items",
        "join",
        "keys",
        "lower",
        "lstrip",
        "pop",
        "remove",
        "removeprefix",
        "removesuffix",
        "replace",
        "reverse",
        "rfind",
        "rsplit",
        "rstrip",
        "sort",
        "split",
        "startswith",
        "strip",
        "union",
        "upper",
        "values",
    }
)
FORBIDDEN_NODES = (
    ast.Import,
    ast.ImportFrom,
    ast.FunctionDef,
    ast.AsyncFunctionDef,
    ast.ClassDef,
    ast.Global,
    ast.Nonlocal,
    ast.With,
    ast.AsyncWith,
    ast.Await,
    ast.Yield,
    ast.YieldFrom,
    ast.Delete,
    ast.While,
)


class FixtureReviewError(ValueError):
    """Reject a candidate outside the predeclared pure-utility fixture review without claiming universal source security."""

    def __init__(self, code):
        """Retain only a stable metadata reason without exposing candidate source or making an approval decision."""
        super().__init__(code)
        self.code = code
        logger.info("d46_fixture_review_rejected code=%s", code)


def case_digest(case):
    """Bind every complete authored source/oracle/issue field with deterministic UTF-8 JSON bytes."""
    return hashlib.sha256(
        json.dumps(
            case, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode()
    ).hexdigest()


def corpus():
    """Load ten exact pre-inference cases and verify every complete source/test digest without evaluating any module."""
    raw = CORPUS_PATH.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == CORPUS_SHA256
    value = json.loads(raw)
    assert len(value["cases"]) == len({row["id"] for row in value["cases"]}) == 10
    for case in value["cases"]:
        for name, digest in case["sha256"].items():
            assert hashlib.sha256(case[name].encode()).hexdigest() == digest
        assert len(case["visible_examples"]) == len(case["heldout_examples"]) == 2
        for name in [
            "buggy_source",
            "reference_source",
            "visible_test_source",
            "heldout_test_source",
        ]:
            tree = ast.parse(case[name])
            assert ast.get_docstring(tree)
            for node in ast.walk(tree):
                if isinstance(
                    node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
                ):
                    assert ast.get_docstring(node)
    logger.info("d46_corpus_verified cases10 sha256=%s", CORPUS_SHA256)
    return value


def candidate_review(case, source):
    """Require the fixed header/API/audit call and bounded pure local operations before a trusted fixture review can approve a model candidate."""
    try:
        if (
            type(source) is not str
            or not 0 < len(source.encode()) <= 8192
            or "\x00" in source
        ):
            raise FixtureReviewError("candidate_bytes")
        actual, original = ast.parse(source), ast.parse(case["buggy_source"])
    except (SyntaxError, UnicodeError, RecursionError):
        raise FixtureReviewError("candidate_syntax") from None
    if (
        not ast.get_docstring(actual)
        or len(actual.body) != len(original.body)
        or not isinstance(actual.body[-1], ast.FunctionDef)
    ):
        raise FixtureReviewError("module_shape")
    if [ast.dump(row) for row in actual.body[1:-1]] != [
        ast.dump(row) for row in original.body[1:-1]
    ]:
        raise FixtureReviewError("logging_header_changed")
    function, previous = actual.body[-1], original.body[-1]
    if (
        function.name != previous.name
        or ast.dump(function.args) != ast.dump(previous.args)
        or function.returns != previous.returns
        or function.decorator_list
        or getattr(function, "type_params", ())
        or not ast.get_docstring(function)
    ):
        raise FixtureReviewError("function_api_changed")
    if len(function.body) < 3 or ast.dump(function.body[1]) != ast.dump(
        previous.body[1]
    ):
        raise FixtureReviewError("initial_audit_changed")
    nodes = [node for statement in function.body[2:] for node in ast.walk(statement)]
    if len(nodes) > 4096 or any(isinstance(node, FORBIDDEN_NODES) for node in nodes):
        raise FixtureReviewError("nonlocal_operation")
    stored = {
        node.id
        for node in nodes
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store)
    }
    if stored & (PURE_CALLS | {"logger", "logging"}):
        raise FixtureReviewError("trusted_name_rebound")
    local = stored | set(case["parameters"]) | PURE_CALLS
    # Bind loads to local value symbols so aliasing cannot turn a permitted builtin call into a dynamic evaluator.
    for node in nodes:
        if isinstance(node, ast.Name) and (
            node.id.startswith("__") or node.id not in local
        ):
            raise FixtureReviewError("unknown_name")
        if isinstance(node, ast.Attribute) and node.attr not in PURE_METHODS:
            raise FixtureReviewError("unreviewed_attribute")
        if isinstance(node, ast.Call):
            valid = (
                isinstance(node.func, ast.Name) and node.func.id in PURE_CALLS
            ) or (
                isinstance(node.func, ast.Attribute) and node.func.attr in PURE_METHODS
            )
            if not valid:
                raise FixtureReviewError("unreviewed_call")
    result = dict(
        description="Accepted only the predeclared pure fixture review; no action executed or general source-safety claim.",
        case_id=case["id"],
        candidate_sha256=hashlib.sha256(source.encode()).hexdigest(),
        function=function.name,
        approved_action=False,
    )
    logger.info(
        "d46_fixture_candidate_reviewed case_id=%s sha256=%s",
        case["id"],
        result["candidate_sha256"],
    )
    return result


def fixture_files(case, variant="buggy_source"):
    """Return complete exact target/visible/held-out fixture bytes without choosing a command, model or approval."""
    if variant not in {"buggy_source", "reference_source"}:
        raise ValueError("fixture_variant")
    result = {
        case["target_path"]: case[variant].encode(),
        case["visible_test_path"]: case["visible_test_source"].encode(),
        case["heldout_test_path"]: case["heldout_test_source"].encode(),
    }
    logger.info(
        "d46_fixture_files_materialized case_id=%s variant=%s", case["id"], variant
    )
    return result


def save_artifact(directory, name, value):
    """Write complete bounded D46 fixture evidence exclusively under private backups and fsync it without exposing source or output in logs."""
    root = (Path.cwd() / "data/backups").resolve()
    if Path(name).name != name or not directory.resolve().is_relative_to(root):
        raise ValueError("artifact_scope")
    raw = (
        json.dumps(
            {
                "description": "Private D46 fixture evidence with exact native/source/model provenance.",
                **value,
            },
            ensure_ascii=False,
            allow_nan=False,
            indent=2,
        )
        + "\n"
    ).encode()
    if len(raw) > 1048576:
        raise ValueError("artifact_limit")
    path = directory / name
    descriptor = os.open(
        path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW, 0o600
    )
    with os.fdopen(descriptor, "wb") as output:
        output.write(raw)
        output.flush()
        os.fsync(output.fileno())
    logger.info("d46_private_artifact_saved bytes=%d", len(raw))
    return dict(
        path=str(path.relative_to(Path.cwd())), sha256=hashlib.sha256(raw).hexdigest()
    )
