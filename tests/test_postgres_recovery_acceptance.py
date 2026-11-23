"""Test maintenance safeguards without restarting infrastructure or reading backup payloads."""

import importlib.util
import json
from pathlib import Path
from unittest.mock import Mock

import pytest

spec = importlib.util.spec_from_file_location(
    "recovery", Path(__file__).parents[1] / "scripts/postgres_recovery_acceptance.py"
)
recovery = importlib.util.module_from_spec(spec)
spec.loader.exec_module(recovery)


def test_drop_probe_guard(tmp_path):
    """Refuse accidental deletion of an application database even on operator error."""
    drill = recovery.RecoveryAcceptance(tmp_path / "backup")
    drill.sql = Mock()
    for name in ("local_assistant", "keycloak_db", "postgres", "la_restore_probe_bad"):
        with pytest.raises(ValueError):
            drill.drop_probe(name)
    drill.sql.assert_not_called()


def test_restore_mismatch_cleans_only_probe(tmp_path):
    """Clean the isolated target and withhold verification when the restored rows differ."""
    drill = recovery.RecoveryAcceptance(tmp_path / "backup")
    archive = tmp_path / "snapshot.dump"
    archive.write_bytes(b"fixture")
    drill.sql = Mock(return_value="")
    drill.command = Mock(return_value=b"")
    drill.fingerprint = Mock(return_value={"assistant.messages": "different"})
    with pytest.raises(RuntimeError, match="differ"):
        drill.verify_restore(archive, {"assistant.messages": "expected"}, "security")
    assert drill.manifest["restore_verified"] is False
    assert (
        drill.sql.call_args_list[-1]
        .args[1]
        .startswith('DROP DATABASE "la_restore_probe_')
    )


def test_quiet_gate_rejects_active_transactions(tmp_path):
    """Prevent maintenance from progressing while other consumers hold transactions."""
    drill = recovery.RecoveryAcceptance(tmp_path / "backup")
    drill.sql = Mock(return_value="1")
    with pytest.raises(RuntimeError, match="drained"):
        drill.require_quiet()


def test_backup_permissions_and_manifest(tmp_path):
    """Keep backup files private, exclusive and covered by a SHA-256 manifest."""
    drill = recovery.RecoveryAcceptance(tmp_path / "backup")

    def write_backup(arguments, *, input_data=None, output=None):
        """Write a deterministic archive fixture without invoking Docker."""
        output.write(b"protected backup fixture")

    drill.command = write_backup
    path = drill.private_output("test.dump", [])
    assert path.stat().st_mode & 0o777 == 0o600
    assert drill.directory.stat().st_mode & 0o777 == 0o700
    drill.save_manifest()
    payload = json.loads((drill.directory / "manifest.json").read_text())
    assert len(payload["backups"][0]["sha256"]) == 64
    assert payload["restore_verified"] is False
    with pytest.raises(FileExistsError):
        drill.private_output("test.dump", [])


def test_restore_rejects_acl_mismatch(tmp_path):
    """Do not certify a data-matching restore whose ownership or access grants differ."""
    drill = recovery.RecoveryAcceptance(tmp_path / "backup")
    archive = tmp_path / "snapshot.dump"
    archive.write_bytes(b"fixture")
    drill.sql = Mock(return_value="")
    drill.command = Mock(return_value=b"")
    drill.fingerprint = Mock(return_value={"assistant.messages": "expected"})
    drill.security_fingerprint = Mock(return_value="wrong-acl")
    with pytest.raises(RuntimeError, match="ownership or ACLs"):
        drill.verify_restore(
            archive, {"assistant.messages": "expected"}, "expected-acl"
        )
    assert drill.manifest["restore_verified"] is False


@pytest.mark.parametrize(
    "extra", [[], ["--execute-restart"], ["--consumer-url", "http://127.0.0.1:9/x"]]
)
def test_cli_refuses_the_legacy_canary_run_by_default(tmp_path, monkeypatch, extra):
    """Follow ADR-123: without the explicit flag, touch neither Docker, the database nor the backup path."""
    drill = Mock()
    monkeypatch.setattr(recovery, "RecoveryAcceptance", drill)
    directory = tmp_path / "backup"
    assert recovery.main(["--backup-directory", str(directory), *extra]) == 2
    drill.assert_not_called()
    assert not directory.exists()


@pytest.mark.parametrize("restart", [False, True])
def test_explicit_legacy_flag_runs_the_superseded_drill(tmp_path, monkeypatch, restart):
    """Run the old canary drill only when the operator names it, passing restart through unchanged."""
    drill = Mock()
    monkeypatch.setattr(recovery, "RecoveryAcceptance", drill)
    directory = tmp_path / "backup"
    arguments = ["--backup-directory", str(directory), "--legacy-canary-run"]
    if restart:
        arguments.append("--execute-restart")
    assert recovery.main(arguments) == 0
    drill.assert_called_once_with(directory)
    drill.return_value.run.assert_called_once_with(
        restart=restart,
        consumer_url="http://127.0.0.1:8081/realms/master/.well-known/openid-configuration",
    )


def test_explicit_legacy_run_failure_still_returns_one(tmp_path, monkeypatch, caplog):
    """Keep the sanitized failure exit code and audit event when the requested legacy run fails."""
    drill = Mock()
    drill.return_value.run.side_effect = RuntimeError("PRIVATE-DETAIL")
    monkeypatch.setattr(recovery, "RecoveryAcceptance", drill)
    arguments = ["--backup-directory", str(tmp_path / "b"), "--legacy-canary-run"]
    assert recovery.main(arguments) == 1
    assert "postgres_recovery_acceptance_failed type=RuntimeError" in caplog.text
    assert "PRIVATE-DETAIL" not in caplog.text
