"""Run a frozen complete application regression with existing in-memory Vault credentials, redacted durable logs and explicit skip/failure accounting."""

import hashlib
import json
import logging
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.engine import URL

logger = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parents[1]


def database_url(secret):
    """Construct the existing app/migrator connection URL in memory without logging or writing credentials."""
    return URL.create(
        "postgresql+psycopg",
        username=secret["username"],
        password=secret["password"],
        host=secret["host"],
        port=int(secret["port"]),
        database=secret["database"],
    ).render_as_string(hide_password=False)


def test_environment(app, migrator, qdrant_key, inherited):
    """Remove operator feature/Vault overrides and enable the accepted actual integration probes with their existing secrets in memory."""
    environment = {
        key: value
        for key, value in inherited.items()
        if not key.startswith(("VAULT_", "ASSISTANT_"))
    }
    environment.update(
        DATABASE_URL=database_url(app),
        LOCAL_ASSISTANT_MEMORY_SCHEMA_PROBE_URL=database_url(migrator),
        LOCAL_ASSISTANT_QDRANT_PROBE_KEY=qdrant_key,
        LOCAL_ASSISTANT_LIVE_E2E="1",
        LOCAL_ASSISTANT_EMBEDDING_COMPARE_LIVE="1",
        PYTHONUNBUFFERED="1",
    )
    return environment


def source_manifest():
    """Hash current tracked/additive source/config/test files while excluding ignored private artifacts and external paths."""
    result = subprocess.run(
        [
            "git",
            "ls-files",
            "-z",
            "--cached",
            "--others",
            "--exclude-standard",
            "--",
            "src",
            "apps",
            "scripts",
            "tests",
            "configs",
            "pyproject.toml",
            "uv.lock",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    paths = sorted(set(result.stdout.decode().strip("\0").split("\0")))
    manifest = {}
    for name in paths:
        path = ROOT / name
        if (
            not name
            or path.is_symlink()
            or not path.is_file()
            or not path.resolve().is_relative_to(ROOT)
        ):
            raise RuntimeError("regression_source_invalid")
        manifest[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    if not 100 <= len(manifest) <= 3000:
        raise RuntimeError("regression_source_count_invalid")
    return manifest


def verify_manifest(manifest):
    """Require identical complete source inventory and bytes before/after a full run instead of silently accepting concurrent edits."""
    if manifest != source_manifest():
        raise RuntimeError("regression_source_changed")


def redact(line, secrets):
    """Remove full URLs/raw private credential values from each complete diagnostic line before durable publication."""
    for secret in sorted(
        set(value for value in secrets if type(value) is str and value),
        key=len,
        reverse=True,
    ):
        line = line.replace(secret, "[REDACTED]")
    return line


def private_json(path, value):
    """Atomically replace only an operator-owned summary file with private synced non-secret metadata."""
    temporary = path.with_name(path.name + ".tmp")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(value, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def summary_counts(log):
    """Extract final pytest counts without treating a zero exit code or missing summary as evidence of zero skipped tests."""
    lines = [
        line
        for line in log.splitlines()
        if re.search(r"\b\d+ passed\b", line) and " in " in line
    ]
    if not lines:
        raise RuntimeError("regression_summary_missing")
    summary = lines[-1]
    result = {
        name: int(match[1])
        if (
            match := re.search(
                r"\b(\d+) " + (r"errors?" if name == "errors" else name) + r"\b",
                summary,
            )
        )
        else 0
        for name in ("passed", "failed", "skipped", "errors")
    }
    match = re.search(r"\bin ([\d.]+)s", summary)
    if not match:
        raise RuntimeError("regression_duration_missing")
    return dict(**result, pytest_seconds=float(match[1]), summary=summary.strip())


def run(root, environment, secrets):
    """Own a fresh full pytest process, redact its log, preserve first outcomes and verify the complete source freeze afterwards."""
    root = root.resolve()
    root.mkdir(mode=0o700, exist_ok=False)
    frozen = source_manifest()
    private_json(
        root / "source-freeze.json",
        dict(
            description="Exact full regression source inventory before launch.",
            sha256=frozen,
        ),
    )
    verify_manifest(frozen)
    started = time.monotonic()
    metadata = dict(
        description="Fresh full current-source regression with actual existing integration credentials; no new model/default/provider or benchmark-original rerun.",
        status="starting",
        boot_id=Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
        source_files=len(frozen),
        wrapper_pid=os.getpid(),
        started_at_utc=datetime.now(timezone.utc).isoformat(),
        source_freeze_sha256=hashlib.sha256(
            (root / "source-freeze.json").read_bytes()
        ).hexdigest(),
    )
    private_json(root / "result.json", metadata)
    log = root / "pytest.log"
    fd = os.open(log, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    process = None
    try:
        with os.fdopen(fd, "w") as output:
            process = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "pytest",
                    "tests",
                    "-v",
                    "-rs",
                    "--tb=short",
                    "-o",
                    "tmp_path_retention_policy=failed",
                    "-o",
                    "tmp_path_retention_count=1",
                ],
                cwd=ROOT,
                env=environment,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            metadata.update(status="running", pytest_pid=process.pid)
            private_json(root / "result.json", metadata)
            for line in process.stdout:
                output.write(redact(line, secrets))
                output.flush()
            code = process.wait()
        verify_manifest(frozen)
        counts = summary_counts(log.read_text())
        metadata.update(
            status="complete", exit_code=code, source_bytes_unchanged=True, **counts
        )
        metadata["accepted_full_software_regression"] = (
            code == 0 and counts["failed"] == counts["errors"] == counts["skipped"] == 0
        )
    except BaseException as exc:
        metadata.update(
            status="failed",
            error_type=type(exc).__name__,
            accepted_full_software_regression=False,
        )
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        raise
    finally:
        metadata.update(
            elapsed_seconds=time.monotonic() - started,
            completed_at_utc=datetime.now(timezone.utc).isoformat(),
            log_sha256=hashlib.sha256(log.read_bytes()).hexdigest(),
        )
        private_json(root / "result.json", metadata)
        logger.info("full_regression_retired status=%s", metadata["status"])
    return metadata


def main():
    """Load already authorized Vault app/migrator/vector credentials in memory and run one new complete suite directory."""
    if len(sys.argv) != 2:
        raise SystemExit(
            "Usage: uv run python -m scripts.full_regression PRIVATE_NEW_DIRECTORY"
        )
    sys.path.insert(0, str((ROOT.parent / "infras/scripts").resolve()))
    from vault_static_secret import load_vault_connection, read_static_secret

    vault = load_vault_connection()
    app = read_static_secret(vault, "secret", "server/local-assistant/postgresql")
    migrator = read_static_secret(
        vault, "secret", "server/local-assistant/postgresql-migrator"
    )
    qdrant = read_static_secret(vault, "secret", "server/qdrant/admin")["api_key"]
    environment = test_environment(app, migrator, qdrant, os.environ)
    secrets = [
        environment["DATABASE_URL"],
        environment["LOCAL_ASSISTANT_MEMORY_SCHEMA_PROBE_URL"],
        app["password"],
        migrator["password"],
        qdrant,
        vault.token,
    ]
    result = run(Path(sys.argv[1]), environment, secrets)
    print(json.dumps(result, sort_keys=True))
    raise SystemExit(0 if result["accepted_full_software_regression"] else 1)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
