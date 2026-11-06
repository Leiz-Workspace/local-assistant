"""Own private evaluation-only Git/source fixtures with fixed commands and no model-selected paths or hooks."""

import hashlib
import logging
import os
import stat
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


class CodingFixture:
    """Create one new private repository for a frozen task without touching an existing application workspace."""

    def __init__(self, root, source):
        """Require a new private directory, create one fixed described source file and commit its initial checkpoint."""
        self.root = Path(root)
        self.root.mkdir(mode=0o700)
        self.template = self.root / ".empty-git-template"
        self.template.mkdir(mode=0o700)
        self.source = self.root / "solve.py"
        self.source.write_text(source)
        self.source.chmod(0o600)
        info = self.root.stat()
        self.root_identity = (info.st_dev, info.st_ino)
        self.original_sha256 = hashlib.sha256(source.encode()).hexdigest()
        self.git("init", "--quiet", "--template=" + str(self.template))
        self.git("add", "--", "solve.py")
        self.git("commit", "--quiet", "-m", "Checkpoint frozen coding fixture")
        self.checkpoint = self.git("rev-parse", "HEAD").strip()
        logger.info("coding_fixture_checkpoint_created")

    def verify_root(self):
        """Require the same owned private nonsymlink directory before each fixed fixture action."""
        info = self.root.lstat()
        if (
            not stat.S_ISDIR(info.st_mode)
            or (info.st_dev, info.st_ino) != self.root_identity
            or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) != 0o700
        ):
            raise RuntimeError("coding_fixture_root_changed")

    def git(self, *arguments):
        """Run only caller-fixed evaluation commands under cleared config and disabled hooks/signing/external filters."""
        self.verify_root()
        command = [
            "/usr/bin/git",
            "-c",
            "core.hooksPath=/dev/null",
            "-c",
            "core.fsmonitor=false",
            "-c",
            "commit.gpgsign=false",
            "-c",
            "core.autocrlf=false",
            "-c",
            "core.attributesFile=/dev/null",
            "-c",
            "user.name=Local evaluation fixture",
            "-c",
            "user.email=fixture@localhost",
            *arguments,
        ]
        environment = {
            "PATH": "/usr/bin:/bin",
            "LANG": "C.UTF-8",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_PAGER": "cat",
        }
        result = subprocess.run(
            command,
            cwd=self.root,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=5,
        )
        if result.returncode or len(result.stdout) > 65536 or len(result.stderr) > 4096:
            raise RuntimeError("coding_fixture_git_failed")
        self.verify_root()
        logger.info("coding_fixture_git_completed")
        return result.stdout.decode("utf-8")

    def verify_source(self):
        """Verify the frozen source/checkpoint before replacing only this private fixture's fixed file."""
        self.verify_root()
        descriptor = os.open(
            self.source, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC
        )
        with os.fdopen(descriptor, "rb") as stream:
            info = os.fstat(stream.fileno())
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_nlink != 1
                or info.st_uid != os.getuid()
            ):
                raise RuntimeError("coding_fixture_source_changed")
            raw = stream.read(8193)
        if (
            hashlib.sha256(raw).hexdigest() != self.original_sha256
            or self.git("rev-parse", "HEAD").strip() != self.checkpoint
        ):
            raise RuntimeError("coding_fixture_source_changed")
        logger.info("coding_fixture_source_verified")

    def replace(self, code):
        """Write a bounded code proposal only to fixed solve.py after frozen source/checkpoint verification."""
        if not isinstance(code, str) or not 1 <= len(code.encode("utf-8")) <= 8192:
            raise ValueError("coding_fixture_code_limit")
        self.verify_source()
        descriptor = os.open(self.source, os.O_WRONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        try:
            info = os.fstat(descriptor)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise RuntimeError("coding_fixture_source_changed")
            os.ftruncate(descriptor, 0)
            raw = code.encode("utf-8")
            offset = 0
            while offset < len(raw):
                offset += os.write(descriptor, raw[offset:])
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        self.verify_root()
        diff = self.git("diff", "--no-ext-diff", "--no-textconv", "--", "solve.py")
        logger.info("coding_fixture_proposal_saved bytes=%d", len(code.encode()))
        return diff
