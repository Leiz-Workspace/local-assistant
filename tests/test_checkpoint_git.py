"""Verify actual isolated private Git byte checkpoints, finite command rejection and native hard-policy/cancel/output cleanup."""

import hashlib
import json
import os
import threading
from time import monotonic

import pytest

from src.application.services.workspace_policy import WorkspaceAccessError
from src.infrastructure.checkpoint_git import CheckpointGit


@pytest.fixture
def git_backend(tmp_path, monkeypatch):
    """Create only owned temporary private Git/template descriptors and close them after joined helper operations."""
    paths = [tmp_path / name for name in ("repo", "template")]
    for path in paths:
        path.mkdir(mode=0o700)
    descriptors = [
        os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC) for path in paths
    ]
    from src.infrastructure import checkpoint_git as module

    original = module.subprocess.Popen
    processes = []

    def tracked(*arguments, **options):
        """Record real isolated process handles solely to verify joined exit after every backend outcome."""
        process = original(*arguments, **options)
        processes.append(process)
        return process

    monkeypatch.setattr(module.subprocess, "Popen", tracked)
    try:
        yield CheckpointGit(*descriptors), paths
    finally:
        for descriptor in descriptors:
            os.close(descriptor)
        for process in processes:
            assert process.poll() is not None
            with pytest.raises(ProcessLookupError):
                os.kill(process.pid, 0)


def test_actual_private_git_commit_and_exact_raw_readback(
    git_backend, monkeypatch, tmp_path, caplog
):
    """Create real private Git blobs/tree/commit under namespaces and preserve raw bytes without host config/hook execution."""
    backend, paths = git_backend
    canary = tmp_path / "UNEXECUTED"
    global_config = tmp_path / "global.gitconfig"
    global_config.write_text(
        "[core]\n hooksPath = "
        + str(tmp_path)
        + "\n[alias]\n hash-object = !touch "
        + str(canary)
        + "\n"
    )
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(global_config))
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "core.sshCommand")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", "PRIVATE-CREDENTIAL-CANARY")
    assert backend.execute("init") == b""
    raw = b'"""Original synthetic source."""\r\nVALUE = "Cedar"\r\n'
    metadata = json.dumps(
        dict(
            description="Synthetic checkpoint metadata.",
            source_sha256=hashlib.sha256(raw).hexdigest(),
        )
    ).encode()
    source = backend.execute("blob", raw).strip().decode()
    meta = backend.execute("blob", metadata).strip().decode()
    tree = backend.execute("tree", identifiers=(meta, source)).strip().decode()
    commit = backend.execute("commit", identifiers=(tree,)).strip().decode()
    assert backend.execute("read_blob", identifiers=(source,)) == raw
    assert backend.execute("read_blob", identifiers=(meta,)) == metadata
    assert backend.execute("read_commit", identifiers=(commit,)).startswith(
        ("tree " + tree + "\n").encode()
    )
    assert b"source.bin\x00" in backend.execute("read_tree", identifiers=(tree,))
    assert paths[0].joinpath("HEAD").read_text() == "ref: refs/heads/checkpoint\n"
    assert not canary.exists() and "PRIVATE-CREDENTIAL-CANARY" not in caplog.text
    assert raw.decode() not in caplog.text


@pytest.mark.parametrize(
    "operation,data,identifiers",
    [
        ("clone", b"", ()),
        ("blob", b"x" * 8193, ()),
        ("tree", b"", ("../../outside", "0" * 40)),
        ("commit", b"", ("--exec=untrusted",)),
        ("read_blob", b"", ("A" * 40,)),
        ("init", b"unexpected", ()),
    ],
)
def test_invalid_plumbing_never_starts_a_process(
    git_backend, monkeypatch, operation, data, identifiers
):
    """Reject arbitrary transports/commands/paths/oversized input before constructing any child process."""
    from src.infrastructure import checkpoint_git as module

    def denied(*arguments, **options):
        """Fail the test if rejected caller data reaches native process creation."""
        pytest.fail("invalid operation started a process")

    monkeypatch.setattr(module.subprocess, "Popen", denied)
    with pytest.raises(WorkspaceAccessError):
        git_backend[0].execute(operation, data, identifiers)


