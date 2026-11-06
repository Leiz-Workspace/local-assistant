"""Verify durable-admission input identity and lease fences independently of PostgreSQL execution."""

import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from test_ingestion_contract import sample

from src.application.services.file_storage_policy import StoragePolicyError
from src.application.services.ingestion_contract import plan_ingestion
from src.infrastructure.repositories.ingestion_journal import (
    PostgresIngestionJournal,
    admission_values,
)


def test_admission_snapshot_has_no_text_and_binds_complete_counts():
    """Persist exact retry identity and complete point/token snapshots without private document content."""
    plan = plan_ingestion(*sample())
    first = admission_values(plan, [17])
    assert first == admission_values(plan, [17])
    assert first["fingerprint"] != admission_values(plan, [18])["fingerprint"]
    assert plan.points[0].text not in json.dumps(first, default=str)
    assert first["points"] == [point.point_id for point in plan.points]


@pytest.mark.parametrize(
    "field",
    [
        "generation",
        "job_id",
        "manifest_json",
        "owner_id",
        "file_id",
        "source_sha256",
        "point_id",
    ],
)
def test_forged_plan_identity_is_rejected_before_admission(field):
    """Refuse inconsistent dataclass snapshots even when an internal caller bypasses the planner."""
    plan = plan_ingestion(*sample())
    if field == "generation":
        changed = replace(plan, generation="b" * 64)
    elif field == "manifest_json":
        changed = replace(plan, manifest_json="{}")
    elif field == "source_sha256":
        changed = replace(plan, source_sha256="b" * 64)
    elif field == "point_id":
        changed = replace(plan, points=(replace(plan.points[0], point_id=uuid4()),))
    else:
        changed = replace(plan, **{field: uuid4()})
    with pytest.raises(StoragePolicyError):
        admission_values(changed, [17])


@pytest.mark.parametrize("field", ["token", "state", "expiry", "deadline"])
def test_old_worker_cannot_renew_retry_or_publish(field):
    """Reject wrong identity, terminal state, expired lease and absolute-deadline violations."""
    journal = PostgresIngestionJournal(None, uuid4())
    now = datetime.now(timezone.utc)
    token = uuid4()
    row = dict(
        state="running",
        lease_token=token,
        lease_expires_at=now + timedelta(seconds=30),
        deadline_at=now + timedelta(seconds=60),
    )
    journal._lease(row, token, now)
    if field == "token":
        token = uuid4()
    elif field == "state":
        row["state"] = "stale"
    elif field == "expiry":
        row["lease_expires_at"] = now
    else:
        row["deadline_at"] = now
    with pytest.raises(StoragePolicyError, match="ingestion_lease_lost"):
        journal._lease(row, token, now)


def test_canonical_but_incomplete_manifest_has_safe_error():
    """Reject malformed but self-consistently hashed snapshots without exposing parser details."""
    import hashlib
    from uuid import NAMESPACE_URL, uuid5

    plan = plan_ingestion(*sample())
    generation = hashlib.sha256(b"{}").hexdigest()
    changed = replace(
        plan,
        manifest_json="{}",
        generation=generation,
        job_id=uuid5(NAMESPACE_URL, "local-assistant:ingestion:" + generation),
    )
    with pytest.raises(StoragePolicyError, match="ingestion_plan_invalid"):
        admission_values(changed, [17])


def test_privilege_downgrade_cannot_broaden_immutable_column_access():
    """Keep V004 rollback from silently restoring inherited broad table UPDATE privileges."""
    import importlib.util
    from pathlib import Path

    path = (
        Path(__file__).resolve().parents[1]
        / "migrations/versions/0004_ingestion_column_grants.py"
    )
    spec = importlib.util.spec_from_file_location("ingestion_grant_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    with pytest.raises(RuntimeError, match="reviewed forward migration"):
        migration.downgrade()
