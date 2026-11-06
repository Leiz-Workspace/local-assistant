"""Verify current-source full regression safeguards, in-memory credential preparation and explicit failure/skip accounting without launching the full suite."""

import json

import pytest

from scripts import full_regression as module


def test_environment_removes_operator_overrides_and_keeps_credentials_in_memory():
    """Bind actual integration variables without retaining inherited Vault or feature-toggle authority."""
    secret = dict(
        username="fixture",
        password="private-fixture",
        host="127.0.0.1",
        port=5432,
        database="fixture",
    )
    value = module.test_environment(
        secret,
        secret,
        "private-vector",
        dict(
            PATH="/usr/bin",
            VAULT_TOKEN="private-vault",
            ASSISTANT_WEB_SEARCH_ENABLED="1",
            ASSISTANT_AUTH_FILE="private-file",
        ),
    )
    assert not any(key.startswith(("VAULT_", "ASSISTANT_")) for key in value)
    assert (
        value["LOCAL_ASSISTANT_LIVE_E2E"] == "1"
        and value["LOCAL_ASSISTANT_EMBEDDING_COMPARE_LIVE"] == "1"
    )
    assert value["LOCAL_ASSISTANT_QDRANT_PROBE_KEY"] == "private-vector"


def test_redaction_handles_complete_url_raw_secrets_and_overlapping_values():
    """Remove longer values first so an overlapping short credential cannot leave part of a private URL exposed."""
    assert (
        module.redact(
            "postgresql://user:private@host private",
            ["private", "postgresql://user:private@host"],
        )
        == "[REDACTED] [REDACTED]"
    )


@pytest.mark.parametrize(
    "line,expected",
    [
        (
            "==== 100 passed in 1.50s ====",
            dict(passed=100, failed=0, skipped=0, errors=0),
        ),
        (
            "==== 2 failed, 90 passed, 8 skipped in 4.00s ====",
            dict(passed=90, failed=2, skipped=8, errors=0),
        ),
    ],
)
def test_summary_counts_never_hide_nonzero_skips_or_failures(line, expected):
    """Keep all final counts explicit rather than promoting partial or skipped cohorts to a complete pass."""
    result = module.summary_counts(line)
    assert all(result[key] == value for key, value in expected.items())


def test_missing_summary_fails_closed():
    """Reject an interrupted test process that never produced complete terminal pytest results."""
    with pytest.raises(RuntimeError):
        module.summary_counts("interrupted without a final result")


def test_private_progress_metadata_is_atomic_and_owner_only(tmp_path):
    """Publish fresh status snapshots without public file permissions or leftover temporary files."""
    path = tmp_path / "result.json"
    module.private_json(
        path, dict(description="Private fixture status.", status="running")
    )
    module.private_json(
        path, dict(description="Private fixture status.", status="complete")
    )
    assert json.loads(path.read_text())["status"] == "complete"
    assert (
        path.stat().st_mode & 0o777 == 0o600
        and not path.with_name("result.json.tmp").exists()
    )


def test_changed_source_inventory_or_bytes_refuses_acceptance(monkeypatch):
    """Require full identical source mappings, including newly added files, before calling a global result reproducible."""
    monkeypatch.setattr(module, "source_manifest", lambda: {"fixture.py": "after"})
    with pytest.raises(RuntimeError, match="source_changed"):
        module.verify_manifest({"fixture.py": "before"})
    with pytest.raises(RuntimeError, match="source_changed"):
        module.verify_manifest({})


def test_singular_collection_error_is_reported_without_fabricating_a_clean_run():
    """Retain pytest's singular error count when some tests passed but collection/setup still failed."""
    result = module.summary_counts("==== 2 passed, 1 error in 0.50s ====")
    assert result["errors"] == 1 and result["passed"] == 2