def test_actual_git_namespace_uid_resources_and_host_denial(
    git_backend, monkeypatch, tmp_path
):
    """Probe the actual exact namespace/policy wrapper with trusted described code while retaining all production mount/resource flags."""
    backend, _ = git_backend
    outside = tmp_path / "HOST-CANARY"
    outside.write_text("PRIVATE-HOST-CANARY")
    code = "\n".join(
        [
            '"""Probe fixed private Git namespace and resources without executing user source."""',
            "import json,os,resource,socket",
            'fd=os.open("/repo/owned",os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600);os.close(fd)',
            'result=dict(uid=os.getuid(),gid=os.getgid(),env=dict(os.environ),home=os.path.exists("/home"),host=os.path.exists('
            + repr(str(outside))
            + '),limits={name:resource.getrlimit(getattr(resource,name)) for name in ["RLIMIT_AS","RLIMIT_CPU","RLIMIT_FSIZE","RLIMIT_NOFILE","RLIMIT_NPROC","RLIMIT_CORE"]})',
            "try:",
            ' socket.create_connection(("127.0.0.1",8080),timeout=.2);result["network"]=True',
            "except OSError:",
            ' result["network"]=False',
            "try:",
            ' open("/tmp/forbidden","w").close();result["tmp_write"]=True',
            "except OSError:",
            ' result["tmp_write"]=False',
            'result["root_readonly"]=bool(os.statvfs("/").f_flag&os.ST_RDONLY)',
            "try:",
            ' open("/controlled-root-canary","w").close();result["root_write"]=True',
            "except OSError:",
            ' result["root_write"]=False',
            "print(json.dumps(result))",
        ]
    )
    original = backend.command

    def probe(arguments):
        """Replace only trusted Git executable/args after the unchanged namespace and prlimit command prefix."""
        command = original(arguments)
        index = command.index("/usr/bin/git")
        return command[:index] + ["/usr/bin/python3", "-I", "-B", "-c", code]

    monkeypatch.setattr(backend, "command", probe)
    result = json.loads(backend.execute("read_blob", identifiers=("0" * 40,)))
    assert result["uid"] == os.getuid() != 0 and result["gid"] == os.getgid()
    assert result["root_readonly"] and not result["root_write"]
    assert (
        not result["home"]
        and not result["host"]
        and not result["network"]
        and not result["tmp_write"]
    )
    assert set(result["env"]) <= {
        "PATH",
        "LANG",
        "LC_CTYPE",
        "PWD",
        "GIT_CONFIG_NOSYSTEM",
        "GIT_CONFIG_GLOBAL",
        "GIT_CONFIG_SYSTEM",
        "GIT_TERMINAL_PROMPT",
        "GIT_OPTIONAL_LOCKS",
    }
    assert result["env"]["PWD"] == "/"
    assert result["env"]["GIT_CONFIG_NOSYSTEM"] == "1"
    assert (
        result["env"]["GIT_CONFIG_GLOBAL"]
        == result["env"]["GIT_CONFIG_SYSTEM"]
        == "/dev/null"
    )
    assert (
        result["env"]["GIT_TERMINAL_PROMPT"]
        == result["env"]["GIT_OPTIONAL_LOCKS"]
        == "0"
    )
    assert result["limits"] == dict(
        RLIMIT_AS=[268435456, 268435456],
        RLIMIT_CPU=[2, 3],
        RLIMIT_FSIZE=[262144, 262144],
        RLIMIT_NOFILE=[32, 32],
        RLIMIT_NPROC=[16, 16],
        RLIMIT_CORE=[0, 0],
    )


