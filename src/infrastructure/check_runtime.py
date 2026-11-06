"""Capture and verify a finite private Python/stdlib/Ruff runtime capsule without installing tools or trusting mutable host caches at execution."""

import hashlib
import logging
import os
import stat
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from time import monotonic
from types import SimpleNamespace

from src.application.services.check_policy import (
    CAPTURE_SECONDS,
    DIGEST,
    MAX_MANIFEST_BYTES,
    MAX_RUNTIME_BYTES,
    MAX_RUNTIME_DIRECTORIES,
    MAX_RUNTIME_FILES,
)
from src.application.services.workspace_policy import WorkspaceAccessError, clean_parts
from src.infrastructure.check_runtime_io import (
    canonical_manifest,
    check_capture,
    copy_source,
    decode_manifest,
    hash_source,
    private_directory,
    private_file,
    read_private,
)
from src.infrastructure.readonly_workspace import (
    READ_FLAGS,
    ROOT_FLAGS,
    open_beneath,
    open_root,
)
from src.infrastructure.workspace_reader import fingerprint

logger = logging.getLogger(__name__)
EXECUTABLE_LIMIT = 32 * 1024**2
STDLIB_FILE_LIMIT = 4 * 1024**2
EXCLUDED = frozenset(
    {
        "__pycache__",
        "site-packages",
        "dist-packages",
        "sitecustomize.py",
        "usercustomize.py",
    }
)
DESCRIPTION = "Captured existing Python/stdlib/Ruff runtime; readonly execution only, no package installation."


@dataclass(frozen=True, slots=True)
class RuntimeSpec:
    """Bind explicit operator-configured existing tool paths and expected executable hashes without client runtime overrides."""

    python: str
    python_sha256: str
    stdlib: str
    ruff: str
    ruff_sha256: str

    def __post_init__(self):
        """Reject ambiguous path/hash configuration before private runtime creation or host tool reads."""
        for value in (self.python, self.stdlib, self.ruff):
            if type(value) is not str:
                raise WorkspaceAccessError("checks_runtime_config_invalid", 503)
            clean_parts(value, absolute=True)
        for value in (self.python_sha256, self.ruff_sha256):
            if type(value) is not str or not DIGEST.fullmatch(value):
                raise WorkspaceAccessError("checks_runtime_config_invalid", 503)
        logger.info("checks_runtime_spec_validated")

    def digest(self):
        """Bind exact trusted seed configuration without putting host paths into a public review or audit log."""
        return hashlib.sha256(
            canonical_manifest(
                dict(
                    python=self.python,
                    python_sha256=self.python_sha256,
                    stdlib=self.stdlib,
                    ruff=self.ruff,
                    ruff_sha256=self.ruff_sha256,
                ),
                MAX_MANIFEST_BYTES,
            )
        ).hexdigest()


