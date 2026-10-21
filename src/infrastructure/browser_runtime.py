"""Own one cached network-none browser container, private worker snapshot and joined local Docker/CDP process lifecycle."""

import asyncio
import fcntl
import hashlib
import json
import logging
import os
import stat
from pathlib import Path
from uuid import uuid4

from src.application.services.browser_policy import BrowserError
from src.application.services.search_pipeline import unique_pairs
from src.application.services.web_fetch_tasks import finish_owned, spawn_owned

logger = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parents[2]
IMAGE = "webrecorder/browsertrix-crawler@sha256:7f9d5e20e0f6efea2e9e257aa37e536495ac9f33422ab886e446dabf1065af2c"
DOCKER_ENV = {
    "PATH": "/usr/bin:/bin",
    "HOME": "/nonexistent",
    "DOCKER_HOST": "unix:///var/run/docker.sock",
    "DOCKER_CONFIG": "/nonexistent",
}


def runtime_config():
    """Read only the fixed described tool configuration and reject mutable-image or relaxed-isolation drift."""
    raw = (ROOT / "configs/browser-readonly-runtime.json").read_bytes()
    if len(raw) > 16384:
        raise BrowserError("browser_runtime_unavailable")
    try:
        value = json.loads(raw, object_pairs_hook=unique_pairs)
        required = dict(
            image=IMAGE,
            browser_binary="/opt/brave.com/brave-origin/brave-origin",
            node_binary="/usr/bin/node",
            expected_product="Chrome/149.0.7827.155",
            browser_native_sandbox=False,
            memory_bytes=1073741824,
            cpus="1",
            pids=256,
            tmpfs_bytes=134217728,
            shm_bytes=67108864,
            navigation_seconds=30,
            resource_requests=32,
            active_resource_handlers=8,
            aggregate_resource_bytes=8388608,
            response_body_bytes=1048576,
            CDP_frame_bytes=2097152,
            CDP_direction_bytes=16777216,
            CDP_events=4096,
            pending_commands=64,
            complete_text_bytes=131072,
            complete_title_bytes=1024,
            complete_result_bytes=262144,
        )
        if type(value) is not dict or any(
            type(value.get(key)) is not type(expected) or value[key] != expected
            for key, expected in required.items()
        ):
            raise ValueError()
        if (
            set(value) != set(required) | {"description", "isolation"}
            or not value["description"]
            or value["isolation"]
            != "nonroot_readonly_drop_all_no_new_privileges_network_none_host_GET_fulfillment"
        ):
            raise ValueError()
        logger.info("browser_runtime_config_verified")
        return value
    except (ValueError, TypeError, KeyError, UnicodeError):
        raise BrowserError("browser_runtime_unavailable") from None