def test_mount_descriptors_are_consumed_before_child_and_cannot_escape_parent(
    git_backend, monkeypatch, tmp_path
):
    """Probe original mount FD numbers and reject real openat parent traversal after bwrap consumes setup-only descriptors."""
    backend, paths = git_backend
    canary = tmp_path / "descriptor-parent-canary"
    canary.write_bytes(b"HOST-PARENT-FD-CANARY")
    descriptors = [backend.repository, backend.template]
    code = "\n".join(
        [
            '"""Check setup-only directory FDs cannot access an explicitly created host canary."""',
            "import os,json,stat",
            "result=dict(open_mount_directories=[],parent_canary_access=False)",
            "for number in " + repr(descriptors) + ":",
            " try:",
            "  info=os.fstat(number)",
            "  if stat.S_ISDIR(info.st_mode):",
            '   result["open_mount_directories"].append(number)',
            '   parent=os.open("..",os.O_RDONLY|os.O_DIRECTORY,dir_fd=number)',
            "   try:",
            '    marker=os.open("descriptor-parent-canary",os.O_RDONLY,dir_fd=parent);os.close(marker);result["parent_canary_access"]=True',
            "   except OSError:",
            "    pass",
            "   os.close(parent)",
            " except OSError:",
            "  pass",
            "print(json.dumps(result))",
        ]
    )
    original = backend.command

    def probe(arguments):
        """Retain exact mount/namespace/resource setup and replace only the final trusted diagnostic program."""
        command = original(arguments)
        return command[: command.index("/usr/bin/git")] + [
            "/usr/bin/python3",
            "-I",
            "-S",
            "-B",
            "-c",
            code,
        ]

    monkeypatch.setattr(backend, "command", probe)
    result = json.loads(backend.execute("read_blob", identifiers=("0" * 40,)))
    assert result == dict(open_mount_directories=[], parent_canary_access=False)
    assert canary.read_bytes() == b"HOST-PARENT-FD-CANARY"
    for descriptor, path in zip(descriptors, paths):
        assert os.fstat(descriptor).st_ino == path.stat().st_ino


@pytest.mark.parametrize("fault", ["cancel", "timeout", "stdout", "stderr", "exit"])
def test_native_failure_and_pipe_caps_join_the_process(git_backend, monkeypatch, fault):
    """Inject trusted diagnostic worker behavior inside the unchanged namespace and bound actual cancellation/time/output/exit failures."""
    backend, _ = git_backend
    original = backend.command
    code = {
        "cancel": "import time;time.sleep(30)",
        "timeout": "import time;time.sleep(30)",
        "stdout": 'import os;os.write(1,b"x"*70000)',
        "stderr": 'import os;os.write(2,b"x"*5000)',
        "exit": "raise SystemExit(7)",
    }[fault]

    def probe(arguments):
        """Retain all isolation/resource flags and replace only the trusted diagnostic executable after prlimit."""
        command = original(arguments)
        return command[: command.index("/usr/bin/git")] + [
            "/usr/bin/python3",
            "-I",
            "-B",
            "-c",
            code,
        ]

    monkeypatch.setattr(backend, "command", probe)
    timer = threading.Timer(0.1, backend.stop.set) if fault == "cancel" else None
    if fault == "timeout":
        backend.deadline = monotonic() + 0.1
    if timer is not None:
        timer.start()
    try:
        with pytest.raises(
            WorkspaceAccessError,
            match={
                "cancel": "checkpoint_cancelled",
                "timeout": "checkpoint_git_timeout",
                "stdout": "checkpoint_git_output_limit",
                "stderr": "checkpoint_git_output_limit",
                "exit": "checkpoint_git_failed",
            }[fault],
        ):
            backend.execute("read_blob", identifiers=("0" * 40,))
    finally:
        if timer is not None:
            timer.cancel()
            timer.join()
