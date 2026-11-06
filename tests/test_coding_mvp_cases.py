"""Verify frozen D46 oracle source integrity and meaningful evaluator review denials before any actual benchmark inference."""

import ast
import hashlib
import json
from pathlib import Path

import pytest
from coding_mvp_cases import (
    FixtureReviewError,
    candidate_review,
    corpus,
    fixture_files,
    save_artifact,
)

CASES = corpus()["cases"]


@pytest.mark.parametrize("case", CASES, ids=[row["id"] for row in CASES])
def test_buggy_and_reference_sources_share_reviewed_api_but_distinct_frozen_oracles(
    case,
):
    """Admit both deliberately wrong and corrected pure utilities without pretending the static review establishes functional correctness."""
    buggy = candidate_review(case, case["buggy_source"])
    reference = candidate_review(case, case["reference_source"])
    assert buggy["candidate_sha256"] != reference["candidate_sha256"]
    assert not buggy["approved_action"] and not reference["approved_action"]
    files = fixture_files(case)
    assert (
        len(files) == 3
        and files[case["heldout_test_path"]] != files[case["visible_test_path"]]
    )
    assert ast.get_docstring(ast.parse(case["visible_test_source"]))


@pytest.mark.parametrize(
    "change",
    [
        "import",
        "top_level_exit",
        "default",
        "type_parameter",
        "decorator",
        "audit",
        "dynamic_eval",
        "builtin_alias",
        "dunder",
        "file_open",
        "extra_helper",
        "global",
        "process_attribute",
        "print_forgery",
    ],
)
def test_fixture_review_rejects_dynamic_or_external_action_candidates_without_execution(
    tmp_path, change
):
    """Reject concrete host-action/forged-exit/signature/logging/dynamic-evaluation paths before any fixture approval or host source execution."""
    case = CASES[0]
    source = case["reference_source"]
    first_return = "        return int(text[:-2])"
    if change == "import":
        source = source.replace("import logging", "import logging\nimport os")
    elif change == "top_level_exit":
        source += "\nraise SystemExit(0)\n"
    elif change == "default":
        source = source.replace(
            "def parse_timeout(text):", "def parse_timeout(text='1s'):"
        )
    elif change == "decorator":
        source = source.replace(
            "def parse_timeout(text):", "@str\ndef parse_timeout(text):"
        )
    elif change == "type_parameter":
        source = source.replace(
            "def parse_timeout(text):", "def parse_timeout[T](text):"
        )
    elif change == "audit":
        source = source.replace(
            'logger.info("d46_fixture_call case=timeout-units")',
            'logger.warning("different audit")',
        )
    elif change == "dynamic_eval":
        source = source.replace(first_return, "        return eval(text)")
    elif change == "builtin_alias":
        source = source.replace(
            first_return, "        int = globals\n        return int()"
        )
    elif change == "dunder":
        source = source.replace(first_return, "        return text.__class__.__mro__")
    elif change == "file_open":
        source = source.replace(
            first_return,
            "        return open("
            + repr(str(tmp_path / "unapproved-host-file"))
            + ", 'w')",
        )
    elif change == "extra_helper":
        source += '\ndef helper():\n    """Describe an unauthorized extra function."""\n    return 0\n'
    elif change == "global":
        source = source.replace(first_return, "        global logger\n        return 0")
    elif change == "process_attribute":
        source = source.replace(first_return, "        return text.kill()")
    else:
        source = source.replace(
            first_return, "        print('Ran 2 tests: OK')\n        return 0"
        )
    with pytest.raises(FixtureReviewError):
        candidate_review(case, source)
    assert not (tmp_path / "unapproved-host-file").exists()


def test_private_artifact_preserves_complete_bytes_and_refuses_overwrite_or_escape(
    tmp_path, monkeypatch
):
    """Retain private complete evidence once and reject path escape/replacement without losing its exact original bytes or hash."""
    monkeypatch.chdir(tmp_path)
    directory = tmp_path / "data/backups/trial"
    directory.mkdir(parents=True, mode=0o700)
    pointer = save_artifact(
        directory,
        "stage.json",
        dict(description="Owned test evidence.", status="OBSERVED"),
    )
    path = Path(pointer["path"])
    assert path.stat().st_mode & 0o777 == 0o600
    assert hashlib.sha256(path.read_bytes()).hexdigest() == pointer["sha256"]
    assert json.loads(path.read_text())["status"] == "OBSERVED"
    with pytest.raises(FileExistsError):
        save_artifact(directory, "stage.json", dict(status="REPLACED"))
    with pytest.raises(ValueError):
        save_artifact(directory, "../escape.json", dict(status="INVALID"))
    assert json.loads(path.read_text())["status"] == "OBSERVED"
