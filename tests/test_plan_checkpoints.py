"""Test durable private signed metadata, exact latest recovery, forward-only budgets and nonblocking kernel locks."""

import copy
from uuid import uuid4

import pytest

from src.application.ports.plan_checkpoint import CheckpointError
from src.infrastructure.plan_checkpoints import PlanCheckpointStore


def state():
    """Create a minimal ready metadata record without raw source, prompts, bodies or approval grants."""
    return dict(
        owner_id=str(uuid4()),
        workspace_id=str(uuid4()),
        profile="core",
        plan_sha256="a" * 64,
        catalog_sha256="b" * 64,
        created_at=100.0,
        observed_at=100.0,
        expires_at=220.0,
        next_step=0,
        attempts=0,
        step_attempts=[0],
        output_bytes=0,
        outputs=[],
        status="ready",
    )


def inflight(value):
    """Charge the only step exactly once before any disposable action boundary."""
    value = copy.deepcopy(value)
    value.update(attempts=1, step_attempts=[1], status="inflight")
    return value


def test_signed_chain_reopens_with_same_key_and_requires_exact_latest_reference(
    tmp_path,
):
    """Read a durable chain through a fresh store object without recovering any tool/approval authority."""
    root = tmp_path / "state"
    store = PlanCheckpointStore(root)
    run_id = uuid4()
    value = state()
    with store.lock(run_id):
        first = store.append(run_id, value, None)
        second = store.append(run_id, inflight(value), first)
        with pytest.raises(CheckpointError, match="stale"):
            store.append(run_id, inflight(value), first)
    key = (root / "signing.key").read_bytes()
    store.close()
    reopened = PlanCheckpointStore(root)
    actual, reference = reopened.latest(run_id)
    assert (
        reference == second
        and actual["attempts"] == 1
        and (root / "signing.key").read_bytes() == key
    )
    assert (root / "signing.key").stat().st_mode & 0o777 == 0o600
    assert root.stat().st_mode & 0o777 == 0o700
    reopened.close()


@pytest.mark.parametrize("change", ["tamper", "partial", "gap"])
def test_corrupt_newest_record_never_falls_back_to_an_older_signed_state(
    tmp_path, change
):
    """Reject damaged, unsigned or noncontiguous durable state rather than rerunning an action from an old snapshot."""
    root = tmp_path / "state"
    store = PlanCheckpointStore(root)
    run_id = uuid4()
    with store.lock(run_id):
        store.append(run_id, state(), None)
    if change == "tamper":
        path = root / f"{run_id}.01.json"
        path.write_bytes(path.read_bytes().replace(b'"attempts":0', b'"attempts":1'))
    else:
        path = root / f"{run_id}.{('02' if change == 'partial' else '03')}.json"
        path.write_bytes(b"{")
    path.chmod(0o600)
    with pytest.raises(CheckpointError, match="invalid"):
        store.latest(run_id)
    store.close()


def test_lock_is_nonblocking_across_independent_store_handles_and_never_removes_outer_ownership(
    tmp_path,
):
    """Keep one run owner across competing recovery attempts and retain its valid append permission after contention."""
    root = tmp_path / "state"
    first = PlanCheckpointStore(root)
    second = PlanCheckpointStore(root)
    run_id = uuid4()
    with first.lock(run_id):
        with pytest.raises(CheckpointError, match="busy"):
            with second.lock(run_id):
                pass
        with pytest.raises(CheckpointError, match="busy"):
            with first.lock(run_id):
                pass
        reference = first.append(run_id, state(), None)
    assert second.latest(run_id)[1] == reference
    first.close()
    second.close()


def test_budget_reset_raw_body_and_private_key_symlinks_are_refused(tmp_path):
    """Prevent accidental budget rollback or secret-bearing checkpoint fields and refuse unowned signing material."""
    root = tmp_path / "state"
    store = PlanCheckpointStore(root)
    run_id = uuid4()
    value = state()
    with store.lock(run_id):
        first = store.append(run_id, value, None)
        second = store.append(run_id, inflight(value), first)
        with pytest.raises(CheckpointError, match="invalid"):
            store.append(run_id, value, second)
        with pytest.raises(CheckpointError, match="invalid"):
            store.append(run_id, dict(value, arguments="private secret"), second)
    store.close()
    (root / "signing.key").chmod(0o644)
    with pytest.raises(CheckpointError, match="unavailable"):
        PlanCheckpointStore(root)


def test_directory_fd_cannot_be_redirected_by_host_path_replacement(tmp_path):
    """Keep writes in the already pinned private directory rather than following a replacement symlink."""
    root = tmp_path / "state"
    store = PlanCheckpointStore(root)
    moved = tmp_path / "original"
    root.rename(moved)
    other = tmp_path / "other"
    other.mkdir(mode=0o700)
    root.symlink_to(other, target_is_directory=True)
    run_id = uuid4()
    with store.lock(run_id):
        store.append(run_id, state(), None)
    assert (moved / f"{run_id}.01.json").is_file() and not list(other.iterdir())
    store.close()
