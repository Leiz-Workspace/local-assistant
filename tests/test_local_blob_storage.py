"""Exercise local blob durability, descriptor safety and process locks on real files."""

import errno
import hashlib
import logging
import multiprocessing
import os
import signal
import stat
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import pytest

from src.application.services.file_storage_policy import (
    DEFAULT_POLICY,
    StoragePolicyError,
    plan_reservation,
)
from src.infrastructure.local_blob_storage import (
    BlobIdentity,
    BlobStorageError,
    LocalBlobStorage,
)

logger = logging.getLogger(__name__)
PAYLOAD = b"private bounded upload\n"


def make_plan(payload=PAYLOAD, **changes):
    """Create a validated reservation with fresh server identities for each test."""
    values = {
        "owner_id": uuid4(),
        "file_id": uuid4(),
        "filename": "private.txt",
        "size_bytes": len(payload),
        "expected_sha256": hashlib.sha256(payload).hexdigest(),
    }
    values.update(changes)
    return plan_reservation(**values)


@pytest.fixture
def storage(tmp_path):
    """Open a disposable private root and close its descriptor after each test."""
    with LocalBlobStorage(tmp_path / "blobs") as adapter:
        logger.info("test_blob_storage_ready")
        yield adapter


def write_ready(storage, plan=None):
    """Publish a small test blob and close its exclusive writer lock."""
    plan = plan or make_plan()
    with storage.create_writer(plan, uuid4()) as writer:
        writer.write(PAYLOAD)
        writer.seal()
        writer.publish()
        identity = writer.identity
    return identity


def process_hold(root, plan, identity, mode, connection):
    """Hold a real independent process lock until the parent releases or kills it."""
    try:
        with LocalBlobStorage(Path(root)) as adapter:
            if mode == "writer":
                handle = adapter.create_writer(plan, identity.lease_id)
                handle.write(PAYLOAD[:3])
            else:
                handle = adapter.open_reader(identity)
            with handle:
                connection.send("locked")
                connection.recv()
        connection.send("closed")
    finally:
        connection.close()


def process_crash_boundary(root, plan, identity, boundary, connection):
    """Pause an independent uploader at a real filesystem crash boundary for SIGKILL."""
    root = Path(root)

    def checkpoint(name):
        """Notify the parent at the selected boundary while retaining every open FD."""
        if name == boundary:
            connection.send(name)
            connection.recv()

    try:
        with LocalBlobStorage(root) as adapter:
            with adapter.create_writer(plan, identity.lease_id) as writer:
                checkpoint("created")
                writer.write(PAYLOAD)
                checkpoint("written")
                writer.seal()
                checkpoint("sealed")
                original_link, original_sync, original_unlink = (
                    os.link,
                    os.fsync,
                    os.unlink,
                )
                final = root.joinpath(*identity.object_parts)
                stage = root.joinpath(*identity.staging_parts)

                def link_then_pause(*args, **kwargs):
                    """Stop immediately after creating the second hard link."""
                    original_link(*args, **kwargs)
                    checkpoint("linked")

                def sync_then_pause(fd):
                    """Stop after syncing the publication or removal parent directory."""
                    original_sync(fd)
                    if final.exists():
                        info = os.fstat(fd)
                        if info.st_ino == final.parent.stat().st_ino:
                            checkpoint("object_synced")
                        if (
                            not stage.exists()
                            and info.st_ino == stage.parent.stat().st_ino
                        ):
                            checkpoint("stage_synced")

                def unlink_then_pause(*args, **kwargs):
                    """Stop after unlink but before the staging directory sync."""
                    original_unlink(*args, **kwargs)
                    checkpoint("stage_unlinked")

                os.link, os.fsync, os.unlink = (
                    link_then_pause,
                    sync_then_pause,
                    unlink_then_pause,
                )
                writer.publish()
                checkpoint("published")
    finally:
        connection.close()


