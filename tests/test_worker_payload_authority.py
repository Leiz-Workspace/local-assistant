"""Verify shared document sandbox stdin stays readable while readonly mount authority blocks host payload reopen/write/chmod."""

import errno
import hashlib
import json
import os
import subprocess
import tempfile

import pytest

from src.infrastructure.file_verifier import sandbox_command


@pytest.mark.parametrize(
    "attack", ["proc_write", "proc_truncate", "mount_write", "chmod"]
)
def test_actual_shared_worker_payload_cannot_reacquire_host_write_authority(
    tmp_path, attack
):
    """Use the real shared namespace/bootstrap with a private file canary and reject descriptor/mount mutations before any host byte changes."""
    path = tmp_path / "private-source"
    raw = b"CONTROLLED-READONLY-HOST-PAYLOAD\x00\r\n"
    path.write_bytes(raw)
    path.chmod(0o600)
    before = path.stat()
    operations = {
        "proc_write": 'fd=os.open("/proc/self/fd/0",os.O_WRONLY);os.write(fd,b"MUTATED");os.close(fd)',
        "proc_truncate": 'fd=os.open("/proc/self/fd/0",os.O_WRONLY|os.O_TRUNC);os.close(fd)',
        "mount_write": 'fd=os.open("/payload",os.O_WRONLY);os.write(fd,b"MUTATED");os.close(fd)',
        "chmod": "os.fchmod(0,0o666)",
    }
    code = "\n".join(
        [
            '"""Probe only a deliberately created private payload through the actual shared document worker command."""',
            "import os,json,hashlib",
            "raw=os.read(0,4096)",
            'result=dict(source_sha256=hashlib.sha256(raw).hexdigest(),readonly_mount=bool(os.statvfs("/payload").f_flag&os.ST_RDONLY),root_readonly=bool(os.statvfs("/").f_flag&os.ST_RDONLY),root_write=False,mutated=False)',
            "try:",
            ' fd=os.open("/controlled-root-canary",os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600);os.close(fd);result["root_write"]=True',
            "except OSError:",
            " pass",
            "try:",
            " " + operations[attack] + ';result["mutated"]=True',
            "except OSError as error:",
            ' result["errno"]=error.errno',
            "print(json.dumps(result))",
        ]
    )
    with path.open("rb") as source:
        result = subprocess.run(
            sandbox_command(["/venv/bin/python", "-I", "-S", "-B", "-c", code]),
            stdin=source,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env={},
            close_fds=True,
            start_new_session=True,
            timeout=5,
        )
    assert result.returncode == 0
    observed = json.loads(result.stdout)
    assert observed["source_sha256"] == hashlib.sha256(raw).hexdigest()
    assert observed["root_readonly"] and not observed["root_write"]
    assert (
        observed["readonly_mount"]
        and not observed["mutated"]
        and observed["errno"] == errno.EROFS
    )
    after = path.stat()
    assert (
        path.read_bytes() == raw
        and after.st_mode == before.st_mode
        and after.st_mtime_ns == before.st_mtime_ns
    )


def test_private_parent_capabilities_remain_valid_after_payload_consumption():
    """Consume only the child stdin copy while the trusted parent's regular file descriptor remains readable and unchanged."""
    raw = b"PARENT-OWNED-CONTROLLED-PAYLOAD"
    with tempfile.TemporaryFile() as source:
        source.write(raw)
        source.seek(0)
        before = os.fstat(source.fileno())
        result = subprocess.run(
            sandbox_command(
                [
                    "/venv/bin/python",
                    "-I",
                    "-S",
                    "-B",
                    "-c",
                    '"""Read only the consumed readonly payload."""; import sys; sys.stdout.buffer.write(sys.stdin.buffer.read())',
                ]
            ),
            stdin=source,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env={},
            close_fds=True,
            start_new_session=True,
            timeout=5,
        )
        assert result.returncode == 0 and result.stdout == raw
        assert os.fstat(source.fileno()).st_ino == before.st_ino
        source.seek(0)
        assert source.read() == raw
