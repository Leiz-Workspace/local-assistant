"""Verify actual thread-only native syscall behavior, sealed filter capability ownership and fail-closed setup faults."""

import errno
import fcntl
import json
import os
import subprocess

import pytest

from src.application.services.workspace_policy import WorkspaceAccessError
from src.infrastructure import check_seccomp as module
from src.infrastructure.check_seccomp import FILTER_BYTES, REQUIRED_SEALS, thread_filter


def test_filter_is_sealed_exact_and_closed_after_its_borrowed_lifetime():
    """Prevent mutation/truncation of the trusted BPF bytes and release the retained parent descriptor exactly once."""
    with thread_filter() as descriptor:
        assert os.read(descriptor, 4096) == FILTER_BYTES
        assert fcntl.fcntl(descriptor, fcntl.F_GET_SEALS) == REQUIRED_SEALS
        for action in (os.write, os.ftruncate):
            with pytest.raises(OSError) as caught:
                action(descriptor, b"changed" if action is os.write else 0)
            assert caught.value.errno == errno.EPERM
    with pytest.raises(OSError) as caught:
        os.fstat(descriptor)
    assert caught.value.errno == errno.EBADF


def test_unsupported_architecture_has_no_weaker_execution_fallback(monkeypatch):
    """Reject an unknown syscall ABI before creating a filter capability or allowing execution."""

    def unsupported_machine():
        """Return an explicitly unsupported syscall ABI for the fail-closed platform gate."""
        return "unsupported"

    monkeypatch.setattr(module.platform, "machine", unsupported_machine)
    with pytest.raises(WorkspaceAccessError) as caught, thread_filter():
        pytest.fail("unsupported syscall ABI admitted")
    assert caught.value.code == "checks_seccomp_unsupported"


def test_filter_does_not_relabel_borrower_failure_as_setup_failure():
    """Preserve a caller's actual post-setup failure while still releasing the borrowed filter FD."""
    failure = OSError("controlled borrower failure")
    with pytest.raises(OSError) as caught, thread_filter() as descriptor:
        raise failure
    assert caught.value is failure
    with pytest.raises(OSError):
        os.fstat(descriptor)


@pytest.mark.parametrize("phase", ["write", "seal"])
def test_filter_setup_fault_closes_the_private_descriptor(monkeypatch, phase):
    """Close an actually created setup FD when write/seal fails without retaining mutable policy or enabling a fallback."""
    original_create = module.os.memfd_create
    original_fcntl = module.fcntl.fcntl
    descriptors = []

    def capture(*arguments):
        """Retain only actual created FD identities for post-failure cleanup assertions."""
        descriptor = original_create(*arguments)
        descriptors.append(descriptor)
        return descriptor

    def fail_write(*arguments):
        """Inject a native policy write failure without exposing private bytes."""
        raise OSError("controlled write fault")

    def fail_seal(descriptor, operation, *arguments):
        """Inject only the final seal stage while preserving real descriptor access."""
        if operation == fcntl.F_ADD_SEALS:
            raise OSError("controlled seal fault")
        return original_fcntl(descriptor, operation, *arguments)

    monkeypatch.setattr(module.os, "memfd_create", capture)
    if phase == "write":
        monkeypatch.setattr(module.os, "write", fail_write)
    else:
        monkeypatch.setattr(module.fcntl, "fcntl", fail_seal)
    with pytest.raises(WorkspaceAccessError) as caught, thread_filter():
        pytest.fail("unsealed filter admitted")
    assert caught.value.code == "checks_seccomp_unavailable"
    for descriptor in descriptors:
        with pytest.raises(OSError):
            os.fstat(descriptor)


def test_native_threads_succeed_but_fork_clone_and_clone3_cannot_create_processes():
    """Apply actual BPF under bwrap and prove threads work while process/alternate-ABI creation paths are denied."""
    with thread_filter() as descriptor:
        code = '''"""Observe trusted controlled syscalls inside the actual thread-only sandbox."""
import ctypes, errno, json, os, threading
values=[]
threads=[threading.Thread(target=values.append,args=(1,)) for _ in range(4)]
for thread in threads:thread.start()
for thread in threads:thread.join()
report=dict(threads_completed=len(values))
try:
 pid=os.fork()
 if pid==0:os._exit(91)
 os.waitpid(pid,0);report["fork"]="unexpected"
except OSError as error:report["fork_errno"]=error.errno
library=ctypes.CDLL(None,use_errno=True)
for name,number,arguments in [("clone",56,(17,0,0,0,0)),("clone3",435,(0,0)),("x32",0x40000039,())]:
 ctypes.set_errno(0)
 result=library.syscall(number,*arguments)
 if result==0 and name=="clone":os._exit(92)
 if result>0 and name=="clone":os.waitpid(result,0)
 report[name]=[result,ctypes.get_errno()]
try:os.fstat(FILTER_DESCRIPTOR);report["setup_fd"]="open"
except OSError as error:report["setup_fd_errno"]=error.errno
print(json.dumps(report))
'''.replace("FILTER_DESCRIPTOR", str(descriptor))
        command = [
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
            "usr/lib",
            "/lib",
            "--symlink",
            "usr/lib64",
            "/lib64",
            "--proc",
            "/proc",
            "--dev",
            "/dev",
            "--remount-ro",
            "/",
            "--chdir",
            "/",
            "--uid",
            str(os.getuid()),
            "--gid",
            str(os.getgid()),
            "--seccomp",
            str(descriptor),
            "--",
            "/usr/bin/prlimit",
            "--as=536870912",
            "--cpu=2:3",
            "--nproc=16",
            "--nofile=64",
            "--core=0",
            "--",
            "/usr/bin/python3",
            "-I",
            "-S",
            "-B",
            "-c",
            code,
        ]
        result = subprocess.run(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            pass_fds=(descriptor,),
            timeout=6,
        )
        assert result.returncode == 0, result.stderr
        report = json.loads(result.stdout)
        assert report == dict(
            threads_completed=4,
            fork_errno=errno.EPERM,
            clone=[-1, errno.EPERM],
            clone3=[-1, errno.ENOSYS],
            x32=[-1, errno.ENOSYS],
            setup_fd_errno=errno.EBADF,
        )
