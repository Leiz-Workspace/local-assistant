"""Verify bounded source-only workflow contracts and proposal parsing without model calls, source execution or granted actions."""

import hashlib
import json

import pytest

from src.application.services.coding_workflow import (
    bounded_record,
    resolve_candidate,
    workflow_messages,
    workflow_options,
)
from src.application.services.workspace_policy import WorkspaceAccessError

CODE = '"""Describe a disposable coding workflow fixture."""\ndef add(left, right):\n    """Return the two integer values added together."""\n    return left + right\n'


def selection(path, raw=CODE.encode()):
    """Build only an explicit fixture path/hash pair without opening a host source file."""
    return dict(path=path, expected_sha256=hashlib.sha256(raw).hexdigest())


def options(**changes):
    """Create finite disposable target/test options with explicit fixed profile and bounded issue."""
    values = dict(
        issue="Fix integer addition.",
        target=selection("sample.py"),
        tests=[selection("test_sample.py")],
        profile="python_unittest",
    )
    return workflow_options(**(values | changes))


def test_exact_prompt_uses_only_selected_bytes_and_immutable_options():
    """Bind fixed target/hash/roles and expose no generated authority or unselected context."""
    selected = options()
    files = selected.selections()
    files[0]["path"] = "changed.py"
    assert selected.files[0][0] == "sample.py"
    messages = workflow_messages(
        selected, dict.fromkeys(["sample.py", "test_sample.py"], CODE.encode())
    )
    value = json.loads(messages[1]["content"])
    assert value["fixed_target"] == "sample.py" and not value["action_authority"]
    assert [row["role"] for row in value["sources"]] == ["target", "test"]
    assert all(row["source"] == CODE for row in value["sources"])
    assert (
        "English" in messages[0]["content"]
        and "separate exact owner approvals" in messages[0]["content"]
    )


@pytest.mark.parametrize(
    "changes",
    [
        dict(issue=""),
        dict(issue="x" * 2049),
        dict(issue="\ud800"),
        dict(issue="bad\x00issue"),
        dict(tests=[]),
        dict(tests=[selection("test_sample.py")] * 4),
        dict(tests=[selection("sample.py")]),
        dict(target=selection("../sample.py")),
        dict(target=selection(".env.py")),
        dict(target=selection("sample.txt")),
        dict(target=dict(path="sample.py", expected_sha256="0" * 64, command="true")),
        dict(profile="shell"),
    ],
)
def test_invalid_or_widened_selection_is_rejected_before_source_access(changes):
    """Reject invalid context sizes, duplicate/unsafe paths, command overrides and unsupported profiles."""
    with pytest.raises(WorkspaceAccessError):
        options(**changes)


@pytest.mark.parametrize(
    "originals",
    [
        {},
        {"sample.py": b"changed", "test_sample.py": CODE.encode()},
        {
            "sample.py": CODE.encode(),
            "test_sample.py": CODE.encode(),
            "outside.py": b"unselected",
        },
    ],
)
def test_missing_changed_or_extra_source_context_prevents_prompt_generation(originals):
    """Refuse source drift or accidental context expansion before making any inference request."""
    with pytest.raises(WorkspaceAccessError):
        workflow_messages(options(), originals)


def test_prompt_limit_rejects_complete_escaped_sources_without_truncation():
    """Reject JSON expansion beyond the prompt budget while leaving every selected original byte intact."""
    raw = ('"""' + "\t" * 8100 + '"""').encode()
    values = [selection(path, raw) for path in ["sample.py", "test_a.py", "test_b.py"]]
    selected = workflow_options(
        "Fix this module.", values[0], values[1:], "python_unittest"
    )
    with pytest.raises(WorkspaceAccessError) as caught:
        workflow_messages(selected, dict.fromkeys([row["path"] for row in values], raw))
    assert caught.value.code == "workflow_prompt_limit"


def test_full_candidate_remains_untrusted_and_mutable_returns_are_isolated():
    """Accept a complete described proposal without asserting edits, test quality or approval authority."""
    value = resolve_candidate(
        json.dumps(dict(plan=["Replace subtraction with addition."], replacement=CODE))
    )
    assert value["replacement"] == CODE and value["plan_trust"] == "generated_untrusted"
    assert not value["action_authority"] and not value["quality_evaluated"]
    copied = bounded_record(value)
    copied["plan"].clear()
    assert value["plan"]


@pytest.mark.parametrize(
    "value",
    [
        None,
        [],
        {},
        dict(plan=[], replacement=CODE),
        dict(plan=["x"] * 6, replacement=CODE),
        dict(plan=["x" * 513], replacement=CODE),
        dict(plan=[" "], replacement=CODE),
        dict(plan=["x"], replacement="VALUE=1"),
        dict(plan=["x"], replacement='"""Module."""\ndef function():\n    return 1\n'),
        dict(plan=["x"], replacement='"""Module."""\nclass Example:\n    pass\n'),
        dict(plan=["x"], replacement=CODE + "\x00"),
        dict(plan=["x"], replacement=CODE, command="true"),
        dict(plan=["x"], replacement=CODE, path="other.py"),
        dict(plan=["x"], replacement=CODE, approval="yes"),
        dict(plan=["x"], replacement=CODE, executed=True),
    ],
)
def test_generated_invalid_shape_descriptions_or_action_fields_are_rejected(value):
    """Reject malformed proposals instead of repairing model output or accepting model-selected action scope."""
    with pytest.raises(WorkspaceAccessError) as caught:
        resolve_candidate(json.dumps(value))
    assert caught.value.code == "workflow_candidate_invalid"


@pytest.mark.parametrize(
    "raw",
    [
        '{"plan":["x"],"replacement":"a","replacement":"b"}',
        '{"plan":[NaN],"replacement":"x"}',
        "```json\n{}\n```",
        "x" * 16385,
    ],
)
def test_ambiguous_nonfinite_fenced_and_oversized_completions_are_not_repaired(raw):
    """Fail the first invalid completion rather than extracting a permissive candidate or silently truncating it."""
    with pytest.raises(WorkspaceAccessError):
        resolve_candidate(raw)


def test_valid_syntax_does_not_execute_source_or_claim_security_sanitization(tmp_path):
    """Parse potentially malicious described source as untrusted data while proving its top-level expression never executes on host."""
    target = tmp_path / "must-not-exist"
    code = (
        '"""Untrusted source syntax fixture."""\n__import__("pathlib").Path('
        + repr(str(target))
        + ').write_text("never execute")\n'
    )
    value = resolve_candidate(
        json.dumps(dict(plan=["Inspect the proposed full file."], replacement=code))
    )
    assert not target.exists() and not value["action_authority"]


@pytest.mark.parametrize(
    "value",
    [[], dict(data="x" * 131073), dict(number=float("nan")), dict(text="\ud800")],
)
def test_noncanonical_oversized_or_aliased_records_cannot_exceed_retention_budget(
    value,
):
    """Reject invalid public/attempt records before retaining or serializing unbounded workflow history."""
    with pytest.raises(WorkspaceAccessError):
        bounded_record(value)
