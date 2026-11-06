"""Snapshot and restore paired PostgreSQL/blob/identity data on existing local infrastructure."""

import argparse
import hashlib
import json
import logging
import os
import re
from pathlib import Path

import psycopg
from psycopg.rows import dict_row
from sqlalchemy.engine import make_url

from apps.api.core.conversation_auth import load_principals
from scripts.postgres_recovery_acceptance import PROBE_PREFIX, RecoveryAcceptance
from src.application.services.file_storage_policy import (
    DEFAULT_POLICY,
    FileReservationPlan,
)
from src.infrastructure.local_blob_storage import LocalBlobStorage
from src.infrastructure.repositories.file_journal import policy_from_snapshot

logger = logging.getLogger(__name__)


class FileStorageRecoveryAcceptance:
    """Require drained admission and prove a protected paired snapshot without production overwrite."""

    def __init__(self, directory: Path, root: Path, auth_file: Path):
        """Create an exclusive private artifact directory and reuse the reviewed existing-cluster helper."""
        self.directory = directory.absolute()
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=False)
        self.root = root
        self.auth_file = auth_file
        self.operator = RecoveryAcceptance(self.directory / "database")

    def write_json(self, name, payload):
        """Write a fresh owner-only JSON artifact and sync its parent before reporting success."""
        descriptor = os.open(
            self.directory / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600
        )
        with os.fdopen(descriptor, "w") as target:
            json.dump(payload, target, sort_keys=True, indent=2)
            target.write("\n")
            target.flush()
            os.fsync(target.fileno())
        parent = os.open(self.directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(parent)
        finally:
            os.close(parent)

    def copy_payloads(self, source, target, rows):
        """Copy bounded verified FD chunks into independent private target inodes with the same IDs."""
        from apps.api.services.files import identity_for

        for row in rows:
            policy = policy_from_snapshot(row["policy_snapshot"])
            plan = FileReservationPlan(
                row["owner_id"],
                row["id"],
                row["display_name"],
                row["declared_size_bytes"],
                row["expected_sha256"],
                row["request_key"],
                row["storage_key"],
                row["request_fingerprint"],
            )
            with source.open_reader(identity_for(row)) as reader:
                reader.verify_integrity(row["actual_size_bytes"], row["actual_sha256"])
                with target.create_writer(
                    plan, row["lease_owner"], policy=policy
                ) as writer:
                    while chunk := reader.read(
                        min(DEFAULT_POLICY.chunk_bytes, policy.chunk_bytes)
                    ):
                        writer.write(chunk)
                    writer.seal()
                    writer.publish()
            logger.info(
                "paired_blob_copied file_id=%s size_bytes=%d",
                row["id"],
                row["actual_size_bytes"],
            )

    def database_archive(self, snapshot, database_name):
        """Stream a private DB archive and bound its size before any in-memory restore helper reads it."""
        path = self.directory / "database/local-assistant.dump"
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as target:
            self.operator.command(
                [
                    "exec",
                    "postgres",
                    "pg_dump",
                    "-U",
                    "home-server",
                    "-d",
                    database_name,
                    "--format=custom",
                    "--snapshot",
                    snapshot,
                ],
                output=target,
            )
            target.flush()
            os.fsync(target.fileno())
        parent = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(parent)
        finally:
            os.close(parent)
        if path.stat().st_size > 64 * 1024**2:
            raise RuntimeError(
                "Local restore drill archive exceeds the reviewed memory bound"
            )
        digest = hashlib.sha256()
        with path.open("rb") as source:
            while chunk := source.read(65536):
                digest.update(chunk)
        self.operator.manifest["backups"].append(
            {
                "file": path.name,
                "bytes": path.stat().st_size,
                "sha256": digest.hexdigest(),
            }
        )
        logger.info("paired_database_archive_written bytes=%d", path.stat().st_size)
        return path, digest.hexdigest()

    def verify_payloads(self, storage, rows):
        """Require exact known inventory, stable namespace and every referenced payload SHA/size."""
        from apps.api.services.files import identity_for

        expected = {row["storage_key"]: row["actual_size_bytes"] for row in rows}
        if storage.inventory() != expected:
            raise RuntimeError("Blob inventory differs from the journal")
        for row in rows:
            if row["policy_snapshot"].get("_storage_namespace") != str(
                storage.namespace_id
            ):
                raise RuntimeError("Storage namespace differs from the journal")
            with storage.open_reader(identity_for(row)) as reader:
                reader.verify_integrity(row["actual_size_bytes"], row["actual_sha256"])
        logger.info("paired_blob_inventory_verified files=%d", len(rows))

    def run(self):
        """Export a quiet DB snapshot, copy blobs and prove isolated row/ACL/blob/identity restoration."""
        url = make_url(os.environ["DATABASE_URL"])
        if url.username != "local_assistant_app" or (
            url.database != "local_assistant"
            and re.fullmatch(PROBE_PREFIX + r"[0-9a-f]{32}", url.database or "") is None
        ):
            raise RuntimeError(
                "Expected the existing application identity and database"
            )
        if not self.root.is_dir():
            raise RuntimeError("Source blob root is missing")
        principals = load_principals(self.auth_file)
        with (
            LocalBlobStorage(self.root) as source,
            psycopg.connect(
                host=url.host,
                port=url.port,
                dbname=url.database,
                user=url.username,
                password=url.password,
                connect_timeout=10,
                options="-c TimeZone=UTC -c statement_timeout=30000 -c lock_timeout=5000",
                row_factory=dict_row,
            ) as database,
        ):
            database.execute(
                "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"
            )
            active = database.execute(
                "SELECT count(*) AS count FROM pg_stat_activity WHERE datname=current_database() AND pid<>pg_backend_pid() AND backend_type='client backend'"
            ).fetchone()["count"]
            if active:
                raise RuntimeError("Stop API consumers before paired backup")
            pending = database.execute(
                "SELECT count(*) AS count FROM assistant.files WHERE state NOT IN ('ready','deleted','rejected','interrupted')"
            ).fetchone()["count"]
            if pending:
                raise RuntimeError("Resolve active file journals before paired backup")
            rows = database.execute(
                "SELECT * FROM assistant.files WHERE state='ready' ORDER BY id LIMIT 10001"
            ).fetchall()
            if len(rows) > 10000:
                raise RuntimeError("Ready inventory exceeds the reviewed bound")
            if not rows or not {row["owner_id"] for row in rows}.issubset(
                set(principals.values())
            ):
                raise RuntimeError(
                    "Nonempty ready files and stable principal bindings are required"
                )
            allocated = (sum(row["declared_size_bytes"] for row in rows), len(rows), 0)
            total = database.execute(
                "SELECT allocated_bytes,allocated_files,active_uploads FROM assistant.file_global_usage WHERE singleton=1"
            ).fetchone()
            if tuple(total.values()) != allocated:
                raise RuntimeError("Global allocation does not match ready journals")
            inconsistent = database.execute(
                "SELECT count(*) AS count FROM assistant.file_owner_usage u LEFT JOIN (SELECT owner_id,sum(declared_size_bytes) AS bytes,count(*) AS files FROM assistant.files WHERE state='ready' GROUP BY owner_id) r USING(owner_id) WHERE u.allocated_bytes<>COALESCE(r.bytes,0) OR u.allocated_files<>COALESCE(r.files,0) OR u.active_uploads<>0"
            ).fetchone()["count"]
            if inconsistent:
                raise RuntimeError("Owner allocation does not match ready journals")
            self.verify_payloads(source, rows)
            expected = self.operator.fingerprint(url.database)
            security = self.operator.security_fingerprint(url.database)
            snapshot = database.execute(
                "SELECT pg_export_snapshot() AS snapshot"
            ).fetchone()["snapshot"]
            archive, archive_sha256 = self.database_archive(snapshot, url.database)
            with LocalBlobStorage(
                self.directory / "blobs", namespace_id=source.namespace_id
            ) as target:
                self.copy_payloads(source, target, rows)
                self.verify_payloads(target, rows)
            database.commit()
            if (
                self.operator.fingerprint(url.database) != expected
                or self.operator.security_fingerprint(url.database) != security
            ):
                raise RuntimeError(
                    "Source metadata changed during maintenance snapshot"
                )
            self.write_json(
                "principals.json",
                {
                    "principals": [
                        {"id": str(owner), "token_sha256": digest}
                        for digest, owner in principals.items()
                    ]
                },
            )
            if load_principals(self.directory / "principals.json") != principals:
                raise RuntimeError("Restored identity bindings differ")
            with (
                LocalBlobStorage(self.directory / "blobs") as backup,
                LocalBlobStorage(
                    self.directory / "restored-blobs", namespace_id=source.namespace_id
                ) as restored,
            ):
                self.copy_payloads(backup, restored, rows)
                self.verify_payloads(restored, rows)
            if archive.stat().st_size > 64 * 1024**2:
                raise RuntimeError(
                    "Local restore drill archive exceeds the reviewed memory bound"
                )
            self.operator.verify_restore(archive, expected, security)
            self.operator.save_manifest()
            manifest = {
                "paired_restore_verified": True,
                "database_restore_verified": True,
                "database_security_verified": True,
                "identity_verified": True,
                "namespace_id": str(source.namespace_id),
                "files": len(rows),
                "bytes": allocated[0],
                "database_archive": "database/local-assistant.dump",
                "database_sha256": archive_sha256,
                "source_row_fingerprints": expected,
                "source_security_sha256": security,
                "inventory": [
                    {
                        "id": str(row["id"]),
                        "owner_id": str(row["owner_id"]),
                        "key": row["storage_key"],
                        "bytes": row["actual_size_bytes"],
                        "sha256": row["actual_sha256"],
                    }
                    for row in rows
                ],
            }
            self.write_json("manifest.json", manifest)
        logger.info(
            "paired_file_restore_verified files=%d bytes=%d",
            manifest["files"],
            manifest["bytes"],
        )
        return manifest


def main() -> int:
    """Run a reviewed local paired restore drill and retain protected artifacts on failure."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backup-directory", required=True, type=Path)
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--auth-file", required=True, type=Path)
    args = parser.parse_args()
    try:
        FileStorageRecoveryAcceptance(
            args.backup_directory, args.source_root, args.auth_file
        ).run()
    except Exception as error:
        logger.error("paired_file_restore_failed type=%s", type(error).__name__)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
