"""Verify that exactly the HAR-006 v2 design tests are pinned to the recorded commit and why (ADR-195)."""

import ast

from benchmarks.tests import har006_v2_pin as pin

RUNNER = pin.ROOT / "benchmarks/context_har006_v2.py"
TESTS = pin.ROOT / "benchmarks/tests" / pin.MODULE


def assigned(tree, name):
    """Return the value node of one module-level assignment."""
    return next(
        node.value
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(getattr(target, "id", None) == name for target in node.targets)
    )


def dependents(tree):
    """Return the test functions that take native_run or call chain()."""
    names = set()
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef) or not node.name.startswith("test_"):
            continue
        uses_run = any(argument.arg == "native_run" for argument in node.args.args)
        calls_chain = any(
            isinstance(call, ast.Call) and getattr(call.func, "id", None) == "chain"
            for call in ast.walk(node)
        )
        if uses_run or calls_chain:
            names.add(node.name)
    return names


def parameter_ids(tree, name):
    """Return the parametrize ids of one test function, or None when it is not parametrized."""
    function = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == name
    )
    for decorator in function.decorator_list:
        if getattr(getattr(decorator, "func", None), "attr", None) != "parametrize":
            continue
        ids = next(
            keyword.value for keyword in decorator.keywords if keyword.arg == "ids"
        )
        if isinstance(ids, ast.List):
            return [ast.literal_eval(item) for item in ids.elts]
        table = assigned(tree, ids.generators[0].iter.id)
        return [ast.literal_eval(row.elts[0]) for row in table.elts]
    return None


def test_pin_covers_exactly_the_v2_sources():
    """The recorded hashes name exactly v2's SOURCES, and the frozen runner itself is unchanged."""
    runner = ast.parse(RUNNER.read_text())
    assert list(pin.RECORDED_SOURCES) == list(
        ast.literal_eval(assigned(runner, "SOURCES"))
    )
    changed = pin.changed_sources()
    assert "benchmarks/context_har006_v2.py" not in changed
    assert {
        "src/application/services/context_composer.py",
        "src/application/services/context_reduction.py",
        "src/application/services/context_inspection.py",
    } <= set(changed)


def test_pinned_tests_are_exactly_the_chain_and_native_run_dependents():
    """The 21 pinned items expand from the tests that use chain() or native_run, with their parametrize ids."""
    tree = ast.parse(TESTS.read_text())
    names = dependents(tree)
    expected = []
    for name in sorted(names):
        ids = parameter_ids(tree, name)
        expected += [name] if ids is None else [f"{name}[{value}]" for value in ids]
    assert sorted(pin.PINNED) == sorted(expected)
    assert len(pin.PINNED) == len(set(pin.PINNED)) == 21
    assert pin.RECORDED_COMMIT.startswith("6cd4da2") and len(pin.RECORDED_COMMIT) == 40
    assert "6cd4da2" in pin.REASON and "21 tests" in pin.REASON
    assert set(pin.WARM_CALIBRATION).isdisjoint(names)
