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
