"""Keep threaded native children of the media workers clear of per-thread malloc arenas under the 512 MiB cap."""

import json
import subprocess
import sys
import tempfile

import pytest

from src.infrastructure.file_verifier import sandbox_command
from src.infrastructure.ocr_worker import CHILD_ENV

THREADS = 8
ARENA = 64 * 1024**2

# Start concurrent threads with 1 MiB stacks that each call malloc, then report VmPeak growth.
PROBE = f"""
import ctypes, threading
def peak():
    for line in open("/proc/self/status"):
        if line.startswith("VmPeak:"):
            return int(line.split()[1]) * 1024
libc = ctypes.CDLL(None)
libc.malloc.restype = ctypes.c_void_p
libc.free.argtypes = [ctypes.c_void_p]
threading.stack_size(1024 * 1024)
gate = threading.Barrier({THREADS}, timeout=5)
def allocate():
    gate.wait()
    libc.free(libc.malloc(4096))
before = peak()
threads = [threading.Thread(target=allocate) for _ in range({THREADS})]
for thread in threads:
    thread.start()
for thread in threads:
    thread.join()
print(peak() - before)
"""

ENTRY = '''
"""Run the unchanged worker entry and limits with decoding replaced by one launcher probe."""
import sys
from src.infrastructure import ocr_worker, {worker} as worker
def process(*args):
    """Measure one threaded child through the production native-child launcher."""
    command = ["/venv/bin/python", "-I", "-S", "-c", sys.argv[2]]
    return {{"growth": int(ocr_worker.child_output(command, limit=64))}}
worker.process = process
worker.main()
'''


def probe(worker):
    """Return the worker's JSON reply after its real sandbox, rlimits and launcher ran the threaded probe."""
    code = ENTRY.format(worker=worker)
    with tempfile.TemporaryFile() as source, tempfile.TemporaryFile() as output:
        source.write(b"payload")
        source.flush()
        source.seek(0)
        subprocess.run(
            sandbox_command(["/venv/bin/python", "-c", code, "[0]", PROBE]),
            stdin=source,
            stdout=output,
            stderr=subprocess.DEVNULL,
            timeout=40,
            env={},
            close_fds=True,
            start_new_session=True,
            check=True,
        )
        output.seek(0)
        return json.loads(output.read())


def test_native_child_environment_caps_malloc_arenas_without_extra_variables():
    """Pin one glibc arena while exposing only the fixed locale, path and thread settings."""
    assert CHILD_ENV == {
        "PATH": "/usr/bin:/bin",
        "LANG": "C.UTF-8",
        "OMP_THREAD_LIMIT": "1",
        "MALLOC_ARENA_MAX": "1",
    }


@pytest.mark.parametrize("worker", ["video_worker", "audio_worker"])
def test_threaded_child_reserves_no_per_thread_arena_under_worker_cap(worker):
    """Grow by thread stacks only, so FFmpeg thread creation cannot race arena reservations to the cap."""
    reply = probe(worker)
    assert set(reply) == {"growth"}, reply
    assert 0 <= reply["growth"] < ARENA // 2


def test_probe_detects_per_thread_arenas_when_the_cap_is_absent():
    """Keep the probe meaningful: the same child without the arena cap reserves at least one 64 MiB arena."""
    env = {key: value for key, value in CHILD_ENV.items() if key != "MALLOC_ARENA_MAX"}
    result = subprocess.run(
        [sys.executable, "-I", "-S", "-c", PROBE],
        capture_output=True,
        env=env,
        timeout=30,
        check=True,
    )
    assert int(result.stdout) >= ARENA
