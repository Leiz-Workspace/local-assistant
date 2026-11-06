"""Prove bounded local database/vector/blob/config restores in owned namespaces while preserving original application data and shared services."""

import hashlib
import json
import logging
import os
import re
import sys
from pathlib import Path
from uuid import uuid4

import httpx

from scripts.postgres_recovery_acceptance import RecoveryAcceptance

logger = logging.getLogger(__name__)
CONFIGS = (
    "configs/models.yaml",
    "configs/embedding-selected.json",
    "configs/embedding-e5-rollback.json",
    "configs/llama-cpp-commit.txt",
)
PREFIX = "la_restore_probe_"


def digest(raw):
    """Hash complete private bytes without printing payloads, database rows or credentials."""
    return hashlib.sha256(raw).hexdigest()


def private_write(path, raw):
    """Write exclusive owner-only finite backup bytes without overwriting an existing path or following links."""
    if type(raw) is not bytes or len(raw) > 64 * 1024 * 1024:
        raise ValueError("recovery_artifact_limit")
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    logger.info("recovery_artifact_written bytes=%d", len(raw))


def guarded_collection(name):
    """Accept only an operator-minted probe namespace, never a live or model-selected collection name."""
    if type(name) is not str or re.fullmatch(PREFIX + r"[0-9a-f]{32}", name) is None:
        raise ValueError("recovery_namespace_invalid")
    return name


def qrequest(client, method, path, *, payload=None, missing_ok=False):
    """Execute one fixed local authenticated vector request and sanitize backend error bodies."""
    try:
        response = client.request(method, path, json=payload)
        if missing_ok and response.status_code == 404:
            return None
        response.raise_for_status()
        return response.json()["result"]
    except Exception:
        logger.warning("recovery_vector_request_failed")
        raise RuntimeError("recovery_vector_request_failed") from None


def collections(client):
    """Return only collection names for original-inventory and owned-target cleanup checks."""
    return sorted(
        row["name"] for row in qrequest(client, "GET", "/collections")["collections"]
    )


def vector_drill(client, root):
    """Restore three authored nonempty vectors/payloads/indexes between two owned collections and leave the original empty inventory unchanged."""
    before = collections(client)
    if before:
        raise RuntimeError("recovery_requires_reviewed_empty_vector_baseline")
    names = [PREFIX + uuid4().hex for _ in range(2)]
    points = [
        dict(
            id=index + 1,
            vector=[float(index + 1)] + [0.0] * 7,
            payload=dict(
                owner_id="d84-authored-fixture",
                source_sha256=digest(f"fixture-{index}".encode()),
            ),
        )
        for index in range(3)
    ]
    schema = dict(vectors=dict(size=8, distance="Dot"))
    try:
        for name in names:
            guarded_collection(name)
            qrequest(client, "PUT", "/collections/" + name, payload=schema)
            for field in ("owner_id", "source_sha256"):
                qrequest(
                    client,
                    "PUT",
                    "/collections/" + name + "/index?wait=true",
                    payload=dict(field_name=field, field_schema="keyword"),
                )
        qrequest(
            client,
            "PUT",
            "/collections/" + names[0] + "/points?wait=true",
            payload=dict(points=points),
        )
        original = qrequest(
            client,
            "POST",
            "/collections/" + names[0] + "/points/scroll",
            payload=dict(limit=4, with_payload=True, with_vector=True),
        )
        assert original["next_page_offset"] is None and len(original["points"]) == 3
        exported = dict(
            description="Authored storage canaries, not production embedding vectors.",
            schema=schema,
            points=original["points"],
            indexes=["owner_id", "source_sha256"],
        )
        raw = json.dumps(exported, sort_keys=True).encode()
        private_write(root / "vector-canary-backup.json", raw)
        loaded = json.loads((root / "vector-canary-backup.json").read_bytes())
        qrequest(
            client,
            "PUT",
            "/collections/" + names[1] + "/points?wait=true",
            payload=dict(points=loaded["points"]),
        )
        restored = qrequest(
            client,
            "POST",
            "/collections/" + names[1] + "/points/scroll",
            payload=dict(limit=4, with_payload=True, with_vector=True),
        )
        assert restored == original
        index_schemas = [
            qrequest(client, "GET", "/collections/" + name)["payload_schema"]
            for name in names
        ]
        assert index_schemas[0] == index_schemas[1] and set(index_schemas[0]) == {
            "owner_id",
            "source_sha256",
        }
        for value in index_schemas[0].values():
            assert value["data_type"] == "keyword"
        private_write(
            root / "vector-canary-restored.json",
            json.dumps(
                dict(points=restored["points"], indexes=index_schemas[1]),
                sort_keys=True,
            ).encode(),
        )
        logger.info("recovery_vector_restore_verified points=3")
        return dict(
            original_collection_count=0,
            canary_points_restored=3,
            keyword_indexes_verified=2,
            logical_backup_sha256=digest(raw),
        )
    finally:
        for name in names:
            qrequest(
                client,
                "DELETE",
                "/collections/" + guarded_collection(name),
                missing_ok=True,
            )
        if collections(client) != before:
            raise RuntimeError("recovery_vector_inventory_changed")
        logger.info("recovery_owned_vector_targets_retired")