class RuntimeCapsule:
    """Own one verified private runtime pin while borrowing its explicitly admitted store root from the lifecycle owner."""

    def __init__(self, parent, spec, stop=None):
        """Create a new bounded capsule or verify retained immutable bytes, preserving incomplete/corrupt entries on failure."""
        self.parent, self.spec, self.fd = parent, spec, None
        self.stop = stop if stop is not None else threading.Event()
        self.deadline = monotonic() + CAPTURE_SECONDS
        self.device = os.fstat(parent).st_dev
        private_directory(parent, self.device)
        if type(spec) is not RuntimeSpec:
            raise WorkspaceAccessError("checks_runtime_config_invalid", 503)
        try:
            try:
                self.fd = open_beneath(parent, "runtime", flags=ROOT_FLAGS)
            except FileNotFoundError:
                self.preflight()
                os.mkdir("runtime", 0o700, dir_fd=parent)
                os.fsync(parent)
                self.fd = open_beneath(parent, "runtime", flags=ROOT_FLAGS)
                private_directory(self.fd, self.device)
                self.build()
            self.identity = self.directory_identity()
            self.validate(self.stop, self.deadline)
            logger.info(
                "checks_runtime_capsule_ready files=%d", len(self.manifest["files"])
            )
        except BaseException:
            self.close()
            raise

    @contextmanager
    def seed_file(self, path):
        """Borrow a native nonsymlink configured seed parent and fixed leaf without following mutable ancestor links."""
        parts = clean_parts(path, absolute=True)
        if len(parts) < 2:
            raise WorkspaceAccessError("checks_runtime_source_invalid", 503)
        directory = open_root(SimpleNamespace(root="/" + "/".join(parts[:-1])))
        try:
            yield directory, parts[-1]
        finally:
            os.close(directory)

    def preflight(self):
        """Reject wrong executable digests before capsule creation and require a trusted root-owned stdlib directory."""
        for path, expected, root_owned in (
            (self.spec.python, self.spec.python_sha256, True),
            (self.spec.ruff, self.spec.ruff_sha256, False),
        ):
            with self.seed_file(path) as (directory, name):
                if (
                    hash_source(
                        directory,
                        name,
                        EXECUTABLE_LIMIT,
                        self.stop,
                        self.deadline,
                        root_owned=root_owned,
                        allow_seed_links=not root_owned,
                    )
                    != expected
                ):
                    raise WorkspaceAccessError("checks_runtime_digest_mismatch", 409)
        descriptor = open_root(SimpleNamespace(root=self.spec.stdlib))
        try:
            self.system_directory(descriptor)
        finally:
            os.close(descriptor)

    def system_directory(self, descriptor):
        """Trust only a stable root-owned nonwritable system stdlib directory, never a project package tree."""
        info = os.fstat(descriptor)
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o22:
            raise WorkspaceAccessError("checks_runtime_source_invalid", 503)
        return info

    def account_directory(self, descriptor):
        """Account current allocated directory blocks once and reject capture inventory/byte overflow."""
        info = private_directory(descriptor, self.device)
        key = (info.st_dev, info.st_ino)
        self.allocated += info.st_blocks * 512 - self.directories.get(key, 0)
        self.directories[key] = info.st_blocks * 512
        if (
            len(self.directories) > MAX_RUNTIME_DIRECTORIES
            or self.allocated > MAX_RUNTIME_BYTES
        ):
            raise WorkspaceAccessError("checks_runtime_capacity", 413)

    @contextmanager
    def new_directory(self, parent, name):
        """Create only a trusted capsule child and retain/fsync its private descriptor through joined capture."""
        os.mkdir(name, 0o700, dir_fd=parent)
        descriptor = open_beneath(parent, name, flags=ROOT_FLAGS)
        try:
            self.account_directory(parent)
            self.account_directory(descriptor)
            parent_info, child_info = os.fstat(parent), os.fstat(descriptor)
            prefix = self.directory_paths[(parent_info.st_dev, parent_info.st_ino)]
            self.directory_paths[(child_info.st_dev, child_info.st_ino)] = (
                prefix + "/" + name
            ).lstrip("/")
            yield descriptor
            os.fsync(descriptor)
            self.account_directory(descriptor)
        finally:
            os.close(descriptor)

    def captured(self, directory, name, relative, record):
        """Account a fresh captured runtime inode and bind its exact private path/hash/size/mode into the manifest."""
        info = os.stat(name, dir_fd=directory, follow_symlinks=False)
        self.allocated += info.st_blocks * 512
        self.account_directory(directory)
        self.files[relative] = record
        if (
            len(self.files) + 1 > MAX_RUNTIME_FILES
            or self.allocated > MAX_RUNTIME_BYTES
        ):
            raise WorkspaceAccessError("checks_runtime_capacity", 413)

    def build(self):
        """Copy only configured executables and bounded trusted stdlib bytes, then durably publish canonical inventory metadata."""
        self.files, self.directories, self.allocated = {}, {}, 0
        root = os.fstat(self.fd)
        self.directory_paths = {(root.st_dev, root.st_ino): ""}
        self.account_directory(self.fd)
        with self.new_directory(self.fd, "bin") as binaries:
            for path, name, expected, root_owned in (
                (self.spec.python, "python3.12", self.spec.python_sha256, True),
                (self.spec.ruff, "ruff", self.spec.ruff_sha256, False),
            ):
                with self.seed_file(path) as (directory, leaf):
                    record = copy_source(
                        directory,
                        leaf,
                        binaries,
                        name,
                        0o500,
                        EXECUTABLE_LIMIT,
                        self.stop,
                        self.deadline,
                        expected_sha256=expected,
                        root_owned=root_owned,
                        allow_seed_links=not root_owned,
                    )
                    self.captured(binaries, name, "bin/" + name, record)
        source = open_root(SimpleNamespace(root=self.spec.stdlib))
        try:
            with (
                self.new_directory(self.fd, "lib") as library,
                self.new_directory(library, "python3.12") as destination,
            ):
                self.copy_stdlib(source, destination, "lib/python3.12/", 0)
        finally:
            os.close(source)
        manifest = dict(
            description=DESCRIPTION,
            version=1,
            config_digest=self.spec.digest(),
            files=self.files,
            directories=sorted(self.directory_paths.values()),
        )
        raw = canonical_manifest(manifest, MAX_MANIFEST_BYTES)
        descriptor = os.open(
            "manifest.json",
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
            0o600,
            dir_fd=self.fd,
        )
        try:
            private_file(descriptor, self.device, 0o600)
            offset = 0
            while offset < len(raw):
                check_capture(self.stop, self.deadline)
                count = os.write(descriptor, raw[offset:])
                if count <= 0:
                    raise OSError("checks_runtime_manifest_write_stalled")
                offset += count
            os.fchmod(descriptor, 0o400)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        os.fsync(self.fd)
        os.fsync(self.parent)
        logger.info("checks_runtime_inventory_published files=%d", len(self.files))

    def copy_stdlib(self, source, destination, prefix, depth):
        """Walk only bounded native system entries, excluding caches/packages/startup hooks and flattening one verified internal alias."""
        check_capture(self.stop, self.deadline)
        before = self.system_directory(source)
        names = sorted(os.listdir(source))
        if depth > 16 or len(names) > MAX_RUNTIME_FILES:
            raise WorkspaceAccessError("checks_runtime_capacity", 413)
        for name in names:
            check_capture(self.stop, self.deadline)
            if name in EXCLUDED:
                continue
            info = os.stat(name, dir_fd=source, follow_symlinks=False)
            if stat.S_ISDIR(info.st_mode):
                child = open_beneath(source, name, flags=ROOT_FLAGS)
                try:
                    with self.new_directory(destination, name) as target:
                        self.copy_stdlib(child, target, prefix + name + "/", depth + 1)
                finally:
                    os.close(child)
            else:
                leaf = name
                if stat.S_ISLNK(info.st_mode):
                    if (
                        depth != 0
                        or name != "_sysconfigdata__linux_x86_64-linux-gnu.py"
                        or os.readlink(name, dir_fd=source)
                        != "_sysconfigdata__x86_64-linux-gnu.py"
                    ):
                        raise WorkspaceAccessError("checks_runtime_source_alias", 503)
                    leaf = "_sysconfigdata__x86_64-linux-gnu.py"
                record = copy_source(
                    source,
                    leaf,
                    destination,
                    name,
                    0o400,
                    STDLIB_FILE_LIMIT,
                    self.stop,
                    self.deadline,
                )
                self.captured(destination, name, prefix + name, record)
        if fingerprint(before) != fingerprint(self.system_directory(source)):
            raise WorkspaceAccessError("checks_runtime_source_changed", 409)

    def directory_identity(self):
        """Require the pinned private runtime to remain the same named nonsymlink inode beneath the admitted store root."""
        if self.fd is None:
            raise WorkspaceAccessError("checks_runtime_unavailable", 503)
        info = private_directory(self.fd, self.device)
        named = os.stat("runtime", dir_fd=self.parent, follow_symlinks=False)
        if (named.st_dev, named.st_ino) != (
            info.st_dev,
            info.st_ino,
        ) or not stat.S_ISDIR(named.st_mode):
            raise WorkspaceAccessError("checks_runtime_changed", 409)
        return info.st_dev, info.st_ino

    def validate(self, stop=None, deadline=None):
        """Verify complete canonical inventory, actual bytes/private metadata and native identities before trusting a runtime for launch."""
        if self.directory_identity() != self.identity:
            raise WorkspaceAccessError("checks_runtime_changed", 409)
        stop = stop if stop is not None else threading.Event()
        deadline = deadline if deadline is not None else monotonic() + CAPTURE_SECONDS
        check_capture(stop, deadline)
        raw, manifest_version = read_private(
            self.fd, "manifest.json", MAX_MANIFEST_BYTES, self.device
        )
        value = decode_manifest(raw, MAX_MANIFEST_BYTES)
        if (
            set(value)
            != {"description", "version", "config_digest", "files", "directories"}
            or value["description"] != DESCRIPTION
            or type(value["version"]) is not int
            or value["version"] != 1
            or value["config_digest"] != self.spec.digest()
            or type(value["files"]) is not dict
            or not 3 <= len(value["files"]) < MAX_RUNTIME_FILES
            or type(value["directories"]) is not list
            or not 1 <= len(value["directories"]) <= MAX_RUNTIME_DIRECTORIES
            or any(type(path) is not str for path in value["directories"])
            or value["directories"] != sorted(set(value["directories"]))
            or "" not in value["directories"]
            or canonical_manifest(value, MAX_MANIFEST_BYTES) != raw
        ):
            raise WorkspaceAccessError("checks_runtime_manifest_invalid", 503)
        for path in value["directories"]:
            if path:
                clean_parts(path)
        for path, record in value["files"].items():
            if (
                type(path) is not str
                or type(record) is not dict
                or set(record) != {"sha256", "size", "mode"}
                or type(record["size"]) is not int
                or record["size"] < 0
                or type(record["mode"]) is not int
                or record["mode"] not in {0o400, 0o500}
                or type(record["sha256"]) is not str
                or not DIGEST.fullmatch(record["sha256"])
            ):
                raise WorkspaceAccessError("checks_runtime_manifest_invalid", 503)
            clean_parts(path)
        records, versions, directories, allocated = (
            {},
            {"manifest.json": manifest_version},
            set(),
            0,
        )
        directory_versions = {}

        def visit(directory, prefix, depth):
            """Hash all admitted private members and reject extra/missing/aliased or oversized runtime inodes."""
            nonlocal allocated
            check_capture(stop, deadline)
            info = private_directory(directory, self.device)
            directory_versions[prefix.rstrip("/")] = fingerprint(info)
            directories.add((info.st_dev, info.st_ino))
            allocated += info.st_blocks * 512
            names = sorted(os.listdir(directory))
            if (
                depth > 16
                or len(names) > MAX_RUNTIME_FILES
                or len(directories) > MAX_RUNTIME_DIRECTORIES
            ):
                raise WorkspaceAccessError("checks_runtime_capacity", 413)
            for name in names:
                check_capture(stop, deadline)
                path = prefix + name
                info = os.stat(name, dir_fd=directory, follow_symlinks=False)
                if stat.S_ISDIR(info.st_mode):
                    child = open_beneath(directory, name, flags=ROOT_FLAGS)
                    try:
                        visit(child, path + "/", depth + 1)
                    finally:
                        os.close(child)
                    continue
                if path == "manifest.json":
                    allocated += info.st_blocks * 512
                    continue
                clean_parts(path)
                if path not in {"bin/python3.12", "bin/ruff"} and not path.startswith(
                    "lib/python3.12/"
                ):
                    raise WorkspaceAccessError("checks_runtime_manifest_invalid", 503)
                mode = 0o500 if path.startswith("bin/") else 0o400
                limit = EXECUTABLE_LIMIT if mode == 0o500 else STDLIB_FILE_LIMIT
                descriptor = open_beneath(directory, name)
                try:
                    before = private_file(descriptor, self.device, mode)
                    if before.st_size > limit:
                        raise WorkspaceAccessError("checks_runtime_capacity", 413)
                finally:
                    os.close(descriptor)
                sha = hash_source(
                    directory, name, limit, stop, deadline, root_owned=False
                )
                after = os.stat(name, dir_fd=directory, follow_symlinks=False)
                if fingerprint(before) != fingerprint(after):
                    raise WorkspaceAccessError("checks_runtime_changed", 409)
                records[path] = dict(sha256=sha, size=after.st_size, mode=mode)
                versions[path] = fingerprint(after)
                allocated += after.st_blocks * 512
                if (
                    len(records) + 1 > MAX_RUNTIME_FILES
                    or allocated > MAX_RUNTIME_BYTES
                ):
                    raise WorkspaceAccessError("checks_runtime_capacity", 413)
            if (
                fingerprint(private_directory(directory, self.device))
                != directory_versions[prefix.rstrip("/")]
            ):
                raise WorkspaceAccessError("checks_runtime_changed", 409)

        visit(self.fd, "", 0)
        if (
            allocated > MAX_RUNTIME_BYTES
            or sorted(directory_versions) != value["directories"]
            or records != value["files"]
            or records.get("bin/python3.12", {}).get("sha256")
            != self.spec.python_sha256
            or records.get("bin/ruff", {}).get("sha256") != self.spec.ruff_sha256
            or not {
                "lib/python3.12/os.py",
                "lib/python3.12/encodings/__init__.py",
                "lib/python3.12/unittest/__init__.py",
            }
            <= set(records)
        ):
            raise WorkspaceAccessError("checks_runtime_integrity_failed", 409)
        if hasattr(self, "fingerprints") and self.fingerprints != versions:
            raise WorkspaceAccessError("checks_runtime_changed", 409)
        if (
            hasattr(self, "directory_fingerprints")
            and self.directory_fingerprints != directory_versions
        ):
            raise WorkspaceAccessError("checks_runtime_changed", 409)
        for path, expected in {
            **versions,
            **{name + "/": native for name, native in directory_versions.items()},
        }.items():
            check_capture(stop, deadline)
            directory = path.endswith("/")
            target = path.rstrip("/")
            descriptor = (
                self.fd
                if not target
                else open_beneath(
                    self.fd,
                    target,
                    flags=ROOT_FLAGS if directory else READ_FLAGS,
                )
            )
            try:
                info = (
                    private_directory(descriptor, self.device)
                    if directory
                    else private_file(
                        descriptor,
                        self.device,
                        0o500 if path.startswith("bin/") else 0o400,
                    )
                )
                if fingerprint(info) != expected:
                    raise WorkspaceAccessError("checks_runtime_changed", 409)
            finally:
                if target:
                    os.close(descriptor)
        if self.directory_identity() != self.identity:
            raise WorkspaceAccessError("checks_runtime_changed", 409)
        self.manifest, self.fingerprints = value, versions
        self.directory_fingerprints = directory_versions
        self.sha256 = hashlib.sha256(raw).hexdigest()
        version = hashlib.sha256(raw)
        for name, native in sorted(versions.items()):
            version.update(name.encode() + b"\x00" + repr(native).encode() + b"\x00")
        for name, native in sorted(directory_versions.items()):
            version.update(
                b"directory\x00"
                + name.encode()
                + b"\x00"
                + repr(native).encode()
                + b"\x00"
            )
        self.version = version.hexdigest()
        self.allocated_bytes = allocated
        logger.info(
            "checks_runtime_capsule_verified files=%d allocated_bytes=%d",
            len(records),
            allocated,
        )

    def close(self):
        """Release the owned runtime pin once after joined work while leaving every durable capsule byte intact."""
        descriptor, self.fd = self.fd, None
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                logger.warning("checks_runtime_pin_close_uncertain")
                raise
            logger.info("checks_runtime_pin_closed")
