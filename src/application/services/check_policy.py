"""Define finite approved test/lint profiles, immutable source selections and fixed execution/storage budgets."""

import logging
import re
from dataclasses import dataclass
from types import MappingProxyType

from src.application.services.workspace_policy import WorkspaceAccessError, clean_parts

logger = logging.getLogger(__name__)
MAX_FILES = 16
MAX_SOURCE_BYTES = 8192
MAX_SOURCE_TOTAL = 131072
MAX_PATH_BYTES = 256
MAX_PATH_PARTS = 4
MAX_JOBS = 32
MAX_OWNER_JOBS = 8
RESERVATION_BYTES = 524288
MAX_JOB_BYTES = 16777216
MAX_RUNTIME_BYTES = 67108864
MAX_RUNTIME_FILES = 800
MAX_RUNTIME_DIRECTORIES = 128
MAX_MANIFEST_BYTES = 131072
MAX_RECORD_BYTES = 32768
PROPOSAL_SECONDS = 120
CAPTURE_SECONDS = 20
WALL_SECONDS = 10
MAX_STDOUT = 16384
MAX_STDERR = 4096
DIGEST = re.compile(r"^[a-f0-9]{64}$")


@dataclass(frozen=True, slots=True)
class CheckProfile:
    """Bind one server-defined profile name to immutable executable arguments without client commands or fixes."""

    name: str
    argv: tuple[str, ...]


PROFILES = MappingProxyType(
    {
        "python_unittest": CheckProfile(
            "python_unittest",
            (
                "/runtime/bin/python3.12",
                "-I",
                "-S",
                "-B",
                "-m",
                "unittest",
                "discover",
                "-s",
                "/snapshot",
                "-t",
                "/snapshot",
                "-p",
                "test_*.py",
            ),
        ),
        "ruff_check": CheckProfile(
            "ruff_check",
            (
                "/runtime/bin/ruff",
                "check",
                "--isolated",
                "--no-cache",
                "--ignore-noqa",
                "--no-respect-gitignore",
                "--target-version",
                "py312",
                "--select",
                "E9,F",
                "--output-format",
                "json",
                "/snapshot",
            ),
        ),
    }
)


def selection_input(profile, files):
    """Validate finite profile and complete unique path/hash selections before any source read or private write."""
    if type(profile) is not str or profile not in PROFILES:
        raise WorkspaceAccessError("checks_profile_invalid", 422)
    if type(files) is not list or not 1 <= len(files) <= MAX_FILES:
        raise WorkspaceAccessError("checks_selection_invalid", 422)
    selected, seen = [], set()
    for value in files:
        if type(value) is not dict or set(value) != {"path", "expected_sha256"}:
            raise WorkspaceAccessError("checks_selection_invalid", 422)
        path, sha = value["path"], value["expected_sha256"]
        parts = clean_parts(path)
        if (
            type(path) is not str
            or len(path.encode("utf-8")) > MAX_PATH_BYTES
            or len(parts) > MAX_PATH_PARTS
            or not path.endswith(".py")
            or path in seen
            or type(sha) is not str
            or not DIGEST.fullmatch(sha)
        ):
            raise WorkspaceAccessError("checks_selection_invalid", 422)
        seen.add(path)
        selected.append((path, sha))
    logger.info(
        "checks_selection_validated profile=%s files=%d", profile, len(selected)
    )
    return PROFILES[profile], tuple(selected)


def source_bytes(raw):
    """Require bounded exact UTF-8 source bytes without parsing or importing selected project code in the host."""
    if type(raw) is not bytes or len(raw) > MAX_SOURCE_BYTES:
        raise WorkspaceAccessError("checks_source_limit", 413)
    try:
        if b"\x00" in raw:
            raise UnicodeError()
        raw.decode("utf-8")
    except UnicodeError:
        raise WorkspaceAccessError("checks_source_invalid", 422) from None
    logger.info("checks_source_bytes_validated bytes=%d", len(raw))
    return raw


def execution_policy(cpu):
    """Return a fresh complete reviewable fixed native policy without caller-selected resource ceilings."""
    if type(cpu) is not int or cpu < 0:
        raise WorkspaceAccessError("checks_cpu_invalid", 503)
    logger.info("checks_execution_policy_bound")
    return dict(
        version=1,
        cpu_affinity=[cpu],
        affinity_change=False,
        wall_seconds=WALL_SECONDS,
        address_space_bytes=536870912,
        cpu_soft_seconds=2,
        cpu_hard_seconds=3,
        scratch_bytes=16777216,
        file_size_bytes=1048576,
        file_descriptors=64,
        threads=16,
        subprocesses=False,
        nested_user_namespaces=False,
        core_bytes=0,
        stdout_bytes=MAX_STDOUT,
        stderr_bytes=MAX_STDERR,
        network=False,
        host_workspace_mount=False,
        credentials=False,
        readonly_root=True,
        readonly_snapshot=True,
        readonly_runtime=True,
        output_is_untrusted=True,
        quality_evaluated=False,
        automatic_retry=False,
    )