@pytest.mark.parametrize(
    "boundary",
    [
        "created",
        "written",
        "sealed",
        "linked",
        "object_synced",
        "stage_unlinked",
        "stage_synced",
        "published",
    ],
)
def test_real_process_crash_reconciles_known_names(storage, tmp_path, boundary):
    """Recover exact names after SIGKILL at every implemented FS publication boundary."""
    plan = make_plan()
    identity = BlobIdentity(plan.owner_id, plan.file_id, uuid4())
    context = multiprocessing.get_context("spawn")
    parent, child = context.Pipe()
    process = context.Process(
        target=process_crash_boundary,
        args=(str(tmp_path / "blobs"), plan, identity, boundary, child),
    )
    process.start()
    child.close()
    try:
        assert parent.poll(10), "Uploader did not reach its crash boundary"
        assert parent.recv() == boundary
        assert storage.purge(identity) is False
        process.kill()
        process.join(5)
        assert not process.is_alive()
        assert storage.purge(identity) is True
        assert storage.purge(identity) is True
        root = tmp_path / "blobs"
        assert not root.joinpath(*identity.staging_parts).exists()
        assert not root.joinpath(*identity.object_parts).exists()
    finally:
        if process.is_alive():
            process.kill()
        process.join(5)
        parent.close()


def test_publish_read_and_idempotent_purge(storage, tmp_path):
    """Verify bytes, opaque names, private permissions and repeatable physical cleanup."""
    plan = make_plan()
    with storage.create_writer(plan, uuid4()) as writer:
        writer.write(PAYLOAD[:5])
        writer.write(PAYLOAD[5:])
        writer.seal()
        identity = writer.identity
        assert storage.purge(identity) is False
        with writer.verification_reader() as source:
            assert source.read() == PAYLOAD
        writer.publish()
        assert storage.purge(identity) is False
        assert not (tmp_path / "blobs").joinpath(*identity.staging_parts).exists()
    final = (tmp_path / "blobs").joinpath(*identity.object_parts)
    assert final.read_bytes() == PAYLOAD
    for item in (tmp_path / "blobs").rglob("*"):
        assert stat.S_IMODE(item.stat().st_mode) == (0o700 if item.is_dir() else 0o600)
    with storage.open_reader(identity) as reader:
        assert reader.read(3) == PAYLOAD[:3]
        assert reader.read() == PAYLOAD[3:]
        assert reader.read() == b""
        assert storage.purge(identity) is False
    assert storage.purge(identity) is True
    assert storage.purge(identity) is True
    assert not final.exists()


@pytest.mark.parametrize("mode", ["writer", "reader"])
def test_paused_process_retains_inode_until_killed(storage, tmp_path, mode):
    """Prove elapsed lease time cannot replace cross-process FD lock ownership."""
    plan = make_plan()
    identity = BlobIdentity(plan.owner_id, plan.file_id, uuid4())
    if mode == "reader":
        identity = write_ready(storage, plan)
    context = multiprocessing.get_context("spawn")
    parent, child = context.Pipe()
    process = context.Process(
        target=process_hold,
        args=(str(tmp_path / "blobs"), plan, identity, mode, child),
    )
    process.start()
    child.close()
    try:
        assert parent.poll(10), "Child did not acquire its lock"
        assert parent.recv() == "locked"
        os.kill(process.pid, signal.SIGSTOP)
        assert storage.purge(identity) is False
        parts = identity.staging_parts if mode == "writer" else identity.object_parts
        assert (tmp_path / "blobs").joinpath(*parts).exists()
        process.kill()
        process.join(5)
        assert not process.is_alive()
        assert storage.purge(identity) is True
        assert not (tmp_path / "blobs").joinpath(*parts).exists()
    finally:
        if process.is_alive():
            process.kill()
        process.join(5)
        parent.close()


@pytest.mark.parametrize("kind", ["root", "ancestor"])
def test_root_symlinks_rejected(tmp_path, kind):
    """Refuse symlinks anywhere in the configured root path without modifying targets."""
    real = tmp_path / "real"
    real.mkdir(mode=0o700)
    linked = tmp_path / "link"
    linked.symlink_to(real, target_is_directory=True)
    target = linked if kind == "root" else linked / "new-root"
    with pytest.raises(BlobStorageError, match="unsafe_root"):
        LocalBlobStorage(target)
    assert list(real.iterdir()) == []


