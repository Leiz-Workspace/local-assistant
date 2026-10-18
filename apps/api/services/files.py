"""Coordinate file journals, isolated verification and private FD I/O without long SQL transactions."""

import asyncio
import logging
from functools import partial
from uuid import UUID, uuid4

from starlette.requests import ClientDisconnect

from src.application.services.file_storage_policy import (
    DEFAULT_POLICY,
    FileReservationPlan,
    StoragePolicyError,
    plan_reservation,
)
from src.infrastructure.file_verifier import verify_file
from src.infrastructure.local_blob_storage import (
    BlobIdentity,
    BlobStorageError,
    LocalBlobStorage,
)
from src.infrastructure.repositories.file_journal import (
    SAFE_ERRORS,
    PostgresFileJournal,
    policy_from_snapshot,
)

logger = logging.getLogger(__name__)


async def finish_task(task):
    """Join owned work despite caller cancellation so live file descriptors cannot be reused early."""
    while True:
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            if task.done():
                return task.result()


async def file_io(function, *arguments, close_result=False, **parameters):
    """Offload serialized file work and join it before propagating cancellation."""
    task = asyncio.create_task(
        asyncio.to_thread(partial(function, *arguments, **parameters))
    )
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        try:
            result = await finish_task(task)
            if close_result:
                await finish_task(asyncio.create_task(asyncio.to_thread(result.close)))
        except Exception:
            logger.warning("file_io_cancelled_operation_failed")
        raise


def verify_writer(writer, policy, declared_media):
    """Lend the sealed FD only for the lifetime of the bounded isolated verifier."""
    with writer.verification_reader() as source:
        return verify_file(
            source,
            writer.plan.display_name,
            policy=policy,
            declared_media=declared_media,
        )


def identity_for(row) -> BlobIdentity:
    """Recover exact opaque names without inventing a different upload lease."""
    return BlobIdentity(row["owner_id"], row["id"], row["lease_owner"] or UUID(int=0))


