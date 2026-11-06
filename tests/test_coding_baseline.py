"""Verify authored coding-case/proposal contracts without running candidate source in the host interpreter."""

import copy
import json
from pathlib import Path

import pytest

from src.application.services.coding_baseline import (
    described_code,
    load_baseline_cases,
    parse_code_proposal,
)
from src.application.services.workspace_policy import WorkspaceAccessError

SOURCE = '"""Fixture source."""\ndef solve(value):\n    """Return the supplied fixture value."""\n    return value\n'


def test_frozen_cases_have_distinct_tasks_and_independent_oracles():
    """Validate all six task definitions and the manually specified large-integer reference result."""
    value = load_baseline_cases(Path("configs/coding-baseline-cases.json").read_bytes())
    assert len(value["tasks"]) == 6 and len({row["id"] for row in value["tasks"]}) == 6
    assert sum(len(row["inputs"]) for row in value["tasks"]) == 28
    assert 1180591620717411303427 // 3 == value["tasks"][0]["expected"][-1]
    assert all(len(row["inputs"]) == len(row["expected"]) for row in value["tasks"])


def test_full_file_proposal_is_only_ast_parsed_on_host(tmp_path):
    """Preserve malicious-looking source text as data without executing even its top-level statements."""
    marker = tmp_path / "never-created"
    source = SOURCE + f"\nopen({str(marker)!r}, 'w').write('untrusted')\n"
    assert parse_code_proposal(json.dumps(dict(code=source))) == source
    assert not marker.exists()


@pytest.mark.parametrize(
    "raw",
    [
        None,
        "[]",
        "invalid",
        '{"code":"a","code":"b"}',
        '{"code":"x","path":"/etc/passwd"}',
        '{"code":"x","command":"id"}',
        '{"code":NaN}',
        json.dumps(dict(code="x" * 8193)),
        json.dumps(dict(code="def solve():\n    return 1")),
        json.dumps(dict(code='"""Module."""\ndef solve():\n    return 1')),
        json.dumps(
            dict(code='"""Module."""\ndef other():\n    """Other."""\n    return 1')
        ),
    ],
)
def test_invalid_or_authority_selecting_proposals_rejected(raw):
    """Reject malformed JSON, over-budget code, missing descriptions/entry and path/command overrides."""
    with pytest.raises(WorkspaceAccessError, match="coding_proposal_invalid"):
        parse_code_proposal(raw)


@pytest.mark.parametrize(
    "fault",
    [
        "version_bool",
        "profile",
        "tokens",
        "count",
        "duplicate",
        "id",
        "requirements",
        "inputs",
        "oracles",
        "extra",
    ],
)
def test_case_artifact_drift_is_rejected(fault):
    """Reject scalar/schema/identity/oracle drift rather than silently changing evaluation scope."""
    value = json.loads(Path("configs/coding-baseline-cases.json").read_text())
    value = copy.deepcopy(value)
    if fault == "version_bool":
        value["version"] = True
    elif fault == "profile":
        value["profile"] = "unrestricted"
    elif fault == "tokens":
        value["max_tokens"] = 2048
    elif fault == "count":
        value["tasks"].pop()
    elif fault == "duplicate":
        value["tasks"][1]["id"] = value["tasks"][0]["id"]
    elif fault == "id":
        value["tasks"][0]["id"] = "../outside"
    elif fault == "requirements":
        value["tasks"][0]["requirements"] = ""
    elif fault == "inputs":
        value["tasks"][0]["inputs"] = [True]
    elif fault == "oracles":
        value["tasks"][0]["expected"] = []
    else:
        value["tasks"][0]["path"] = "/etc/passwd"
    with pytest.raises((ValueError, WorkspaceAccessError)):
        load_baseline_cases(json.dumps(value).encode())


def test_every_nested_function_requires_description():
    """Check helper and class descriptions rather than only the public solve entry."""
    with pytest.raises(WorkspaceAccessError):
        described_code(SOURCE + "\ndef helper():\n    return 1\n")