def config_object_drill(root):
    """Restore only fixed non-secret config files and one authored blob/metadata pair into disjoint private directories."""
    backup, restored = root / "config-backup", root / "config-restored"
    backup.mkdir(mode=0o700)
    restored.mkdir(mode=0o700)
    manifest = {}
    for index, name in enumerate(CONFIGS):
        source = Path(name)
        if (
            source.is_symlink()
            or not source.is_file()
            or source.stat().st_size > 1024 * 1024
        ):
            raise RuntimeError("recovery_config_invalid")
        raw = source.read_bytes()
        private_write(backup / str(index), raw)
        private_write(restored / str(index), (backup / str(index)).read_bytes())
        assert raw == (restored / str(index)).read_bytes() == source.read_bytes()
        manifest[name] = digest(raw)
    blob = b"D84 authored synthetic object payload.\n"
    private_write(root / "object-source.bin", blob)
    private_write(root / "object-backup.bin", blob)
    metadata = dict(
        description="Synthetic private object canary, not original user data.",
        id=uuid4().hex,
        bytes=len(blob),
        sha256=digest(blob),
    )
    private_write(
        root / "object-metadata.json", json.dumps(metadata, sort_keys=True).encode()
    )
    private_write(
        root / "object-restored.bin", (root / "object-backup.bin").read_bytes()
    )
    assert digest((root / "object-restored.bin").read_bytes()) == metadata["sha256"]
    logger.info("recovery_config_object_restore_verified configs=%d", len(manifest))
    return dict(
        config_sha256=manifest,
        synthetic_object_bytes=len(blob),
        synthetic_object_sha256=metadata["sha256"],
    )


def drill(root, key):
    """Run actual quiet DB restore and owned vector/blob/config drills without original writes, shared restart or recovered grants."""
    root = root.resolve()
    root.mkdir(mode=0o700, exist_ok=False)
    operator = RecoveryAcceptance(root / "postgres")
    operator.require_quiet()
    rows = operator.fingerprint("local_assistant")
    security = operator.security_fingerprint("local_assistant")
    revision = operator.sql(
        "local_assistant", "SELECT version_num FROM assistant.alembic_version"
    )
    if revision != "0006":
        raise RuntimeError("recovery_schema_unexpected")
    archive = operator.private_output(
        "local-assistant.dump",
        [
            "exec",
            operator.container,
            "pg_dump",
            "-U",
            operator.admin,
            "-d",
            "local_assistant",
            "--format=custom",
        ],
    )
    if archive.stat().st_size > 64 * 1024 * 1024:
        raise RuntimeError("recovery_archive_limit")
    assert (
        operator.fingerprint("local_assistant") == rows
        and operator.security_fingerprint("local_assistant") == security
    )
    operator.verify_restore(archive, rows, security)
    operator.save_manifest()
    with httpx.Client(
        base_url="http://127.0.0.1:6333",
        headers={"api-key": key},
        timeout=30,
        trust_env=False,
        follow_redirects=False,
    ) as client:
        vectors = vector_drill(client, root)
    config_object = config_object_drill(root)
    assert (
        operator.fingerprint("local_assistant") == rows
        and operator.security_fingerprint("local_assistant") == security
    )
    assert (
        operator.sql(
            "local_assistant", "SELECT version_num FROM assistant.alembic_version"
        )
        == revision
    )
    assert (
        operator.sql(
            "postgres",
            "SELECT count(*) FROM pg_database WHERE datname LIKE 'la_restore_probe_%'",
        )
        == "0"
    )
    result = dict(
        description="Actual same-cluster isolated restore; existing roles assumed. No original writes, restart, off-host/failover/RPO/RTO certification.",
        status="COMPLETE",
        database_tables_verified=len(rows),
        database_security_sha256=security,
        database_row_fingerprint_sha256=digest(
            json.dumps(rows, sort_keys=True).encode()
        ),
        schema_revision=revision,
        database_archive_sha256=digest(archive.read_bytes()),
        database_archive_bytes=archive.stat().st_size,
        vectors=vectors,
        config_object=config_object,
        owned_database_and_vector_targets_retired=True,
        original_data_security_configs_unchanged=True,
        shared_services_restarted=False,
    )
    private_write(
        root / "result.json", json.dumps(result, indent=2, sort_keys=True).encode()
    )
    logger.info("release_recovery_drill_complete tables=%d", len(rows))
    return result


def main():
    """Read the existing local Vault credential in memory and execute one explicitly named private output directory."""
    if len(sys.argv) != 2:
        raise SystemExit(
            "Usage: uv run python -m scripts.release_recovery_drill PRIVATE_NEW_DIRECTORY"
        )
    sys.path.insert(0, str(Path("../infras/scripts").resolve()))
    from vault_static_secret import load_vault_connection, read_static_secret

    key = read_static_secret(load_vault_connection(), "secret", "server/qdrant/admin")[
        "api_key"
    ]
    drill(Path(sys.argv[1]), key)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