@pytest.mark.parametrize("mode", [0o755, 0o750, 0o777, 0o500])
def test_nonprivate_root_rejected(tmp_path, mode):
    """Fail closed on existing incorrect permissions without silently chmodding data."""
    root = tmp_path / "root"
    root.mkdir(mode=0o700)
    root.chmod(mode)
    with pytest.raises(BlobStorageError, match="unsafe_directory"):
        LocalBlobStorage(root)
    assert stat.S_IMODE(root.stat().st_mode) == mode


@pytest.mark.parametrize("branch", ["objects", "staging"])
def test_symlinked_subdirectory_never_followed(storage, tmp_path, branch):
    """Keep descriptor traversal from writing or deleting outside the private root."""
    outside = tmp_path / "outside"
    outside.mkdir(mode=0o700)
    sentinel = outside / "sentinel"
    sentinel.write_bytes(b"untouched")
    (tmp_path / "blobs" / branch).symlink_to(outside, target_is_directory=True)
    plan = make_plan()
    if branch == "staging":
        with pytest.raises(OSError):
            storage.create_writer(plan, uuid4())
    else:
        with storage.create_writer(plan, uuid4()) as writer:
            writer.write(PAYLOAD)
            writer.seal()
            with pytest.raises(OSError):
                writer.publish()
    assert sentinel.read_bytes() == b"untouched"
    assert len(list(outside.iterdir())) == 1


@pytest.mark.parametrize("kind", ["symlink", "hardlink", "fifo", "directory", "public"])
def test_unsafe_ready_inode_rejected(storage, tmp_path, kind):
    """Reject nonregular, multiply linked or publicly readable blobs on read and purge."""
    identity = write_ready(storage)
    final = (tmp_path / "blobs").joinpath(*identity.object_parts)
    outside = tmp_path / "sentinel"
    outside.write_bytes(b"untouched")
    outside.chmod(0o600)
    if kind == "public":
        final.chmod(0o644)
    elif kind == "hardlink":
        os.link(final, tmp_path / "extra-link")
    else:
        final.unlink()
        if kind == "symlink":
            final.symlink_to(outside)
        elif kind == "fifo":
            os.mkfifo(final, 0o600)
        else:
            final.mkdir(mode=0o700)
    with pytest.raises((BlobStorageError, OSError)):
        storage.open_reader(identity)
    with pytest.raises(BlobStorageError):
        storage.purge(identity)
    assert outside.read_bytes() == b"untouched"
    assert final.exists()


def test_public_intermediate_directory_rejected(storage, tmp_path):
    """Require mode 0700 on generated directories rather than trusting only the root."""
    (tmp_path / "blobs" / "staging").mkdir(mode=0o755)
    with pytest.raises(BlobStorageError, match="unsafe_directory"):
        storage.create_writer(make_plan(), uuid4())


def test_existing_stage_is_not_truncated(storage, tmp_path):
    """Use exclusive creation so a repeated lease cannot truncate another live writer."""
    plan, lease = make_plan(), uuid4()
    with storage.create_writer(plan, lease) as writer:
        writer.write(PAYLOAD)
        with pytest.raises(BlockingIOError):
            storage.create_writer(plan, lease)
        assert (tmp_path / "blobs").joinpath(
            *writer.identity.staging_parts
        ).read_bytes() == PAYLOAD

    with pytest.raises(FileExistsError):
        storage.create_writer(plan, lease)


def test_publication_collision_preserves_both_objects(storage, tmp_path):
    """Never overwrite or purge a distinct destination inode on publication collision."""
    plan = make_plan()
    identity = write_ready(storage, plan)
    final = (tmp_path / "blobs").joinpath(*identity.object_parts)
    with storage.create_writer(plan, uuid4()) as writer:
        writer.write(PAYLOAD)
        writer.seal()
        collision = writer.identity
        with pytest.raises(BlobStorageError, match="object_exists"):
            writer.publish()
    with pytest.raises(BlobStorageError, match="object_collision"):
        storage.purge(collision)
    assert final.read_bytes() == PAYLOAD
    assert (tmp_path / "blobs").joinpath(
        *collision.staging_parts
    ).read_bytes() == PAYLOAD