class NativeBrowserWorker:
    """Retain an exact owned container and local attachment until confirmed removal, never deleting unknown job entries."""

    def __init__(self, *, root=None):
        """Bind an inert private-root test seam without creating directories, containers, credentials or processes."""
        self.root = Path(root) if root is not None else ROOT / "data/browser-jobs"
        self.job_id = uuid4().hex
        self.name = "la-browser-" + self.job_id
        self.directory = self.root / self.job_id
        self.container_id = None
        self.process = None
        self.stderr_task = None
        self.stderr_bytes = 0
        self.stderr_hash = hashlib.sha256()
        self.fault = None
        self.root_fd = None
        self.root_identity = None
        self.job_identity = None
        self.worker_identity = None
        self.journal_identity = None
        self.journal_digest = None
        self.create_attempted = False
        self.closed = False
        self.retired = False
        self.config = None
        self.worker_sha256 = None
        logger.info("browser_worker_handle_initialized")

    def prepare(self):
        """Lock a private owned root and create only an exclusive bounded worker/journal snapshot without user paths."""
        if os.getuid() == 0:
            raise BrowserError("browser_runtime_unavailable")
        self.config = runtime_config()
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.root_fd = os.open(
            self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
        )
        info = os.fstat(self.root_fd)
        if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
            raise BrowserError("browser_runtime_unavailable")
        self.root_identity = (info.st_dev, info.st_ino)
        try:
            fcntl.flock(self.root_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise BrowserError("browser_busy") from None
        if os.listdir(self.root_fd):
            raise BrowserError("browser_cleanup_uncertain")
        source = ROOT / "scripts/browser_readonly_worker.cjs"
        descriptor = os.open(source, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        try:
            info = os.fstat(descriptor)
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_uid != os.getuid()
                or info.st_nlink != 1
                or info.st_mode & 0o022
                or info.st_size > 65536
            ):
                raise BrowserError("browser_runtime_unavailable")
            raw = os.read(descriptor, 65537)
        finally:
            os.close(descriptor)
        if not raw or len(raw) > 65536:
            raise BrowserError("browser_runtime_unavailable")
        self.worker_sha256 = hashlib.sha256(raw).hexdigest()
        self.directory.mkdir(mode=0o700)
        info = self.directory.lstat()
        self.job_identity = (info.st_dev, info.st_ino)
        descriptor = os.open(
            self.directory / "worker.cjs",
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
        )
        with os.fdopen(descriptor, "wb") as output:
            output.write(raw)
            output.flush()
            os.fsync(output.fileno())
            info = os.fstat(output.fileno())
            self.worker_identity = (info.st_dev, info.st_ino)
        self.journal("prepared")
        logger.info("browser_worker_snapshot_prepared")

    def journal(self, state):
        """Write finite owned-container metadata only, without URLs, headers, page bytes or raw native diagnostics."""
        raw = (
            json.dumps(
                dict(
                    description="Known operation-owned read-only browser resources; no automatic recovery or authority from this journal.",
                    job_id=self.job_id,
                    image=IMAGE,
                    container_name=self.name,
                    container_id=self.container_id,
                    worker_sha256=self.worker_sha256,
                    state=state,
                    stderr_bytes=self.stderr_bytes,
                    stderr_sha256=self.stderr_hash.hexdigest(),
                ),
                sort_keys=True,
            )
            + "\n"
        ).encode()
        self.require_job_identity()
        flags = os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC
        if self.journal_identity is None:
            flags |= os.O_CREAT | os.O_EXCL
        descriptor = os.open(self.directory / "journal.json", flags, 0o600)
        with os.fdopen(descriptor, "r+b") as output:
            info = os.fstat(output.fileno())
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_uid != os.getuid()
                or info.st_nlink != 1
                or stat.S_IMODE(info.st_mode) != 0o600
            ):
                raise BrowserError("browser_cleanup_uncertain")
            identity = (info.st_dev, info.st_ino)
            if self.journal_identity is not None:
                if (
                    identity != self.journal_identity
                    or hashlib.sha256(output.read(8193)).hexdigest()
                    != self.journal_digest
                ):
                    raise BrowserError("browser_cleanup_uncertain")
            output.seek(0)
            output.truncate()
            output.write(raw)
            output.flush()
            os.fsync(output.fileno())
            self.journal_identity = identity
            self.journal_digest = hashlib.sha256(raw).hexdigest()
        logger.info("browser_worker_journal_recorded")

    def require_job_identity(self):
        """Refuse changed or symlinked root/job paths before touching any journal or cleanup target."""
        root, job = self.root.lstat(), self.directory.lstat()
        if (
            not stat.S_ISDIR(root.st_mode)
            or not stat.S_ISDIR(job.st_mode)
            or (root.st_dev, root.st_ino) != self.root_identity
            or (job.st_dev, job.st_ino) != self.job_identity
        ):
            raise BrowserError("browser_cleanup_uncertain")

    async def command(self, *arguments):
        """Join one fixed local Docker metadata/create/remove command without shell, remote context, credential helper or page arguments."""
        process = await asyncio.create_subprocess_exec(
            "/usr/bin/docker",
            *arguments,
            env=DOCKER_ENV,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        output, error = await process.communicate()
        if len(output) > 65536 or len(error) > 65536:
            raise BrowserError("browser_runtime_unavailable")
        logger.info(
            "browser_owned_docker_command_completed exit=%d", process.returncode
        )
        return process.returncode, output, error

    def absent(self, code, error, target):
        """Recognize only a completed exact-target not-found response, never a daemon/network/authorization failure."""
        expected = {
            f"Error: No such container: {target}",
            f"Error: No such object: {target}",
            f"Error response from daemon: No such container: {target}",
        }
        return code != 0 and error.decode("utf-8", errors="replace").strip() in expected

    async def start_owned(self):
        """Create and verify the exact unstarted container before attaching its sole bounded inherited CDP channel."""
        self.prepare()
        config = self.config
        arguments = [
            "create",
            "--pull=never",
            "--name",
            self.name,
            "--init",
            "--interactive",
            "--network",
            "none",
            "--read-only",
            "--user",
            f"{os.getuid()}:{os.getgid()}",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges:true",
            "--memory",
            str(config["memory_bytes"]),
            "--memory-swap",
            str(config["memory_bytes"]),
            "--cpus",
            config["cpus"],
            "--pids-limit",
            str(config["pids"]),
            "--tmpfs",
            f"/tmp:rw,noexec,nosuid,nodev,size={config['tmpfs_bytes']}",
            "--shm-size",
            str(config["shm_bytes"]),
            "--env",
            "HOME=/tmp",
            "--env",
            "NODE_OPTIONS=",
            "--label",
            "local.assistant.browser=readonly",
            "--label",
            "local.assistant.browser.owner=" + self.job_id,
            "--mount",
            f"type=bind,src={self.directory / 'worker.cjs'},dst=/worker/readonly.cjs,readonly",
            "--entrypoint",
            "/usr/bin/node",
            IMAGE,
            "/worker/readonly.cjs",
        ]
        self.create_attempted = True
        code, output, _ = await self.command(*arguments)
        if code != 0:
            raise BrowserError("browser_runtime_unavailable")
        value = output.decode("ascii").strip()
        if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
            raise BrowserError("browser_runtime_unavailable")
        self.container_id = value
        code, raw, _ = await self.command("container", "inspect", value)
        if code != 0:
            raise BrowserError("browser_runtime_unavailable")
        record = json.loads(raw)[0]
        config, host = record["Config"], record["HostConfig"]
        if (
            config["Labels"].get("local.assistant.browser.owner") != self.job_id
            or record["Name"] != "/" + self.name
            or config["Image"] != IMAGE
        ):
            raise BrowserError("browser_cleanup_uncertain")
        if (
            host["NetworkMode"] != "none"
            or not host["ReadonlyRootfs"]
            or host["Privileged"]
            or host["CapDrop"] != ["ALL"]
            or host["SecurityOpt"] != ["no-new-privileges:true"]
            or host["Memory"] != 1073741824
            or host["MemorySwap"] != 1073741824
            or host["NanoCpus"] != 1000000000
            or host["PidsLimit"] != 256
            or host["DeviceRequests"]
            or config["User"] != f"{os.getuid()}:{os.getgid()}"
        ):
            raise BrowserError("browser_runtime_unavailable")
        if (
            host["PortBindings"]
            or len(record["Mounts"]) != 1
            or record["Mounts"][0]["RW"]
            or record["Mounts"][0]["Destination"] != "/worker/readonly.cjs"
            or record["Mounts"][0]["Source"] != str(self.directory / "worker.cjs")
        ):
            raise BrowserError("browser_runtime_unavailable")
        self.journal("created")
        self.process = await asyncio.create_subprocess_exec(
            "/usr/bin/docker",
            "start",
            "--attach",
            "--interactive",
            value,
            env=DOCKER_ENV,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            limit=2097153,
        )
        self.stderr_task = spawn_owned(self.collect_stderr())
        self.journal("attached")
        logger.info("browser_owned_container_attached")
        return self

    async def start(self):
        """Shield and join acquisition so a late created container or attachment cannot escape cancellation cleanup."""
        task = spawn_owned(self.start_owned())
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            try:
                await finish_owned(task)
            except BaseException:
                logger.info("browser_cancelled_acquisition_joined")
            raise
        except BrowserError:
            raise
        except Exception:
            raise BrowserError("browser_runtime_unavailable") from None

    async def collect_stderr(self):
        """Consume metadata-only worker diagnostics with bounded retained memory and signal overflow without echoing them."""
        while True:
            chunk = await self.process.stderr.read(4096)
            if not chunk:
                return
            self.stderr_bytes += len(chunk)
            self.stderr_hash.update(chunk)
            if self.stderr_bytes > 65536:
                self.fault = BrowserError("browser_runtime_unavailable")
                if self.process.stdin:
                    self.process.stdin.close()

    async def close_owned(self):
        """Remove only the exact labeled owned container, join CLI/diagnostic EOF and unlink only known private job files."""
        uncertain = False
        journal_uncertain = False
        try:
            if self.directory.exists():
                try:
                    self.journal("closing")
                except Exception:
                    journal_uncertain = True
                    logger.info("browser_closing_journal_unavailable")
            target = self.container_id or self.name
            code, raw, error = (
                await self.command("container", "inspect", target)
                if self.create_attempted
                else (1, b"", f"Error: No such container: {target}".encode())
            )
            if code == 0:
                record = json.loads(raw)[0]
                if (
                    record["Config"]
                    .get("Labels", {})
                    .get("local.assistant.browser.owner")
                    != self.job_id
                    or record["Config"]["Image"] != IMAGE
                    or record["Name"] != "/" + self.name
                ):
                    raise BrowserError("browser_cleanup_uncertain")
                code, _, _ = await self.command("rm", "--force", record["Id"])
                if code != 0:
                    raise BrowserError("browser_cleanup_uncertain")
                code, _, error = await self.command(
                    "container", "inspect", record["Id"]
                )
                if not self.absent(code, error, record["Id"]):
                    raise BrowserError("browser_cleanup_uncertain")
            elif not self.absent(code, error, target):
                raise BrowserError("browser_cleanup_uncertain")
            if self.process is not None:
                if self.process.stdin:
                    self.process.stdin.close()
                if self.process.returncode is None:
                    try:
                        self.process.kill()
                    except ProcessLookupError:
                        pass
                await self.process.wait()
            if self.stderr_task is not None:
                await finish_owned(self.stderr_task)
            self.retired = True
            if journal_uncertain:
                raise BrowserError("browser_cleanup_uncertain")
            if self.root_fd is not None and self.root_identity is not None:
                current = self.root.lstat()
                if (
                    not stat.S_ISDIR(current.st_mode)
                    or (current.st_dev, current.st_ino) != self.root_identity
                ):
                    raise BrowserError("browser_cleanup_uncertain")
            if self.root_fd is not None and self.directory.exists():
                self.require_job_identity()
                if set(path.name for path in self.directory.iterdir()) != {
                    "worker.cjs",
                    "journal.json",
                }:
                    raise BrowserError("browser_cleanup_uncertain")
                for name in ("worker.cjs", "journal.json"):
                    path = self.directory / name
                    info = path.lstat()
                    if (
                        not stat.S_ISREG(info.st_mode)
                        or info.st_uid != os.getuid()
                        or info.st_nlink != 1
                        or stat.S_IMODE(info.st_mode) != 0o600
                    ):
                        raise BrowserError("browser_cleanup_uncertain")
                    expected_identity = (
                        self.worker_identity
                        if name == "worker.cjs"
                        else self.journal_identity
                    )
                    expected_digest = (
                        self.worker_sha256
                        if name == "worker.cjs"
                        else self.journal_digest
                    )
                    if (
                        info.st_dev,
                        info.st_ino,
                    ) != expected_identity or hashlib.sha256(
                        path.read_bytes()
                    ).hexdigest() != expected_digest:
                        raise BrowserError("browser_cleanup_uncertain")
                self.journal("retired")
                for name in ("worker.cjs", "journal.json"):
                    (self.directory / name).unlink()
                self.directory.rmdir()
            logger.info("browser_owned_runtime_retired")
        except BaseException:
            uncertain = True
            self.fault = BrowserError("browser_cleanup_uncertain")
            logger.info("browser_runtime_cleanup_uncertain")
            if self.directory.exists():
                try:
                    self.journal("cleanup_uncertain")
                except Exception:
                    logger.info("browser_uncertain_journal_unavailable")
            raise BrowserError("browser_cleanup_uncertain") from None
        finally:
            self.closed = True
            if self.root_fd is not None:
                os.close(self.root_fd)
                self.root_fd = None
            if uncertain:
                logger.info("browser_owned_job_retained")

    async def close(self):
        """Join actual cleanup despite repeated caller cancellation and preserve uncertainty instead of deleting unknown entries."""
        if self.closed:
            if self.fault and self.fault.code == "browser_cleanup_uncertain":
                raise self.fault
            return
        try:
            task = spawn_owned(self.close_owned())
        except BaseException:
            self.fault = BrowserError("browser_cleanup_uncertain")
            self.closed = True
            try:
                if self.directory.exists():
                    self.journal("cleanup_dispatch_uncertain")
            finally:
                if self.root_fd is not None:
                    os.close(self.root_fd)
                    self.root_fd = None
            raise self.fault from None
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            await finish_owned(task)
            raise
