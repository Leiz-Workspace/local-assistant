"""Back up the shared PostgreSQL cluster, prove an isolated restore and optionally restart safely."""

import argparse
import hashlib
import json
import logging
import os
import re
import subprocess
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

logger = logging.getLogger(__name__)
PROBE_PREFIX = "la_restore_probe_"


def identifier(value: str) -> str:
    """Quote a PostgreSQL identifier without allowing statement injection."""
    return '"' + value.replace('"', '""') + '"'


def literal(value: str) -> str:
    """Quote a PostgreSQL text literal used only in operator-generated queries."""
    return "'" + value.replace("'", "''") + "'"


class RecoveryAcceptance:
    """Run a guarded recovery drill against one existing Docker PostgreSQL instance."""

    def __init__(self, directory: Path, *, container="postgres", admin="home-server"):
        """Create a new private backup directory without overwriting an existing artifact."""
        self.directory = directory.resolve()
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=False)
        self.directory.chmod(0o700)
        self.container = container
        self.admin = admin
        self.manifest = {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "backups": [],
            "restore_verified": False,
            "restart_verified": False,
        }

    def command(self, arguments, *, input_data=None, output=None):
        """Run an explicit Docker command without exposing SQL, payloads or driver errors."""
        result = subprocess.run(
            ["docker", *arguments],
            input=input_data,
            stdout=output if output is not None else subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=180,
        )
        if result.returncode:
            raise RuntimeError(
                "PostgreSQL operator command failed; protected artifacts retained"
            )
        return result.stdout if output is None else b""

    def sql(self, database: str, query: str) -> str:
        """Execute one fail-fast operator SQL request through the container's local socket."""
        return (
            self.command(
                [
                    "exec",
                    self.container,
                    "psql",
                    "-X",
                    "-qAt",
                    "-v",
                    "ON_ERROR_STOP=1",
                    "-U",
                    self.admin,
                    "-d",
                    database,
                    "-c",
                    query,
                ]
            )
            .decode()
            .strip()
        )

    def private_output(self, name: str, arguments):
        """Write a backup stream directly to an exclusive owner-only file."""
        path = self.directory / name
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            self.command(arguments, output=stream)
            stream.flush()
            os.fsync(stream.fileno())
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        self.manifest["backups"].append(
            {"file": name, "sha256": digest, "bytes": path.stat().st_size}
        )
        logger.info(
            "postgres_backup_written file=%s bytes=%d", name, path.stat().st_size
        )
        return path

    def save_manifest(self):
        """Persist the non-secret verification summary with protected file permissions."""
        path = self.directory / "manifest.json"
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(descriptor, "w") as stream:
            json.dump(self.manifest, stream, indent=2)
            stream.write("\n")

    def require_quiet(self):
        """Reject active consumer transactions, current app connections or pending inference."""
        active = self.sql(
            "postgres",
            "SELECT count(*) FROM pg_stat_activity WHERE pid <> pg_backend_pid() AND backend_type = 'client backend' AND (xact_start IS NOT NULL OR datname = 'local_assistant');",
        )
        if (
            active != "0"
            or self.sql(
                "local_assistant",
                "SELECT count(*) FROM assistant.inference_runs WHERE status='pending';",
            )
            != "0"
        ):
            raise RuntimeError(
                "Consumers must be drained and pending inference resolved before the drill"
            )
        logger.info(
            "postgres_maintenance_precondition_passed active_transactions=0 app_connections=0 pending_runs=0"
        )

    def fingerprint(self, database: str) -> dict:
        """Hash canonical row representations for every application table without printing rows."""
        tables = self.sql(
            database,
            "SELECT json_build_array(schemaname,tablename)::text FROM pg_tables WHERE schemaname NOT IN ('pg_catalog','information_schema') ORDER BY schemaname,tablename;",
        )
        result = {}
        for row in tables.splitlines():
            schema, table = json.loads(row)
            relation = identifier(schema) + "." + identifier(table)
            value = self.sql(
                database,
                "SET TIME ZONE 'UTC'; SELECT count(*)::text || ':' || md5(COALESCE(string_agg(payload,E'\\n' ORDER BY payload),'')) FROM (SELECT row_to_json(t)::text AS payload FROM "
                + relation
                + " t) records;",
            )
            result[schema + "." + table] = value
        return result

    def security_fingerprint(self, database: str) -> str:
        """Compare schema/table owners and normalized ACLs independently of target object OIDs."""
        query = """
        SELECT encoded FROM (
          SELECT json_build_array('schema',nspname,pg_get_userbyid(nspowner),
            ARRAY(SELECT item::text FROM unnest(nspacl) item ORDER BY item::text))::text AS encoded
          FROM pg_namespace WHERE nspname NOT LIKE 'pg_%' AND nspname <> 'information_schema'
          UNION ALL
          SELECT json_build_array('relation',n.nspname,c.relname,pg_get_userbyid(c.relowner),
            ARRAY(SELECT item::text FROM unnest(c.relacl) item ORDER BY item::text))::text
          FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
          WHERE n.nspname NOT LIKE 'pg_%' AND n.nspname <> 'information_schema'
            AND c.relkind IN ('r','p','S','v','m')
        ) records ORDER BY encoded;
        """
        return hashlib.sha256(self.sql(database, query).encode()).hexdigest()

    def drop_probe(self, database: str):
        """Drop only the uniquely generated restore target, never an application database."""
        if re.fullmatch(PROBE_PREFIX + r"[0-9a-f]{32}", database) is None:
            raise ValueError("Refusing to drop a non-probe database")
        self.sql("postgres", "DROP DATABASE " + identifier(database) + ";")
        logger.info("postgres_restore_probe_removed")

    def verify_restore(self, archive: Path, expected: dict, expected_security: str):
        """Restore the app archive into a temporary database on the existing instance and compare."""
        probe = PROBE_PREFIX + uuid4().hex
        created = False
        try:
            self.sql(
                "postgres",
                "CREATE DATABASE " + identifier(probe) + " TEMPLATE template0;",
            )
            created = True
            self.command(
                [
                    "exec",
                    "-i",
                    self.container,
                    "pg_restore",
                    "-U",
                    self.admin,
                    "-d",
                    probe,
                    "--exit-on-error",
                ],
                input_data=archive.read_bytes(),
            )
            if self.fingerprint(probe) != expected:
                raise RuntimeError("Restored rows differ from the source snapshot")
            if self.security_fingerprint(probe) != expected_security:
                raise RuntimeError(
                    "Restored ownership or ACLs differ from the source snapshot"
                )
            self.manifest["restore_security_verified"] = True
            self.manifest["restore_verified"] = True
            logger.info("postgres_isolated_restore_verified tables=%d", len(expected))
        finally:
            if created:
                self.drop_probe(probe)

    def consumer_ready(self, url: str):
        """Verify the existing Keycloak discovery endpoint without logging its response."""
        with urllib.request.urlopen(url, timeout=5) as response:
            if response.status != 200 or not isinstance(
                json.load(response).get("issuer"), str
            ):
                raise RuntimeError("Dependent consumer is not ready")

    def run(self, *, restart: bool, consumer_url: str):
        """Require verified backup/restore and quiet consumers before an explicitly enabled restart."""
        canary = str(uuid4())
        self.manifest["canary_id"] = canary
        created = False
        try:
            mounts = json.loads(
                self.command(
                    ["inspect", "--format", "{{json .Mounts}}", self.container]
                )
            )
            if not any(
                mount.get("Type") == "volume"
                and mount.get("Destination") == "/var/lib/postgresql/data"
                for mount in mounts
            ):
                raise RuntimeError(
                    "Expected persistent PostgreSQL data volume not found"
                )
            self.require_quiet()
            self.consumer_ready(consumer_url)
            self.sql(
                "local_assistant",
                "INSERT INTO assistant.conversations (id,title,metadata) VALUES ("
                + literal(canary)
                + ",'Recovery acceptance canary','{\"acceptance_probe\":true}'::jsonb);",
            )
            created = True
            expected = self.fingerprint("local_assistant")
            self.manifest["source_row_fingerprints"] = expected
            expected_security = self.security_fingerprint("local_assistant")
            self.manifest["source_security_sha256"] = expected_security
            databases = self.sql(
                "postgres",
                "SELECT datname FROM pg_database WHERE NOT datistemplate AND datallowconn ORDER BY datname;",
            ).splitlines()
            app_archive = None
            for index, database in enumerate(databases):
                archive = self.private_output(
                    f"database-{index}.dump",
                    [
                        "exec",
                        self.container,
                        "pg_dump",
                        "-U",
                        self.admin,
                        "-d",
                        database,
                        "--format=custom",
                    ],
                )
                self.manifest["backups"][-1]["database"] = database
                if database == "local_assistant":
                    app_archive = archive
            self.private_output(
                "globals.sql",
                [
                    "exec",
                    self.container,
                    "pg_dumpall",
                    "-U",
                    self.admin,
                    "--globals-only",
                ],
            )
            if app_archive is None or self.fingerprint("local_assistant") != expected:
                raise RuntimeError(
                    "Source changed during backup or app archive missing"
                )
            self.verify_restore(app_archive, expected, expected_security)
            self.save_manifest()
            if restart:
                self.require_quiet()
                self.consumer_ready(consumer_url)
                logger.warning("postgres_shared_restart_started verified_restore=true")
                self.command(["restart", "--time", "60", self.container])
                for attempt in range(60):
                    try:
                        ready = self.command(
                            [
                                "exec",
                                self.container,
                                "pg_isready",
                                "-U",
                                self.admin,
                                "-d",
                                "postgres",
                            ]
                        ).decode()
                        if "accepting connections" in ready:
                            break
                    except RuntimeError:
                        pass
                    time.sleep(0.5)
                else:
                    raise RuntimeError(
                        "PostgreSQL did not recover; retained backups require operator review"
                    )
                if self.fingerprint("local_assistant") != expected:
                    raise RuntimeError("Source data changed across PostgreSQL restart")
                for attempt in range(30):
                    try:
                        self.consumer_ready(consumer_url)
                        break
                    except Exception:
                        time.sleep(0.5)
                else:
                    raise RuntimeError(
                        "Dependent Keycloak did not recover after restart"
                    )
                self.manifest["restart_verified"] = True
                logger.info(
                    "postgres_restart_persistence_verified dependent_keycloak_ready=true"
                )
        finally:
            if created:
                self.sql(
                    "local_assistant",
                    "DELETE FROM assistant.conversations WHERE id="
                    + literal(canary)
                    + " AND metadata @> '{\"acceptance_probe\":true}'::jsonb;",
                )
                logger.info("postgres_acceptance_canary_removed")
            self.save_manifest()


def main() -> int:
    """Run the reviewed operator drill and emit only safe audit events."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backup-directory", required=True, type=Path)
    parser.add_argument("--execute-restart", action="store_true")
    parser.add_argument(
        "--consumer-url",
        default="http://127.0.0.1:8081/realms/master/.well-known/openid-configuration",
    )
    arguments = parser.parse_args()
    try:
        RecoveryAcceptance(arguments.backup_directory).run(
            restart=arguments.execute_restart, consumer_url=arguments.consumer_url
        )
    except Exception as error:
        logger.error(
            "postgres_recovery_acceptance_failed type=%s", type(error).__name__
        )
        return 1
    logger.info("postgres_recovery_acceptance_passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