@pytest.mark.parametrize("failure", ["short", "overflow", "hash"])
def test_byte_contract_failures_remain_hidden_and_purgeable(storage, tmp_path, failure):
    """Reject invalid streams before publication while preserving cleanup ownership."""
    plan = make_plan(expected_sha256="0" * 64) if failure == "hash" else make_plan()
    with storage.create_writer(plan, uuid4()) as writer:
        identity = writer.identity
        with pytest.raises(StoragePolicyError):
            writer.write(
                PAYLOAD[:-1]
                if failure == "short"
                else PAYLOAD + (b"x" if failure == "overflow" else b"")
            )
            writer.seal()
        with pytest.raises(BlobStorageError, match="writer_not_publishable"):
            writer.publish()
        assert not (tmp_path / "blobs").joinpath(*identity.object_parts).exists()
    assert storage.purge(identity) is True


@pytest.mark.parametrize("size", [0, -1, True, 65537])
def test_reader_chunk_bounds(storage, size):
    """Prevent unbounded reads through a published blob handle."""
    identity = write_ready(storage)
    with storage.open_reader(identity) as reader:
        with pytest.raises(BlobStorageError, match="invalid_read_size"):
            reader.read(size)


@pytest.mark.parametrize("chunk", [b"", b"x" * 65537, "text", bytearray(b"text")])
def test_writer_chunk_bounds(storage, chunk):
    """Reject invalid chunk types and lengths before touching payload bytes."""
    with storage.create_writer(make_plan(), uuid4()) as writer:
        with pytest.raises(BlobStorageError, match="invalid_write_size"):
            writer.write(chunk)
        assert writer.bytes_written == 0


def test_short_os_writes_are_completed(storage, monkeypatch):
    """Finish partial kernel writes while hashing exactly the bytes actually accepted."""
    real_write = os.write

    def write_short(fd, data):
        """Force real partial writes without replacing filesystem behavior."""
        return real_write(fd, data[:3])

    monkeypatch.setattr(os, "write", write_short)
    identity = write_ready(storage)
    with storage.open_reader(identity) as reader:
        assert reader.read() == PAYLOAD


def test_disk_floor_checked_before_write(storage, monkeypatch, tmp_path):
    """Keep partial data charged and hidden when the actual free-space floor is crossed."""
    with storage.create_writer(make_plan(), uuid4()) as writer:

        def exhausted_capacity():
            """Report exactly the free-space floor before the next physical write."""
            return DEFAULT_POLICY.min_free_bytes

        monkeypatch.setattr(storage, "free_bytes", exhausted_capacity)
        with pytest.raises(BlobStorageError, match="insufficient_disk_space"):
            writer.write(PAYLOAD)
        assert writer.bytes_written == 0
        assert (tmp_path / "blobs").joinpath(
            *writer.identity.staging_parts
        ).stat().st_size == 0


def test_kernel_enospc_poison_writer(storage, monkeypatch):
    """Prevent retries from treating an interrupted write as a valid stream."""
    with storage.create_writer(make_plan(), uuid4()) as writer:
        with monkeypatch.context() as context:

            def fail_write(fd, data):
                """Inject a kernel capacity failure at the write boundary."""
                raise OSError(errno.ENOSPC, "sensitive system message")

            context.setattr(os, "write", fail_write)
            with pytest.raises(OSError):
                writer.write(PAYLOAD)
        with pytest.raises(BlobStorageError, match="writer_not_writable"):
            writer.write(PAYLOAD)
    assert storage.purge(writer.identity) is True


