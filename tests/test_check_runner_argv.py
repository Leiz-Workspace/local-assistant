"""Verify the native check argv takes every prlimit ceiling from the reviewed execution policy without launching a child."""

import os
from uuid import uuid4

import pytest

from src.application.services.check_policy import PROFILES, execution_policy
from src.application.services.workspace_policy import WorkspaceAccessError
from src.infrastructure import check_runner as module
from src.infrastructure.check_runner import NativeChecks, resource_arguments

REVIEWED_LIMITS = [
    "--as=536870912",
    "--cpu=2:3",
    "--fsize=1048576",
    "--nofile=64",
    "--nproc=16",
    "--core=0",
]


@pytest.fixture
def pins(tmp_path):
    """Open two private 0700 directory pins and close them after the argv-only checks."""
    descriptors = []
    for name in ("snapshot", "runtime"):
        path = tmp_path / name
        path.mkdir(mode=0o700)
        path.chmod(0o700)
        descriptors.append(os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC))
    try:
        yield descriptors
    finally:
        for descriptor in descriptors:
            os.close(descriptor)


def runner(pins, profile="python_unittest"):
    """Bind a runner to the disposable pins and one currently permitted CPU."""
    return NativeChecks(*pins, profile, min(os.sched_getaffinity(0)), uuid4())


def prlimit_segment(argv):
    """Return only the arguments between the prlimit executable and its separator."""
    start = argv.index("/usr/bin/prlimit") + 1
    return argv[start : argv.index("--", start)]


@pytest.mark.parametrize("profile", sorted(PROFILES))
def test_current_policy_argv_is_byte_identical_to_the_reviewed_command(pins, profile):
    """Keep the exact namespace, resource and profile argv the reviewed policy produced before derivation."""
    snapshot, runtime = pins
    argv = runner(pins, profile).command(9)
    assert argv == [
        "/usr/bin/bwrap",
        "--unshare-all",
        "--unshare-user",
        "--disable-userns",
        "--assert-userns-disabled",
        "--die-with-parent",
        "--new-session",
        "--cap-drop",
        "ALL",
        "--clearenv",
        "--ro-bind",
        "/usr",
        "/usr",
        "--symlink",
        "usr/bin",
        "/bin",
        "--symlink",
        "usr/lib",
        "/lib",
        "--symlink",
        "usr/lib64",
        "/lib64",
        "--ro-bind-fd",
        str(snapshot),
        "/snapshot",
        "--ro-bind-fd",
        str(runtime),
        "/runtime",
        "--proc",
        "/proc",
        "--dev",
        "/dev",
        "--size",
        "16777216",
        "--tmpfs",
        "/tmp",
        "--remount-ro",
        "/",
        "--chdir",
        "/snapshot",
        "--uid",
        str(os.getuid()),
        "--gid",
        str(os.getgid()),
        "--setenv",
        "PATH",
        "/runtime/bin:/usr/bin:/bin",
        "--setenv",
        "LANG",
        "C.UTF-8",
        "--setenv",
        "TMPDIR",
        "/tmp",
        "--setenv",
        "MALLOC_ARENA_MAX",
        "1",
        "--setenv",
        "RAYON_NUM_THREADS",
        "1",
        "--seccomp",
        "9",
        "--",
        "/usr/bin/prlimit",
        *REVIEWED_LIMITS,
        "--",
        *PROFILES[profile].argv,
    ]
    assert resource_arguments(execution_policy(0)) == REVIEWED_LIMITS


def test_prlimit_arguments_follow_a_changed_reviewed_policy(pins, monkeypatch):
    """Change every policy ceiling and require the enforced argv, not a separate literal copy, to follow it."""
    changed = dict(
        address_space_bytes=268435456,
        cpu_soft_seconds=5,
        cpu_hard_seconds=7,
        file_size_bytes=2048,
        file_descriptors=32,
        threads=8,
        core_bytes=4096,
    )

    def edited_policy(cpu):
        """Return the real reviewed policy with only the resource ceilings edited."""
        return dict(execution_policy(cpu), **changed)

    monkeypatch.setattr(module, "execution_policy", edited_policy)
    attempt = runner(pins)
    assert attempt.observation["policy"]["cpu_hard_seconds"] == 7
    assert prlimit_segment(attempt.command(9)) == [
        "--as=268435456",
        "--cpu=5:7",
        "--fsize=2048",
        "--nofile=32",
        "--nproc=8",
        "--core=4096",
    ]


@pytest.mark.parametrize(
    "field,value",
    [
        ("address_space_bytes", None),
        ("address_space_bytes", -1),
        ("cpu_soft_seconds", 2.5),
        ("cpu_soft_seconds", 4),
        ("file_size_bytes", True),
        ("file_descriptors", "64"),
        ("threads", None),
        ("core_bytes", -1),
        ("core_bytes", "0"),
        ("core_bytes", None),
    ],
)
def test_malformed_policy_ceiling_fails_closed_before_any_argv(
    pins, monkeypatch, field, value
):
    """Refuse a missing, negative, non-integer or inverted CPU ceiling instead of passing it to prlimit."""

    def edited_policy(cpu):
        """Return the reviewed policy with one malformed or removed resource ceiling."""
        policy = execution_policy(cpu)
        if value is None:
            del policy[field]
        else:
            policy[field] = value
        return policy

    monkeypatch.setattr(module, "execution_policy", edited_policy)
    attempt = runner(pins)
    with pytest.raises(WorkspaceAccessError) as caught:
        attempt.command(9)
    assert caught.value.code == "checks_runner_policy_invalid"
    assert caught.value.status_code == 503


def test_boundary_zero_ceilings_and_equal_cpu_limits_are_rendered_exactly():
    """Accept zero ceilings and an equal soft/hard CPU pair without rounding or reordering."""
    policy = dict(
        address_space_bytes=0,
        cpu_soft_seconds=3,
        cpu_hard_seconds=3,
        file_size_bytes=0,
        file_descriptors=0,
        threads=0,
        core_bytes=0,
    )
    assert resource_arguments(policy) == [
        "--as=0",
        "--cpu=3:3",
        "--fsize=0",
        "--nofile=0",
        "--nproc=0",
        "--core=0",
    ]


def test_policy_drift_after_binding_is_still_refused_before_derivation(pins):
    """Keep the existing changed-policy fence ahead of argv derivation."""
    attempt = runner(pins)
    attempt.policy = dict(attempt.policy, threads=32)
    with pytest.raises(WorkspaceAccessError) as caught:
        attempt.command(9)
    assert caught.value.code == "checks_runner_policy_changed"
