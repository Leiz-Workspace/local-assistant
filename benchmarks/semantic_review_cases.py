"""Define inert review snippets and trusted finite probe semantics without executing source or model-supplied code."""

import logging

LOGGER = logging.getLogger(__name__)
HEADER = '"""Provide controlled semantic review evidence only; never execute this fixture."""\n'
CLAIMS = [
    "truthiness",
    "byte_quota",
    "exclusive_range",
    "caller_type",
    "cancellation",
    "unit_conversion",
    "style",
    "performance",
]
SNIPPETS = {
    "truthy": 'def choose(value, fallback):\n    """Use fallback only for None; preserve every other value."""\n    return value or fallback\n',
    "none_only": 'def choose(value, fallback):\n    """Use fallback only for None; preserve every other value."""\n    return fallback if value is None else value\n',
    "char_quota": 'def allowed(text, limit):\n    """Accept exactly text whose UTF-8 encoding fits the nonnegative byte limit."""\n    if len(text) > limit:\n        return False\n    return True\n',
    "byte_quota": 'def allowed(text, limit):\n    """Accept exactly text whose UTF-8 encoding fits the nonnegative byte limit."""\n    if len(text.encode("utf-8")) > limit:\n        return False\n    return True\n',
    "open_range": 'def sequence(n):\n    """Return integers from one through nonnegative n, inclusive."""\n    return list(range(1, n))\n',
    "closed_range": 'def sequence(n):\n    """Return integers from one through nonnegative n, inclusive."""\n    return list(range(1, n + 1))\n',
    "int_digits": 'def parse(raw):\n    """Return the nonnegative caller integer unchanged."""\n    if not raw.isdigit():\n        raise ValueError("input")\n    return int(raw)\n',
    "int_copy": 'def parse(raw):\n    """Return the nonnegative caller integer unchanged."""\n    return int(raw)\n',
    "catch_base": 'import asyncio\n\nasync def observe(job):\n    """Return job output; map ordinary errors to None and propagate cancellation/interruption."""\n    try:\n        return await job\n    except BaseException:\n        return None\n',
    "catch_exception": 'import asyncio\n\nasync def observe(job):\n    """Return job output; map ordinary errors to None and propagate cancellation/interruption."""\n    try:\n        return await job\n    except Exception:\n        return None\n',
    "unknown_units": 'def duration(value):\n    """Convert the caller value to seconds according to the agreed caller units."""\n    return value * 60\n',
    "conflicting_units": 'def duration(value):\n    """Convert the caller value to seconds according to the agreed caller units."""\n    return value * 60\n',
}


def cases():
    """Create twelve opaque-ID cases with predeclared admissible locations and no previous cohort reuse."""
    result = []
    for index, kind in enumerate(SNIPPETS, 1):
        source = HEADER + SNIPPETS[kind]
        caller = "Use only the stated function contract and these four probes."
        if kind in {"int_digits", "int_copy"}:
            caller = "The only caller passes a nonnegative Python int, never a string."
        if kind == "unknown_units":
            caller = "Caller units are not recorded. Minutes and hours are both plausible; no agreed units are available."
        if kind == "conflicting_units":
            caller = "Two equally current approved caller policies conflict: one says seconds, one says minutes. No precedence rule exists."
        lines = source.splitlines()
        faulty = {
            "truthy": ["return value or fallback"],
            "char_quota": ["if len(text) > limit:", "return True"],
            "open_range": ["return list(range(1, n))"],
            "int_digits": ["if not raw.isdigit():"],
            "catch_base": ["except BaseException:", "return None"],
        }.get(kind, [])
        accepted = [
            i + 1 for i, line in enumerate(lines) if line.strip(" \t") in faulty
        ]
        if kind in {"truthy", "none_only"}:
            inputs = [
                dict(value=value, fallback="backup") for value in [0, "", None, 8]
            ]
        elif kind in {"char_quota", "byte_quota"}:
            inputs = [
                dict(text=text, limit=limit)
                for text, limit in [("a", 1), ("ế", 1), ("汉字", 5), ("abc", 4)]
            ]
        elif kind in {"open_range", "closed_range"}:
            inputs = [dict(n=value) for value in [0, 1, 3, 5]]
        elif kind in {"int_digits", "int_copy"}:
            inputs = [dict(raw=value) for value in [0, 1, 9, 42]]
        elif kind in {"catch_base", "catch_exception"}:
            inputs = [
                dict(job=value)
                for value in ["ok", "ValueError", "CancelledError", "KeyboardInterrupt"]
            ]
        else:
            inputs = [dict(value=value) for value in [0, 1, 2, 5]]
        claim = {
            "truthy": "truthiness",
            "char_quota": "byte_quota",
            "open_range": "exclusive_range",
            "int_digits": "caller_type",
            "catch_base": "cancellation",
        }.get(kind)
        verdict = (
            "uncertain"
            if kind in {"unknown_units", "conflicting_units"}
            else "defect"
            if faulty
            else "no_defect"
        )
        result.append(
            dict(
                id=f"semantic-{index:02d}",
                kind=kind,
                source=source,
                caller=caller,
                probes={f"p{i}": value for i, value in enumerate(inputs)},
                gold=dict(verdict=verdict, claim=claim, accepted_lines=accepted),
            )
        )
    LOGGER.info("semantic_review_cases_defined count=%d", len(result))
    return result


def outcomes(case, probe):
    """Compute only registered trusted operations on fixed inputs, never eval/exec/import a source snippet."""
    if case["source"] != HEADER + SNIPPETS[case["kind"]] or probe not in case["probes"]:
        raise ValueError("unregistered_semantic_case")
    kind, value = case["kind"], case["probes"][probe]
    if kind in {"truthy", "none_only"}:
        expected = value["fallback"] if value["value"] is None else value["value"]
        observed = value["value"] or value["fallback"] if kind == "truthy" else expected
    elif kind in {"char_quota", "byte_quota"}:
        expected = len(value["text"].encode("utf-8")) <= value["limit"]
        observed = (
            len(value["text"]) <= value["limit"] if kind == "char_quota" else expected
        )
    elif kind in {"open_range", "closed_range"}:
        expected = list(range(1, value["n"] + 1))
        observed = list(range(1, value["n"])) if kind == "open_range" else expected
    elif kind in {"int_digits", "int_copy"}:
        expected = value["raw"]
        observed = "AttributeError" if kind == "int_digits" else expected
    elif kind in {"catch_base", "catch_exception"}:
        expected = (
            "ok"
            if value["job"] == "ok"
            else None
            if value["job"] == "ValueError"
            else value["job"]
        )
        observed = (
            ("ok" if value["job"] == "ok" else None)
            if kind == "catch_base"
            else expected
        )
    else:
        raise ValueError("caller_contract_not_established")
    LOGGER.info("semantic_trusted_probe_evaluated")
    return expected, observed


def equal(left, right):
    """Compare finite JSON outcomes without conflating booleans, numbers or stringified values."""
    return type(left) is type(right) and (
        all(equal(a, b) for a, b in zip(left, right, strict=True))
        if type(left) is list and len(left) == len(right)
        else left == right
    )