@pytest.mark.parametrize("boundary", ["file", "publish_directory", "staging_directory"])
def test_fsync_failure_never_claims_ready(storage, tmp_path, monkeypatch, boundary):
    """Recover exact journal names after failures before or after durable publication."""
    with storage.create_writer(make_plan(), uuid4()) as writer:
        writer.write(PAYLOAD)
        if boundary != "file":
            writer.seal()
        real_sync = os.fsync
        calls = 0

        def fail_sync(fd):
            """Fail at a selected file or parent-directory durability boundary."""
            nonlocal calls
            if boundary == "file" and stat.S_ISREG(os.fstat(fd).st_mode):
                raise OSError(errno.EIO, "sensitive sync message")
            if boundary != "file":
                name = f"{writer.identity.file_id}.blob"
                try:
                    os.stat(name, dir_fd=fd, follow_symlinks=False)
                    is_destination = True
                except (FileNotFoundError, NotADirectoryError):
                    is_destination = False
                if is_destination:
                    calls = 1
                    if boundary == "publish_directory":
                        raise OSError(errno.EIO, "sensitive sync message")
                elif calls:
                    raise OSError(errno.EIO, "sensitive sync message")
            real_sync(fd)

        with monkeypatch.context() as context:
            context.setattr(os, "fsync", fail_sync)
            with pytest.raises((BlobStorageError, OSError)):
                writer.seal() if boundary == "file" else writer.publish()
        assert writer.published is False
        assert storage.purge(writer.identity) is False
    assert storage.purge(writer.identity) is True
    root = tmp_path / "blobs"
    assert not root.joinpath(*writer.identity.object_parts).exists()
    assert not root.joinpath(*writer.identity.staging_parts).exists()


def test_purge_fsync_retry_resyncs_missing_name(storage, monkeypatch, tmp_path):
    """Require a directory resync on retry even when the preceding unlink already ran."""
    identity = write_ready(storage)
    real_sync = os.fsync
    final = (tmp_path / "blobs").joinpath(*identity.object_parts)

    def fail_sync(fd):
        """Simulate failure after unlink and before parent-directory durability."""
        if not final.exists():
            raise OSError(errno.EIO, "sensitive sync message")
        real_sync(fd)

    with monkeypatch.context() as context:
        context.setattr(os, "fsync", fail_sync)
        with pytest.raises(BlobStorageError, match="purge_failed"):
            storage.purge(identity)
    calls = []

    def count_sync(fd):
        """Record actual retry syncs before delegating to the kernel."""
        calls.append(fd)
        real_sync(fd)

    monkeypatch.setattr(os, "fsync", count_sync)
    assert storage.purge(identity) is True
    assert calls


def test_cross_device_publication_does_not_copy(storage, monkeypatch, tmp_path):
    """Fail on EXDEV without an unsafe copy fallback or removing staged bytes."""
    with storage.create_writer(make_plan(), uuid4()) as writer:
        writer.write(PAYLOAD)
        writer.seal()

        def fail_link(*args, **kwargs):
            """Inject a cross-device publication failure at the link syscall."""
            raise OSError(errno.EXDEV, "sensitive device names")

        monkeypatch.setattr(os, "link", fail_link)
        with pytest.raises(BlobStorageError, match="publication_failed"):
            writer.publish()
        assert (tmp_path / "blobs").joinpath(
            *writer.identity.staging_parts
        ).read_bytes() == PAYLOAD


def test_staging_inode_substitution_detected(storage, tmp_path):
    """Refuse publication after the locked staging name is replaced by another inode."""
    with storage.create_writer(make_plan(), uuid4()) as writer:
        writer.write(PAYLOAD)
        writer.seal()
        stage = (tmp_path / "blobs").joinpath(*writer.identity.staging_parts)
        stage.rename(stage.with_suffix(".moved"))
        stage.write_bytes(PAYLOAD)
        stage.chmod(0o600)
        with pytest.raises(BlobStorageError, match="inode_changed"):
            writer.publish()


@pytest.mark.parametrize("mutation", ["content", "size"])
def test_verifier_fd_cannot_silently_change_sealed_payload(storage, mutation):
    """Rehash sealed bytes after verification before admitting a final object name."""
    with storage.create_writer(make_plan(), uuid4()) as writer:
        writer.write(PAYLOAD)
        writer.seal()
        with writer.verification_reader() as source:
            if mutation == "content":
                os.pwrite(source.fileno(), b"X", 0)
            else:
                os.ftruncate(source.fileno(), len(PAYLOAD) - 1)
        with pytest.raises(BlobStorageError, match="sealed_blob_changed"):
            writer.publish()