class FileService:
    """Own a single process's file operations, guarded I/O and bounded shutdown joins."""

    def __init__(
        self,
        journal: PostgresFileJournal,
        storage: LocalBlobStorage,
        policy=DEFAULT_POLICY,
    ):
        """Reuse the existing app pool and a dedicated private blob root."""
        self.journal = PostgresFileJournal(
            journal.sessions, journal.policy, namespace_id=storage.namespace_id
        )
        self.storage = storage
        self.policy = policy
        self.active = set()
        self.closing = False

    def track(self):
        """Register active uploads/download responses before they own any locked FD."""
        if self.closing:
            raise StoragePolicyError("file_storage_closing", 503)
        task = asyncio.current_task()
        self.active.add(task)
        return task

    def untrack(self, task):
        """Remove only completed resource-owning work from the shutdown inventory."""
        self.active.discard(task)

    async def reserve(
        self, owner_id, *, filename, size_bytes, sha256, request_key=None
    ):
        """Validate declarations and commit atomic quota admission before body consumption."""
        plan = plan_reservation(
            owner_id=owner_id,
            file_id=uuid4(),
            filename=filename,
            size_bytes=size_bytes,
            expected_sha256=sha256,
            request_key=request_key,
            policy=self.policy,
        )
        free = await file_io(self.storage.free_bytes)
        return await self.journal.reserve(plan, free_bytes=free)

    async def upload(
        self, owner_id, file_id, stream, *, declared_media=None, content_length=None
    ):
        """Consume a raw body once, maintaining leases and cleaning failures without quota shortcuts."""
        task = self.track()
        lease = uuid4()
        try:
            row = await self.journal.get(owner_id, file_id)
            if row["state"] != "reserved":
                raise StoragePolicyError("file_not_claimable", 409)
            if (
                content_length is not None
                and content_length != row["declared_size_bytes"]
            ):
                raise StoragePolicyError("file_size_mismatch", 422)
            try:
                return await self._upload_owned(
                    owner_id, row, lease, stream, declared_media
                )
            except BaseException as error:
                cleanup = asyncio.create_task(
                    self._failed_upload(owner_id, file_id, lease, error)
                )
                try:
                    await finish_task(cleanup)
                except Exception:
                    logger.error(
                        "file_failed_upload_cleanup_pending file_id=%s", file_id
                    )
                raise
        finally:
            self.untrack(task)

    async def _upload_owned(self, owner_id, row, lease, stream, declared_media):
        """Hold the resource guard from post-lock DB claim until all finalization I/O ends."""
        identity = BlobIdentity(owner_id, row["id"], lease)
        policy = policy_from_snapshot(row["policy_snapshot"])
        plan = FileReservationPlan(
            owner_id,
            row["id"],
            row["display_name"],
            row["declared_size_bytes"],
            row["expected_sha256"],
            row["request_key"],
            row["storage_key"],
            row["request_fingerprint"],
        )
        guard = writer = heartbeat = None
        heartbeat_error = []
        heartbeat_lock = asyncio.Lock()
        upload_task = asyncio.current_task()

        async def beat():
            """Sample progress under a local lock so concurrent heartbeats cannot regress it."""
            async with heartbeat_lock:
                await self.journal.heartbeat(
                    owner_id, row["id"], lease, writer.bytes_written
                )

        async def maintain_lease():
            """Cancel the uploader if a heartbeat loses its DB lease or storage connection."""
            try:
                while True:
                    await asyncio.sleep(policy.heartbeat_seconds)
                    await beat()
            except asyncio.CancelledError:
                raise
            except Exception as error:
                heartbeat_error.append(error)
                upload_task.cancel()

        try:
            guard = await file_io(
                self.storage.lock_resource, identity, close_result=True
            )
            await self.journal.claim(owner_id, row["id"], lease)
            writer = await file_io(
                self.storage.create_writer,
                plan,
                lease,
                guard=guard,
                policy=policy,
                close_result=True,
            )
            await file_io(guard.close)
            guard = None
            heartbeat = asyncio.create_task(maintain_lease())
            async with asyncio.timeout(policy.upload_seconds):
                iterator = aiter(stream)
                while True:
                    try:
                        chunk = await asyncio.wait_for(
                            anext(iterator), timeout=policy.idle_seconds
                        )
                    except StopAsyncIteration:
                        break
                    if not chunk:
                        continue
                    if writer.bytes_written + len(chunk) > plan.size_bytes:
                        raise StoragePolicyError("file_size_mismatch", 413)
                    view = memoryview(chunk)
                    for offset in range(0, len(view), policy.chunk_bytes):
                        await file_io(
                            writer.write,
                            bytes(view[offset : offset + policy.chunk_bytes]),
                        )
                await file_io(writer.seal)
                await beat()
                await self.journal.verifying(owner_id, row["id"], lease)
                media = await file_io(verify_writer, writer, policy, declared_media)
                await beat()
                await file_io(writer.publish)
                await beat()
                heartbeat.cancel()
                await asyncio.gather(heartbeat, return_exceptions=True)
                return await self.journal.ready(owner_id, row["id"], lease, media)
        except asyncio.CancelledError:
            if heartbeat_error:
                raise StoragePolicyError("file_lease_lost", 409) from None
            raise
        except BlockingIOError:
            raise StoragePolicyError("file_busy", 409) from None
        finally:
            if heartbeat is not None:
                heartbeat.cancel()
                await asyncio.gather(heartbeat, return_exceptions=True)
            if writer is not None:
                await file_io(writer.close)
            if guard is not None:
                await file_io(guard.close)

    async def _failed_upload(self, owner_id, file_id, lease, error):
        """Fence failures after writer FDs close, then attempt honest physical cleanup."""
        interrupted = isinstance(
            error, (asyncio.CancelledError, ClientDisconnect, TimeoutError)
        )
        code = (
            "upload_timeout"
            if isinstance(error, TimeoutError)
            else "upload_interrupted"
        )
        if not interrupted:
            code = (
                error.code
                if isinstance(error, StoragePolicyError) and error.code in SAFE_ERRORS
                else "verification_failed"
            )
        try:
            row = await self.journal.begin_purge(
                owner_id,
                file_id,
                uuid4(),
                target="interrupted" if interrupted else "rejected",
                error_code=code,
                lease_owner=lease,
            )
        except StoragePolicyError as failure:
            if failure.code in {"file_lease_lost", "file_not_found"}:
                return
            raise
        await self.cleanup(row)

    async def cleanup(self, row) -> bool:
        """Retain allocation on busy/unsafe/failed FS cleanup and release only after success."""
        if row["policy_snapshot"].get("_storage_namespace") != str(
            self.storage.namespace_id
        ):
            logger.error("file_purge_namespace_mismatch file_id=%s", row["id"])
            return False
        if row["quota_released_at"] is not None:
            return True
        try:
            purged = await file_io(self.storage.purge, identity_for(row))
        except (OSError, BlobStorageError):
            logger.error("file_purge_pending file_id=%s", row["id"])
            return False
        if not purged:
            return False
        await self.journal.release_purged(
            row["owner_id"], row["id"], row["purge_token"]
        )
        return True

    async def delete(self, owner_id, file_id) -> bool:
        """Hide an owned file immediately and report whether physical cleanup completed."""
        row = await self.journal.begin_purge(owner_id, file_id, uuid4())
        return await self.cleanup(row)

    async def open_download(self, owner_id, file_id):
        """Authorize, lock, verify bytes and recheck ready ownership before serving any content."""
        row = await self.journal.get(owner_id, file_id)
        if row["state"] != "ready":
            raise StoragePolicyError("file_not_ready", 409)
        reader = await file_io(
            self.storage.open_reader, identity_for(row), close_result=True
        )
        try:
            await file_io(
                reader.verify_integrity, row["actual_size_bytes"], row["actual_sha256"]
            )
            row = await self.journal.get(owner_id, file_id)
            if row["state"] != "ready":
                raise StoragePolicyError("file_not_ready", 409)
            return row, reader
        except BaseException:
            await file_io(reader.close)
            raise

    async def shutdown(self):
        """Cancel and join resource owners before closing the root or disposing the DB pool."""
        self.closing = True
        tasks = [task for task in self.active if task is not asyncio.current_task()]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        await file_io(self.storage.close)
        logger.info("file_storage_shutdown active_operations=%d", len(self.active))