def test_purge_never_scans_unknown_lease(storage, tmp_path):
    """Report an unknown staging lease without deleting data or claiming safe release."""
    plan = make_plan()
    unknown = BlobIdentity(plan.owner_id, plan.file_id, uuid4())
    with storage.create_writer(plan, uuid4()) as writer:
        writer.write(PAYLOAD)
    with pytest.raises(BlobStorageError, match="untracked_staging_entry"):
        storage.purge(unknown)
    assert (tmp_path / "blobs").joinpath(*writer.identity.staging_parts).exists()
    assert storage.purge(writer.identity) is True


def test_new_owner_has_independent_opaque_paths(storage, tmp_path):
    """Keep another owner's UUID namespace absent even when file UUIDs coincide."""
    plan = make_plan()
    identity = write_ready(storage, plan)
    other = BlobIdentity(uuid4(), identity.file_id, identity.lease_id)
    assert storage.purge(other) is True
    with pytest.raises(FileNotFoundError):
        storage.open_reader(other)
    assert (tmp_path / "blobs").joinpath(*identity.object_parts).read_bytes() == PAYLOAD


@pytest.mark.parametrize("position", [0, 1, 2])
def test_only_uuid_identities_accepted(position):
    """Reject path-like identity strings before they reach directory traversal."""
    values = [uuid4(), uuid4(), uuid4()]
    values[position] = "../../outside"
    with pytest.raises(BlobStorageError, match="invalid_identity"):
        BlobIdentity(*values)


def test_tampered_storage_key_is_rejected(storage):
    """Refuse a reservation whose internal key disagrees with its UUID identity."""
    with pytest.raises(BlobStorageError, match="invalid_storage_key"):
        storage.create_writer(replace(make_plan(), storage_key="../outside"), uuid4())


def test_closed_handles_cannot_use_recycled_descriptors(storage):
    """Make repeated close safe and all subsequent handle operations fail closed."""
    writer = storage.create_writer(make_plan(), uuid4())
    writer.close()
    writer.close()
    with pytest.raises(BlobStorageError, match="handle_closed"):
        writer.write(PAYLOAD)
    storage.close()
    storage.close()
    with pytest.raises(BlobStorageError, match="storage_closed"):
        storage.free_bytes()


def test_handles_close_after_caller_exception(storage):
    """Release writer locks when a stream or verifier raises in a context manager."""
    with pytest.raises(RuntimeError, match="client disconnected"):
        with storage.create_writer(make_plan(), uuid4()) as writer:
            writer.write(PAYLOAD)
            raise RuntimeError("client disconnected")
    assert storage.purge(writer.identity) is True


def test_operations_do_not_leak_descriptors(storage):
    """Exercise repeated success and exclusive-open failures against real FD inventory."""
    before = len(os.listdir("/proc/self/fd"))
    for _ in range(20):
        plan = make_plan()
        with storage.create_writer(plan, uuid4()) as writer:
            with pytest.raises(BlockingIOError):
                storage.create_writer(plan, writer.identity.lease_id)
            writer.write(PAYLOAD)
            writer.seal()
            writer.publish()
        with storage.open_reader(writer.identity) as reader:
            assert reader.read() == PAYLOAD
        assert storage.purge(writer.identity) is True
    assert len(os.listdir("/proc/self/fd")) == before


def test_storage_logs_do_not_include_content_or_private_paths(
    storage, tmp_path, caplog
):
    """Audit state changes using stable IDs without filename, payload or hash leakage."""
    plan = make_plan(filename="sensitive-personal-label.txt")
    with caplog.at_level(logging.DEBUG):
        identity = write_ready(storage, plan)
        assert storage.purge(identity) is True
    assert "blob_published" in caplog.text
    assert "blob_purged" in caplog.text
    for sensitive in (
        str(tmp_path),
        plan.display_name,
        plan.expected_sha256,
        PAYLOAD.decode().strip(),
    ):
        assert sensitive not in caplog.text


def test_admission_guard_retained_by_writer(storage):
    """Prevent purge after admission ends while its writer still owns the lock."""
    plan = make_plan()
    identity = BlobIdentity(plan.owner_id, plan.file_id, uuid4())
    with storage.lock_resource(identity) as guard:
        assert storage.purge(identity) is False
        writer = storage.create_writer(plan, identity.lease_id, guard=guard)
    try:
        writer.write(PAYLOAD)
        assert storage.purge(identity) is False
    finally:
        writer.close()
    assert storage.purge(identity) is True


def test_guard_cannot_be_reused_after_close(storage):
    """Reject stale guard descriptors before creating a staging inode."""
    plan = make_plan()
    identity = BlobIdentity(plan.owner_id, plan.file_id, uuid4())
    with storage.lock_resource(identity) as guard:
        pass
    with pytest.raises(BlobStorageError, match="invalid_resource_lock"):
        storage.create_writer(plan, identity.lease_id, guard=guard)


def test_guard_is_bound_to_the_actual_root_inode(storage, tmp_path):
    """Reject a matching UUID guard from another storage root."""
    plan = make_plan()
    identity = BlobIdentity(plan.owner_id, plan.file_id, uuid4())
    with LocalBlobStorage(tmp_path / "different-root") as other:
        with other.lock_resource(identity) as guard:
            with pytest.raises(BlobStorageError, match="invalid_resource_lock"):
                storage.create_writer(plan, identity.lease_id, guard=guard)


def test_creation_and_purge_cannot_race_between_open_and_lock(storage, monkeypatch):
    """Hold a directory lock before a new payload FD acquires its inode lock."""
    plan = make_plan()
    identity = BlobIdentity(plan.owner_id, plan.file_id, uuid4())
    real_open = os.open
    attempted = []

    def open_during_purge(path, flags, *args, **kwargs):
        """Attempt cleanup precisely when the writer is about to create its inode."""
        if str(path).endswith(".part") and flags & os.O_CREAT:
            attempted.append(storage.purge(identity))
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", open_during_purge)
    with storage.create_writer(plan, identity.lease_id) as writer:
        writer.write(PAYLOAD)
        assert attempted == [False]
    assert storage.purge(identity) is True


def test_tampered_oversize_plan_cannot_bypass_adapter_cap(storage):
    """Apply bounds even if an internal caller bypasses the policy planner."""
    plan = replace(make_plan(), size_bytes=DEFAULT_POLICY.max_file_bytes + 1)
    with pytest.raises(StoragePolicyError, match="file_too_large"):
        storage.create_writer(plan, uuid4())


def test_absent_name_sync_failure_closes_parent_descriptor(storage, monkeypatch):
    """Avoid leaking a directory FD when cleanup resyncs an already absent payload."""
    plan = make_plan()
    identity = BlobIdentity(plan.owner_id, plan.file_id, uuid4())
    with storage.lock_resource(identity) as guard:
        parent_inode = os.fstat(guard._fd).st_ino
    before = len(os.listdir("/proc/self/fd"))
    real_sync = os.fsync

    def fail_missing_parent_sync(fd):
        """Fail the missing-name retry branch after the resource guard is acquired."""
        if os.fstat(fd).st_ino == parent_inode:
            raise OSError(errno.EIO, "sensitive directory message")
        real_sync(fd)

    with monkeypatch.context() as context:
        context.setattr(os, "fsync", fail_missing_parent_sync)
        with pytest.raises(BlobStorageError, match="purge_failed"):
            storage.purge(identity)
    assert len(os.listdir("/proc/self/fd")) == before
    assert storage.purge(identity) is True


def test_context_entry_failure_closes_its_handle(storage, tmp_path):
    """Release descriptors if an inode changes before entering a returned handle."""
    before = len(os.listdir("/proc/self/fd"))
    writer = storage.create_writer(make_plan(), uuid4())
    stage = (tmp_path / "blobs").joinpath(*writer.identity.staging_parts)
    stage.chmod(0o644)
    with pytest.raises(BlobStorageError, match="unsafe_blob"):
        with writer:
            pytest.fail("Unsafe inode was admitted")
    assert len(os.listdir("/proc/self/fd")) == before
